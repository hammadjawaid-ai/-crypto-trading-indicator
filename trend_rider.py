"""🌊 TREND RIDER — the validated money core (daily-scale trend following).

The ONLY strategy that survived full validation (backtest_trendrider,
3 years daily, fees included, out-of-sample coins 41-100):
  top-40 LONG +0.320R/trade (n=498) · OOS LONG +0.153R/trade (n=648)
  win ~34-40% with avg win ~2.6x avg loss · hold ~7-10 days · shorts: no
  edge (dropped). Realistic +2-6%/month at 1%% risk, lumpy by design.

Spec (exactly what was backtested):
  ENTRY : daily close breaks the prior 20-day high AND close > EMA50(1d)
  STOP  : entry − 2.5×ATR(14d)
  MANAGE: chandelier trail = peak − 3×ATR(14d), never loosens; no fixed TP
  HOLD  : days-to-weeks; exit only on the trail

`scan(symbols)` returns today's fresh LONG breakout signals with the full
plan. tp1/tp2 are +2R/+4R waypoints so the shadow trader / paper ladder can
approximate the ride; the real policy is the trail. 30-min kline cache so
the 24/7 brain can call this every cycle cheaply.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

import binance_client

BREAK_N = 20
EMA_N = 50
ATR_N = 14
STOP_ATR = 2.5
TRAIL_ATR = 3.0
_CACHE: dict = {}
_TTL = 1800.0


def _daily(sym: str):
    now = time.time()
    hit = _CACHE.get(sym)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    try:
        d = binance_client.get_klines(sym, "1d", limit=300)
    except Exception:
        d = None
    _CACHE[sym] = (now, d)
    return d


def _atr(h, l, c, n=ATR_N):
    pc = np.roll(c, 1)
    pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(n).mean().to_numpy()


def scan(symbols: list[str]) -> list[dict]:
    """Fresh daily LONG breakout signals right now (today's bar)."""
    picks = []
    for sym in symbols:
        d = _daily(sym)
        if d is None or len(d) < EMA_N + BREAK_N + 5:
            continue
        h = d["high"].to_numpy()
        l = d["low"].to_numpy()
        c = d["close"].to_numpy()
        e50 = d["close"].ewm(span=EMA_N, adjust=False).mean().to_numpy()
        atr = _atr(h, l, c)
        t = len(d) - 1                     # today's (forming) daily bar
        a = float(atr[t - 1]) if atr[t - 1] == atr[t - 1] else 0.0
        if a <= 0:
            continue
        hi_prev = float(np.max(h[t - BREAK_N:t]))     # prior 20d high
        if not (c[t] > hi_prev and c[t] > e50[t]):
            continue
        entry = float(c[t])
        risk = STOP_ATR * a
        stop = entry - risk
        picks.append({
            "symbol": sym,
            "base": sym.replace("USDT", ""),
            "side": "LONG",
            "tier": "TREND",
            "score": round((entry / hi_prev - 1) * 100, 2),  # breakout %
            "entry": entry,
            "stop": stop,
            "tp1": entry + 2 * risk,       # +2R waypoint (ladder proxy)
            "tp2": entry + 4 * risk,       # +4R waypoint
            "atr_d": a,
            "trail_atr": TRAIL_ATR,
            "hold": "days-to-weeks (chandelier trail, no fixed TP)",
        })
    picks.sort(key=lambda x: x["score"], reverse=True)
    return picks
