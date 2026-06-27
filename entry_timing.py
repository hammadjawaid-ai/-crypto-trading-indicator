"""Entry-timing detector — for an ALIVE setup, is NOW a good time to enter?

Backtested (2026-06-18, MAX/HIGH ELITE fires): entering on a
pullback + confirmation candle won ~50% vs ~23% entering at the fire —
more than double. This computes that signal LIVE so the ACTIVE MAX/HIGH
board can flag each alive setup ✅ TAKE NOW vs ⏳ WAIT.

The winning condition (LONG; SHORT mirrors), straight from the backtest:
  - price has PULLED BACK to/below the planned entry (cheaper entry), AND
  - a CONFIRMATION candle just printed: bullish close (close>open),
    momentum up (close>prev close), trend intact (close>EMA20), and a
    volume uptick (>1.2x the 20-bar average).
Four states: TAKE_NOW (pullback + full confirmation — act), GET_READY
(pulled back & holding above/below the EMA20, one confirmation candle away —
poised to act, kills reaction lag), WAIT (no pullback or still falling),
MISSED (ran away without a pullback — let it go).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import binance_client

VOL_MULT = 1.2
PULLBACK_LOOKBACK = 48   # bars (~2 days on 1h) to look for the pullback


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _atr_pctile(df, n: int = 14, lookback: int = 100) -> float:
    """ATR(n) percentile rank of the latest bar within its last `lookback`
    bars (0–100). High = the coin is already moving with elevated volatility
    = HOT. Backtested (2026-06-27): a TAKE_NOW firing while HOT (this rank in
    the top 40%) won ~74% vs ~55% in a quiet tape AND ran further
    (MFE-R 1.65 vs 1.23). Used as a descriptive 🔥 HOT tag, not a gate."""
    h = df["high"].to_numpy(); l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    if len(c) < n + 2:
        return 0.0
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).rolling(n).mean().to_numpy()
    cur = atr[-1]
    if cur != cur:        # NaN guard
        return 0.0
    ref = atr[-lookback:]
    ref = ref[~np.isnan(ref)]
    if len(ref) == 0:
        return 0.0
    return float((ref < cur).mean() * 100.0)


HOT_PCTILE = 60.0   # ATR rank ≥ this (top 40%) = HOT


def entry_signal(symbol: str, side: str, entry: float,
                 stop: float = 0.0, df=None) -> dict:
    """Return {status, reason, px, hot, atr_pct} where status is one of:
       TAKE_NOW | GET_READY | WAIT | MISSED | UNKNOWN. `hot` flags an elevated
       ATR state (validated: HOT TAKE_NOWs win more and run further)."""
    side = (side or "").upper()
    if side not in ("LONG", "SHORT") or not entry:
        return {"status": "UNKNOWN", "reason": "bad inputs", "px": 0.0}
    if df is None:
        try:
            df = binance_client.get_klines(symbol, "1h", limit=120)
        except Exception:
            return {"status": "UNKNOWN", "reason": "no data", "px": 0.0}
    if df is None or len(df) < 30:
        return {"status": "UNKNOWN", "reason": "no data", "px": 0.0}

    o = df["open"].to_numpy(); h = df["high"].to_numpy()
    l = df["low"].to_numpy(); c = df["close"].to_numpy()
    v = df["volume"].to_numpy()
    ema20 = _ema(df["close"], 20).to_numpy()
    vma = pd.Series(v).rolling(20).mean().to_numpy()
    cur = float(c[-1])
    win = min(PULLBACK_LOOKBACK, len(df) - 1)
    vol_ok = vma[-1] > 0 and v[-1] > VOL_MULT * vma[-1]

    # Hotness — descriptive (ATR elevated => the move tends to win more + run
    # further when it's a TAKE_NOW). Attached to every result via _r().
    atr_pct = _atr_pctile(df, 14, 100)
    hot = atr_pct >= HOT_PCTILE

    def _r(status, reason):
        return {"status": status, "reason": reason, "px": cur,
                "hot": bool(hot), "atr_pct": round(atr_pct, 1)}

    if side == "LONG":
        pulled = float(np.min(l[-win:])) <= entry
        struct = c[-1] > ema20[-1]              # right side of the EMA20
        green = c[-1] > o[-1] or c[-1] > c[-2]  # some bullish turn showing
        conf = (c[-1] > o[-1] and c[-1] > c[-2] and c[-1] > ema20[-1]
                and vol_ok)
        extended = (cur > entry * 1.02) and not pulled
    else:
        pulled = float(np.max(h[-win:])) >= entry
        struct = c[-1] < ema20[-1]
        green = c[-1] < o[-1] or c[-1] < c[-2]
        conf = (c[-1] < o[-1] and c[-1] < c[-2] and c[-1] < ema20[-1]
                and vol_ok)
        extended = (cur < entry * 0.98) and not pulled

    # ARMING = pulled back, holding the right side of the EMA20, and a turn
    # is showing — but the FULL confirmation candle (momentum + volume kick)
    # hasn't printed yet. It's a strict subset of the old "pulled, no conf"
    # WAIT state, so TAKE_NOW fires on EXACTLY the same condition as before —
    # this only flags that you're one good candle away, zero cost to the edge.
    arming = pulled and struct and green and not conf

    if pulled and conf:
        return _r("TAKE_NOW", "pullback + confirmation candle "
                              "(close>EMA20, momentum, volume)")
    if extended:
        return _r("MISSED", "ran away without a pullback")
    if arming:
        return _r("GET_READY",
                  "pulled back & holding the right side of EMA20 — "
                  "one confirmation candle (momentum + volume) away")
    if pulled:
        return _r("WAIT", "pulled back — waiting for a confirmation candle")
    return _r("WAIT", "no pullback / confirmation yet")
