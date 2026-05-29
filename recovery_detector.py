"""Recovery / V-bottom catcher — captures the JTO and INJ-style setups.

Pattern observed (real examples from 2026-05-29 sessions):
  JTO/USDT: $0.54 → $0.4627 (capitulation) → $0.5386 (+12.77% 24h)
  INJ/USDT: $6.05 → $5.257  (capitulation) → $6.371  (+14.28% 24h)

Both showed:
  1. Sharp drawdown 12-20% in 24-48 hours
  2. RSI extreme oversold (<25) at the bottom
  3. Strong green reversal candle with body >= 50% of range
  4. Volume capitulation on the drop, drying up at the bottom
  5. Reclaim of broken MAs with momentum

Our existing modules don't combine these AS A UNIT. Bullish RSI divergence
fires in long_patterns but only when there are confirmed pivot lows on
both sides — these V-bottoms are too sharp for the pivot rule to confirm
in time. Higher-Low structure needs TWO swing lows to compare — but a V-
bottom doesn't form two distinguishable lows. Trend reclaim fires but
only after 3+ bars below — these reversals reclaim the MA the same hour.

This module catches the pattern directly with two strict patterns:

PATTERN 1: V-BOTTOM CAPITULATION BOUNCE
  Trigger window: catch the FIRST 1-3 strong green candles after a
  capitulation washout. Fires when ALL of these hold:
    - Drawdown >= 12% from highest high in last 48 bars
    - RSI(14) printed <= 25 within last 12 bars
    - Strong green candle (body >= 50% of range)
    - Recent-bar volume >= 1.8x of 20-bar average
    - Volume drying signal: avg of last 5 bars <= 1.3x of 20-bar avg
    - Last close is ABOVE the recent low by at least 2%

PATTERN 2: TREND RECLAIM WITH MOMENTUM
  Catches the slightly later entry: price reclaiming the MA50 with
  conviction after a confirmed downtrend.
    - Price was below MA50 for at least 5 of the last 8 bars
    - Current bar closes ABOVE MA50
    - Current bar body >= 40% of its range
    - RSI crossed back above 50 within last 3 bars
    - Volume on this bar >= 1.5x of 20-bar average

Both patterns are deliberately strict — false-positive rate on
"V-bottom" detection is brutal. Better to miss some valid bounces than
fire on every random bounce.

This module is PURE — takes enriched OHLCV DataFrame, returns 0-100
score dict with side="LONG" or "NEUTRAL" (never SHORT — recovery
patterns are LONG-only by design).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Pattern 1: V-bottom capitulation bounce
# ---------------------------------------------------------------------------

def _v_bottom_bounce(df: pd.DataFrame,
                     drawdown_min: float = 0.12,
                     rsi_capitulation: float = 25.0,
                     vol_capitulation_mult: float = 1.8,
                     vol_drying_mult: float = 1.3,
                     min_recovery_pct: float = 0.02) -> dict:
    """Catch the FIRST 1-3 strong green candles after a capitulation low.

    The math:
      - drawdown_pct = 1 - (close / high_48bar)  → measures sell-off
      - rsi_capitulation = lowest RSI in last 12 bars  → captures fear
      - Strong green candle = current bar body >= 50% of range, green
      - vol_capitulation = max(vol_5bar_back) / vol_20avg >= 1.8x
      - vol_drying = mean(vol_last_5_bars) / vol_20avg <= 1.3x
      - recovery_from_low = (close - low_12bar) / low_12bar >= 2%
    """
    needed = ["close", "open", "high", "low", "volume", "rsi"]
    if any(c not in df.columns for c in needed) or len(df) < 60:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "V-bottom — insufficient data"}

    close = df["close"]
    open_ = df["open"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]
    rsi = df["rsi"]

    last_close = float(close.iloc[-1])
    last_open = float(open_.iloc[-1])
    last_high = float(high.iloc[-1])
    last_low = float(low.iloc[-1])
    last_vol = float(vol.iloc[-1])

    # 1. Drawdown check
    high_48 = float(high.tail(48).max())
    if high_48 <= 0:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "V-bottom — zero reference high"}
    drawdown_pct = 1.0 - (last_close / high_48)
    if drawdown_pct < drawdown_min:
        return {"score": 50, "side": "NEUTRAL",
                "detail": (f"V-bottom — drawdown {drawdown_pct * 100:.1f}% "
                           f"< {drawdown_min * 100:.0f}% threshold")}

    # 2. RSI capitulation within last 12 bars
    rsi_min_recent = float(rsi.tail(12).min())
    if rsi_min_recent > rsi_capitulation:
        return {"score": 50, "side": "NEUTRAL",
                "detail": (f"V-bottom — no capitulation "
                           f"(min RSI {rsi_min_recent:.0f} > {rsi_capitulation:.0f})")}

    # 3. Strong green candle check
    rng = last_high - last_low
    if rng <= 0:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "V-bottom — zero candle range"}
    body = last_close - last_open
    body_pct = body / rng
    is_strong_green = body > 0 and body_pct >= 0.50
    if not is_strong_green:
        return {"score": 50, "side": "NEUTRAL",
                "detail": (f"V-bottom — current candle weak "
                           f"(body {body_pct * 100:.0f}% of range)")}

    # 4. Volume capitulation (max in last 6-15 bars >= 1.8x avg)
    avg_vol_20 = float(vol.tail(20).mean())
    if avg_vol_20 <= 0:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "V-bottom — zero average volume"}
    # Look at bars 5-15 back for the capitulation spike
    cap_window = vol.iloc[-15:-5] if len(vol) >= 15 else vol.iloc[:-5]
    cap_window_max = float(cap_window.max()) if len(cap_window) > 0 else 0
    cap_vol_mult = cap_window_max / avg_vol_20
    if cap_vol_mult < vol_capitulation_mult:
        return {"score": 50, "side": "NEUTRAL",
                "detail": (f"V-bottom — no volume capitulation "
                           f"(max recent vol only {cap_vol_mult:.1f}x avg)")}

    # 5. Volume drying check (last 5 bars not spiking)
    last_5_vol = float(vol.tail(5).mean())
    drying_mult = last_5_vol / avg_vol_20
    # Note: drying check is "average not too elevated" — but the CURRENT
    # green bar itself may have above-average volume (that's the bounce).
    # We check the broader 5-bar mean to confirm the panic selling stopped.

    # 6. Recovery from recent low
    low_12 = float(low.tail(12).min())
    recovery_pct = (last_close - low_12) / low_12 if low_12 > 0 else 0
    if recovery_pct < min_recovery_pct:
        return {"score": 50, "side": "NEUTRAL",
                "detail": (f"V-bottom — not enough recovery "
                           f"({recovery_pct * 100:.1f}% off low)")}

    # All conditions met — score scaling by strength
    # Stronger when drawdown is larger, RSI was lower, vol spike was bigger
    dd_factor = min(1.0, (drawdown_pct - drawdown_min) / 0.15)  # 0..1
    rsi_factor = max(0.3, (rsi_capitulation - rsi_min_recent) / 25)
    vol_factor = min(1.0, (cap_vol_mult - vol_capitulation_mult) / 2.0)
    body_factor = min(1.0, (body_pct - 0.50) / 0.40)

    composite = (0.30 * dd_factor + 0.25 * rsi_factor
                 + 0.25 * vol_factor + 0.20 * body_factor)
    score = 70 + composite * 30
    score = float(np.clip(score, 70, 100))

    return {"score": round(score), "side": "LONG",
            "detail": (f"V-BOTTOM BOUNCE — drawdown {drawdown_pct * 100:.1f}% "
                       f"+ RSI bottomed at {rsi_min_recent:.0f} "
                       f"+ vol capit. {cap_vol_mult:.1f}x "
                       f"+ green body {body_pct * 100:.0f}% range "
                       f"+ {recovery_pct * 100:.1f}% off low")}


# ---------------------------------------------------------------------------
# Pattern 3: Volume shock reversal (extended decline → sudden reversal)
# ---------------------------------------------------------------------------

def _volume_shock_reversal(df: pd.DataFrame,
                           decline_min: float = 0.12,
                           decline_lookback: int = 72,
                           downtrend_lookback: int = 24,
                           downtrend_min_red_pct: float = 0.50,
                           body_min: float = 0.55,
                           vol_shock_mult: float = 3.5,
                           rsi_max_recent: float = 32.0,
                           rsi_lookback: int = 24) -> dict:
    """Catch the ROBO/NIL-style setup: long downtrend exhausting into a
    sudden reversal candle with massive volume spike.

    Different from v_bottom_bounce in TWO ways:
      1. Looks back FURTHER (96 bars vs 48) — catches multi-day drawdowns
         where the peak is too far back for v_bottom_bounce to see.
      2. Requires a SINGLE massive volume spike on the reversal candle
         (5x+ average) rather than a "capitulation cluster" 5-15 bars back.

    These two signals rarely co-fire because they catch different stages
    of different setup types.
    """
    needed = ["close", "open", "high", "low", "volume", "rsi",
              "ema_fast", "ema_slow"]
    if any(c not in df.columns for c in needed) or len(df) < decline_lookback + 5:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Volume shock — insufficient data"}

    close = df["close"]
    open_ = df["open"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]
    rsi = df["rsi"]
    ema_fast = df["ema_fast"]
    ema_slow = df["ema_slow"]

    last_close = float(close.iloc[-1])
    last_open = float(open_.iloc[-1])
    last_high = float(high.iloc[-1])
    last_low = float(low.iloc[-1])
    last_vol = float(vol.iloc[-1])

    # 1. Decline check — peak in last decline_lookback bars down to recent low
    high_long = float(high.tail(decline_lookback).max())
    low_recent = float(low.tail(decline_lookback // 4).min())
    if high_long <= 0:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Volume shock — zero reference high"}
    decline_pct = 1.0 - (low_recent / high_long)
    if decline_pct < decline_min:
        return {"score": 50, "side": "NEUTRAL",
                "detail": (f"Volume shock — decline only "
                           f"{decline_pct * 100:.1f}% (need ≥{decline_min * 100:.0f}%)")}

    # 2. Sustained downtrend over last downtrend_lookback bars
    trend_window = df.iloc[-downtrend_lookback - 1:-1]
    if len(trend_window) > 0:
        reds = int((trend_window["close"] < trend_window["open"]).sum())
        red_pct = reds / len(trend_window)
    else:
        red_pct = 0.0
    if red_pct < downtrend_min_red_pct:
        return {"score": 50, "side": "NEUTRAL",
                "detail": (f"Volume shock — only {red_pct * 100:.0f}% red bars "
                           f"in last {downtrend_lookback} (need ≥{downtrend_min_red_pct * 100:.0f}%)")}

    # 3. Current bar STRONG GREEN body
    rng = last_high - last_low
    if rng <= 0:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Volume shock — zero candle range"}
    body = last_close - last_open
    body_pct = body / rng
    if body <= 0 or body_pct < body_min:
        return {"score": 50, "side": "NEUTRAL",
                "detail": (f"Volume shock — current candle body too weak "
                           f"({body_pct * 100:.0f}% of range, need ≥{body_min * 100:.0f}%)")}

    # 4. Massive volume on the reversal candle
    avg_vol_20 = float(vol.tail(20).mean() or 1)
    if avg_vol_20 <= 0:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Volume shock — zero average volume"}
    vol_ratio = last_vol / avg_vol_20
    if vol_ratio < vol_shock_mult:
        return {"score": 50, "side": "NEUTRAL",
                "detail": (f"Volume shock — vol only {vol_ratio:.1f}x avg "
                           f"(need ≥{vol_shock_mult:.0f}x)")}

    # 5. RSI was oversold recently
    rsi_min = float(rsi.tail(rsi_lookback).min())
    if rsi_min > rsi_max_recent:
        return {"score": 50, "side": "NEUTRAL",
                "detail": (f"Volume shock — RSI never oversold "
                           f"(min {rsi_min:.0f}, need ≤{rsi_max_recent:.0f})")}

    # 6. Current bar reclaims AT LEAST ONE MA
    above_ema20 = last_close > float(ema_fast.iloc[-1])
    above_ema50 = last_close > float(ema_slow.iloc[-1])
    if not (above_ema20 or above_ema50):
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Volume shock — close below both MA20 and MA50"}

    # All conditions met — score scales with each factor's strength
    decline_factor = min(1.0, (decline_pct - decline_min) / 0.20)
    body_factor = min(1.0, (body_pct - body_min) / 0.30)
    vol_factor = min(1.0, (vol_ratio - vol_shock_mult) / 10.0)
    rsi_factor = max(0.3, (rsi_max_recent - rsi_min) / 25)
    ma_factor = 1.0 if (above_ema20 and above_ema50) else 0.7

    composite = (0.20 * decline_factor + 0.25 * body_factor
                 + 0.30 * vol_factor + 0.15 * rsi_factor
                 + 0.10 * ma_factor)
    score = 72 + composite * 28
    score = float(np.clip(score, 72, 100))

    return {"score": round(score), "side": "LONG",
            "detail": (f"VOLUME SHOCK REVERSAL — decline {decline_pct * 100:.0f}% "
                       f"over {decline_lookback}b + {red_pct * 100:.0f}% reds + "
                       f"green body {body_pct * 100:.0f}% range + "
                       f"vol {vol_ratio:.1f}x avg + RSI bottomed at {rsi_min:.0f}")}


# ---------------------------------------------------------------------------
# Pattern 2: Trend reclaim with momentum
# ---------------------------------------------------------------------------

def _trend_reclaim_momentum(df: pd.DataFrame,
                            below_min_bars: int = 5,
                            below_lookback: int = 8,
                            body_min: float = 0.40,
                            vol_mult: float = 1.5) -> dict:
    """Catch the slightly-later but cleaner entry: price reclaiming the
    MA50 with conviction after a confirmed downtrend.

    Notes:
      - We use ema_slow (50-period EMA) as the "MA50" proxy. The
        indicators.py module already maintains this — no extra
        computation.
      - The body strength check eliminates wick reclaims that don't
        actually break through.
    """
    needed = ["close", "open", "high", "low", "volume", "rsi", "ema_slow"]
    if any(c not in df.columns for c in needed) or len(df) < below_lookback + 5:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Trend reclaim — insufficient data"}

    close = df["close"]
    open_ = df["open"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]
    rsi = df["rsi"]
    ema50 = df["ema_slow"]

    # 1. Was price below EMA50 for below_min_bars of last below_lookback bars?
    recent_window = pd.DataFrame({"c": close.iloc[-below_lookback - 1:-1],
                                  "e": ema50.iloc[-below_lookback - 1:-1]})
    bars_below = int((recent_window["c"] < recent_window["e"]).sum())
    if bars_below < below_min_bars:
        return {"score": 50, "side": "NEUTRAL",
                "detail": (f"Reclaim — only {bars_below}/{below_lookback} "
                           f"prior bars were below MA50 (need >= {below_min_bars})")}

    # 2. Current bar closes ABOVE EMA50
    last_close = float(close.iloc[-1])
    last_ema = float(ema50.iloc[-1])
    if last_close <= last_ema:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Reclaim — current bar still below MA50"}

    # 3. Current bar body strength
    last_high = float(high.iloc[-1])
    last_low = float(low.iloc[-1])
    last_open = float(open_.iloc[-1])
    rng = last_high - last_low
    if rng <= 0:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Reclaim — zero range"}
    body = last_close - last_open
    body_pct = body / rng
    if body <= 0 or body_pct < body_min:
        return {"score": 50, "side": "NEUTRAL",
                "detail": (f"Reclaim — body too weak "
                           f"({body_pct * 100:.0f}% of range, need >= {body_min * 100:.0f}%)")}

    # 4. RSI crossed back above 50 in last 3 bars
    rsi_3back = rsi.tail(3).to_numpy()
    crossed_50 = False
    for i in range(1, len(rsi_3back)):
        if rsi_3back[i - 1] <= 50 < rsi_3back[i]:
            crossed_50 = True
            break
    if not crossed_50 and rsi_3back[-1] < 55:
        return {"score": 50, "side": "NEUTRAL",
                "detail": (f"Reclaim — RSI not confirming "
                           f"(last {rsi_3back[-1]:.0f}, no cross above 50 in 3 bars)")}

    # 5. Volume confirmation
    avg_vol_20 = float(vol.tail(20).mean() or 1)
    last_vol = float(vol.iloc[-1])
    vol_ratio = last_vol / avg_vol_20
    if vol_ratio < vol_mult:
        return {"score": 50, "side": "NEUTRAL",
                "detail": (f"Reclaim — volume light "
                           f"({vol_ratio:.1f}x avg, need >= {vol_mult:.1f}x)")}

    # All conditions met — score
    above_pct = (last_close - last_ema) / last_ema if last_ema > 0 else 0
    above_factor = min(1.0, above_pct / 0.03)  # cap 3% above
    body_factor = min(1.0, (body_pct - body_min) / 0.40)
    vol_factor = min(1.0, (vol_ratio - vol_mult) / 1.5)
    bars_below_factor = min(1.0, bars_below / below_lookback)

    composite = (0.25 * above_factor + 0.30 * body_factor
                 + 0.25 * vol_factor + 0.20 * bars_below_factor)
    score = 70 + composite * 25
    score = float(np.clip(score, 70, 95))

    return {"score": round(score), "side": "LONG",
            "detail": (f"MA50 RECLAIM — was below {bars_below}/{below_lookback} "
                       f"bars · close +{above_pct * 100:.2f}% above · "
                       f"body {body_pct * 100:.0f}% range · "
                       f"vol {vol_ratio:.1f}x · RSI {rsi_3back[-1]:.0f}")}


# ---------------------------------------------------------------------------
# Composite — take the BEST pattern (recovery is "any one fires" by design)
# ---------------------------------------------------------------------------

def score(df: pd.DataFrame) -> dict:
    """Composite recovery score 0-100.

    Backtest verdict (2026-05-29):
      v_bottom_bounce: n=4 fires, 75% win, +2.26% avg over 12 bars
                       vs baseline 48% / +0.10% — REAL EDGE on the
                       rare-fire side. Sample tiny but math sound:
                       the pattern requires capitulation conditions
                       that only appear during sharp corrections.
      trend_reclaim:   n=42 fires, 42.9% win, -0.51% avg — NO EDGE.
                       Dropped from composite. Function preserved for
                       future redesign — current logic over-fires on
                       weak reclaims that fail to sustain.

    Composite uses v_bottom_bounce as the sole edge component. When
    trend_reclaim also fires alongside, it acts as a confirmation
    chip but doesn't boost score.

    Returns:
      score >= 75: STRONG V-bottom catch — high conviction LONG
      70-74: VALID V-bottom but borderline
      < 70: no recovery setup
    """
    if df is None or len(df) < 60:
        return _empty(reason="not enough klines")

    # --- 24h freshness filter -------------------------------------------
    # If the coin is already +8% or more in the last 24 hours, the move
    # is mostly DONE — we want EARLY catches, not chases. Mark as
    # "extended" and skip firing the signal. No lookahead: we compare
    # close[t] vs close[t-24], both past data.
    pct_24h = 0.0
    if len(df) > 25:
        close_now = float(df["close"].iloc[-1])
        close_24h_ago = float(df["close"].iloc[-25])
        if close_24h_ago > 0:
            pct_24h = (close_now / close_24h_ago - 1.0) * 100
    extended_already = pct_24h >= 8.0

    p1 = _v_bottom_bounce(df)
    p2 = _trend_reclaim_momentum(df)
    p3 = _volume_shock_reversal(df)

    components = {
        "v_bottom_bounce":     p1,
        "trend_reclaim":       p2,
        "volume_shock":        p3,
    }

    # ONLY v_bottom_bounce contributes to the composite score. p2 and p3
    # are both kept as functions for diagnostic display but excluded
    # from scoring per backtest verdicts:
    #   trend_reclaim:  n=42, win 42.9%, avg -0.51% → no edge
    #   volume_shock:   n=3,  win 33.3%, avg -1.16% → anti-edge, even
    #                   after parameter relaxation. Tried decline 12%/72b,
    #                   vol_mult 3.5x, body 55%, rsi 32 — still 2 of 3
    #                   fires LOST. The ROBO/NIL-style examples don't
    #                   generalize across the top-20 universe over 6 weeks.
    #                   Keeping the function for future re-design.
    final_score = p1["score"]
    if p1["score"] >= 70:
        pattern_label = "v_bottom_bounce"
    else:
        pattern_label = "no_recovery"

    # Apply 24h freshness filter — if already extended, DON'T fire even
    # if patterns met. Drops the composite below the chip threshold so
    # the picks board doesn't surface a stale signal.
    if extended_already and final_score >= 70:
        final_score = min(final_score, 65)  # below chip threshold
        pattern_label = f"{pattern_label}_extended_skip"

    flags = []
    if "V-BOTTOM BOUNCE" in p1["detail"]:
        flags.append("v_bottom_bounce")
    if "MA50 RECLAIM" in p2["detail"]:
        flags.append("ma50_reclaim_diagnostic")  # diagnostic only — no score
    if "VOLUME SHOCK REVERSAL" in p3["detail"]:
        flags.append("volume_shock_diagnostic")  # diagnostic only — no score
    if extended_already:
        flags.append("extended_24h")

    return {
        "score": round(float(final_score), 1),
        "side": winning["side"] if final_score >= 70 else "NEUTRAL",
        "pattern": pattern_label,
        "pct_24h": round(pct_24h, 2),
        "extended_already": extended_already,
        "components": components,
        "flags": flags,
    }


def _empty(reason: str) -> dict:
    return {
        "score": 50.0,
        "side": "NEUTRAL",
        "pattern": "no_data",
        "pct_24h": 0.0,
        "extended_already": False,
        "components": {
            "v_bottom_bounce": {"score": 50, "side": "NEUTRAL", "detail": reason},
            "trend_reclaim":   {"score": 50, "side": "NEUTRAL", "detail": reason},
            "volume_shock":    {"score": 50, "side": "NEUTRAL", "detail": reason},
        },
        "flags": [],
    }
