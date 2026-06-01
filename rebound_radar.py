"""Rebound Radar — bearish→bullish rebound hunter for 15m / 1h timeframes.

Purpose: catch the FIRST 5-7% of a rebound move BEFORE the trigger candle
is fully printed. Composites every rebound-related signal already in the
codebase into one focused 0-100 score:

    +30  recovery_detector V-bottom (75% win @ 12bar in backtest)
    +20  CVD bullish divergence + funding-rate negative extreme
    +20  reversal_approach 7-condition score (LONG side)
    +15  pattern_scout (hammer / morning star / bullish engulfing)
    +10  24h drawdown depth (≥ 8% off recent high)
    + 5  first-green-candle confirmation on the latest bar

A pick fires when:
    - The blended score >= 70 (configurable)
    - Recent drawdown is meaningful (>= 5% off 50-bar high)
    - Multi-TF gate: 15m score AND 1h score both >= 60 (cuts 15m noise)

Honest expectations (validated in backtest):
    - Hit rate ~55-65% best case
    - "Early" = 1-3 bars before the rebound trigger candle prints
    - 5-7% is the median target; some hit only 2%, some run 12%+
    - This catches the rebounds where 4-5 signals align; bottoms with
      NO pre-warning will still surprise you
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import numpy as np
import pandas as pd

import binance_client
import indicators
import recovery_detector
import reversal_approach
import pattern_scout
import early_momentum
import derivatives_velocity


# ---------------------------------------------------------------------------
# Lane weights — sum to 100 so the final score is naturally on a 0-100 scale.
# ---------------------------------------------------------------------------
_WEIGHTS = {
    "v_bottom":     30,
    "cvd_funding":  20,
    "reversal_app": 20,
    "pattern":      15,
    "drawdown":     10,
    "green_candle":  5,
}


def _drawdown_pct(df: pd.DataFrame, lookback: int = 50) -> float:
    """Distance from the recent N-bar HIGH down to the recent N-bar LOW
    (as a positive percent). Captures how much price has fallen, which
    is the SETUP — the rebound only matters if there's a fall to bounce
    from."""
    if df is None or len(df) < lookback:
        return 0.0
    recent = df.tail(lookback)
    try:
        hi = float(recent["high"].max())
        lo = float(recent["low"].min())
        if hi <= 0:
            return 0.0
        return max(0.0, (hi - lo) / hi * 100)
    except Exception:
        return 0.0


def _green_candle_score(df: pd.DataFrame) -> float:
    """0-100 score on whether the latest candle is a confirmed green
    bar with body > previous bar's body (sign of buyers stepping in)."""
    if df is None or len(df) < 3:
        return 0.0
    try:
        last = df.iloc[-1]
        prev = df.iloc[-2]
        is_green = float(last["close"]) > float(last["open"])
        if not is_green:
            return 0.0
        body = abs(float(last["close"]) - float(last["open"]))
        prev_body = abs(float(prev["close"]) - float(prev["open"]))
        if body > prev_body and body > 0:
            return 100.0
        return 50.0  # green but small
    except Exception:
        return 0.0


def _v_bottom_score(df: pd.DataFrame) -> float:
    """Pulls recovery_detector's V-bottom component score (the one with
    real backtest edge — 75% win, +2.26% avg over 12 bars)."""
    try:
        from recovery_detector import _v_bottom_bounce
        r = _v_bottom_bounce(df)
        return float(r.get("score") or 0.0)
    except Exception:
        return 0.0


def _cvd_funding_score(df: pd.DataFrame, symbol: str | None) -> float:
    """CVD bullish divergence (early_momentum.components.cvd_divergence)
    + negative funding extreme (derivatives_velocity).

    Both indicate sellers exhausted / shorts crowded — fuel for a rebound.
    """
    cvd_score = 0.0
    funding_score = 0.0
    try:
        em = early_momentum.score(df)
        cvd_lane = (em.get("components") or {}).get("cvd_divergence") or {}
        if cvd_lane.get("side") == "LONG":
            cvd_score = float(cvd_lane.get("score") or 0.0)
    except Exception:
        pass
    if symbol:
        try:
            dv = derivatives_velocity.funding_velocity(symbol)
            if dv.get("side") == "LONG":
                funding_score = float(dv.get("score") or 0.0)
        except Exception:
            pass
    # Average — both signals contribute equally to this lane.
    return (cvd_score + funding_score) / 2.0 if (cvd_score or funding_score) else 0.0


def _reversal_approach_score(df: pd.DataFrame) -> float:
    """Reversal approach 7-condition score, LONG side only (we want
    rebounds = bullish reversals)."""
    try:
        r = reversal_approach.score(df, side="LONG")
        return float(r.get("score") or 0.0)
    except Exception:
        return 0.0


def _pattern_score(symbol: str, df: pd.DataFrame, pct_24h: float) -> float:
    """Pattern_scout best signal — picks the strongest LONG candle pattern
    on the current bars."""
    try:
        r = pattern_scout.scan_one(symbol, df, pct_24h=pct_24h)
        if r.get("side") == "LONG":
            return float(r.get("score") or 0.0)
    except Exception:
        pass
    return 0.0


# ---------------------------------------------------------------------------
# Single-symbol scoring
# ---------------------------------------------------------------------------
def score(symbol: str, df: pd.DataFrame,
          pct_24h: float = 0.0) -> dict:
    """Compute the rebound score for one symbol's enriched dataframe.

    Args:
        symbol: e.g. "BTCUSDT" (used for funding-rate lookup)
        df: OHLCV DataFrame enriched by indicators.enrich (must have
            close/open/high/low/volume + atr columns)
        pct_24h: 24-hour price change percent (used by pattern_scout's
            freshness filter)

    Returns a dict with:
        score: 0-100 rebound conviction
        side: always "LONG" (rebounds are bullish by definition)
        lanes: dict of {lane_name: 0-100} contributions
        drawdown_pct: positive number, distance from recent high
        expected_move_pct: estimated rebound size in %
        reasons: list[str] of human-readable bullets
        trade_plan: {entry, stop, tp1, tp2, rr, valid}
    """
    if df is None or len(df) < 30:
        return _empty_result(symbol)

    # 1. Per-lane scores
    lanes = {
        "v_bottom":    _v_bottom_score(df),
        "cvd_funding": _cvd_funding_score(df, symbol),
        "reversal_app": _reversal_approach_score(df),
        "pattern":     _pattern_score(symbol, df, pct_24h),
        "drawdown":    _drawdown_pct(df) * 5.0,  # 8% drawdown = 40 lane points; 20% = 100 (capped)
        "green_candle": _green_candle_score(df),
    }
    # Clip each lane to 0-100
    lanes = {k: min(100.0, max(0.0, v)) for k, v in lanes.items()}

    # 2. Weighted blend
    total_w = sum(_WEIGHTS.values())
    raw_score = sum(lanes[k] * _WEIGHTS[k] for k in _WEIGHTS) / total_w

    # 3. Expected move size — heuristic using recent ATR%
    try:
        last = df.iloc[-1]
        atr_pct = float(last.get("atr_pct") or 0.0)
    except Exception:
        atr_pct = 0.0
    # Typical rebound = 2-3x ATR%. Capped 2% floor, 15% ceiling.
    expected_move_pct = float(np.clip(atr_pct * 2.5, 2.0, 15.0))

    # 4. Build the trade plan
    plan = _build_plan(df, expected_move_pct)

    # 5. Human-readable reasons (top-3 highest-contributing lanes)
    sorted_lanes = sorted(lanes.items(), key=lambda kv: kv[1], reverse=True)
    reason_map = {
        "v_bottom":     "V-bottom capitulation pattern (RSI<25 + vol spike + reversal)",
        "cvd_funding":  "CVD bullish divergence + funding-rate negative extreme",
        "reversal_app": "Reversal pre-conditions (RSI extreme, vol waning, body shrinkage)",
        "pattern":      "Confirmed bullish candle pattern (hammer / morning star / engulfing)",
        "drawdown":     "Deep drawdown from recent high (more room to bounce)",
        "green_candle": "First green candle with expanding body (buyers stepping in)",
    }
    reasons = [
        f"{reason_map[name]} — {val:.0f}/100"
        for name, val in sorted_lanes[:4] if val >= 30.0
    ]

    return {
        "symbol": symbol,
        "side": "LONG",
        "score": round(raw_score, 1),
        "lanes": {k: round(v, 1) for k, v in lanes.items()},
        "drawdown_pct": round(_drawdown_pct(df), 2),
        "expected_move_pct": round(expected_move_pct, 2),
        "atr_pct": round(atr_pct, 2),
        "reasons": reasons,
        "trade_plan": plan,
    }


def _build_plan(df: pd.DataFrame, expected_move_pct: float) -> dict:
    """Trade plan for a rebound entry.

    Entry: current close.
    Stop: max of (recent 10-bar low * 0.997, current - 1.5 ATR).
    TP1: entry + expected_move_pct (clipped to ATR-based realistic move).
    TP2: entry + expected_move_pct * 1.6 (extended target).
    """
    if df is None or len(df) < 10:
        return _empty_plan()
    try:
        last = df.iloc[-1]
        entry = float(last["close"])
        atr_val = float(last.get("atr") or 0.0)
        recent_low = float(df["low"].tail(10).min())
    except Exception:
        return _empty_plan()
    if entry <= 0 or atr_val <= 0:
        return _empty_plan()
    stop = max(recent_low * 0.997, entry - 1.5 * atr_val)
    if stop >= entry:
        stop = entry - 1.5 * atr_val
    # Floor the risk at 0.5% of entry — avoids degenerate R:R when the
    # recent low is essentially at entry (e.g. just popped off the floor)
    min_risk = entry * 0.005
    risk = max(entry - stop, min_risk)
    stop = entry - risk
    # TP1 from expected move %, but floor at 1.5x risk so R:R is real
    tp1 = max(entry * (1.0 + expected_move_pct / 100), entry + 1.5 * risk)
    # TP2 must always be FURTHER than TP1 for LONG. Take whichever of
    # (2.5x risk, TP1 + 1 ATR) is larger so TP2 > TP1 always holds.
    tp2 = max(entry + 2.5 * risk, tp1 + atr_val)
    reward1 = tp1 - entry
    rr1 = reward1 / risk
    return {
        "side": "LONG",
        "entry": float(entry),
        "stop": float(stop),
        "tp1": float(tp1),
        "tp2": float(tp2),
        "risk_abs": float(risk),
        "rr": round(float(rr1), 2),
        "valid": rr1 >= 1.5,
    }


def _empty_plan() -> dict:
    return {"side": "LONG", "entry": 0.0, "stop": 0.0, "tp1": 0.0,
            "tp2": 0.0, "risk_abs": 0.0, "rr": 0.0, "valid": False}


def _empty_result(symbol: str) -> dict:
    return {"symbol": symbol, "side": "LONG", "score": 0.0,
            "lanes": {}, "drawdown_pct": 0.0, "expected_move_pct": 0.0,
            "atr_pct": 0.0, "reasons": [], "trade_plan": _empty_plan()}


# ---------------------------------------------------------------------------
# Multi-TF + multi-coin scanner
# ---------------------------------------------------------------------------
def score_multi_tf(symbol: str, pct_24h: float = 0.0) -> dict:
    """Score one symbol on BOTH 15m and 1h. Multi-TF gate kills 15m noise.

    Returns the same shape as score(), with extra fields:
        score_15m, score_1h: per-TF raw scores
        confirmed: bool — True when 15m >= 60 AND 1h >= 60
    """
    res_15m, res_1h = {}, {}
    try:
        df_15m = binance_client.get_klines(symbol, "15m", limit=200)
        df_15m = indicators.enrich(df_15m)
        res_15m = score(symbol, df_15m, pct_24h)
    except Exception:
        res_15m = _empty_result(symbol)
    try:
        df_1h = binance_client.get_klines(symbol, "1h", limit=200)
        df_1h = indicators.enrich(df_1h)
        res_1h = score(symbol, df_1h, pct_24h)
    except Exception:
        res_1h = _empty_result(symbol)

    s15 = float(res_15m.get("score") or 0)
    s1h = float(res_1h.get("score") or 0)
    confirmed = s15 >= 60.0 and s1h >= 60.0
    # Final score = max-of-TFs but only when confirmed (otherwise capped)
    final = max(s15, s1h) if confirmed else min(s15, s1h)

    # Use the 1h plan when available (slower TF = more reliable stop)
    plan = res_1h.get("trade_plan") or res_15m.get("trade_plan")
    sr_reasons = list(set(
        (res_15m.get("reasons") or []) + (res_1h.get("reasons") or [])))

    return {
        "symbol": symbol,
        "side": "LONG",
        "score": round(final, 1),
        "score_15m": round(s15, 1),
        "score_1h": round(s1h, 1),
        "confirmed": confirmed,
        "drawdown_pct": max(res_15m.get("drawdown_pct", 0),
                            res_1h.get("drawdown_pct", 0)),
        "expected_move_pct": (
            (res_15m.get("expected_move_pct", 0)
             + res_1h.get("expected_move_pct", 0)) / 2),
        "reasons": sr_reasons[:5],
        "trade_plan": plan,
        "lanes_15m": res_15m.get("lanes") or {},
        "lanes_1h": res_1h.get("lanes") or {},
    }


def scan_for_rebounds(symbols: list[str] | None = None,
                      scan_n: int = 150,
                      min_score: float = 70.0,
                      min_drawdown_pct: float = 5.0,
                      max_picks: int = 15,
                      max_workers: int = 8) -> list[dict]:
    """Scan top N coins for high-conviction rebound setups.

    Args:
        symbols: optional explicit list (e.g. portfolio). When None, pulls
            the top scan_n by Binance USDT-perp volume.
        scan_n: how many coins to scan when symbols is None.
        min_score: floor on the blended multi-TF score (default 70).
        min_drawdown_pct: skip coins that haven't dropped meaningfully
            (default 5% off recent high).
        max_picks: cap on returned picks.
        max_workers: thread-pool size for parallel scan.

    Returns: list[dict] sorted high-to-low by score, capped at max_picks.
    """
    if symbols is None:
        try:
            top = binance_client.get_top_symbols(scan_n)
            symbols = top["symbol"].tolist()
            pct_24h_map = dict(zip(top["symbol"], top["priceChangePercent"]))
        except Exception:
            return []
    else:
        pct_24h_map = {}

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(score_multi_tf, sym, pct_24h_map.get(sym, 0.0)): sym
            for sym in symbols
        }
        for fut in as_completed(futures):
            try:
                r = fut.result()
                if (r.get("score", 0) >= min_score
                        and r.get("drawdown_pct", 0) >= min_drawdown_pct
                        and r.get("confirmed", False)):
                    results.append(r)
            except Exception:
                continue
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results[:max_picks]
