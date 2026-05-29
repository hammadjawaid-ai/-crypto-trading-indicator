"""Relative Strength vs BTC — a leading rotation signal.

When alts out-perform BTC during BTC chop or pullbacks, capital is
rotating in BEFORE the broader trend confirms. Classic Minervini/IBD
relative strength, adapted for crypto.

The formula at its core:
    rs = (alt_return_over_N) / (btc_return_over_N)

Multiple windows are blended (short, medium, long) so a coin needs to
out-perform across timeframes — not just on one isolated window.
A z-score normalises the RS against the coin's own recent history,
catching meaningful *acceleration* in relative strength rather than
just whoever happens to be up the most today.

This module is PURE — takes two DataFrames (alt, BTC), returns a
0–100 score dict. No state, no API calls, no Streamlit dependency.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# Lookback windows (in bars) — short / medium / long
# Tuned for 1h candles: ~4h, ~24h, ~4d. The list is bar-count, not time
# units, so callers using 15m bars should pass scaled windows via
# `windows=` if they want true time-equivalence.
DEFAULT_WINDOWS_1H = (4, 24, 96)


def _safe_returns(close: pd.Series, n: int) -> pd.Series:
    """Forward % return over n bars (vectorised, NaN-safe)."""
    prev = close.shift(n)
    return (close / prev.replace(0, np.nan)) - 1.0


def _align(alt: pd.DataFrame, btc: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Align alt and BTC closes on a common index (intersection).

    Returns (alt_close, btc_close) restricted to the bars present in both
    DataFrames. Raises ValueError if there's no overlap.
    """
    common = alt.index.intersection(btc.index)
    if len(common) < 30:
        raise ValueError(f"Too few overlapping bars: {len(common)}")
    return alt.loc[common, "close"], btc.loc[common, "close"]


def score(alt_df: pd.DataFrame, btc_df: pd.DataFrame,
          windows: tuple[int, ...] = DEFAULT_WINDOWS_1H,
          z_lookback: int = 200) -> dict:
    """Compute relative strength score for ONE alt vs BTC.

    Args:
        alt_df: alt OHLCV DataFrame.
        btc_df: BTC OHLCV DataFrame (any quote — typically BTCUSDT).
        windows: tuple of lookback bar counts for RS computation.
        z_lookback: bars over which to z-score the blended RS.

    Returns dict:
        {
          "score": 0-100,
          "side": "LONG" | "SHORT" | "NEUTRAL",
          "rs_z":         z-score of blended RS,
          "rs_blended":   raw RS (avg of windows, dimensionless),
          "windows": {16: {"rs": .., "alt_ret_pct": .., "btc_ret_pct": ..}, ...},
          "detail":  human-readable summary,
        }

    Score interpretation:
       >=80  STRONG RS leader — significantly out-performing BTC
       60-79 mild RS lead
       40-59 in-line with BTC
       21-39 mild RS laggard
        <=20 STRONG RS laggard — significantly under-performing BTC
    """
    try:
        alt_close, btc_close = _align(alt_df, btc_df)
    except ValueError as exc:
        return _empty_result(str(exc))

    if len(alt_close) < max(windows) + 10:
        return _empty_result(
            f"Need at least {max(windows) + 10} bars, have {len(alt_close)}")

    # Per-window RS readings
    window_data: dict[int, dict] = {}
    rs_values: list[float] = []
    for w in windows:
        alt_ret = float(_safe_returns(alt_close, w).iloc[-1] or 0)
        btc_ret = float(_safe_returns(btc_close, w).iloc[-1] or 0)
        # RS expressed as relative-percent-difference, NaN-safe
        if btc_ret == 0 and alt_ret == 0:
            rs = 0.0
        elif abs(btc_ret) < 1e-6:
            # BTC essentially flat — RS is just the alt's return signal
            rs = alt_ret
        else:
            # Relative outperformance: alt minus btc in absolute %-points.
            # Using subtraction (not division) avoids exploding RS when
            # BTC moves are tiny and provides a clean linear scale.
            rs = alt_ret - btc_ret
        window_data[w] = {
            "rs": round(rs, 4),
            "alt_ret_pct": round(alt_ret * 100, 2),
            "btc_ret_pct": round(btc_ret * 100, 2),
        }
        rs_values.append(rs)

    rs_blended = float(np.mean(rs_values))

    # Z-score the blended RS over its own recent history. Use a rolling
    # RS series at the SHORTEST window for the historical baseline so
    # the z-score reflects *acceleration* in RS, not just the level.
    short_w = windows[0]
    rs_history = (_safe_returns(alt_close, short_w)
                  - _safe_returns(btc_close, short_w))
    rs_hist_recent = rs_history.tail(z_lookback).dropna()
    if len(rs_hist_recent) < 30:
        rs_z = 0.0
    else:
        mu = float(rs_hist_recent.mean())
        sd = float(rs_hist_recent.std() or 1.0)
        if sd > 0:
            rs_z = (rs_blended - mu) / sd
        else:
            rs_z = 0.0

    # Map z-score to 0–100 score with a clean sigmoid-like ramp:
    #   z = -2 -> ~12, z = -1 -> ~30, z = 0 -> 50, z = +1 -> ~70, z = +2 -> ~88
    raw_score = 50.0 + 19.0 * float(np.tanh(rs_z))
    raw_score = float(np.clip(raw_score, 0, 100))

    # Side: LONG if RS is positive AND z-score confirms outperformance.
    # SHORT if RS is negative AND z confirms underperformance.
    if rs_blended > 0 and rs_z >= 0.5:
        side = "LONG"
    elif rs_blended < 0 and rs_z <= -0.5:
        side = "SHORT"
    else:
        side = "NEUTRAL"

    # Build a human-readable detail string
    parts: list[str] = []
    for w in windows:
        d = window_data[w]
        parts.append(f"{w}b: alt {d['alt_ret_pct']:+.1f}% vs "
                     f"BTC {d['btc_ret_pct']:+.1f}%")
    detail = " · ".join(parts) + f" · z {rs_z:+.2f}"

    return {
        "score": round(raw_score, 1),
        "side": side,
        "rs_z": round(rs_z, 3),
        "rs_blended": round(rs_blended, 4),
        "windows": window_data,
        "detail": detail,
    }


def rank_universe(scores: dict[str, dict]) -> dict[str, float]:
    """Cross-sectionally rank the RS scores of a universe of alts.

    Given a {symbol: score_dict} mapping (one entry per coin), returns
    a {symbol: percentile} mapping (0.0 = bottom, 1.0 = top RS leader).

    Cross-sectional rank is the part of the original Minervini RS line —
    "this coin's RS percentile vs every other tradeable coin". Use this
    to flag "top 10% RS leader" in the picks UI.
    """
    if not scores:
        return {}
    syms = list(scores.keys())
    raw = np.array([scores[s].get("rs_blended", 0.0) for s in syms])
    # Percentile rank (0..1)
    order = raw.argsort()
    ranks = np.empty_like(order, dtype=float)
    n = len(raw)
    if n <= 1:
        return {syms[0]: 0.5} if syms else {}
    ranks[order] = np.linspace(0.0, 1.0, n)
    return {syms[i]: float(ranks[i]) for i in range(n)}


def _empty_result(reason: str) -> dict:
    return {
        "score": 50.0,
        "side": "NEUTRAL",
        "rs_z": 0.0,
        "rs_blended": 0.0,
        "windows": {},
        "detail": reason,
    }
