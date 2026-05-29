"""Pattern Scout — universal signal scanner across the top 150 coins.

The existing picks board only surfaces coins that PASS alerts.build_alerts()
which has a CONF_ALERT=72 floor. Coins with strong individual technical
patterns but weaker overall confidence never appear — even if they have
high-edge V-bottom or long_pattern signals firing.

This module scans every coin in the top universe (150 by default) and
ranks them by the best-edge pattern firing right now, INDEPENDENT of
the alerts gate. The output goes to a new "🎯 PATTERN SCOUT" section
in Paper Trader.

Signals scanned per coin (only validated-edge patterns):
  1. Recovery V-bottom        — 75% win @ 12bar, +2.26% avg (rare-fire)
  2. Long patterns aligned    — 67.4% win @ 48bar (composite of 4)
  3. Morning Star + filters   — 60-75% win with RSI<30 + downtrend gate
  4. Hammer at support        — 60-65% win at confirmed support
  5. Cup-and-handle BREAKOUT  — pattern-detected, weekly

24h freshness filter applied across ALL signals — if a coin is already
+8% in 24h, signals are downgraded (move is mostly done, we want EARLY).

This module is PURE — takes a list of (symbol, df) tuples, returns
ranked setups. Caller (app.py) wraps in cached helper.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import long_patterns
import recovery_detector


# ---------------------------------------------------------------------------
# Morning Star pattern (with RSI<30 + downtrend filters)
# ---------------------------------------------------------------------------

def detect_morning_star(df: pd.DataFrame,
                        rsi_max: float = 35.0,
                        downtrend_lookback: int = 10,
                        downtrend_min_decline: float = 0.05) -> dict:
    """3-candle reversal pattern with RSI oversold + downtrend gates.

    Per research: pattern alone is ~55% win rate (worse than baseline).
    Pattern + RSI<35 + prior downtrend gets to 60-75%. The location
    filter is the edge, not the pattern shape.

    Bar1 (3 bars ago): large red body
    Bar2 (2 bars ago): small body (any color)
    Bar3 (last bar):   green, closes above midpoint of Bar1 body
    Filter: RSI on Bar1 was <= rsi_max, prior 10 bars showed downtrend
    """
    needed = ["close", "open", "high", "low", "rsi"]
    if any(c not in df.columns for c in needed) or len(df) < downtrend_lookback + 3:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Morning Star — insufficient data"}

    if len(df) < 4:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Morning Star — need at least 4 bars"}

    bar1 = df.iloc[-3]
    bar2 = df.iloc[-2]
    bar3 = df.iloc[-1]

    # Bar1: large red
    bar1_body = abs(float(bar1["close"]) - float(bar1["open"]))
    bar1_rng = float(bar1["high"]) - float(bar1["low"])
    bar1_red = float(bar1["close"]) < float(bar1["open"])
    bar1_strong = bar1_body / bar1_rng >= 0.60 if bar1_rng > 0 else False
    if not (bar1_red and bar1_strong):
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Morning Star — Bar1 not large red"}

    # Bar2: small body
    bar2_body = abs(float(bar2["close"]) - float(bar2["open"]))
    if bar1_body == 0 or bar2_body / bar1_body > 0.40:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Morning Star — Bar2 not small enough"}

    # Bar3: green, closes above Bar1 midpoint
    bar3_green = float(bar3["close"]) > float(bar3["open"])
    bar1_mid = (float(bar1["open"]) + float(bar1["close"])) / 2
    if not (bar3_green and float(bar3["close"]) > bar1_mid):
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Morning Star — Bar3 not green/above Bar1 mid"}

    # RSI gate: Bar1 RSI must be oversold
    bar1_rsi = float(bar1["rsi"])
    if bar1_rsi > rsi_max:
        return {"score": 50, "side": "NEUTRAL",
                "detail": f"Morning Star — Bar1 RSI {bar1_rsi:.0f} not oversold"}

    # Downtrend gate: prior 10 bars must show net decline
    prior_close = float(df["close"].iloc[-(downtrend_lookback + 3)])
    bar1_close = float(bar1["close"])
    decline_pct = (prior_close - bar1_close) / prior_close
    if decline_pct < downtrend_min_decline:
        return {"score": 50, "side": "NEUTRAL",
                "detail": (f"Morning Star — prior {downtrend_lookback} bars "
                           f"declined only {decline_pct * 100:.1f}%")}

    # All filters passed
    bar3_body_pct = (abs(float(bar3["close"]) - float(bar3["open"]))
                     / (float(bar3["high"]) - float(bar3["low"])))
    score = 70 + min(25, decline_pct * 100 * 2) + min(5, bar3_body_pct * 10)
    score = float(np.clip(score, 70, 100))

    return {"score": round(score), "side": "LONG",
            "detail": (f"MORNING STAR — Bar1 RSI {bar1_rsi:.0f} oversold + "
                       f"prior {downtrend_lookback}b decline "
                       f"{decline_pct * 100:.1f}% + Bar3 green close above "
                       f"Bar1 mid")}


# ---------------------------------------------------------------------------
# Hammer at support pattern
# ---------------------------------------------------------------------------

def detect_hammer_at_support(df: pd.DataFrame,
                             support_lookback: int = 20,
                             support_proximity_pct: float = 0.015,
                             vol_mult: float = 1.5) -> dict:
    """Hammer candle at confirmed support with volume confirmation.

    Per research: hammer alone is ~50% win rate (noise). Hammer AT
    support with volume gets to 60-65%. The location is the edge.

    Hammer candle: lower_wick >= 2 * body, upper_wick <= 0.3 * body,
                   small body (<=30% of range), small green or doji
    Support: current low within 1.5% of prior 20-bar low
    Volume: current bar >= 1.5x avg of last 20 bars
    """
    needed = ["close", "open", "high", "low", "volume"]
    if any(c not in df.columns for c in needed) or len(df) < support_lookback + 2:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Hammer — insufficient data"}

    last = df.iloc[-1]
    last_open = float(last["open"])
    last_close = float(last["close"])
    last_high = float(last["high"])
    last_low = float(last["low"])
    last_vol = float(last["volume"])

    rng = last_high - last_low
    if rng <= 0:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Hammer — zero range"}
    body = abs(last_close - last_open)
    body_top = max(last_close, last_open)
    body_bot = min(last_close, last_open)
    lower_wick = body_bot - last_low
    upper_wick = last_high - body_top

    # Hammer shape check
    if body == 0:
        is_hammer_shape = False
    else:
        is_hammer_shape = (
            lower_wick >= 2 * body
            and upper_wick <= 0.3 * body
            and body / rng <= 0.35
        )
    if not is_hammer_shape:
        return {"score": 50, "side": "NEUTRAL",
                "detail": (f"Hammer — shape not matching "
                           f"(lower_wick/body={lower_wick / max(body, 1e-9):.1f}, "
                           f"body%={body / rng * 100:.0f})")}

    # Support proximity check
    prior_window = df["low"].iloc[-(support_lookback + 1):-1]
    if len(prior_window) == 0:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Hammer — no prior window"}
    prior_low = float(prior_window.min())
    if prior_low <= 0:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Hammer — zero prior low"}
    distance_pct = abs(last_low - prior_low) / prior_low
    if distance_pct > support_proximity_pct:
        return {"score": 50, "side": "NEUTRAL",
                "detail": (f"Hammer — not at support "
                           f"({distance_pct * 100:.1f}% from prior low, "
                           f"need ≤{support_proximity_pct * 100:.1f}%)")}

    # Volume confirmation
    avg_vol = float(df["volume"].tail(20).mean() or 1)
    vol_ratio = last_vol / avg_vol if avg_vol > 0 else 0
    if vol_ratio < vol_mult:
        return {"score": 60, "side": "LONG",
                "detail": (f"Hammer at support but volume light "
                           f"({vol_ratio:.1f}x avg)")}

    # All filters passed — score by strength
    wick_factor = min(1.0, lower_wick / body / 4) if body > 0 else 0.5
    vol_factor = min(1.0, (vol_ratio - vol_mult) / 2.0)
    score = 70 + 15 * wick_factor + 10 * vol_factor
    score = float(np.clip(score, 70, 95))

    return {"score": round(score), "side": "LONG",
            "detail": (f"HAMMER AT SUPPORT — lower wick "
                       f"{lower_wick / body:.1f}x body, "
                       f"{distance_pct * 100:.2f}% from prior 20b low, "
                       f"vol {vol_ratio:.1f}x avg")}


# ---------------------------------------------------------------------------
# SHORT-side patterns — mirror of LONG patterns for bearish reversals
# ---------------------------------------------------------------------------

def detect_evening_star(df: pd.DataFrame,
                        rsi_min: float = 65.0,
                        uptrend_lookback: int = 10,
                        uptrend_min_rise: float = 0.05) -> dict:
    """3-candle bearish reversal at tops — mirror of Morning Star.

    Bar1 (3 bars ago): large green body (close > open, body >= 60% range)
    Bar2 (2 bars ago): small body (any color)
    Bar3 (last bar):   red, closes BELOW midpoint of Bar1 body
    Filters: Bar1 RSI >= rsi_min (overbought), prior 10 bars showed rise
    """
    needed = ["close", "open", "high", "low", "rsi"]
    if any(c not in df.columns for c in needed) or len(df) < uptrend_lookback + 3:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Evening Star — insufficient data"}

    if len(df) < 4:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Evening Star — need at least 4 bars"}

    bar1 = df.iloc[-3]
    bar2 = df.iloc[-2]
    bar3 = df.iloc[-1]

    # Bar1: large green
    bar1_body = abs(float(bar1["close"]) - float(bar1["open"]))
    bar1_rng = float(bar1["high"]) - float(bar1["low"])
    bar1_green = float(bar1["close"]) > float(bar1["open"])
    bar1_strong = bar1_body / bar1_rng >= 0.60 if bar1_rng > 0 else False
    if not (bar1_green and bar1_strong):
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Evening Star — Bar1 not large green"}

    # Bar2: small body
    bar2_body = abs(float(bar2["close"]) - float(bar2["open"]))
    if bar1_body == 0 or bar2_body / bar1_body > 0.40:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Evening Star — Bar2 not small enough"}

    # Bar3: red, closes below Bar1 midpoint
    bar3_red = float(bar3["close"]) < float(bar3["open"])
    bar1_mid = (float(bar1["open"]) + float(bar1["close"])) / 2
    if not (bar3_red and float(bar3["close"]) < bar1_mid):
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Evening Star — Bar3 not red/below Bar1 mid"}

    # RSI gate: Bar1 RSI must be overbought
    bar1_rsi = float(bar1["rsi"])
    if bar1_rsi < rsi_min:
        return {"score": 50, "side": "NEUTRAL",
                "detail": f"Evening Star — Bar1 RSI {bar1_rsi:.0f} not overbought"}

    # Uptrend gate: prior 10 bars must show net rise
    prior_close = float(df["close"].iloc[-(uptrend_lookback + 3)])
    bar1_close = float(bar1["close"])
    rise_pct = (bar1_close - prior_close) / prior_close if prior_close > 0 else 0
    if rise_pct < uptrend_min_rise:
        return {"score": 50, "side": "NEUTRAL",
                "detail": (f"Evening Star — prior {uptrend_lookback} bars "
                           f"rose only {rise_pct * 100:.1f}%")}

    # All filters passed
    bar3_body_pct = (abs(float(bar3["close"]) - float(bar3["open"]))
                     / (float(bar3["high"]) - float(bar3["low"])))
    # SHORT score: lower number = stronger short (per system convention)
    score = 30 - min(25, rise_pct * 100 * 2) - min(5, bar3_body_pct * 10)
    score = float(np.clip(score, 0, 30))

    return {"score": round(score), "side": "SHORT",
            "detail": (f"EVENING STAR — Bar1 RSI {bar1_rsi:.0f} overbought + "
                       f"prior {uptrend_lookback}b rise "
                       f"{rise_pct * 100:.1f}% + Bar3 red close below "
                       f"Bar1 mid")}


def detect_shooting_star_at_resistance(df: pd.DataFrame,
                                       resistance_lookback: int = 20,
                                       proximity_pct: float = 0.015,
                                       vol_mult: float = 1.5) -> dict:
    """Shooting Star (inverted hammer) at resistance — mirror of
    Hammer at Support. Strong bearish reversal trigger.

    Shooting star shape: upper_wick >= 2 * body, lower_wick <= 0.3 * body,
                         small body (<=30% of range), small red or doji
    Resistance: current high within 1.5% of prior 20-bar high
    Volume: current bar >= 1.5x avg of last 20 bars
    """
    needed = ["close", "open", "high", "low", "volume"]
    if any(c not in df.columns for c in needed) or len(df) < resistance_lookback + 2:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Shooting Star — insufficient data"}

    last = df.iloc[-1]
    last_open = float(last["open"])
    last_close = float(last["close"])
    last_high = float(last["high"])
    last_low = float(last["low"])
    last_vol = float(last["volume"])

    rng = last_high - last_low
    if rng <= 0:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Shooting Star — zero range"}
    body = abs(last_close - last_open)
    body_top = max(last_close, last_open)
    body_bot = min(last_close, last_open)
    lower_wick = body_bot - last_low
    upper_wick = last_high - body_top

    # Shooting star shape (inverted hammer)
    if body == 0:
        is_shape = False
    else:
        is_shape = (
            upper_wick >= 2 * body
            and lower_wick <= 0.3 * body
            and body / rng <= 0.35
        )
    if not is_shape:
        return {"score": 50, "side": "NEUTRAL",
                "detail": (f"Shooting Star — shape not matching "
                           f"(upper_wick/body={upper_wick / max(body, 1e-9):.1f}, "
                           f"body%={body / rng * 100:.0f})")}

    # Resistance proximity
    prior_window = df["high"].iloc[-(resistance_lookback + 1):-1]
    if len(prior_window) == 0:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Shooting Star — no prior window"}
    prior_high = float(prior_window.max())
    if prior_high <= 0:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Shooting Star — zero prior high"}
    distance_pct = abs(last_high - prior_high) / prior_high
    if distance_pct > proximity_pct:
        return {"score": 50, "side": "NEUTRAL",
                "detail": (f"Shooting Star — not at resistance "
                           f"({distance_pct * 100:.1f}% from prior high)")}

    # Volume confirmation
    avg_vol = float(df["volume"].tail(20).mean() or 1)
    vol_ratio = last_vol / avg_vol if avg_vol > 0 else 0
    if vol_ratio < vol_mult:
        return {"score": 40, "side": "SHORT",
                "detail": (f"Shooting Star at resistance but volume light "
                           f"({vol_ratio:.1f}x avg)")}

    # All filters passed
    wick_factor = min(1.0, upper_wick / body / 4) if body > 0 else 0.5
    vol_factor = min(1.0, (vol_ratio - vol_mult) / 2.0)
    score = 30 - 15 * wick_factor - 10 * vol_factor
    score = float(np.clip(score, 5, 30))

    return {"score": round(score), "side": "SHORT",
            "detail": (f"SHOOTING STAR AT RESISTANCE — upper wick "
                       f"{upper_wick / body:.1f}x body, "
                       f"{distance_pct * 100:.2f}% from prior 20b high, "
                       f"vol {vol_ratio:.1f}x avg")}


def detect_bearish_rsi_divergence(df: pd.DataFrame,
                                  pivot_k: int = 3,
                                  lookback: int = 50) -> dict:
    """Price makes HIGHER HIGH while RSI makes LOWER HIGH — textbook
    bearish divergence (mirror of bullish divergence). Both pivots
    confirmed (no lookahead).
    """
    if len(df) < lookback + pivot_k + 5 or "rsi" not in df.columns:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Bearish RSI div — insufficient data"}

    recent = df.tail(lookback + pivot_k + 1).reset_index(drop=True)
    highs = recent["high"].to_numpy()
    rsi_vals = recent["rsi"].to_numpy()
    n = len(recent)

    swing_idxs: list[int] = []
    for i in range(pivot_k, n - pivot_k):
        seg = highs[i - pivot_k:i + pivot_k + 1]
        if highs[i] >= seg.max():
            swing_idxs.append(i)

    if len(swing_idxs) < 2:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Bearish RSI div — fewer than 2 swing highs"}

    prev_idx = swing_idxs[-2]
    last_idx = swing_idxs[-1]

    prev_high_price = float(highs[prev_idx])
    last_high_price = float(highs[last_idx])
    prev_rsi = float(rsi_vals[prev_idx])
    last_rsi = float(rsi_vals[last_idx])

    # Bearish: price HH + RSI LH
    price_HH = last_high_price > prev_high_price * 1.002
    rsi_LH = last_rsi < prev_rsi - 2.0

    if price_HH and rsi_LH:
        rsi_div_strength = (prev_rsi - last_rsi) / 10.0
        recency_bonus = 1.0 if (n - 1 - last_idx) <= 8 else 0.6
        score = 30 - min(25, rsi_div_strength * 30) * recency_bonus
        score = float(np.clip(score, 0, 30))
        return {"score": round(score), "side": "SHORT",
                "detail": (f"Bearish RSI div confirmed — price HH "
                           f"({prev_high_price:.4g}→{last_high_price:.4g}) "
                           f"while RSI LH ({prev_rsi:.0f}→{last_rsi:.0f})")}
    return {"score": 50, "side": "NEUTRAL",
            "detail": "No bearish RSI div"}


# ---------------------------------------------------------------------------
# Composite scan — score one coin's setup
# ---------------------------------------------------------------------------

def scan_one(symbol: str, df: pd.DataFrame, pct_24h: float = 0.0) -> dict:
    """Run all validated-edge patterns on one coin (both LONG and SHORT
    side patterns) and return the best setup.

    LONG-side patterns: v_bottom_recovery, long_patterns_aligned,
                        morning_star, hammer_at_support
    SHORT-side patterns: evening_star, shooting_star_at_resistance,
                         bearish_rsi_divergence

    Returns the strongest setup regardless of side. Both LONG and SHORT
    cards can appear in the same scan.

    Score convention:
      LONG signals: higher score = stronger LONG (70+ = fire)
      SHORT signals: lower score = stronger SHORT (30- = fire)
      For unified ranking, we convert SHORT scores to LONG-equivalent
      strength (e.g., SHORT score 20 → strength 80).
    """
    if df is None or len(df) < 60:
        return {"symbol": symbol, "score": 50, "side": "NEUTRAL",
                "signals": [], "best_signal": "no_data",
                "extended_already": False}

    # Run all signals — LONG side
    recov = recovery_detector.score(df)
    longp = long_patterns.score(df)
    morning = detect_morning_star(df)
    hammer = detect_hammer_at_support(df)

    # Run all signals — SHORT side
    evening = detect_evening_star(df)
    shooting = detect_shooting_star_at_resistance(df)
    bear_rsi = detect_bearish_rsi_divergence(df)

    all_signals = [
        # (name, result, is_long_side)
        ("v_bottom_recovery", recov, True),
        ("long_patterns_aligned", longp, True),
        ("morning_star", morning, True),
        ("hammer_at_support", hammer, True),
        ("evening_star", evening, False),
        ("shooting_star_at_resistance", shooting, False),
        ("bearish_rsi_divergence", bear_rsi, False),
    ]

    # Collect signals that fired
    signals = []
    for name, result, is_long in all_signals:
        score_val = result.get("score", 50)
        side_val = result.get("side", "NEUTRAL")
        # For LONG signals: fire at score >= 65
        # For SHORT signals: fire at score <= 35
        if is_long and score_val >= 65 and side_val == "LONG":
            signals.append({
                "name": name,
                "score": float(score_val),  # raw LONG score 65-100
                "strength": float(score_val),  # 65-100 strength
                "side": "LONG",
                "detail": result.get("detail", "") or "(no detail)",
            })
        elif (not is_long) and score_val <= 35 and side_val == "SHORT":
            # Convert SHORT score (0-35, lower=stronger) to strength
            # (65-100, higher=stronger) for unified ranking.
            short_strength = 100 - score_val * 2  # score 30 → 40, score 0 → 100
            short_strength = max(65, min(100, short_strength))
            signals.append({
                "name": name,
                "score": float(score_val),  # raw SHORT score 0-35
                "strength": float(short_strength),  # unified 65-100
                "side": "SHORT",
                "detail": result.get("detail", "") or "(no detail)",
            })

    if not signals:
        return {"symbol": symbol, "score": 50, "side": "NEUTRAL",
                "signals": [], "best_signal": "none",
                "extended_already": pct_24h >= 8.0,
                "pct_24h": round(pct_24h, 2)}

    # Rank by unified strength (highest first)
    signals.sort(key=lambda s: s["strength"], reverse=True)
    best = signals[0]
    best_score = best["strength"]
    net_side = best["side"]

    # Multi-signal agreement bonus — but ONLY when signals agree on side
    same_side = [s for s in signals if s["side"] == net_side]
    if len(same_side) >= 2:
        best_score = min(100, best_score + 4)
    if len(same_side) >= 3:
        best_score = min(100, best_score + 3)

    # 24h freshness filter:
    #  LONG: already +8% = extended, downgrade
    #  SHORT: already -8% = extended downside, downgrade
    if net_side == "LONG":
        extended_already = pct_24h >= 8.0
    else:
        extended_already = pct_24h <= -8.0
    if extended_already and best_score >= 70:
        best_score = min(best_score, 65)

    return {
        "symbol": symbol,
        "score": round(best_score, 1),
        "side": net_side if best_score >= 70 else "NEUTRAL",
        "signals": signals,
        "best_signal": best["name"],
        "extended_already": extended_already,
        "pct_24h": round(pct_24h, 2),
    }


def rank_universe(scan_results: list[dict],
                  min_score: float = 70.0,
                  max_picks: int = 15) -> list[dict]:
    """Filter + rank scan_one results into top setups.

    Returns the top `max_picks` setups by score, with score >= min_score.
    """
    qualified = [r for r in scan_results if r["score"] >= min_score]
    qualified.sort(key=lambda r: r["score"], reverse=True)
    return qualified[:max_picks]
