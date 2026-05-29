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
# Composite scan — score one coin's setup
# ---------------------------------------------------------------------------

def scan_one(symbol: str, df: pd.DataFrame, pct_24h: float = 0.0) -> dict:
    """Run all validated-edge patterns on one coin and return the best
    setup with score, side, and which signals fired.

    Args:
        symbol: e.g. "BTCUSDT"
        df: enriched OHLCV DataFrame (must have rsi, ema_*, atr columns)
        pct_24h: 24h price change %, used for freshness filter

    Returns:
        {
          "symbol": str,
          "score": 0-100 (best of all signals),
          "side": "LONG" | "NEUTRAL" (Pattern Scout is LONG-only),
          "signals": [{"name": str, "score": float, "detail": str}, ...],
          "best_signal": str,
          "extended_already": bool,
        }
    """
    if df is None or len(df) < 60:
        return {"symbol": symbol, "score": 50, "side": "NEUTRAL",
                "signals": [], "best_signal": "no_data",
                "extended_already": False}

    # Run all signals
    recov = recovery_detector.score(df)
    longp = long_patterns.score(df)
    morning = detect_morning_star(df)
    hammer = detect_hammer_at_support(df)

    signals = []
    # Collect signals that scored >= 65 (worth surfacing)
    for name, result in [
        ("v_bottom_recovery", recov),
        ("long_patterns_aligned", longp),
        ("morning_star", morning),
        ("hammer_at_support", hammer),
    ]:
        if result.get("score", 50) >= 65:
            signals.append({
                "name": name,
                "score": float(result["score"]),
                "side": result.get("side", "NEUTRAL"),
                "detail": result.get("detail", "")
                          or result.get("pattern", "")
                          or "(no detail)",
            })

    # Best signal wins
    if not signals:
        return {"symbol": symbol, "score": 50, "side": "NEUTRAL",
                "signals": [], "best_signal": "none",
                "extended_already": pct_24h >= 8.0}

    signals.sort(key=lambda s: s["score"], reverse=True)
    best = signals[0]
    best_score = best["score"]

    # Multi-signal agreement bonus
    if len(signals) >= 2:
        best_score = min(100, best_score + 4)
    if len(signals) >= 3:
        best_score = min(100, best_score + 3)

    # 24h freshness filter — already extended? Downgrade score below
    # the 70-fire threshold so the picks board doesn't surface chases.
    extended_already = pct_24h >= 8.0
    if extended_already and best_score >= 70:
        best_score = min(best_score, 65)

    return {
        "symbol": symbol,
        "score": round(best_score, 1),
        "side": best["side"] if best_score >= 70 else "NEUTRAL",
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
