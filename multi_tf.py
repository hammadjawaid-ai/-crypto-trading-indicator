"""Multi-timeframe trend alignment + entry timing.

Used as a TIERED GATE in the quality filter (Fix #1, 2026-06-06).

  3/3 on 15m + 1h + 4h    → MAX tier eligible (best)
  2/3 on 15m + 1h + 4h    → HIGH tier (good)
  1/3 on 15m + 1h + 4h    → needs combined score >= 85 to pass
  0/3 on any TF           → reject (fighting the tape)

3m timeframe is checked ONLY for HERO CARD entry timing (Fix #2) —
NOT used in the multi-TF gate because 3m is too noisy to require
alignment with 4h (a clean trend would still oscillate every few
minutes on 3m and almost never align).

Trend state per TF is classified by EMA20 + EMA50 position + recent
slope. BULL = above both EMAs with EMA20 rising. BEAR = below both
with EMA20 falling. NEUTRAL = mixed/sideways.
"""
from __future__ import annotations

import time
import pandas as pd

import binance_client


# ---------------------------------------------------------------------------
# Module-level cache — keyed by (symbol, tf). TTL 3 min per entry.
# Trend states change slowly; refetching every scan is wasteful.
# ---------------------------------------------------------------------------
_TREND_CACHE: dict = {}
_TREND_CACHE_TTL = 180  # 3 min


def _cached_trend(symbol: str, tf: str, limit: int = 100) -> str:
    """Trend state for a single symbol/TF with cache."""
    now = time.time()
    key = (symbol, tf)
    entry = _TREND_CACHE.get(key)
    if entry and (now - entry["ts"]) < _TREND_CACHE_TTL:
        return entry["state"]
    try:
        df = binance_client.get_klines(symbol, tf, limit=limit)
        state = _trend_state(df)
    except Exception:
        state = "UNKNOWN"
    _TREND_CACHE[key] = {"ts": now, "state": state}
    return state


def _trend_state(df: pd.DataFrame) -> str:
    """Classify trend as BULL/BEAR/NEUTRAL using EMA20 + EMA50 + slope.

    Rules:
      BULL: close > EMA20 > EMA50 AND EMA20 rising over last 10 bars
      BEAR: close < EMA20 < EMA50 AND EMA20 falling over last 10 bars
      Mixed: fall back to EMA20 slope (>0.5% over 10 bars = BULL,
             <-0.5% = BEAR, else NEUTRAL)
    """
    if df is None or len(df) < 50:
        return "NEUTRAL"
    close = df["close"]
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    c = float(close.iloc[-1])
    e20 = float(ema20.iloc[-1])
    e50 = float(ema50.iloc[-1])
    # Slope over last 10 bars
    if len(ema20) >= 10 and ema20.iloc[-10] > 0:
        slope_20 = (e20 - float(ema20.iloc[-10])) / float(ema20.iloc[-10])
    else:
        slope_20 = 0.0
    # Clean stacks
    if c > e20 > e50 and slope_20 > 0:
        return "BULL"
    if c < e20 < e50 and slope_20 < 0:
        return "BEAR"
    # Mixed — fall back to slope
    if slope_20 > 0.005:
        return "BULL"
    if slope_20 < -0.005:
        return "BEAR"
    return "NEUTRAL"


def get_multi_tf_alignment(symbol: str, side: str) -> dict:
    """Multi-TF alignment count for a pick on 15m + 1h + 4h.

    LONG: count TFs in BULL state
    SHORT: count TFs in BEAR state
    NEUTRAL on a TF doesn't count toward alignment but doesn't reject

    Returns:
        {
            "aligned": 0-3,           how many TFs are in pick direction
            "against": 0-3,           how many TFs are in OPPOSITE direction
            "tfs": {"15m": "BULL", ...},  per-TF state
            "side": "LONG"|"SHORT",
            "summary": "15m BULL · 1h BULL · 4h NEUTRAL",
        }
    """
    side = (side or "").upper()
    target = "BULL" if side == "LONG" else "BEAR"
    opposite = "BEAR" if side == "LONG" else "BULL"

    tfs = {}
    for tf in ("15m", "1h", "4h"):
        tfs[tf] = _cached_trend(symbol, tf, limit=100)

    aligned = sum(1 for s in tfs.values() if s == target)
    against = sum(1 for s in tfs.values() if s == opposite)
    summary = " · ".join(f"{tf} {state}" for tf, state in tfs.items())

    return {
        "aligned": aligned,
        "against": against,
        "tfs": tfs,
        "side": side,
        "target_state": target,
        "summary": summary,
    }


def get_3m_entry_signal(symbol: str, side: str) -> dict:
    """Check if 3m momentum supports immediate entry.

    Used for HERO CARD ULTRA filter — confirms NOW is a good moment
    to click open. Not a heavy trend check, just "are the last few
    3m candles supporting this direction RIGHT NOW?"

    Returns:
        {
            "supports": bool,  True if entry NOW is supported
            "reason": str,     short human-readable reason
            "change_15m_pct": float,  last 15min change % on 3m candles
        }
    """
    side = (side or "").upper()
    try:
        df = binance_client.get_klines(symbol, "3m", limit=30)
        if df is None or len(df) < 20:
            return {"supports": False, "reason": "no 3m data",
                    "change_15m_pct": 0.0}
    except Exception as exc:
        return {"supports": False, "reason": f"fetch failed: {exc}",
                "change_15m_pct": 0.0}

    close = df["close"]
    c = float(close.iloc[-1])
    # 8-period EMA on 3m (24 min)
    ema8 = close.ewm(span=8, adjust=False).mean()
    e8 = float(ema8.iloc[-1])
    # Last 5 candles = 15 min of micro-price-action
    if len(close) >= 6:
        change_15m = (c / float(close.iloc[-6]) - 1.0) * 100
    else:
        change_15m = 0.0
    # Last candle direction
    last_change = (c / float(close.iloc[-2]) - 1.0) * 100 \
        if len(close) >= 2 and float(close.iloc[-2]) > 0 else 0

    if side == "LONG":
        # Want: close above 3m EMA8, recent 15m not crashing
        if c > e8 and change_15m > -0.5:
            return {
                "supports": True,
                "reason": (
                    f"3m above EMA8 · last 15m "
                    f"{change_15m:+.2f}%"),
                "change_15m_pct": round(change_15m, 3),
            }
        return {
            "supports": False,
            "reason": (
                f"3m below EMA8 or last 15m crashing "
                f"({change_15m:+.2f}%)"),
            "change_15m_pct": round(change_15m, 3),
        }
    elif side == "SHORT":
        if c < e8 and change_15m < 0.5:
            return {
                "supports": True,
                "reason": (
                    f"3m below EMA8 · last 15m "
                    f"{change_15m:+.2f}%"),
                "change_15m_pct": round(change_15m, 3),
            }
        return {
            "supports": False,
            "reason": (
                f"3m above EMA8 or last 15m ripping up "
                f"({change_15m:+.2f}%)"),
            "change_15m_pct": round(change_15m, 3),
        }
    return {"supports": False, "reason": "unknown side",
            "change_15m_pct": 0.0}
