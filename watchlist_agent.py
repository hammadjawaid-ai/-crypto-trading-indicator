"""Watchlist Agent — multi-TF deep analysis for the 19 portfolio coins.

The 24/7 Agent's Section 1. Every refresh, this module fans out across the
fixed portfolio of 19 coins the user actively tracks, runs the deepest
per-timeframe analysis available, and returns one structured report per
coin so the UI can render its card grid.

Design contract (locked by the spec):
    PORTFOLIO_COINS      — the 19 base tickers, ordered
    analyze_portfolio()  — list[dict] per-coin reports, parallel scan
    get_portfolio_symbols() — resolved Binance USDT-perp tickers, with
                              graceful skip for any base that 404s

Per-coin report shape:
    {symbol, base, price_now, pct_24h,
     per_tf      : {tf: analyzer_output}                  one entry per TF
     consensus   : {side, score, tier}                    blended verdict
     top_signal  : "label (tf)"                           one-line chip
     forecast_forming : bool                              early-move flag
     unavailable      : bool                              true if skipped}

The function `analyze_multi_tf` on `coin_deep_analyzer` is the spec's
canonical engine — when present, it's used verbatim. When it doesn't yet
exist (current state) we fall back to a multi-TF stack that wires the
already-cached signals.analyze + early_momentum + reversal_approach +
pattern_scout outputs into the same shape. Either way the public API is
stable.

Parallelism: ThreadPoolExecutor with max_workers=6, matching the budget
the existing scan paths use. Each coin's work is wrapped in try/except so
one bad coin can never sink the whole scan. Coins whose Binance lookup
404s are listed under the result's "unavailable" key.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

import binance_client
import indicators


# ---------------------------------------------------------------------------
# The portfolio — 19 coins, in the order the user manages them.
# ---------------------------------------------------------------------------
PORTFOLIO_COINS: list[str] = [
    "BTC", "ETH", "SOL", "INJ", "WLD", "FET", "AVAX", "LINK", "UNI",
    "RENDER", "SUI", "XRP", "ADA", "VIRTUAL", "TAO", "INIT", "NEAR",
    "KERNEL", "KAITO", "DASH",
]

# Timeframes scanned per coin. Matches the four-TF strip the design uses.
_TIMEFRAMES: tuple[str, ...] = ("15m", "1h", "4h", "1d")

# TF weights for the blended consensus — same shape used everywhere else
# in the codebase (early_momentum.aggregate_scores, forecast.predict_one),
# so the watchlist agent never disagrees with the rest of the system on
# how to compress a multi-TF read into one number.
_TF_WEIGHTS: dict[str, float] = {"15m": 0.20, "1h": 0.30, "4h": 0.30, "1d": 0.20}

# Parallel worker budget — same as breakout / other scans use for the
# top-N coin sweep. Six is enough to keep wall-clock under ~6s for 19
# coins even with the slowest TF fetch on the cold path.
_MAX_WORKERS = 6


# ---------------------------------------------------------------------------
# Optional dependency — the canonical engine if it exists.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - presence-only import; behaviour tested below
    import coin_deep_analyzer  # type: ignore
    _HAS_DEEP_ANALYZER = hasattr(coin_deep_analyzer, "analyze_multi_tf")
except Exception:
    coin_deep_analyzer = None  # type: ignore
    _HAS_DEEP_ANALYZER = False


# ---------------------------------------------------------------------------
# Symbol resolution
# ---------------------------------------------------------------------------
def _to_symbol(base: str) -> str:
    """Build the Binance USDT-perp ticker for a base asset."""
    return f"{base.upper()}USDT"


def get_portfolio_symbols() -> list[str]:
    """Return the resolved Binance USDT tickers for the portfolio.

    Skips any base that 404s on Binance — gracefully tested with a cheap
    2-candle klines probe (the smallest request the API accepts). The
    return order matches PORTFOLIO_COINS so downstream UIs can keep the
    user's chosen sort.
    """
    available: list[str] = []
    for base in PORTFOLIO_COINS:
        sym = _to_symbol(base)
        try:
            df = binance_client.get_klines(sym, "1h", limit=2)
            if df is not None and len(df) >= 1:
                available.append(sym)
        except Exception:
            # 404 / delisted / rebranded ticker — skip silently. The
            # symbol shows up in analyze_portfolio()'s unavailable list
            # so the UI can still tell the user "this coin is missing".
            continue
    return available


# ---------------------------------------------------------------------------
# Per-TF analyzer — uses coin_deep_analyzer if present, falls back otherwise.
# ---------------------------------------------------------------------------
def _pct_24h_from_df(df: pd.DataFrame) -> float:
    """Approximate 24h pct change from the loaded candles.

    Used by the fallback per-TF stack (specifically pattern_scout, which
    expects a pct_24h hint). Calculated from the last 24 1h-equivalent
    bars when possible, otherwise from the first/last close in df.
    """
    if df is None or len(df) < 2:
        return 0.0
    try:
        last = float(df["close"].iloc[-1])
        # Roughly 24h back — fall back to first row for short series.
        ref_idx = max(0, len(df) - 25)
        ref = float(df["close"].iloc[ref_idx])
        if ref <= 0:
            return 0.0
        return (last - ref) / ref * 100.0
    except Exception:
        return 0.0


def _fallback_per_tf(symbol: str, tf: str) -> dict:
    """Fallback per-TF analysis when coin_deep_analyzer is unavailable.

    Wires together the modules that already have validated edge in this
    codebase: signals.analyze (core TA stack), early_momentum (CVD + TTM
    + ROC² + SMC + VWAP), reversal_approach (pre-fire reversal), and
    pattern_scout (live candle pattern). The fused score is the simple
    average of the four lanes' 0-100 reads, with side determined by
    majority vote — keep it simple, defer the heavy 11-layer fusion to
    coin_deep_analyzer once it lands.
    """
    # Heavy imports kept local so the module remains lightweight when
    # only the constants are needed (e.g. by app.py at import time).
    import signals
    import early_momentum
    import reversal_approach
    import pattern_scout

    df = binance_client.get_klines(symbol, tf)
    df = indicators.enrich(df)

    # --- core TA stack ---
    sig = signals.analyze(df)
    sig_score = float(sig.get("score", 0))            # -100..+100
    sig_side = "LONG" if sig_score > 18 else (
        "SHORT" if sig_score < -18 else "NEUTRAL")
    sig_0_100 = 50.0 + sig_score / 2.0                # map to 0..100

    # --- early momentum (with 4h context when not already on 4h) ---
    ctx_df = None
    if tf != "4h":
        try:
            ctx_df = binance_client.get_klines(symbol, "4h")
            ctx_df = indicators.enrich(ctx_df)
        except Exception:
            ctx_df = None
    try:
        em = early_momentum.score_with_4h_context(df, ctx_df)
    except Exception:
        em = {"score": 50.0, "side": "NEUTRAL"}

    # --- pre-fire reversal approach ---
    try:
        rev = reversal_approach.scan_both_sides(df)
    except Exception:
        rev = {"score": 50.0, "side": "NEUTRAL"}

    # --- live candle pattern ---
    try:
        pat = pattern_scout.scan_one(symbol, df, pct_24h=_pct_24h_from_df(df))
    except Exception:
        pat = {"score": 50.0, "side": "NEUTRAL", "best_signal": None}

    # --- fuse into one TF verdict (mean of lanes, majority side) ---
    lanes = [
        ("signals", sig_0_100, sig_side),
        ("early_momentum", float(em.get("score", 50)), em.get("side", "NEUTRAL")),
        ("reversal", float(rev.get("score", 50)), rev.get("side", "NEUTRAL")),
        ("pattern", float(pat.get("score", 50)), pat.get("side", "NEUTRAL")),
    ]
    fused_score = sum(s for _, s, _ in lanes) / len(lanes)
    long_w = sum((s - 50) for _, s, sd in lanes if sd == "LONG")
    short_w = sum((50 - s) for _, s, sd in lanes if sd == "SHORT")
    if long_w > short_w and long_w > 5:
        fused_side = "LONG"
    elif short_w > long_w and short_w > 5:
        fused_side = "SHORT"
    else:
        fused_side = "NEUTRAL"

    # Identify the strongest "thing fired" for the top_signal chip.
    top: str | None = None
    if pat.get("best_signal") and pat.get("best_signal") != "no_data":
        top = str(pat["best_signal"])
    elif float(rev.get("score", 50)) >= 70:
        top = "reversal approach"
    elif float(em.get("score", 50)) >= 65 or float(em.get("score", 50)) <= 35:
        top = "early momentum"

    return {
        "tf": tf,
        "score": round(fused_score, 1),
        "side": fused_side,
        "conviction": _conviction_tier(fused_score, fused_side),
        "components": {
            "signals": sig,
            "early_momentum": em,
            "reversal_approach": rev,
            "pattern_scout": pat,
        },
        "top_signal": top,
        "price": float(df["close"].iloc[-1]),
    }


def _normalise_per_tf(per_tf_raw: dict) -> dict:
    """Normalise per-TF analyzer output so the rest of this module reads
    one consistent shape regardless of which engine produced it.

    The canonical coin_deep_analyzer.analyze() uses `conviction_score`
    and `confidence_tier`; our fallback uses `score` and `conviction`.
    Map both to a unified pair so _blend_consensus / _pick_top_signal /
    _is_forecast_forming can stay simple.
    """
    out: dict = {}
    for tf, r in per_tf_raw.items():
        if not isinstance(r, dict):
            continue
        # Score: prefer existing "score", fall back to "conviction_score".
        score = r.get("score")
        if score is None:
            score = r.get("conviction_score", 50.0)
        # Tier: prefer "conviction", fall back to "confidence_tier", else
        # derive from score+side.
        tier = r.get("conviction") or r.get("confidence_tier")
        side = r.get("side", "NEUTRAL")
        if not tier:
            tier = _conviction_tier(float(score), side)
        # Surface a one-line "top_signal" hint. canonical engine puts the
        # best driver under "drivers"[0]; our fallback already provides
        # "top_signal".
        top = r.get("top_signal")
        if not top and r.get("drivers"):
            try:
                top = r["drivers"][0].get("lane") or r["drivers"][0].get("note")
            except Exception:
                top = None
        if not top and r.get("ignited"):
            top = "ignited"
        merged = dict(r)
        merged["score"] = float(score)
        merged["side"] = side
        merged["conviction"] = tier
        merged["top_signal"] = top
        merged["tf"] = tf
        out[tf] = merged
    return out


def _deep_analyze_symbol(symbol: str) -> tuple[dict, dict | None]:
    """Run analyzer across every TF for one symbol.

    Returns (per_tf, multi_summary). When coin_deep_analyzer is available
    its analyze_multi_tf() result also carries a pre-computed blended /
    side / confidence / mtf_aligned summary which we forward so the
    consensus block can prefer the canonical engine's verdict.

    When falling back, multi_summary is None and the caller computes
    consensus locally via _blend_consensus.
    """
    if _HAS_DEEP_ANALYZER:
        try:
            result = coin_deep_analyzer.analyze_multi_tf(symbol)  # type: ignore
            if isinstance(result, dict) and result.get("per_tf"):
                return _normalise_per_tf(result["per_tf"]), result
        except Exception:
            # Fall through to local fallback rather than blowing up the
            # whole coin — keeps the watchlist resilient if the engine
            # has a bug for one specific symbol.
            pass
    out: dict = {}
    for tf in _TIMEFRAMES:
        try:
            out[tf] = _fallback_per_tf(symbol, tf)
        except Exception as exc:
            out[tf] = {"tf": tf, "score": 50.0, "side": "NEUTRAL",
                       "conviction": "NONE", "top_signal": None,
                       "error": str(exc)}
    return _normalise_per_tf(out), None


# ---------------------------------------------------------------------------
# Consensus + tiering
# ---------------------------------------------------------------------------
def _conviction_tier(score: float, side: str) -> str:
    """Map a 0-100 fused score + side into a human tier label.

    Tiers mirror what the picks board uses elsewhere so downstream UI
    rendering can colour-match against existing card styles:
        STRONG   — score >= 75 LONG or <= 25 SHORT
        STANDARD — score >= 65 LONG or <= 35 SHORT
        WEAK     — directional but inside the dead zone
        NONE     — neutral
    """
    if side == "NEUTRAL":
        return "NONE"
    if side == "LONG":
        if score >= 75:
            return "STRONG"
        if score >= 65:
            return "STANDARD"
        return "WEAK"
    if side == "SHORT":
        if score <= 25:
            return "STRONG"
        if score <= 35:
            return "STANDARD"
        return "WEAK"
    return "NONE"


def _blend_consensus(per_tf: dict) -> dict:
    """Weighted blend of per-TF scores into one consensus verdict.

    Uses _TF_WEIGHTS so the consensus matches the rest of the system's
    multi-TF arithmetic. Side is decided by signed weight on the
    distance-from-50, not by simple majority of TF sides.
    """
    if not per_tf:
        return {"side": "NEUTRAL", "score": 50.0, "tier": "NONE"}
    total_w = 0.0
    blended = 0.0
    long_w = 0.0
    short_w = 0.0
    for tf, r in per_tf.items():
        w = _TF_WEIGHTS.get(tf, 0.25)
        score = float(r.get("score", 50))
        side = r.get("side", "NEUTRAL")
        total_w += w
        blended += w * score
        if side == "LONG":
            long_w += w * (score - 50)
        elif side == "SHORT":
            short_w += w * (50 - score)
    if total_w <= 0:
        return {"side": "NEUTRAL", "score": 50.0, "tier": "NONE"}
    blended /= total_w
    if long_w > short_w and long_w > 3:
        side = "LONG"
    elif short_w > long_w and short_w > 3:
        side = "SHORT"
    else:
        side = "NEUTRAL"
    return {
        "side": side,
        "score": round(blended, 1),
        "tier": _conviction_tier(blended, side),
    }


def _pick_top_signal(per_tf: dict) -> str:
    """Choose one short label for the per-coin chip on the card.

    Priority: STRONG-tier TF first, then STANDARD-tier, then whichever
    TF has the named pattern/signal firing. Empty string if nothing
    interesting found.
    """
    # Tier priority — strongest first, then earliest TF in case of tie.
    tier_rank = {"STRONG": 0, "STANDARD": 1, "WEAK": 2, "NONE": 3}
    candidates = []
    for tf in _TIMEFRAMES:
        r = per_tf.get(tf)
        if not r:
            continue
        tier = r.get("conviction", _conviction_tier(
            float(r.get("score", 50)), r.get("side", "NEUTRAL")))
        label = r.get("top_signal") or r.get("side", "")
        candidates.append((tier_rank.get(tier, 3), tf, label, r.get("side", "")))
    if not candidates:
        return ""
    candidates.sort()
    best_rank, tf, label, side = candidates[0]
    if not label:
        return ""
    if side and side not in str(label).upper():
        return f"{label} {side} ({tf})"
    return f"{label} ({tf})"


def _is_forecast_forming(per_tf: dict, pct_24h: float) -> bool:
    """True if at least one TF shows STANDARD+ conviction that opposes
    the current 24h trend direction — the early-move signal.

    Interpretation: price has been pushing one way for 24h, but a
    timeframe with real conviction now points the other way. That's the
    moment to watch for a flip — exactly what the design's "FORMING NOW"
    banner is meant to surface.
    """
    if not per_tf:
        return False
    # Current price trend from the 24h move. Dead zone of ±1% so noise
    # doesn't trigger spurious forming reads.
    if pct_24h > 1.0:
        trend_side = "LONG"
    elif pct_24h < -1.0:
        trend_side = "SHORT"
    else:
        trend_side = "NEUTRAL"
    if trend_side == "NEUTRAL":
        # No clear trend to disagree with — only count a STRONG read on
        # any TF as a forming signal.
        for r in per_tf.values():
            tier = r.get("conviction", _conviction_tier(
                float(r.get("score", 50)), r.get("side", "NEUTRAL")))
            if tier == "STRONG":
                return True
        return False
    for r in per_tf.values():
        side = r.get("side", "NEUTRAL")
        tier = r.get("conviction", _conviction_tier(
            float(r.get("score", 50)), r.get("side", "NEUTRAL")))
        if side == "NEUTRAL" or tier in ("NONE", "WEAK"):
            continue
        if side != trend_side:
            # Standard+ conviction disagrees with the dominant 24h move.
            return True
    return False


# ---------------------------------------------------------------------------
# Per-coin worker
# ---------------------------------------------------------------------------
def _analyze_one(base: str) -> dict:
    """Compute the per-coin report for one portfolio base ticker.

    Wraps the full pipeline in a single try/except so a coin that 404s
    or throws inside one of the lanes can never take down the rest of
    the watchlist — the caller just sees `unavailable=True` and moves on.
    """
    symbol = _to_symbol(base)
    base_report = {
        "symbol": symbol,
        "base": base,
        "price_now": None,
        "pct_24h": None,
        "per_tf": {},
        "consensus": {"side": "NEUTRAL", "score": 50.0, "tier": "NONE"},
        "top_signal": "",
        "forecast_forming": False,
        "unavailable": False,
    }
    try:
        # Cheap availability + headline metrics probe. Reuses the same
        # endpoint binance_client already exposes — no extra requests.
        probe = binance_client.get_klines(symbol, "1h", limit=2)
        if probe is None or len(probe) < 2:
            base_report["unavailable"] = True
            return base_report
        price_now = float(probe["close"].iloc[-1])
        base_report["price_now"] = price_now
    except Exception:
        base_report["unavailable"] = True
        return base_report

    try:
        per_tf, multi_summary = _deep_analyze_symbol(symbol)
    except Exception as exc:
        # Deep analysis itself failed — return a stub so the UI still
        # shows the coin tile with an error note rather than vanishing.
        base_report["error"] = f"deep analysis failed: {exc}"
        return base_report

    base_report["per_tf"] = per_tf

    # 24h pct change — prefer the longest TF in per_tf (it has the most
    # bars of history) for a stable read; fall back to the 1h probe.
    try:
        if "1d" in per_tf and per_tf["1d"].get("components", {}).get("signals"):
            # When the canonical engine ran, components may carry the
            # enriched frame; otherwise drop through to the probe-based
            # estimate. Either way, we want a value the card can show.
            pass
        # Pull a 1d frame for an honest 24h change calculation.
        day_df = binance_client.get_klines(symbol, "1d", limit=2)
        if day_df is not None and len(day_df) >= 1:
            open_today = float(day_df["open"].iloc[-1])
            if open_today > 0:
                base_report["pct_24h"] = round(
                    (base_report["price_now"] - open_today) / open_today * 100.0,
                    2,
                )
    except Exception:
        # Non-fatal — leave pct_24h as None and let the UI handle it.
        pass

    # Prefer the canonical engine's blended summary when present — it
    # encodes the full 11-layer fusion (MTF bonus, regime tilt, F&G,
    # consensus bump) which is richer than our local _blend_consensus.
    if multi_summary:
        blended = float(multi_summary.get("blended_score", 50.0))
        side = multi_summary.get("side", "NEUTRAL")
        tier = _conviction_tier(blended, side)
        base_report["consensus"] = {
            "side": side,
            "score": round(blended, 1),
            "tier": tier,
            "confidence": int(multi_summary.get("confidence", 50)),
            "mtf_aligned": bool(multi_summary.get("mtf_aligned", False)),
            "ignited_any": bool(multi_summary.get("ignited_any", False)),
        }
    else:
        base_report["consensus"] = _blend_consensus(per_tf)

    base_report["top_signal"] = _pick_top_signal(per_tf)
    base_report["forecast_forming"] = _is_forecast_forming(
        per_tf, base_report.get("pct_24h") or 0.0
    )
    return base_report


# ---------------------------------------------------------------------------
# Public scan
# ---------------------------------------------------------------------------
def analyze_portfolio() -> list[dict]:
    """Run deep analysis across the 19 portfolio coins in parallel.

    Returns one dict per coin in PORTFOLIO_COINS order (so the UI keeps
    the user's chosen ordering). Coins whose data was unavailable carry
    `unavailable=True` so the card grid can render a placeholder rather
    than dropping them silently.

    Implementation notes:
      * max_workers=6 matches the other scan helpers in this codebase.
      * Each coin runs inside its own try/except inside _analyze_one;
        ThreadPoolExecutor errors are caught here as a belt-and-braces
        guard so one stuck future doesn't strand the whole result list.
    """
    results_by_base: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(_analyze_one, base): base
                   for base in PORTFOLIO_COINS}
        for fut in as_completed(futures):
            base = futures[fut]
            try:
                results_by_base[base] = fut.result()
            except Exception as exc:
                # Unexpected — _analyze_one already swallows errors, so
                # this catches only truly exceptional thread failures.
                results_by_base[base] = {
                    "symbol": _to_symbol(base),
                    "base": base,
                    "price_now": None,
                    "pct_24h": None,
                    "per_tf": {},
                    "consensus": {"side": "NEUTRAL", "score": 50.0,
                                  "tier": "NONE"},
                    "top_signal": "",
                    "forecast_forming": False,
                    "unavailable": True,
                    "error": f"worker crashed: {exc}",
                }

    # Preserve the user's portfolio order — Python dicts preserve
    # insertion order, so iterating PORTFOLIO_COINS gives us a stable
    # presentation regardless of completion order.
    return [results_by_base[b] for b in PORTFOLIO_COINS if b in results_by_base]
