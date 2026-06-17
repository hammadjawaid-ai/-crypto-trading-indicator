"""Walk-forward backtest for the 15m Early Burst Radar.

Validates the scan_15m_early playbook: does catching bursts on the 15m
clock have edge — and specifically, does the GATED version (very-early
freshness + 1h-trend aligned) beat the ungated one?

Method (no lookahead, vectorized for speed):
  - For each coin, fetch 15m klines.
  - Burst candidate at bar t when vol[t] >= 2.5x its trailing-20 mean
    AND range[t] >= 2.0x trailing ATR (same as scan_15m_early).
  - Side from close-in-range + candle direction.
  - freshness from the move over the last 4 bars (≈ forming 1h bar):
       very early <4% | early 4-8% | extended >8%
  - 1h-trend proxy: price vs EMA80 / EMA200 on the 15m series
    (80 bars ≈ 1h-EMA20, 200 ≈ 1h-EMA50) — no lookahead.
  - Trade: entry = close[t], stop = ±1.2*ATR, tp1 = ±2.0*ATR.
    Walk forward up to FORWARD bars; SL-first if both hit same bar.

Outputs win rate + expectancy (R) overall and split by
freshness × alignment, so we can see which slice is tradeable.
"""
from __future__ import annotations
import sys, io, time
import numpy as np
import pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client

N_COINS = 25
LIMIT = 2880          # ~30 days of 15m bars
FORWARD = 32          # 8 hours (32 x 15m) — let bursts run for the sweep
LOOKBACK = 20
VOL_MULT = 2.5
RANGE_MULT = 2.0
TP_MULT, SL_MULT = 2.0, 1.2
R_WIN = TP_MULT / SL_MULT   # +1.67R per win

print(f"Fetching top {N_COINS} symbols…")
try:
    syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]
except Exception as e:
    print("failed:", e); sys.exit(1)

def atr_series(df, n=LOOKBACK):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

signals = []
t0 = time.time()
for i, sym in enumerate(syms):
    try:
        df = binance_client.get_klines(sym, "15m", limit=LIMIT)
    except Exception:
        continue
    if df is None or len(df) < 300:
        continue
    df = df.reset_index(drop=True)
    close, high, low, vol = df["close"], df["high"], df["low"], df["volume"]
    volma = vol.rolling(LOOKBACK).mean()
    atr = atr_series(df)
    ema80 = close.ewm(span=80, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()
    rng = high - low
    n = len(df)
    for t in range(210, n - FORWARD - 1):
        v = float(vol.iloc[t]); vm = float(volma.iloc[t] or 0)
        a = float(atr.iloc[t] or 0)
        if vm <= 0 or a <= 0:
            continue
        vol_ratio = v / vm
        range_ratio = float(rng.iloc[t]) / a
        if vol_ratio < VOL_MULT or range_ratio < RANGE_MULT:
            continue
        o = float(df["open"].iloc[t]); c = float(close.iloc[t])
        hi = float(high.iloc[t]); lo = float(low.iloc[t])
        r = hi - lo
        if r <= 0:
            continue
        close_pos = (c - lo) / r
        prevc = float(close.iloc[t - 1])
        pct = (c - prevc) / prevc if prevc > 0 else 0
        if close_pos >= 0.65 and pct > 0:
            side = "LONG"
        elif close_pos <= 0.35 and pct < 0:
            side = "SHORT"
        else:
            continue
        # freshness — move over last 4 bars
        c4 = float(close.iloc[t - 4])
        move = (c / c4 - 1) * 100 if c4 > 0 else 0
        mag = abs(move)
        fresh = ("very early" if mag < 4 else
                 "early" if mag < 8 else "extended")
        # 1h-trend proxy
        px, e80, e200 = c, float(ema80.iloc[t]), float(ema200.iloc[t])
        if px > e80 > e200:
            trend = "BULL"
        elif px < e80 < e200:
            trend = "BEAR"
        else:
            trend = "MIXED"
        aligned = ((side == "LONG" and trend == "BULL")
                   or (side == "SHORT" and trend == "BEAR"))
        # forward path — capture max favorable excursion (in ATR units)
        # BEFORE the 1.2-ATR stop is hit, so we can sweep any TP level.
        entry = c
        stop = entry - SL_MULT * a if side == "LONG" else entry + SL_MULT * a
        max_fav = 0.0
        stopped = False
        for fb in range(1, FORWARD + 1):
            fh = float(high.iloc[t + fb]); fl = float(low.iloc[t + fb])
            if side == "LONG":
                fav = (fh - entry) / a
                max_fav = max(max_fav, fav)
                if fl <= stop:
                    stopped = True; break
            else:
                fav = (entry - fl) / a
                max_fav = max(max_fav, fav)
                if fh >= stop:
                    stopped = True; break
        signals.append((side, fresh, aligned, max_fav, stopped))
    print(f"  [{i+1}/{N_COINS}] {sym:12} cumulative {len(signals)} "
          f"signals ({time.time()-t0:.0f}s)")

# signals = (side, fresh, aligned, max_fav, stopped)
def expectancy(rows, tp):
    """Expectancy at a given TP (ATR mult), stop fixed at SL_MULT.
    A win = max favorable excursion reached tp before the stop hit.
    win pays tp/SL_MULT R; loss = -1R; flat (neither) = 0."""
    if not rows:
        return 0, 0, 0.0, 0.0
    r_win = tp / SL_MULT
    w = l = 0
    for _side, _f, _al, mf, stopped in rows:
        if mf >= tp:
            w += 1            # hit target (favorable excursion reached)
        elif stopped:
            l += 1            # stopped out before reaching target
        # else flat — neither within window
    n = len(rows)
    wr = w / n * 100
    exp = (w * r_win - l) / n
    return n, w, wr, exp

print("\n" + "=" * 72)
print(f"15m EARLY BURST — {len(signals)} signals, {N_COINS} coins, "
      f"~{LIMIT*15//1440}d, fwd {FORWARD}x15m, SL {SL_MULT} ATR")
print("=" * 72)

def report(label, rows):
    if not rows:
        print(f"\n{label}: (no signals)")
        return
    print(f"\n{label} (n={len(rows)}):")
    print("   TP(ATR)  win%   exp(R)")
    for tp in (2.0, 3.0, 4.0, 5.0, 6.0):
        n, w, wr, e = expectancy(rows, tp)
        flag = "  <== best" if e == max(
            expectancy(rows, x)[3] for x in (2, 3, 4, 5, 6)) else ""
        print(f"   {tp:>4.1f}   {wr:5.1f}%  {e:+.3f}{flag}")

report("OVERALL", signals)
report("very-early + 1h-aligned (THE PLAYBOOK)",
       [r for r in signals if r[1] == "very early" and r[2]])
report("very-early (any trend)",
       [r for r in signals if r[1] == "very early"])
report("aligned (any freshness)",
       [r for r in signals if r[2]])
print(f"\nDone in {time.time()-t0:.0f}s.")
