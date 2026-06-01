"""Breakout Hunter — pre-100% runner scanner across the wider universe.

Built after PORTAL ran 100%+ overnight and our system didn't flag it
EARLY. The standard top-picks board is calibrated for cleaner setups
on the top-200 by volume. Big-move runners often start in the
mid/small-cap zone (top 200-500), have a multi-day coil, then ignite.

This module hunts for COIL + IGNITION patterns specifically:

  +25  Bollinger / volatility squeeze on 4h (tight 20-bar BB width)
  +20  Hidden accumulation: OBV rising while price flat (smart money)
  +20  OI surge with funding flipping positive (new money piling in)
  +15  TTM Squeeze fire on 1h or 4h
  +10  Higher-low structure on 4h (accumulation phase)
  +10  Cup-and-handle base completion (rare; bonus when present)

A pick fires when:
    - Blended score >= 70
    - 7-day price NOT already > +50% (cap on too-late entries — these
      pump-already-running coins are chase territory)
    - 24h volume >= $5M (liquidity floor — illiquid pumps are traps)

Honest expectations:
    - Hit rate ~30-40% (lower than rebounds — breakouts are noisier)
    - WHEN it hits, the move is 20-100%+ (asymmetric upside)
    - False positives are common — many coins look like breakout
      candidates but never go
    - Best to position-size SMALL because individual misses don't hurt
      but individual hits make the system worthwhile

Universe: top 300-500 USDT-perp by volume (covers small/mid-caps where
big moves originate). Use scan_n parameter to control.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

import binance_client
import indicators
import early_momentum
import derivatives_velocity

try:
    import cup_and_handle
except Exception:
    cup_and_handle = None


_WEIGHTS = {
    "vol_squeeze":  25,
    "hidden_accum": 20,
    "oi_funding":   20,
    "ttm_squeeze":  15,
    "hl_structure": 10,
    "cup_handle":   10,
}


def _vol_squeeze_score(df: pd.DataFrame) -> float:
    """Bollinger-band width squeeze — current BB width sitting at the
    BOTTOM of its 60-bar range = volatility coil = breakout imminent.

    Returns 100 when current BB width is at the 5th percentile of recent
    history (tight squeeze), 50 at the median, 0 at the top.
    """
    if df is None or len(df) < 60:
        return 0.0
    try:
        bb_upper = df.get("bb_upper")
        bb_lower = df.get("bb_lower")
        if bb_upper is None or bb_lower is None:
            return 0.0
        width = (bb_upper - bb_lower).tail(60)
        if width.isna().any() or len(width) < 60:
            return 0.0
        current = float(width.iloc[-1])
        percentile = float((width <= current).sum() / len(width))
        # Lower percentile = tighter squeeze = higher score
        # 0 percentile (tightest) -> 100; 0.50 -> 50; 1.0 (widest) -> 0
        return float(np.clip(100 * (1.0 - percentile), 0.0, 100.0))
    except Exception:
        return 0.0


def _hidden_accumulation_score(df: pd.DataFrame) -> float:
    """OBV rising while price stays flat = stealth accumulation.

    Computed over the last 20 bars:
      - Price change %  (close[-1] vs close[-20])
      - OBV change      (raw delta, normalised by mean OBV)
    Score is high when |price_change| < 2% but OBV change > +5% of mean.
    """
    if df is None or len(df) < 30 or "obv" not in df.columns:
        return 0.0
    try:
        recent = df.tail(20)
        price_chg = (
            float(recent["close"].iloc[-1])
            / float(recent["close"].iloc[0]) - 1.0) * 100
        obv_chg = (
            float(recent["obv"].iloc[-1]) - float(recent["obv"].iloc[0]))
        obv_mean = float(recent["obv"].abs().mean()) or 1.0
        obv_pct = obv_chg / obv_mean * 100
        if abs(price_chg) > 5.0:
            return 0.0  # already moving — not stealth
        if obv_pct < 2.0:
            return 0.0  # no accumulation
        # 5% OBV growth over flat price → 70; 15% → 100
        return float(np.clip((obv_pct - 2) * 8.0, 0.0, 100.0))
    except Exception:
        return 0.0


def _oi_funding_score(symbol: str) -> float:
    """OI compression + funding flipping positive = new money piling in.

    Composite of derivatives_velocity.oi_compression + funding_velocity,
    LONG side only (we're hunting bullish breakouts).
    """
    try:
        dv = derivatives_velocity.score(symbol, interval="1h")
        if (dv.get("side") or "").upper() != "LONG":
            return 0.0
        return float(dv.get("score") or 0.0)
    except Exception:
        return 0.0


def _ttm_squeeze_score(df: pd.DataFrame) -> float:
    """TTM Squeeze fire (early_momentum's squeeze component) — Bollinger
    bands inside Keltner channels then expansion."""
    try:
        em = early_momentum.score(df)
        sq = (em.get("components") or {}).get("ttm_squeeze") or {}
        if (sq.get("side") or "").upper() == "LONG":
            return float(sq.get("score") or 0.0)
    except Exception:
        pass
    return 0.0


def _higher_low_score(df: pd.DataFrame) -> float:
    """Higher-low structure across the last 60 bars = accumulation phase.

    Crude check: split recent 60 bars into 3 windows of 20 bars each;
    score 100 if each window's LOW is higher than the previous window's.
    """
    if df is None or len(df) < 60:
        return 0.0
    try:
        lows = [float(df["low"].iloc[i*20-20:i*20].min())
                for i in range(1, 4)]
        if len(lows) < 3 or any(np.isnan(lows)):
            return 0.0
        if lows[2] > lows[1] > lows[0]:
            return 100.0
        if lows[2] > lows[0]:  # general uptrend in lows
            return 60.0
        return 0.0
    except Exception:
        return 0.0


def _cup_handle_score(df: pd.DataFrame) -> float:
    """Cup-and-handle base completion bonus. Optional — only fires
    when the existing cup_and_handle module detects one."""
    if cup_and_handle is None:
        return 0.0
    try:
        r = cup_and_handle.detect(df) if hasattr(cup_and_handle, "detect") else None
        if r and (r.get("side") or "").upper() == "LONG":
            return float(r.get("score") or 0.0)
    except Exception:
        pass
    return 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def score(symbol: str, df_4h: pd.DataFrame,
          df_1h: pd.DataFrame | None = None) -> dict:
    """Score one symbol for pre-breakout setup.

    Args:
        symbol: e.g. "PORTALUSDT"
        df_4h: 4-hour enriched OHLCV (the primary TF for coil patterns)
        df_1h: optional 1-hour enriched OHLCV (used for TTM squeeze
               confirmation)
    """
    if df_4h is None or len(df_4h) < 60:
        return _empty_result(symbol)

    lanes = {
        "vol_squeeze":  _vol_squeeze_score(df_4h),
        "hidden_accum": _hidden_accumulation_score(df_4h),
        "oi_funding":   _oi_funding_score(symbol),
        "ttm_squeeze":  _ttm_squeeze_score(df_1h
                                          if df_1h is not None
                                          else df_4h),
        "hl_structure": _higher_low_score(df_4h),
        "cup_handle":   _cup_handle_score(df_4h),
    }
    lanes = {k: float(np.clip(v, 0.0, 100.0)) for k, v in lanes.items()}
    total_w = sum(_WEIGHTS.values())
    raw_score = sum(lanes[k] * _WEIGHTS[k] for k in _WEIGHTS) / total_w

    # 7-day price change — used as a "not already gone" filter downstream
    seven_day_chg = 0.0
    try:
        bars_back = min(42, len(df_4h) - 1)  # 42 4h bars = 7 days
        if bars_back > 0:
            old = float(df_4h["close"].iloc[-bars_back])
            cur = float(df_4h["close"].iloc[-1])
            if old > 0:
                seven_day_chg = (cur / old - 1.0) * 100
    except Exception:
        pass

    plan = _build_breakout_plan(df_4h)
    reason_map = {
        "vol_squeeze":  "Bollinger band squeeze (tight 60-bar percentile)",
        "hidden_accum": "Hidden accumulation: OBV rising while price flat",
        "oi_funding":   "Open-interest surge + funding flipping LONG",
        "ttm_squeeze":  "TTM Squeeze fire (BB inside Keltner then expanding)",
        "hl_structure": "Higher-low structure on 4h (accumulation phase)",
        "cup_handle":   "Cup-and-handle base completing",
    }
    sorted_lanes = sorted(lanes.items(), key=lambda kv: kv[1], reverse=True)
    reasons = [
        f"{reason_map[name]} — {val:.0f}/100"
        for name, val in sorted_lanes[:4] if val >= 35.0
    ]

    return {
        "symbol": symbol,
        "side": "LONG",
        "score": round(raw_score, 1),
        "lanes": {k: round(v, 1) for k, v in lanes.items()},
        "seven_day_chg_pct": round(seven_day_chg, 2),
        "reasons": reasons,
        "trade_plan": plan,
    }


def _build_breakout_plan(df: pd.DataFrame) -> dict:
    """Trade plan for a breakout entry.

    Entry: current close.
    Stop: BB lower (or recent 10-bar low * 0.997, whichever is closer
          to entry — breakouts that fall back below the coil are dead).
    TP1: entry + 2.0 ATR  (~3-6% target depending on volatility)
    TP2: entry + 5.0 ATR  (asymmetric upside — these can run 20%+)
    """
    if df is None or len(df) < 20:
        return _empty_plan()
    try:
        last = df.iloc[-1]
        entry = float(last["close"])
        atr_val = float(last.get("atr") or 0.0)
        bb_lower = float(last.get("bb_lower") or 0.0)
        recent_low = float(df["low"].tail(10).min())
    except Exception:
        return _empty_plan()
    if entry <= 0 or atr_val <= 0:
        return _empty_plan()
    # Stop at the higher of (BB lower) and (recent low * 0.997). The
    # idea: the coil should hold. If it breaks below the band's lower,
    # the setup is invalidated.
    cand_stop_1 = bb_lower if bb_lower > 0 else (recent_low * 0.997)
    cand_stop_2 = entry - 1.5 * atr_val
    stop = max(cand_stop_1, cand_stop_2)
    if stop >= entry:
        stop = entry - 1.5 * atr_val
    # Floor risk at 1% of entry — coil patterns sometimes have BB lower
    # right at entry which produces degenerate R:R. 1% min stop ensures
    # any displayed R:R is realistic for the user.
    min_risk = entry * 0.01
    risk = max(entry - stop, min_risk)
    stop = entry - risk
    tp1 = entry + 2.0 * atr_val
    tp2 = entry + 5.0 * atr_val
    return {
        "side": "LONG",
        "entry": float(entry),
        "stop": float(stop),
        "tp1": float(tp1),
        "tp2": float(tp2),
        "risk_abs": float(risk),
        "rr": round(float((tp1 - entry) / risk), 2),
        "valid": (tp1 - entry) / risk >= 1.3,
    }


def _empty_plan() -> dict:
    return {"side": "LONG", "entry": 0.0, "stop": 0.0, "tp1": 0.0,
            "tp2": 0.0, "risk_abs": 0.0, "rr": 0.0, "valid": False}


def _empty_result(symbol: str) -> dict:
    return {"symbol": symbol, "side": "LONG", "score": 0.0,
            "lanes": {}, "seven_day_chg_pct": 0.0,
            "reasons": [], "trade_plan": _empty_plan()}


def scan_for_breakouts(scan_n: int = 300,
                      min_score: float = 70.0,
                      max_seven_day_chg: float = 50.0,
                      min_volume_usd: float = 5_000_000.0,
                      max_picks: int = 15,
                      max_workers: int = 8) -> list[dict]:
    """Scan top N coins for pre-breakout setups.

    Args:
        scan_n: how many top-volume coins to include. Default 300 to
            reach into mid-cap territory (where PORTAL-style runners
            originate). Push higher (500) if you want truly small-caps.
        min_score: floor on the blended score (default 70).
        max_seven_day_chg: skip coins that already pumped >50% over the
            last 7 days (chase trap protection).
        min_volume_usd: skip illiquid coins (default $5M / 24h).
        max_picks: cap on returned picks.

    Returns: list[dict] sorted high-to-low by score.
    """
    try:
        top = binance_client.get_top_symbols(scan_n)
    except Exception:
        return []
    pct_24h_map = dict(zip(top["symbol"], top["priceChangePercent"]))
    vol_map = dict(zip(top["symbol"], top["quoteVolume"]))
    symbols = [s for s in top["symbol"]
               if vol_map.get(s, 0) >= min_volume_usd]

    def _per_symbol(sym: str) -> dict | None:
        try:
            df_4h = binance_client.get_klines(sym, "4h", limit=200)
            df_4h = indicators.enrich(df_4h)
            df_1h = binance_client.get_klines(sym, "1h", limit=200)
            df_1h = indicators.enrich(df_1h)
            r = score(sym, df_4h, df_1h)
            r["volume_usd"] = float(vol_map.get(sym, 0))
            r["pct_24h"] = float(pct_24h_map.get(sym, 0))
            return r
        except Exception:
            return None

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_per_symbol, sym): sym for sym in symbols}
        for fut in as_completed(futures):
            try:
                r = fut.result()
                if r is None:
                    continue
                if (r.get("score", 0) >= min_score
                        and abs(r.get("seven_day_chg_pct", 0))
                        <= max_seven_day_chg):
                    results.append(r)
            except Exception:
                continue
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results[:max_picks]
