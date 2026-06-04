"""Distribution-top detector — catch big SHORT setups like NEAR -25%.

Existing modules are LONG-biased: liq_exhaustion, rebound, recovery,
breakout_coil all detect BOTTOMS. The ELITE composite has no real
"top-detection" lane, which is why NEAR's 25.9% drawdown was never
flagged — pattern_scout was firing LONG 93 right before the crash.

This module is the missing SHORT lane. It detects six independent
signals of distribution at a market top:

  1. PRICE NEAR HIGH        — close within X% of N-bar high
  2. RSI OVERBOUGHT          — RSI ≥ 70 at the top (textbook)
  3. BEARISH MACD DIVERGENCE — price makes new high, MACD does not
                               (smart-money distribution signature)
  4. VOLUME CLIMAX           — recent bar volume well above 20-bar avg
                               (final retail buy spike before drop)
  5. UPPER WICK REJECTION    — long upper wicks at the high
                               (failed breakout attempts)
  6. MOMENTUM EXHAUSTION     — N consecutive smaller bullish bodies
                               OR price stalling after long uptrend

Each component returns 0-1. Final score = weighted sum × 100, with the
divergence and wick rejection components carrying the most weight
because those are the institutional-signature events.

  Component weights:
    macd_divergence:   0.25  ← KEY signal (smart-money divergence)
    wick_rejection:    0.20  ← failed breakouts at the top
    volume_climax:     0.15
    rsi_overbought:    0.15
    price_near_high:   0.15
    momentum_exhaust:  0.10

Score thresholds:
  >= 70: STRONG SHORT setup forming
  >= 60: WATCH (early signs)
  <  60: not firing

Returns dict with side="SHORT", score, components, and a trade plan.

This module is PURE — takes OHLCV DataFrame, returns score dict.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# Component weights (sum to 1.0). Heavily favor LEADING signals
# because the user's goal is to catch the move BEFORE the drop, not
# after. Confirming signals (divergence/wick/exhaust) carry less weight
# since they're mostly post-peak by definition.
_WEIGHTS = {
    "price_near_high": 0.25,  # leading — fires AT peak
    "rapid_rise":      0.20,  # leading — parabolic move signature
    "rsi_overbought":  0.20,  # leading — overbought at peak
    "wick_rejection":  0.10,  # confirming — failed breakout
    "macd_divergence": 0.10,  # confirming — divergence signal
    "volume_climax":   0.10,  # mixed timing
    "momentum_exhaust": 0.05,  # confirming
}


# ---------------------------------------------------------------------------
# Component 1: price near recent high
# ---------------------------------------------------------------------------
def _price_near_high(df: pd.DataFrame, lookback: int = 50,
                    proximity_pct: float = 0.04) -> dict:
    """Returns 0-1 strength. 1.0 when current close >= 99% of lookback
    high, scales down to 0 at proximity_pct distance below.

    Curve tuned aggressively: within 1% of high gives 0.95+ strength
    so leading signals can hit threshold on their own at the peak."""
    if len(df) < lookback + 1:
        return {"strength": 0.0, "high": 0.0, "distance_pct": 999.0}
    high_n = float(df["high"].tail(lookback).max())
    close = float(df["close"].iloc[-1])
    if high_n <= 0 or close <= 0:
        return {"strength": 0.0, "high": high_n, "distance_pct": 999.0}
    distance = (high_n - close) / high_n  # >=0
    if distance >= proximity_pct:
        return {"strength": 0.0, "high": high_n,
                "distance_pct": distance * 100}
    # Aggressive curve: within 0.5% = 1.0, within 1% = 0.92, 2% = 0.75
    # 3% = 0.55, 4% = 0.0 (vs old linear which gave 0.66 at 1%)
    ratio = distance / proximity_pct  # 0..1
    # Quadratic-like ease: 1 - sqrt(ratio) gives steeper drop near max
    strength = 1.0 - (ratio ** 0.6)
    return {"strength": float(np.clip(strength, 0, 1)),
            "high": high_n, "distance_pct": distance * 100}


# ---------------------------------------------------------------------------
# Component 2: RSI overbought (also accepts RECENT peak RSI not just current)
# ---------------------------------------------------------------------------
def _rsi_overbought(df: pd.DataFrame) -> dict:
    """Returns 0-1 strength. Uses BOTH current RSI and the max RSI in
    the last 5 bars — RSI can drop quickly off the peak so we want to
    catch the topping signature even when current RSI has cooled."""
    if "rsi" not in df.columns or len(df) < 5:
        return {"strength": 0.0, "rsi": 50.0}
    last_rsi = float(df["rsi"].iloc[-1]) if not pd.isna(
        df["rsi"].iloc[-1]) else 50.0
    # Recent peak RSI (last 5 bars) — catches the topping signature
    recent_peak = float(df["rsi"].tail(5).max())
    # Use the HIGHER of the two — the topping signal stays valid even
    # if RSI has cooled 1-2 bars after the peak
    effective_rsi = max(last_rsi, recent_peak * 0.95)
    if effective_rsi < 60:
        return {"strength": 0.0, "rsi": last_rsi,
                "recent_peak_rsi": recent_peak}
    # Aggressive curve: 60=0.0, 65=0.5, 70=0.85, 75=1.0, 80+=1.0
    # Catches RSI 70 (textbook overbought) at strong strength.
    if effective_rsi >= 75:
        strength = 1.0
    elif effective_rsi >= 70:
        # 70->0.85, 75->1.0
        strength = 0.85 + (effective_rsi - 70) / 5 * 0.15
    elif effective_rsi >= 65:
        # 65->0.5, 70->0.85
        strength = 0.5 + (effective_rsi - 65) / 5 * 0.35
    else:
        # 60->0.0, 65->0.5
        strength = (effective_rsi - 60) / 5 * 0.5
    return {"strength": float(np.clip(strength, 0, 1)),
            "rsi": last_rsi, "recent_peak_rsi": recent_peak}


# ---------------------------------------------------------------------------
# Component 2b: RAPID RISE — parabolic move signature
# ---------------------------------------------------------------------------
def _rapid_rise(df: pd.DataFrame) -> dict:
    """Catches the parabolic top — when price has risen rapidly over the
    last N bars, mean reversion / distribution is statistically likely.
    Scales by how big the move was vs typical volatility (ATR-normalized).

    NEAR-style move: $2.30 -> $3.09 in ~20 bars = +34% in 20h. That's
    far above the typical 1h ATR. Such moves rarely sustain.
    """
    if len(df) < 25:
        return {"strength": 0.0, "pct_change_20bar": 0.0}
    close_now = float(df["close"].iloc[-1])
    close_20bar_ago = float(df["close"].iloc[-21])
    if close_20bar_ago <= 0:
        return {"strength": 0.0, "pct_change_20bar": 0.0}
    pct = (close_now / close_20bar_ago - 1) * 100
    if pct < 7:
        # Less than 7% in 20 bars — not parabolic
        return {"strength": 0.0, "pct_change_20bar": pct}
    # Scale: 7% = 0.2, 15% = 0.6, 25%+ = 1.0
    strength = min((pct - 7) / 18, 1.0) * 0.8 + 0.2
    return {"strength": float(np.clip(strength, 0, 1)),
            "pct_change_20bar": pct}


# ---------------------------------------------------------------------------
# Component 3: bearish MACD divergence (KEY signal)
# ---------------------------------------------------------------------------
def _macd_divergence(df: pd.DataFrame, lookback: int = 40) -> dict:
    """Detect bearish divergence using TWO methods (both catch tops):

    Method A — Slope-based (works in fast rallies without clear pivots):
      Compare the last 5-bar price slope vs MACD slope. If price is
      sloping up but MACD slope is flat/down, that's divergence.

    Method B — Pivot-based (works when there are clear pivot highs):
      Find 2 pivot highs (2 bars each side), compare prices and MACD
      values. If price higher but MACD lower, divergence.

    Returns the STRONGER of the two methods' strength values.
    """
    if ("macd" not in df.columns
            or "macd_hist" not in df.columns
            or len(df) < lookback + 3):
        return {"strength": 0.0, "has_divergence": False}
    recent = df.tail(lookback).reset_index(drop=True)
    highs = recent["high"].to_numpy()
    macd_vals = recent["macd"].to_numpy()
    closes = recent["close"].to_numpy()

    # Method A — slope-based (catches fast monotonic rallies)
    slope_strength = 0.0
    if len(recent) >= 12:
        # Compare last 5-bar price slope to last 5-bar MACD slope
        price_now = closes[-1]
        price_5bar = closes[-6]
        macd_now = macd_vals[-1]
        macd_5bar = macd_vals[-6]
        macd_10bar = macd_vals[-11] if len(macd_vals) > 11 else macd_5bar
        if (not pd.isna(macd_now) and not pd.isna(macd_5bar)
                and not pd.isna(macd_10bar)
                and price_5bar > 0):
            price_chg_pct = (price_now - price_5bar) / price_5bar
            # MACD declining in last 10 bars
            macd_declining = (macd_now < macd_5bar
                             or macd_5bar < macd_10bar)
            # Price up >2% in last 5 bars while MACD declining
            if price_chg_pct > 0.02 and macd_declining:
                # Stronger price rise + stronger MACD decline = stronger signal
                macd_drop = (macd_5bar - macd_now) / max(
                    abs(macd_5bar), 0.001)
                slope_strength = min(
                    price_chg_pct * 10 + max(macd_drop, 0) * 2, 1.0)

    # Method B — pivot-based (kept for clean reversal scenarios)
    pivot_strength = 0.0
    pivot_idxs = []
    for i in range(2, len(highs) - 2):
        if highs[i] == max(highs[i - 2:i + 3]):
            pivot_idxs.append(i)
    # Fallback: include current bar as second pivot if it's a new high
    if len(pivot_idxs) == 1:
        cur_idx = len(highs) - 1
        if highs[cur_idx] > highs[pivot_idxs[0]] and cur_idx > pivot_idxs[0] + 3:
            pivot_idxs.append(cur_idx)
    if len(pivot_idxs) < 2:
        # No pivots — slope-based only
        return {"strength": float(np.clip(slope_strength, 0, 1)),
                "has_divergence": slope_strength > 0,
                "method": "slope" if slope_strength > 0 else "none"}
    # Take the 2 most recent pivots
    p1_idx, p2_idx = pivot_idxs[-2], pivot_idxs[-1]
    p1_high = highs[p1_idx]
    p2_high = highs[p2_idx]
    p1_macd = macd_vals[p1_idx]
    p2_macd = macd_vals[p2_idx]
    price_pct_up_for_reason = 0.0
    # For bearish divergence: price2 > price1 (higher high) AND macd2 < macd1
    if (p2_high > p1_high
            and not pd.isna(p1_macd) and not pd.isna(p2_macd)
            and p2_macd < p1_macd):
        # Bearish divergence — quantify strength
        price_pct_up = (p2_high - p1_high) / max(p1_high, 1e-9)
        macd_pct_down = (
            (p1_macd - p2_macd) / max(abs(p1_macd), 1e-9))
        pivot_strength = (
            min(price_pct_up * 20, 1.0) * 0.5
            + min(macd_pct_down, 1.0) * 0.5)
        price_pct_up_for_reason = price_pct_up * 100

    # Combine — return the STRONGER of the two methods
    final_strength = max(slope_strength, pivot_strength)
    return {
        "strength": float(np.clip(final_strength, 0, 1)),
        "has_divergence": final_strength > 0,
        "method": ("pivot" if pivot_strength >= slope_strength
                   else "slope"),
        "slope_strength": slope_strength,
        "pivot_strength": pivot_strength,
        "price_extension_pct": price_pct_up_for_reason,
    }


# ---------------------------------------------------------------------------
# Component 4: volume climax
# ---------------------------------------------------------------------------
def _volume_climax(df: pd.DataFrame, lookback: int = 20) -> dict:
    """Returns 0-1 strength. The last 1-3 bars must show volume
    significantly above the 20-bar average AT the price high (distribution).

    Volume alone isn't enough — we want volume up + price stalling.
    """
    if len(df) < lookback + 3 or "volume" not in df.columns:
        return {"strength": 0.0, "vol_ratio": 1.0}
    vol_avg_20 = float(df["volume"].tail(lookback).mean())
    if vol_avg_20 <= 0:
        return {"strength": 0.0, "vol_ratio": 1.0}
    # Use the max of last 3 bars (recent climax)
    vol_last3_max = float(df["volume"].tail(3).max())
    ratio = vol_last3_max / vol_avg_20
    if ratio < 1.5:
        return {"strength": 0.0, "vol_ratio": ratio}
    # Scale: 1.5x = 0.3, 2.0x = 0.6, 3.0x = 1.0
    strength = min((ratio - 1.5) / 1.5, 1.0)
    # Cap if recent 3 bars are still strongly bullish (no climax yet)
    # — climax means the buying is exhausted
    last3 = df.tail(3)
    bull_count = sum(1 for i in range(len(last3))
                    if last3["close"].iloc[i] > last3["open"].iloc[i])
    if bull_count == 3:
        # All bull bars — likely still in the rally, not climaxing yet
        strength *= 0.5
    return {"strength": float(np.clip(strength, 0, 1)),
            "vol_ratio": ratio, "bull_count_last3": bull_count}


# ---------------------------------------------------------------------------
# Component 5: upper-wick rejection (failed breakout)
# ---------------------------------------------------------------------------
def _wick_rejection(df: pd.DataFrame) -> dict:
    """Long upper wicks at the recent high = sellers stepping in.
    Check last 3-5 bars for bars with upper wick > 2x body.
    """
    if len(df) < 5:
        return {"strength": 0.0, "n_rejections": 0}
    recent = df.tail(5)
    n_rejections = 0
    max_wick_ratio = 0.0
    for i in range(len(recent)):
        o = float(recent["open"].iloc[i])
        h = float(recent["high"].iloc[i])
        l = float(recent["low"].iloc[i])
        c = float(recent["close"].iloc[i])
        bar_rng = h - l
        if bar_rng <= 0:
            continue
        body = abs(c - o)
        upper_wick = h - max(o, c)
        # Upper wick must be >= 2× body AND >= 50% of total range
        if (body > 0 and upper_wick / max(body, 0.0001) >= 2.0
                and upper_wick / bar_rng >= 0.5):
            n_rejections += 1
            wick_ratio = upper_wick / max(body, 0.0001)
            if wick_ratio > max_wick_ratio:
                max_wick_ratio = wick_ratio
    if n_rejections == 0:
        return {"strength": 0.0, "n_rejections": 0,
                "max_wick_ratio": 0.0}
    # Scale: 1 rejection = 0.5, 2 = 0.8, 3+ = 1.0
    strength = min(n_rejections * 0.4 + 0.1, 1.0)
    return {"strength": float(np.clip(strength, 0, 1)),
            "n_rejections": n_rejections,
            "max_wick_ratio": max_wick_ratio}


# ---------------------------------------------------------------------------
# Component 6: momentum exhaustion
# ---------------------------------------------------------------------------
def _momentum_exhaustion(df: pd.DataFrame, lookback: int = 10) -> dict:
    """Detect uptrend losing steam: consecutive bullish bars with
    SMALLER bodies than the prior bull bar (body shrinkage), OR
    price stalling near the high with tight range bars after a run.
    """
    if len(df) < lookback + 2:
        return {"strength": 0.0, "body_shrink_count": 0}
    recent = df.tail(lookback)
    # Count of consecutive bullish bars with shrinking bodies (most recent)
    body_shrink_count = 0
    prev_body = None
    for i in range(len(recent) - 1, -1, -1):
        o = float(recent["open"].iloc[i])
        c = float(recent["close"].iloc[i])
        body = c - o  # positive for bull bar
        if body <= 0:
            # First bear bar breaks the streak
            break
        if prev_body is None:
            prev_body = body
            body_shrink_count = 1
            continue
        # Body must be smaller than the NEWER one (which came later
        # we iterate backwards, so older bars should have BIGGER bodies)
        if body > prev_body:
            body_shrink_count += 1
            prev_body = body
        else:
            break
    # Need at least 3 consecutive shrinking bull bars for exhaustion
    if body_shrink_count < 3:
        return {"strength": 0.0, "body_shrink_count": body_shrink_count}
    # Scale: 3 = 0.5, 4 = 0.75, 5+ = 1.0
    strength = min((body_shrink_count - 2) * 0.25, 1.0)
    return {"strength": float(np.clip(strength, 0, 1)),
            "body_shrink_count": body_shrink_count}


# ---------------------------------------------------------------------------
# Master score function
# ---------------------------------------------------------------------------
def score(df: pd.DataFrame,
         df_4h: pd.DataFrame | None = None) -> dict:
    """Compute the distribution-top composite score.

    Args:
        df: 1h OHLCV DataFrame (enriched with RSI, MACD, etc.)
        df_4h: optional 4h df for higher-TF confirmation

    Returns dict with:
        score: 0-100 composite
        side: always "SHORT" (this lane only fires short)
        components: per-component breakdown
        reasons: list[str] of firing components
        valid: bool — true if score >= 60
    """
    if df is None or len(df) < 50:
        return _empty()
    try:
        comps = {
            "price_near_high": _price_near_high(df),
            "rsi_overbought":  _rsi_overbought(df),
            "rapid_rise":      _rapid_rise(df),
            "macd_divergence": _macd_divergence(df),
            "volume_climax":   _volume_climax(df),
            "wick_rejection":  _wick_rejection(df),
            "momentum_exhaust": _momentum_exhaustion(df),
        }
        # Weighted composite
        weighted = sum(
            comps[name]["strength"] * _WEIGHTS.get(name, 0)
            for name in _WEIGHTS)
        # Multi-TF bonus: if 4h is also near its own high, +0.10
        mtf_bonus = 0.0
        if df_4h is not None and len(df_4h) >= 30:
            try:
                p4h = _price_near_high(df_4h, lookback=20,
                                       proximity_pct=0.05)
                if p4h["strength"] >= 0.5:
                    mtf_bonus = 0.10
            except Exception:
                pass
        score_raw = (weighted + mtf_bonus) * 100
        score_clipped = float(np.clip(score_raw, 0, 100))
        # Build reasons list
        reasons = []
        if comps["macd_divergence"]["strength"] >= 0.4:
            d = comps["macd_divergence"]
            ext = d.get("price_extension_pct", 0)
            reasons.append(
                f"bearish MACD divergence (price +{ext:.1f}% but "
                f"MACD dropped)")
        if comps["wick_rejection"]["strength"] >= 0.4:
            n = comps["wick_rejection"]["n_rejections"]
            reasons.append(
                f"{n} upper-wick rejection{'s' if n != 1 else ''} "
                "at top (failed breakout)")
        if comps["rsi_overbought"]["strength"] >= 0.4:
            r = comps["rsi_overbought"]["rsi"]
            reasons.append(f"RSI {r:.0f} (overbought)")
        if comps["volume_climax"]["strength"] >= 0.3:
            v = comps["volume_climax"]["vol_ratio"]
            reasons.append(
                f"volume climax {v:.1f}x avg (distribution)")
        if comps["price_near_high"]["strength"] >= 0.5:
            d = comps["price_near_high"]["distance_pct"]
            reasons.append(
                f"within {d:.1f}% of 50-bar high")
        if comps["rapid_rise"]["strength"] >= 0.4:
            p = comps["rapid_rise"]["pct_change_20bar"]
            reasons.append(
                f"parabolic +{p:.1f}% in 20 bars (overheated)")
        if comps["momentum_exhaust"]["strength"] >= 0.3:
            n = comps["momentum_exhaust"]["body_shrink_count"]
            reasons.append(
                f"{n} consecutive smaller bull bodies "
                "(exhaustion)")
        if mtf_bonus > 0:
            reasons.append("4h also at top")
        return {
            "score": round(score_clipped, 1),
            "side": "SHORT",
            "components": comps,
            "reasons": reasons,
            "valid": score_clipped >= 50,
            "mtf_bonus": mtf_bonus,
        }
    except Exception as exc:
        return _empty(error=str(exc))


def _empty(error: str = "") -> dict:
    return {
        "score": 0.0,
        "side": "SHORT",
        "components": {},
        "reasons": [],
        "valid": False,
        "error": error,
    }
