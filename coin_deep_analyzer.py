"""Coin Deep Analyzer — fuse every signal module into one CONVICTION verdict.

This module is the multi-layer fusion brain used by the 24/7 Agent. It takes
a symbol + timeframe and produces a single conviction object:

    {
      "symbol": str, "tf": str,
      "side": "LONG"|"SHORT"|"NEUTRAL",
      "conviction_score": 0-100,           # final, post-regime, post-MTF
      "confidence_tier": "MAX"|"HIGH"|"STRONG"|"STANDARD"|"LOW",
      "confidence": 0-100,                 # how many lanes align + strength
      "bull_bear": "Bullish"|"Bearish"|"Neutral",
      "ignited": bool,
      "directional_raw": -100..+100,       # weighted lane sum pre-MTF
      "mtf_bonus": float,                  # +20 / -30 / -60 / 0
      "regime": "BULL"|"BEAR"|"CHOP"|"TRANSITION"|"UNKNOWN",
      "lanes": {lane_name: signed_vote},   # rounded
      "drivers": [{lane, vote, note}],     # top contributors
      "breakdown": {lane: {vote, note}},   # full per-lane contribution
      "reasons": [str],                    # human-readable rationale lines
      "forecast": dict,                    # forecast.predict_one output
      "support_resistance": dict,          # SR levels used for the plan
      "trade_plan": {entry, stop, tp1, tp2, rr, side, valid, ...},
      "components": {                      # raw module outputs (for UI)
        "signals", "early_momentum", "long_patterns", "recovery",
        "reversal_approach", "pattern_scout", "rs_vs_btc",
        "derivatives_velocity"
      },
    }

Multi-TF aggregation: analyze_multi_tf(symbol) calls analyze() across
15m, 1h, 4h and 1d and adds a "consensus" bump of +5 per agreeing TF
(max +15) to the blended conviction score.

NOTE on score conventions used by upstream modules:
  - signals.analyze() returns a score in [-100, +100] with bias_label.
  - All other module score() functions return 0-100 with `side`.
This module normalises every lane to a signed vote in -100..+100 before
weighting (LONG = positive, SHORT = negative).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable

import numpy as np

import binance_client
import derivatives_velocity
import early_momentum
import forecast
import indicators
import long_patterns
import market_regime
import pattern_scout
import recovery_detector
import reversal_approach
import rs_vs_btc
import signals
import support_resistance


# ---------------------------------------------------------------------------
# Lane weights (sum to 1.00). Calibrated to which modules carry backtested
# edge per task #11-#52 in this codebase. Mirrors the design spec.
# ---------------------------------------------------------------------------
_LANE_WEIGHTS: dict[str, float] = {
    "signals_core":   0.20,   # signals.analyze — TA stack
    "early_momentum": 0.16,   # CVD+TTM+ROC²+SMC+VWAP
    "long_patterns":  0.09,   # bullish RSI div / engulfing / HL / reclaim
    "recovery":       0.05,   # V-bottom catch (LONG only)
    "rev_approach":   0.09,   # pre-fire reversal conditions
    "pattern_scout":  0.13,   # live candle pattern best signal
    "rs_vs_btc":      0.07,   # alt RS vs BTC
    "deriv_velocity": 0.10,   # funding ROC + OI coil
    "long_short_skew": 0.04,  # combined LP - rec asymmetry placeholder
    "regime_lane":    0.07,   # regime long_bias / short_bias as direct lane
}
# Weights are normalised at use time to be defensive against future edits.

# Dead-zone for lane votes: scores between these endpoints contribute 0.
# Mirrors the claude-trader research recommendation to suppress noise from
# barely-firing signals.
_DEAD_ZONE_LOW = 45.0
_DEAD_ZONE_HIGH = 55.0


# ---------------------------------------------------------------------------
# Tiny per-process cache so analyze_multi_tf() doesn't refetch the same TF
# klines or recompute BTC frames N times. Keyed by (symbol, tf). 5-min TTL.
# ---------------------------------------------------------------------------
import time as _time

_CACHE_TTL_S = 300
_klines_cache: dict[tuple[str, str], tuple[float, Any]] = {}


def _load_klines_cached(symbol: str, tf: str) -> Any:
    """Internal cached kline loader. Returns an enriched DataFrame.

    External callers can override by passing a `loaders` dict to analyze();
    this helper is only used when no override is provided.
    """
    key = (symbol, tf)
    now = _time.time()
    cached = _klines_cache.get(key)
    if cached and (now - cached[0] <= _CACHE_TTL_S):
        return cached[1]
    df = binance_client.get_klines(symbol, tf)
    df = indicators.enrich(df)
    _klines_cache[key] = (now, df)
    return df


# ---------------------------------------------------------------------------
# Vote normalisers — every lane gets converted to -100..+100 (LONG positive).
# ---------------------------------------------------------------------------
def _vote_from_side_score(d: dict | None) -> float:
    """Normalise a {score: 0-100, side: LONG/SHORT/NEUTRAL} dict to a vote.

    Score 50 = no vote. Dead zone 45-55 = 0. Otherwise the deviation from 50
    is doubled (so a score of 80 LONG becomes +60), then sign-flipped to
    match `side`. Used by every module except signals.analyze.
    """
    if not d:
        return 0.0
    try:
        s = float(d.get("score", 50.0))
    except (TypeError, ValueError):
        return 0.0
    side = (d.get("side") or "NEUTRAL").upper()
    if _DEAD_ZONE_LOW <= s <= _DEAD_ZONE_HIGH:
        return 0.0
    magnitude = abs(s - 50.0) * 2.0  # 0..100
    if side == "LONG":
        return magnitude
    if side == "SHORT":
        return -magnitude
    # NEUTRAL with score outside dead zone: keep a small signed lean using
    # the raw deviation direction so we don't lose information silently.
    return (s - 50.0) * 2.0


def _vote_from_signed_score(d: dict | None) -> float:
    """Normalise a signals.analyze() result (score in -100..+100) to a vote.

    Uses bias_label when present to set the sign; otherwise relies on the
    raw score sign. Dead zone applied at |score| < 10.
    """
    if not d:
        return 0.0
    try:
        s = float(d.get("score", 0.0))
    except (TypeError, ValueError):
        return 0.0
    if abs(s) < 10.0:
        return 0.0
    bias = (d.get("bias_label") or d.get("side") or "").upper()
    if bias == "LONG":
        return abs(s)
    if bias == "SHORT":
        return -abs(s)
    return float(np.clip(s, -100.0, 100.0))


def _vote_from_regime(regime_info: dict | None) -> float:
    """Convert market_regime detect_regime() output into a directional vote.

    BULL → positive vote, BEAR → negative. Magnitude scales with regime
    confidence so a CHOP regime contributes nothing.
    """
    if not regime_info:
        return 0.0
    regime = (regime_info.get("regime") or "").upper()
    composite = float(regime_info.get("composite") or 50.0)
    confidence = float(regime_info.get("confidence") or 0.0) / 100.0
    if regime in ("CHOP", "UNKNOWN"):
        return 0.0
    return (composite - 50.0) * 2.0 * max(0.2, confidence)


# ---------------------------------------------------------------------------
# Lane assembly — invokes every signal module and returns a dict of votes.
# ---------------------------------------------------------------------------
def _assemble_lanes(
    symbol: str,
    tf: str,
    df: Any,
    df_4h: Any,
    df_1d: Any,
    btc_df: Any,
    regime: dict,
    loaders: dict | None,
) -> tuple[dict[str, tuple[float, str]], dict[str, dict]]:
    """Run all module scorers and return (lanes, components).

    `lanes` maps lane_name -> (signed_vote, human-readable note).
    `components` keeps the raw module outputs for the card UI.
    """
    components: dict[str, dict] = {}

    # signals.analyze — uses the [-100, +100] convention
    try:
        sig = signals.analyze(df)
    except Exception as exc:
        sig = {"score": 0.0, "bias_label": "NEUTRAL",
               "confidence": 0, "error": str(exc)}
    components["signals"] = sig

    try:
        em = early_momentum.score(df)
    except Exception as exc:
        em = {"score": 50.0, "side": "NEUTRAL", "error": str(exc)}
    components["early_momentum"] = em

    try:
        lp = long_patterns.score(df)
    except Exception as exc:
        lp = {"score": 50.0, "side": "NEUTRAL", "error": str(exc)}
    components["long_patterns"] = lp

    try:
        rec = recovery_detector.score(df)
    except Exception as exc:
        # recovery_detector has a known undefined-name code path on the
        # NEUTRAL branch; swallow so the rest of the conviction still runs.
        rec = {"score": 50.0, "side": "NEUTRAL", "error": str(exc)}
    components["recovery"] = rec

    try:
        rev = reversal_approach.scan_both_sides(df)
    except Exception as exc:
        rev = {"score": 50.0, "side": "NEUTRAL", "error": str(exc)}
    components["reversal_approach"] = rev

    try:
        pct_24h = _pct_24h(df)
        pat = pattern_scout.scan_one(symbol, df, pct_24h=pct_24h)
    except Exception as exc:
        pat = {"score": 50.0, "side": "NEUTRAL",
               "best_signal": "error", "error": str(exc)}
    components["pattern_scout"] = pat

    # RS vs BTC — skip when the symbol IS BTC (self-comparison is 0).
    if symbol.upper().startswith("BTC"):
        rs = {"score": 50.0, "side": "NEUTRAL", "detail": "is BTC"}
    else:
        try:
            rs = rs_vs_btc.score(df, btc_df)
        except Exception as exc:
            rs = {"score": 50.0, "side": "NEUTRAL", "error": str(exc)}
    components["rs_vs_btc"] = rs

    try:
        deriv_v = derivatives_velocity.score(symbol, interval=tf)
    except Exception as exc:
        deriv_v = {"score": 50.0, "side": "NEUTRAL", "error": str(exc)}
    components["derivatives_velocity"] = deriv_v

    # Build signed votes (lane weight applied AFTER assembly so callers can
    # see the raw lane contribution before weighting).
    raw_votes: dict[str, tuple[float, str]] = {
        "signals_core":   (_vote_from_signed_score(sig),
                           "Core TA stack (signals.analyze)"),
        "early_momentum": (_vote_from_side_score(em),
                           "CVD + TTM squeeze + ROC² + SMC + VWAP"),
        "long_patterns":  (_vote_from_side_score(lp),
                           "Classical LONG patterns (RSI div / engulfing / HL)"),
        "recovery":       (_vote_from_side_score(rec),
                           "V-bottom / capitulation bounce"),
        "rev_approach":   (_vote_from_side_score(rev),
                           "Pre-fire reversal conditions"),
        "pattern_scout":  (_vote_from_side_score(pat),
                           "Live candle pattern best signal"),
        "rs_vs_btc":      (_vote_from_side_score(rs),
                           "Alt relative strength vs BTC"),
        "deriv_velocity": (_vote_from_side_score(deriv_v),
                           "Funding ROC + OI compression"),
        "regime_lane":    (_vote_from_regime(regime),
                           "Market regime tilt as a lane"),
    }

    # Asymmetry / skew: when LP fires LONG strongly AND recovery LONG also
    # fires, lean a bit further long. When SHORT (rev/em) cluster, lean
    # short. Captures the "two lanes agreeing on a directional theme".
    lp_v = raw_votes["long_patterns"][0]
    rec_v = raw_votes["recovery"][0]
    em_v = raw_votes["early_momentum"][0]
    rev_v = raw_votes["rev_approach"][0]
    if lp_v > 20.0 and rec_v > 20.0:
        skew = +min(50.0, (lp_v + rec_v) / 3.0)
        skew_note = "LONG cluster: long_patterns + recovery agree"
    elif em_v < -20.0 and rev_v < -20.0:
        skew = -min(50.0, (abs(em_v) + abs(rev_v)) / 3.0)
        skew_note = "SHORT cluster: early_momentum + rev_approach agree"
    else:
        skew = 0.0
        skew_note = "No directional cluster"
    raw_votes["long_short_skew"] = (skew, skew_note)

    # Apply lane weights — normalise to be defensive against weight drift.
    total_weight = sum(_LANE_WEIGHTS.values()) or 1.0
    weighted: dict[str, tuple[float, str]] = {}
    for name, (vote, note) in raw_votes.items():
        w = _LANE_WEIGHTS.get(name, 0.0) / total_weight
        weighted[name] = (vote * w, note)

    return weighted, components


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _pct_24h(df: Any) -> float:
    """Approximate 24h % change from the enriched DF without re-fetching.

    Uses the last 24 hourly bars when df frequency looks hourly; otherwise
    falls back to whatever the last 24 rows represent. Returns 0.0 on error.
    """
    try:
        if df is None or len(df) < 25:
            return 0.0
        close_now = float(df["close"].iloc[-1])
        close_24 = float(df["close"].iloc[-25])
        if close_24 <= 0:
            return 0.0
        return (close_now / close_24 - 1.0) * 100.0
    except Exception:
        return 0.0


def _confidence_tier(conviction: float,
                     side: str,
                     mtf_aligned: bool,
                     ignited: bool,
                     forecast_aligned: bool) -> str:
    """Map (conviction, MTF, ignited, forecast) onto the badge tiers used
    by the existing app.py cards.

    Mirrors the spec:
      MAX     conviction >= 90 AND (mtf_aligned OR ignited)
      HIGH    conviction >= 85 AND (mtf_aligned OR ignited OR forecast)
      STRONG  conviction >= 80 AND forecast aligned
      STANDARD 65 <= conviction < 80
      LOW     conviction < 65
    """
    c = float(conviction)
    if side == "NEUTRAL":
        return "LOW"
    if c >= 90.0 and (mtf_aligned or ignited):
        return "MAX"
    if c >= 85.0 and (mtf_aligned or ignited or forecast_aligned):
        return "HIGH"
    # STRONG: 80+ score is enough — don't require forecast_aligned too
    # (the forecast module is noisy on shorter timeframes; combined
    # score >=80 already means multiple lanes agreed).
    if c >= 80.0:
        return "STRONG"
    if c >= 65.0:
        return "STANDARD"
    return "LOW"


def _format_reasons(side: str,
                    drivers: list[dict],
                    pat: dict,
                    em: dict,
                    rev: dict,
                    regime: dict,
                    mtf_bonus: float,
                    ignited: bool,
                    plan: dict | None) -> list[str]:
    """Build human-readable reason lines for the card."""
    out: list[str] = []
    if side == "NEUTRAL":
        out.append("No clean directional read across the lane stack.")
    else:
        out.append(f"Conviction biased {side} from a weighted vote of all "
                   "signal modules.")
    if drivers:
        top = drivers[0]
        out.append(f"Top driver: {top['note']} ({top['vote']:+.1f})")
    if pat and pat.get("best_signal") not in (None, "none", "no_data", "error"):
        out.append(f"Pattern Scout: {pat.get('best_signal')} "
                   f"({pat.get('score', 50):.0f})")
    if em and em.get("flags"):
        out.append("Early momentum flags: " + ", ".join(em["flags"][:3]))
    if rev and rev.get("conditions_met", 0) >= 4:
        out.append(f"Reversal pre-conditions: "
                   f"{rev['conditions_met']}/7 met")
    if regime:
        out.append(f"Regime: {regime.get('regime','UNKNOWN')} "
                   f"(conf {regime.get('confidence',0):.0f})")
    if mtf_bonus > 0:
        out.append("Multi-timeframe HTF agreement bonus applied.")
    elif mtf_bonus < 0:
        out.append("Higher-TF conflict penalty applied.")
    if ignited:
        out.append("IGNITED — high-magnitude vote + MTF + pattern fire.")
    if plan and plan.get("valid"):
        out.append(f"Plan: entry {plan['entry']:.4g} stop {plan['stop']:.4g} "
                   f"TP1 {plan['tp1']:.4g} (R:R {plan['rr']:.2f})")
    return out


# ---------------------------------------------------------------------------
# Trade plan — anchored to support_resistance + ATR per the spec.
# ---------------------------------------------------------------------------
def _build_trade_plan(df: Any, side: str, sr: dict,
                      directional_raw: float = 0.0) -> dict | None:
    """Compute entry / stop / TP1 / TP2 / R:R.

    LONG: stop = max(swing_low - 0.5*ATR, nearest_support * 0.997)
          tp1  = min(nearest_resistance * 0.997, entry + 2*ATR)
          tp2  = entry + 3.5*ATR
    SHORT: mirrored.

    For NEUTRAL: ALWAYS produces a speculative plan using the directional_raw
    bias (positive=LONG, negative=SHORT, exactly 0 defaults to LONG). The
    user wanted every coin to have an openable card — the conviction tier
    badge already communicates that it's a low-conviction signal.
    R:R floor 1.0 (was 1.2) — speculative plans are tagged invalid=true
    but still returned with valid:false so the UI can warn the user.
    """
    if df is None or len(df) < 30:
        return None
    try:
        last = df.iloc[-1]
        entry = float(last["close"])
        atr_val = float(last.get("atr") or 0.0)
        if atr_val <= 0 or not np.isfinite(atr_val):
            return None
    except Exception:
        return None
    # Coerce NEUTRAL to a directional choice. Default to LONG when truly
    # flat — the user can ignore the card or toggle direction manually.
    if side not in ("LONG", "SHORT"):
        side = "SHORT" if directional_raw < -2.0 else "LONG"

    swing_lookback = min(50, len(df) - 1)
    recent = df.iloc[-swing_lookback:]
    try:
        swing_low = float(recent["low"].min())
        swing_high = float(recent["high"].max())
    except Exception:
        return None

    near_sup = (sr or {}).get("nearest_support") or {}
    near_res = (sr or {}).get("nearest_resistance") or {}
    sup_price = float(near_sup.get("price") or 0.0)
    res_price = float(near_res.get("price") or 0.0)

    # Minimum R:R enforced — TP1 is pushed out to at least 1.5x risk so
    # the trade is mathematically worth taking. If nearest S/R is closer
    # than that, treat it as a "pause level" and put TP1 further.
    MIN_RR_TP1 = 1.5
    MIN_RR_TP2 = 2.5

    if side == "LONG":
        # Stop: furthest of (swing low - 0.5 ATR) and (nearest support * 0.997)
        candidate_stop_swing = swing_low - 0.5 * atr_val
        candidate_stop_sr = (sup_price * 0.997) if sup_price > 0 else candidate_stop_swing
        stop = max(candidate_stop_swing, candidate_stop_sr)
        # Stop must be below entry; if not, fall back to ATR-based stop.
        if stop >= entry:
            stop = entry - 1.5 * atr_val
        risk = entry - stop
        # TP1: respect resistance level OR enforce min R:R 1.5, whichever
        # gives the user a worthwhile trade. If resistance is close, use
        # ATR-based 1.5x risk target instead — it's better to set an
        # achievable goal beyond the noise than wait for a too-near level.
        tp1_min = entry + MIN_RR_TP1 * risk
        if res_price > 0 and res_price * 0.997 > tp1_min:
            tp1 = res_price * 0.997
        else:
            tp1 = tp1_min
        # TP2: 2.5x risk OR next zone beyond TP1, whichever is further.
        tp2 = max(entry + MIN_RR_TP2 * risk, tp1 + 0.8 * atr_val)
        reward = tp1 - entry
    else:  # SHORT
        candidate_stop_swing = swing_high + 0.5 * atr_val
        candidate_stop_sr = (res_price * 1.003) if res_price > 0 else candidate_stop_swing
        stop = min(candidate_stop_swing, candidate_stop_sr)
        if stop <= entry:
            stop = entry + 1.5 * atr_val
        risk = stop - entry
        tp1_min = entry - MIN_RR_TP1 * risk
        if sup_price > 0 and sup_price * 1.003 < tp1_min:
            tp1 = sup_price * 1.003
        else:
            tp1 = tp1_min
        tp2 = min(entry - MIN_RR_TP2 * risk, tp1 - 0.8 * atr_val)
        reward = entry - tp1

    if risk <= 0 or not np.isfinite(risk):
        return None
    rr = float(reward / risk) if risk > 0 else 0.0
    # `valid` flag — UI uses it to decorate cards. R:R >= 1.5 = solid plan,
    # 1.0-1.5 = marginal (we still return it so the user can override).
    valid = rr >= 1.5 and reward > 0

    return {
        "side": side,
        "entry": float(entry),
        "stop": float(stop),
        "tp1": float(tp1),
        "tp2": float(tp2),
        "risk_abs": float(risk),
        "reward_abs": float(reward),
        "rr": round(rr, 2),
        "atr": float(atr_val),
        "valid": bool(valid),
    }


# ---------------------------------------------------------------------------
# Public API — single-TF analyze
# ---------------------------------------------------------------------------
def analyze(symbol: str, tf: str, loaders: dict | None = None) -> dict:
    """Fuse every signal module into a single conviction object for one
    (symbol, timeframe). Safe to call without `loaders` — it will fall back
    to the internal cached binance_client / indicators path. Passing
    `loaders` (a dict of callables matching app.load_* signatures) lets the
    caller route through Streamlit's @st.cache_data layer instead.
    """
    loaders = loaders or {}
    load_klines = loaders.get("load_klines", _load_klines_cached)
    load_regime = loaders.get("load_market_regime", market_regime.detect_regime)
    load_sr = loaders.get("load_support_resistance", None)

    # Layer 0: load enriched klines for this TF + the 4h / 1d gates + BTC.
    try:
        df = load_klines(symbol, tf)
    except Exception as exc:
        return _empty_result(symbol, tf, f"klines load failed: {exc}")
    try:
        df_4h = load_klines(symbol, "4h") if tf != "4h" else df
    except Exception:
        df_4h = df
    try:
        df_1d = load_klines(symbol, "1d") if tf != "1d" else df
    except Exception:
        df_1d = df
    try:
        btc_df = load_klines("BTCUSDT", tf)
    except Exception:
        btc_df = df  # degrade gracefully — RS lane will go neutral

    # Layer 1+: regime
    try:
        regime = load_regime() if callable(load_regime) else {}
    except Exception:
        regime = {"regime": "UNKNOWN", "composite": 50.0, "confidence": 0.0}

    # Layer 2: assemble all lanes
    weighted_lanes, components = _assemble_lanes(
        symbol, tf, df, df_4h, df_1d, btc_df, regime, loaders,
    )

    # Layer 3: raw directional (-100..+100 sum of weighted lane votes)
    directional_raw = float(sum(v for v, _ in weighted_lanes.values()))
    directional_raw = float(np.clip(directional_raw, -100.0, 100.0))

    if directional_raw > 5.0:
        side = "LONG"
    elif directional_raw < -5.0:
        side = "SHORT"
    else:
        side = "NEUTRAL"

    # Layer 4: MTF agreement bonus / penalty
    try:
        sig_4h = signals.analyze(df_4h)
    except Exception:
        sig_4h = {"bias_label": "NEUTRAL", "score": 0.0}
    try:
        sig_1d = signals.analyze(df_1d)
    except Exception:
        sig_1d = {"bias_label": "NEUTRAL", "score": 0.0}

    side_4h = (sig_4h.get("bias_label") or "NEUTRAL").upper()
    side_1d = (sig_1d.get("bias_label") or "NEUTRAL").upper()

    mtf_bonus = 0.0
    if side != "NEUTRAL":
        agree_4h = (side_4h == side)
        agree_1d = (side_1d == side)
        if agree_4h and agree_1d:
            mtf_bonus = 20.0       # Both higher TFs agree → big boost
        elif agree_4h or agree_1d:
            mtf_bonus = 8.0        # One higher TF agrees → small boost
        elif (not agree_4h) and side_4h != "NEUTRAL":
            # Adverse 4h — small penalty (was -30/-60 which obliterated
            # valid contrarian signals). Capped at -15 even in adverse
            # regime so a strong setup still surfaces.
            mtf_bonus = -10.0
            reg_name = (regime.get("regime") or "").upper()
            if reg_name == "BEAR" and side == "LONG":
                mtf_bonus = -15.0
            if reg_name == "BULL" and side == "SHORT":
                mtf_bonus = -15.0

    # Apply MTF bonus in the direction of `side` (positive bonus boosts the
    # conviction toward 100; negative bonus pulls back to 50).
    if side == "LONG":
        directional = directional_raw + mtf_bonus
    elif side == "SHORT":
        directional = directional_raw - mtf_bonus
    else:
        directional = directional_raw
    directional = float(np.clip(directional, -100.0, 100.0))

    # Layer 5: map signed directional to 0-100 conviction.
    # AMPLIFIED 1.8x — the weighted-lane sum rarely exceeds ±20 even
    # with strong signals because every lane weight is a fraction
    # summing to ~1.0. Multiplying by 1.8 maps directional 17 → score
    # 80 (STRONG), directional 28 → score 100 (clipped). The previous
    # formula (50 + directional/2) pinned everything to 50-60 LOW
    # regardless of actual signal strength.
    score_100 = 50.0 + directional * 1.8
    score_100 = float(np.clip(score_100, 0.0, 100.0))

    # Layer 6: regime tilt (±8 cap per task #37)
    try:
        score_100 = float(market_regime.regime_tilt(
            score_100, side if side != "NEUTRAL" else "LONG",
            regime, max_tilt=8.0,
        ))
    except Exception:
        pass

    # Layer 7: support / resistance (used by both forecast hint + plan)
    if callable(load_sr):
        try:
            sr = load_sr(symbol, tf)
        except Exception:
            sr = support_resistance.compute_support_resistance(df)
    else:
        try:
            sr = support_resistance.compute_support_resistance(df)
        except Exception:
            sr = {"supports": [], "resistances": [],
                  "nearest_support": None, "nearest_resistance": None,
                  "price_now": 0.0}

    # Layer 8: confidence — aligned lane count × strength
    aligned_lanes = [
        name for name, (v, _) in weighted_lanes.items()
        if (v > 0 and side == "LONG") or (v < 0 and side == "SHORT")
    ]
    nonzero = [v for v, _ in weighted_lanes.values() if abs(v) > 1e-3]
    avg_strength = (sum(abs(v) for v in nonzero) / max(1, len(nonzero))
                    if nonzero else 0.0)
    confidence = int(round(min(
        100.0, len(aligned_lanes) * 8.0 + avg_strength * 0.8
    )))
    if mtf_bonus > 0:
        confidence = min(100, confidence + 10)
    if mtf_bonus < 0:
        confidence = max(0, confidence - 15)

    # Layer 9: bull/bear label + ignited flag
    if score_100 >= 60.0:
        bull_bear = "Bullish"
    elif score_100 <= 40.0:
        bull_bear = "Bearish"
    else:
        bull_bear = "Neutral"

    pat = components.get("pattern_scout") or {}
    rev = components.get("reversal_approach") or {}
    em = components.get("early_momentum") or {}
    ignited = (
        abs(directional_raw) >= 70.0
        and mtf_bonus > 0
        and (
            pat.get("best_signal") not in (None, "none", "no_data", "error")
            or float(rev.get("score") or 0.0) >= 80.0
        )
        and confidence >= 70
    )

    # Layer 10: forecast
    try:
        df_15m = (load_klines(symbol, "15m")
                  if tf != "15m" else df)
    except Exception:
        df_15m = df
    try:
        per_tf_fc = {
            "15m": signals.analyze(df_15m),
            "1h":  signals.analyze(df if tf == "1h" else load_klines(symbol, "1h")),
            "4h":  sig_4h,
        }
    except Exception:
        per_tf_fc = {"15m": sig_4h, "1h": sig_4h, "4h": sig_4h}
    try:
        fc = forecast.predict_one(
            per_tf=per_tf_fc, radar=None,
            backdrop={"regime": regime},
        )
    except Exception as exc:
        fc = {"outlook": "n/a", "outlook_word": "Neutral",
              "confidence": 0, "horizons": {}, "error": str(exc)}

    forecast_aligned = False
    fc_word = (fc.get("outlook_word") or "").lower()
    if side == "LONG" and fc_word == "bullish":
        forecast_aligned = True
    elif side == "SHORT" and fc_word == "bearish":
        forecast_aligned = True

    # Layer 11: trade plan — always built (NEUTRAL falls back to LONG
    # or SHORT based on directional_raw sign). Card UI uses plan["valid"]
    # to render a "marginal R:R" warning when ≥1.0 but <1.5.
    plan = _build_trade_plan(df, side, sr,
                             directional_raw=float(directional_raw))

    # Drivers + breakdown
    drivers_full = sorted(
        [{"lane": k, "vote": round(v, 2), "note": n}
         for k, (v, n) in weighted_lanes.items() if abs(v) >= 1.0],
        key=lambda d: abs(d["vote"]), reverse=True,
    )
    drivers = drivers_full[:6]
    breakdown = {
        k: {"vote": round(v, 2), "note": n}
        for k, (v, n) in weighted_lanes.items()
    }

    # Confidence tier — uses both MTF flag and forecast alignment.
    mtf_aligned_for_tier = mtf_bonus > 0
    tier = _confidence_tier(score_100, side, mtf_aligned_for_tier,
                            ignited, forecast_aligned)

    reasons = _format_reasons(
        side, drivers, pat, em, rev, regime, mtf_bonus, ignited, plan,
    )

    return {
        "symbol": symbol,
        "tf": tf,
        "side": side,
        "conviction_score": round(float(score_100), 1),
        "confidence_tier": tier,
        "confidence": int(confidence),
        "bull_bear": bull_bear,
        "ignited": bool(ignited),
        "directional_raw": round(directional_raw, 1),
        "mtf_bonus": float(mtf_bonus),
        "regime": (regime.get("regime") or "UNKNOWN"),
        "lanes": {k: round(v, 2) for k, (v, _) in weighted_lanes.items()},
        "drivers": drivers,
        "breakdown": breakdown,
        "reasons": reasons,
        "forecast": fc,
        "forecast_aligned": forecast_aligned,
        "support_resistance": sr,
        "trade_plan": plan,
        "components": components,
    }


# ---------------------------------------------------------------------------
# Public API — multi-TF aggregation
# ---------------------------------------------------------------------------
_MULTI_TFS: tuple[str, ...] = ("15m", "1h", "4h", "1d")
_TF_BLEND_WEIGHTS: dict[str, float] = {
    "15m": 0.20, "1h": 0.30, "4h": 0.30, "1d": 0.20,
}


def analyze_multi_tf(symbol: str,
                     loaders: dict | None = None,
                     tfs: Iterable[str] = _MULTI_TFS,
                     max_workers: int = 4) -> dict:
    """Run analyze() across every timeframe in `tfs` and return a fused
    multi-TF verdict.

    Adds a `consensus` field that bumps blended conviction by +5 per
    agreeing TF (max +15) once at least 3 of 4 timeframes vote the same
    side.

    Returns:
      {
        "symbol": str,
        "per_tf": {tf: analyze() result},
        "blended_score": 0-100,
        "side": "LONG"|"SHORT"|"NEUTRAL",
        "confidence": 0-100,
        "confidence_tier": str,
        "consensus": int,                 # 0..15 bump applied
        "consensus_count": {LONG, SHORT, NEUTRAL},
        "mtf_aligned": bool,              # 3-of-4 same side
        "ignited_any": bool,
        "trade_plan": dict | None,        # picked from the strongest TF
      }
    """
    tfs_list = list(tfs)
    per_tf: dict[str, dict] = {}

    # Parallelise the per-TF analyses — each one is independent. Use a small
    # pool since each analyze() already does several network calls under it.
    workers = max(1, min(max_workers, len(tfs_list)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(analyze, symbol, tf, loaders): tf
                   for tf in tfs_list}
        for fut in as_completed(futures):
            tf = futures[fut]
            try:
                per_tf[tf] = fut.result()
            except Exception as exc:
                per_tf[tf] = _empty_result(symbol, tf, str(exc))

    # Weighted blend (sign-aware) across timeframes
    total_w = sum(_TF_BLEND_WEIGHTS.get(tf, 0.0) for tf in per_tf) or 1.0
    blended = 50.0 + sum(
        (per_tf[tf]["conviction_score"] - 50.0)
        * (_TF_BLEND_WEIGHTS.get(tf, 0.25) / total_w)
        for tf in per_tf
    )

    sides = [per_tf[tf]["side"] for tf in per_tf]
    count = {"LONG": sides.count("LONG"),
             "SHORT": sides.count("SHORT"),
             "NEUTRAL": sides.count("NEUTRAL")}
    mtf_aligned = count["LONG"] >= 3 or count["SHORT"] >= 3

    # Consensus bump: +5 per agreeing TF, max +15.
    if blended >= 50.0:
        bump = min(15, max(0, (count["LONG"] - 1) * 5))
    else:
        bump = min(15, max(0, (count["SHORT"] - 1) * 5))
    blended_with_consensus = float(np.clip(blended + bump, 0.0, 100.0))

    if blended_with_consensus >= 60.0:
        side = "LONG"
    elif blended_with_consensus <= 40.0:
        side = "SHORT"
    else:
        side = "NEUTRAL"

    # Confidence — weighted blend of per-TF confidences + MTF bonus
    confidence = int(round(sum(
        per_tf[tf]["confidence"] * (_TF_BLEND_WEIGHTS.get(tf, 0.25) / total_w)
        for tf in per_tf
    )))
    if mtf_aligned:
        confidence = min(100, confidence + 10)

    ignited_any = any(per_tf[tf].get("ignited") for tf in per_tf)
    forecast_aligned = any(
        per_tf[tf].get("forecast_aligned") and per_tf[tf]["side"] == side
        for tf in per_tf
    )
    tier = _confidence_tier(blended_with_consensus, side,
                            mtf_aligned, ignited_any, forecast_aligned)

    # Trade plan: pick the strongest aligned TF's plan as the canonical one.
    plan = None
    aligned_tfs = [tf for tf in per_tf if per_tf[tf]["side"] == side]
    if aligned_tfs:
        best_tf = max(aligned_tfs,
                      key=lambda t: per_tf[t]["conviction_score"]
                      if side == "LONG"
                      else 100.0 - per_tf[t]["conviction_score"])
        plan = per_tf[best_tf].get("trade_plan")

    return {
        "symbol": symbol,
        "per_tf": per_tf,
        "blended_score": round(blended_with_consensus, 1),
        "blended_score_pre_consensus": round(blended, 1),
        "side": side,
        "confidence": confidence,
        "confidence_tier": tier,
        "consensus": int(bump),
        "consensus_count": count,
        "mtf_aligned": bool(mtf_aligned),
        "ignited_any": bool(ignited_any),
        "trade_plan": plan,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _empty_result(symbol: str, tf: str, reason: str) -> dict:
    """Neutral fallback used when an upstream load fails fatally."""
    return {
        "symbol": symbol,
        "tf": tf,
        "side": "NEUTRAL",
        "conviction_score": 50.0,
        "confidence_tier": "LOW",
        "confidence": 0,
        "bull_bear": "Neutral",
        "ignited": False,
        "directional_raw": 0.0,
        "mtf_bonus": 0.0,
        "regime": "UNKNOWN",
        "lanes": {},
        "drivers": [],
        "breakdown": {},
        "reasons": [f"Analyzer error: {reason}"],
        "forecast": {"outlook": "n/a", "outlook_word": "Neutral",
                     "confidence": 0, "horizons": {}},
        "forecast_aligned": False,
        "support_resistance": {
            "supports": [], "resistances": [],
            "nearest_support": None, "nearest_resistance": None,
            "price_now": 0.0,
        },
        "trade_plan": None,
        "components": {},
        "error": reason,
    }
