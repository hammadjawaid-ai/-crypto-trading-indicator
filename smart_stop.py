"""Structural stop placement — the validated GIGGLE fix.

Overnight backtest (backtest_smartstop, 565 entries): placing the stop just
below the recent SWING LOW (a real structural level) instead of a fixed
distance beat the plan stop on BOTH win rate (70.3% vs 65.7%) and expectancy
(−0.014R vs −0.049R), and directly cuts the "stopped-then-ran" leak (32% of
losses). Mechanism: the stop no longer sits inside the coin's noise band, so
ordinary volatility can't wick it out before the real move.

`structural_stop(df1h, side, entry, plan_stop, tp1)` returns the stop to use:
the swing-low (LONG) / swing-high (SHORT) minus/plus a small ATR buffer.
Falls back to the plan stop if the structural level is unusable (wrong side
of entry, beyond TP1, or absurdly wide). Pure-python, no network.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

LOOKBACK = 10        # swing window (bars) — matches the validated backtest
BUF = 0.25           # ATR buffer beyond the swing level
MAX_ATR = 4.0        # sanity cap: never risk more than 4×ATR (avoids a
                     # runaway-wide stop when the swing is very far)


def _atr(h, l, c, n=14):
    pc = np.roll(c, 1)
    pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(n).mean().to_numpy()


def structural_stop(df1h, side, entry, plan_stop, tp1,
                    lookback: int = LOOKBACK, buf: float = BUF):
    """Return the structural stop for this setup, or plan_stop as fallback.

    df1h: recent 1h OHLC DataFrame (needs >= lookback+15 rows, columns
    high/low/close). side: 'LONG'/'SHORT'. entry/plan_stop/tp1: floats."""
    try:
        side = (side or "").upper()
        entry = float(entry)
        plan_stop = float(plan_stop)
        tp1 = float(tp1)
        if entry <= 0 or plan_stop <= 0 or tp1 <= 0:
            return plan_stop
        if df1h is None or len(df1h) < lookback + 15:
            return plan_stop
        h = df1h["high"].to_numpy()
        l = df1h["low"].to_numpy()
        c = df1h["close"].to_numpy()
        atr = _atr(h, l, c, 14)
        a = float(atr[-1])
        if not (a > 0):
            return plan_stop
        if side == "LONG":
            swing = float(np.min(l[-lookback:]))
            s = swing - buf * a
            # guards: must be below entry, below TP1, not absurdly wide
            if not (s < entry and s < tp1):
                return plan_stop
            if (entry - s) > MAX_ATR * a:            # too wide → cap at plan
                return plan_stop
            return s
        elif side == "SHORT":
            swing = float(np.max(h[-lookback:]))
            s = swing + buf * a
            if not (s > entry and s > tp1):
                return plan_stop
            if (s - entry) > MAX_ATR * a:
                return plan_stop
            return s
        return plan_stop
    except Exception:
        return plan_stop
