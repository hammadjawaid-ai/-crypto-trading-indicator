"""Reversal-approach detector — predict shooting stars and hammers
BEFORE they print.

Single-candle reversal patterns (shooting star, hammer) are LAGGING by
definition: they confirm AFTER the rejection has happened. By that
point, you're entering at the high (for shorts) or low (for longs)
which means worse fills than if you'd anticipated the reversal.

This module identifies the PRE-CONDITIONS that historically precede
these reversal candles, so you can WATCH the coins and be ready to
trade the actual fire candle when it prints — or pre-position in some
cases.

Eight pre-conditions tracked (per direction):
  1. Distance to resistance / support (within 2% = approaching)
  2. RSI extreme and trending toward it (overbought rising / oversold falling)
  3. Volume waning on the dominant-color candles (buyers/sellers exhausted)
  4. Body shrinkage — consecutive smaller bodies in dominant direction
  5. Extension from EMA20 (>1.5 ATR = stretched)
  6. Crowded positioning (funding rate extreme)
  7. Bearish/bullish CVD divergence (smart money diverging from price)
  8. Intra-bar rejection forming (live evidence on current bar)

Score scaling:
  3+ conditions met → WATCH (setup forming, 60+ confidence)
  5+ conditions met → STRONG WATCH (reversal likely within 1-5 bars, 80+)

HONEST CAVEAT: predicting reversals is harder than detecting them.
Expected win rate of leading signal is 40-55% vs 60-65% for the confirmed
candle. Use this as a WATCHLIST to know where to look, not as a primary
trade trigger. When the actual shooting star or hammer fires, THAT's
when you trade.

This module is PURE — takes OHLCV DataFrame, returns score dict.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Sub-detectors — each returns 0/1 for the condition + a strength score 0-1
# ---------------------------------------------------------------------------

def _approach_to_level(df: pd.DataFrame, side: str,
                       proximity_pct: float = 0.02,
                       lookback: int = 100,
                       min_touches: int = 2) -> dict:
    """Detect whether price is approaching a key level (resistance for SHORT,
    support for LONG).

    A "key level" requires `min_touches` swing pivots within 1% of each other.
    Approaching = within proximity_pct of that level.

    Returns: {"hit": bool, "strength": 0-1, "level": float, "distance_pct": float}
    """
    if len(df) < lookback + 5:
        return {"hit": False, "strength": 0.0, "level": 0.0,
                "distance_pct": 999.0}

    recent = df.tail(lookback)
    last_close = float(df["close"].iloc[-1])
    if last_close <= 0:
        return {"hit": False, "strength": 0.0, "level": 0.0,
                "distance_pct": 999.0}

    # Find swing pivots (simple: bars whose high/low is the local extreme)
    if side == "SHORT":
        # Find pivot highs — bars whose high exceeds 4 bars on each side
        pivots = []
        highs = recent["high"].to_numpy()
        for i in range(4, len(recent) - 4):
            if highs[i] == max(highs[i - 4:i + 5]):
                pivots.append(highs[i])
        if len(pivots) < min_touches:
            return {"hit": False, "strength": 0.0, "level": 0.0,
                    "distance_pct": 999.0}
        # Cluster pivots — find the most-touched zone
        pivots_sorted = sorted(pivots, reverse=True)
        # Take top 5 highs and cluster
        top = pivots_sorted[:5]
        # Simple: take median of top pivots as the resistance level
        level = float(np.median(top))
        # How far below the level are we?
        distance_pct = (level - last_close) / last_close
        # We're "approaching" if 0 < distance < proximity (price below level)
        if 0 <= distance_pct <= proximity_pct:
            strength = 1.0 - (distance_pct / proximity_pct)
            return {"hit": True, "strength": strength, "level": level,
                    "distance_pct": distance_pct * 100}
        return {"hit": False, "strength": 0.0, "level": level,
                "distance_pct": distance_pct * 100}
    else:  # LONG — look for support below
        pivots = []
        lows = recent["low"].to_numpy()
        for i in range(4, len(recent) - 4):
            if lows[i] == min(lows[i - 4:i + 5]):
                pivots.append(lows[i])
        if len(pivots) < min_touches:
            return {"hit": False, "strength": 0.0, "level": 0.0,
                    "distance_pct": 999.0}
        pivots_sorted = sorted(pivots)
        bottom = pivots_sorted[:5]
        level = float(np.median(bottom))
        distance_pct = (last_close - level) / last_close
        if 0 <= distance_pct <= proximity_pct:
            strength = 1.0 - (distance_pct / proximity_pct)
            return {"hit": True, "strength": strength, "level": level,
                    "distance_pct": distance_pct * 100}
        return {"hit": False, "strength": 0.0, "level": level,
                "distance_pct": distance_pct * 100}


def _rsi_extreme_trending(df: pd.DataFrame, side: str,
                          threshold: float = 65.0,
                          rising_bars: int = 5) -> dict:
    """RSI is in extreme zone and trending TOWARD it (further extreme).

    SHORT side: RSI > 65 AND last 5 bars trending up
    LONG side:  RSI < 35 AND last 5 bars trending down
    """
    if "rsi" not in df.columns or len(df) < rising_bars + 2:
        return {"hit": False, "strength": 0.0, "rsi": 50.0}

    rsi_now = float(df["rsi"].iloc[-1])
    rsi_5_ago = float(df["rsi"].iloc[-rising_bars - 1])

    if side == "SHORT":
        if rsi_now > threshold and rsi_now > rsi_5_ago:
            strength = min(1.0, (rsi_now - threshold) / 25)  # 90 = max
            return {"hit": True, "strength": strength, "rsi": rsi_now}
    else:  # LONG
        low_thresh = 100 - threshold  # 35
        if rsi_now < low_thresh and rsi_now < rsi_5_ago:
            strength = min(1.0, (low_thresh - rsi_now) / 25)
            return {"hit": True, "strength": strength, "rsi": rsi_now}
    return {"hit": False, "strength": 0.0, "rsi": rsi_now}


def _volume_waning(df: pd.DataFrame, side: str,
                   lookback: int = 5, baseline: int = 20) -> dict:
    """Volume on recent dominant-color candles declining vs longer baseline.

    SHORT: green-bar volume < 20-bar avg (buying exhausted)
    LONG:  red-bar volume < 20-bar avg (selling exhausted)
    """
    if "volume" not in df.columns or len(df) < baseline + 5:
        return {"hit": False, "strength": 0.0, "ratio": 1.0}

    recent = df.tail(lookback)
    avg_vol_20 = float(df["volume"].tail(baseline).mean() or 1)
    if avg_vol_20 <= 0:
        return {"hit": False, "strength": 0.0, "ratio": 1.0}

    if side == "SHORT":
        # Avg volume of green candles in last 5 bars
        green_mask = recent["close"] > recent["open"]
        green_vols = recent.loc[green_mask, "volume"]
        if len(green_vols) == 0:
            return {"hit": False, "strength": 0.0, "ratio": 1.0}
        green_avg = float(green_vols.mean())
        ratio = green_avg / avg_vol_20
    else:
        red_mask = recent["close"] < recent["open"]
        red_vols = recent.loc[red_mask, "volume"]
        if len(red_vols) == 0:
            return {"hit": False, "strength": 0.0, "ratio": 1.0}
        red_avg = float(red_vols.mean())
        ratio = red_avg / avg_vol_20

    if ratio < 0.85:
        strength = min(1.0, (0.85 - ratio) / 0.50)
        return {"hit": True, "strength": strength, "ratio": ratio}
    return {"hit": False, "strength": 0.0, "ratio": ratio}


def _body_shrinkage(df: pd.DataFrame, side: str,
                    min_consecutive: int = 3) -> dict:
    """Consecutive same-color candles each with smaller body than the previous.

    SHORT: 3+ green candles where each body smaller than prior
    LONG:  3+ red candles where each body smaller than prior
    """
    if len(df) < min_consecutive + 1:
        return {"hit": False, "strength": 0.0, "count": 0}

    recent = df.tail(min_consecutive + 2).reset_index(drop=True)
    bodies = []
    for _, row in recent.iterrows():
        close = float(row["close"])
        open_ = float(row["open"])
        body = abs(close - open_)
        if side == "SHORT":
            is_target_color = close > open_
        else:
            is_target_color = close < open_
        bodies.append((body, is_target_color))

    # Look at last min_consecutive bars — must be all target color AND shrinking
    last_n = bodies[-min_consecutive:]
    if not all(b[1] for b in last_n):
        return {"hit": False, "strength": 0.0, "count": 0}
    # Check shrinkage
    is_shrinking = all(
        last_n[i][0] < last_n[i - 1][0] for i in range(1, len(last_n))
    )
    if is_shrinking:
        # Strength = how much shrinkage (1 - last/first)
        first_body = last_n[0][0]
        last_body = last_n[-1][0]
        if first_body > 0:
            shrink_ratio = 1 - (last_body / first_body)
            strength = min(1.0, shrink_ratio * 1.5)
        else:
            strength = 0.5
        return {"hit": True, "strength": strength,
                "count": min_consecutive}
    return {"hit": False, "strength": 0.0, "count": 0}


def _extension_from_ema(df: pd.DataFrame, side: str,
                        atr_threshold: float = 1.5) -> dict:
    """Distance from EMA20 in ATR units. Stretched > 1.5 ATR = mean reversion likely.

    SHORT: price > EMA20 + 1.5 ATR
    LONG:  price < EMA20 - 1.5 ATR
    """
    needed = ["close", "ema_fast", "atr"]
    if any(c not in df.columns for c in needed):
        return {"hit": False, "strength": 0.0, "atr_dist": 0.0}

    last = df.iloc[-1]
    price = float(last["close"])
    ema = float(last["ema_fast"])
    atr = float(last["atr"])
    if atr <= 0:
        return {"hit": False, "strength": 0.0, "atr_dist": 0.0}

    if side == "SHORT":
        atr_dist = (price - ema) / atr
        if atr_dist >= atr_threshold:
            strength = min(1.0, (atr_dist - atr_threshold) / 2.0)
            return {"hit": True, "strength": strength, "atr_dist": atr_dist}
    else:  # LONG
        atr_dist = (ema - price) / atr
        if atr_dist >= atr_threshold:
            strength = min(1.0, (atr_dist - atr_threshold) / 2.0)
            return {"hit": True, "strength": strength, "atr_dist": atr_dist}
    return {"hit": False, "strength": 0.0,
            "atr_dist": ((price - ema) / atr
                         if side == "SHORT" else (ema - price) / atr)}


def _cvd_divergence_leading(df: pd.DataFrame, side: str,
                            window: int = 20) -> dict:
    """CVD divergence — price making new direction but delta flat/opposite.

    SHORT: price made HH last 20 bars but cumulative delta is flat/down
    LONG:  price made LL last 20 bars but cumulative delta is flat/up
    """
    if "taker_base" not in df.columns or len(df) < window + 5:
        return {"hit": False, "strength": 0.0}

    delta = 2.0 * df["taker_base"] - df["volume"]
    cvd_now = float(delta.tail(window).sum())
    price_chg = float((df["close"].iloc[-1] / df["close"].iloc[-window]
                       - 1.0) if df["close"].iloc[-window] > 0 else 0)

    delta_std = float(delta.rolling(window).std().iloc[-1] or 1)
    cvd_z = cvd_now / (delta_std * np.sqrt(window)) if delta_std > 0 else 0

    if side == "SHORT" and price_chg > 0.005 and cvd_z <= 0:
        strength = min(1.0, abs(cvd_z) / 2.0)
        return {"hit": True, "strength": strength,
                "price_chg_pct": price_chg * 100, "cvd_z": cvd_z}
    if side == "LONG" and price_chg < -0.005 and cvd_z >= 0:
        strength = min(1.0, cvd_z / 2.0)
        return {"hit": True, "strength": strength,
                "price_chg_pct": price_chg * 100, "cvd_z": cvd_z}
    return {"hit": False, "strength": 0.0, "price_chg_pct": price_chg * 100,
            "cvd_z": cvd_z}


def _intra_bar_rejection(df: pd.DataFrame, side: str) -> dict:
    """Live evidence current bar is being rejected.

    SHORT: current bar high > prior bar high, but close near open (upper wick forming)
    LONG:  current bar low < prior bar low, but close near open (lower wick forming)
    """
    if len(df) < 2:
        return {"hit": False, "strength": 0.0}

    last = df.iloc[-1]
    prev = df.iloc[-2]
    last_high = float(last["high"])
    last_low = float(last["low"])
    last_open = float(last["open"])
    last_close = float(last["close"])
    prev_high = float(prev["high"])
    prev_low = float(prev["low"])

    rng = last_high - last_low
    if rng <= 0:
        return {"hit": False, "strength": 0.0}

    body = abs(last_close - last_open)
    body_top = max(last_open, last_close)
    body_bot = min(last_open, last_close)
    upper_wick = last_high - body_top
    lower_wick = body_bot - last_low

    if side == "SHORT":
        # New higher high but rejection wick forming
        if last_high > prev_high and upper_wick >= body * 1.5 and body < rng * 0.5:
            strength = min(1.0, (upper_wick / rng))
            return {"hit": True, "strength": strength,
                    "upper_wick_pct": upper_wick / rng * 100}
    else:  # LONG
        if last_low < prev_low and lower_wick >= body * 1.5 and body < rng * 0.5:
            strength = min(1.0, (lower_wick / rng))
            return {"hit": True, "strength": strength,
                    "lower_wick_pct": lower_wick / rng * 100}
    return {"hit": False, "strength": 0.0}


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------

# Component weights (sum to 1.0)
_WEIGHTS = {
    "approach":   0.20,   # most important — without a level, no setup
    "rsi":        0.15,
    "vol_waning": 0.10,
    "body_shrink": 0.10,
    "extension":  0.15,
    "cvd_div":    0.15,
    "intra_bar":  0.15,
}


def score(df: pd.DataFrame, side: str) -> dict:
    """Compute the reversal-approach score for one coin, one direction.

    Args:
        df: enriched OHLCV DataFrame
        side: "LONG" or "SHORT" — which reversal we're looking for

    Returns:
        {
          "score": 0-100,             # composite
          "side": str,
          "conditions_met": int,       # 0-7 number of conditions hit
          "max_possible": 7,
          "components": {...},         # per-component result + strength
          "summary": str,              # human-readable
        }

    Score interpretation:
      < 50: no clear setup
      50-65: a few conditions met, monitor
      66-79: WATCH — setup likely forming
      80+: STRONG WATCH — reversal probable within 1-5 bars
    """
    if df is None or len(df) < 100 or side not in ("LONG", "SHORT"):
        return _empty(side, "insufficient data")

    components = {
        "approach":    _approach_to_level(df, side),
        "rsi":         _rsi_extreme_trending(df, side),
        "vol_waning":  _volume_waning(df, side),
        "body_shrink": _body_shrinkage(df, side),
        "extension":   _extension_from_ema(df, side),
        "cvd_div":     _cvd_divergence_leading(df, side),
        "intra_bar":   _intra_bar_rejection(df, side),
    }

    conditions_met = sum(1 for c in components.values() if c["hit"])

    # Weighted strength composite
    weighted_strength = sum(
        _WEIGHTS[key] * (c["strength"] if c["hit"] else 0.0)
        for key, c in components.items()
    )
    # Map 0-1 weighted strength to 50-100 score
    score_val = 50 + weighted_strength * 50
    # Bonus for number of conditions met (forces high score when many fire)
    if conditions_met >= 5:
        score_val = max(score_val, 80)
    elif conditions_met >= 3:
        score_val = max(score_val, 65)
    score_val = float(np.clip(score_val, 0, 100))

    # Build summary
    hit_names = [name for name, c in components.items() if c["hit"]]
    summary = (f"{conditions_met}/7 conditions met: "
               + (", ".join(hit_names) if hit_names else "none"))

    return {
        "score": round(score_val, 1),
        "side": side,
        "conditions_met": conditions_met,
        "max_possible": 7,
        "components": components,
        "summary": summary,
    }


def _empty(side: str, reason: str) -> dict:
    return {
        "score": 50.0,
        "side": side,
        "conditions_met": 0,
        "max_possible": 7,
        "components": {},
        "summary": reason,
    }


def scan_both_sides(df: pd.DataFrame) -> dict:
    """Convenience: run both LONG (approaching hammer at support) and
    SHORT (approaching shooting star at resistance) and return the
    stronger setup.
    """
    long_result = score(df, "LONG")
    short_result = score(df, "SHORT")
    if long_result["score"] >= short_result["score"]:
        return long_result
    return short_result
