"""Walk-forward backtest for the 15m GRIND detector (staircase moves).

Same methodology as backtest_early_burst: no lookahead, vectorized,
captures max-favorable-excursion so we can sweep TP, split by
freshness x 1h-alignment. Tests whether catching grind-up moves on
15m has any real edge.
"""
from __future__ import annotations
import sys, io, time
import numpy as np
import pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client

N_COINS = 25
LIMIT = 2880          # ~30 days of 15m
FORWARD = 32          # 8h
SL_MULT = 1.2
NET_MIN = 2.5         # grind: net move over last 8 bars
GREEN_MIN = 5

print(f"Fetching top {N_COINS}…")
syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]

def atr_series(df, n=20):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

sigs = []
t0 = time.time()
for idx, sym in enumerate(syms):
    try:
        df = binance_client.get_klines(sym, "15m", limit=LIMIT)
    except Exception:
        continue
    if df is None or len(df) < 300:
        continue
    df = df.reset_index(drop=True)
    close, high, low = df["close"], df["high"], df["low"]
    atr = atr_series(df)
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema80 = close.ewm(span=80, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()
    green = (close > close.shift(1)).astype(int)
    n = len(df)
    for t in range(210, n - FORWARD - 1):
        a = float(atr.iloc[t] or 0)
        if a <= 0:
            continue
        c_now = float(close.iloc[t]); c_8 = float(close.iloc[t-8])
        if c_8 <= 0:
            continue
        net = (c_now / c_8 - 1) * 100
        greens = int(green.iloc[t-7:t+1].sum())
        e20 = float(ema20.iloc[t]); e20p = float(ema20.iloc[t-4])
        # LONG grind
        if net >= NET_MIN and greens >= GREEN_MIN and c_now > e20 and e20 > e20p:
            side = "LONG"
        elif net <= -NET_MIN and (8-greens) >= GREEN_MIN and c_now < e20 and e20 < e20p:
            side = "SHORT"
        else:
            continue
        # freshness from last-4-bar move (the radar's meter)
        c4 = float(close.iloc[t-4])
        mv = (c_now/c4-1)*100 if c4 > 0 else 0
        mag = abs(mv)
        fresh = "very early" if mag < 4 else "early" if mag < 8 else "extended"
        # 1h trend proxy
        px = c_now; e80 = float(ema80.iloc[t]); e200 = float(ema200.iloc[t])
        trend = "BULL" if px>e80>e200 else "BEAR" if px<e80<e200 else "MIXED"
        aligned = (side=="LONG" and trend=="BULL") or (side=="SHORT" and trend=="BEAR")
        # forward MFE before stop
        entry = c_now
        stop = entry - SL_MULT*a if side=="LONG" else entry + SL_MULT*a
        mfe = 0.0; stopped = False
        for fb in range(1, FORWARD+1):
            fh=float(high.iloc[t+fb]); fl=float(low.iloc[t+fb])
            if side=="LONG":
                mfe=max(mfe,(fh-entry)/a)
                if fl<=stop: stopped=True; break
            else:
                mfe=max(mfe,(entry-fl)/a)
                if fh>=stop: stopped=True; break
        sigs.append((side, fresh, aligned, mfe, stopped))
    print(f"  [{idx+1}/{N_COINS}] {sym:12} cum {len(sigs)} "
          f"({time.time()-t0:.0f}s)")

def exp_at(rows, tp):
    rw = tp/SL_MULT; w=l=0
    for *_, mf, st in rows:
        if mf>=tp: w+=1
        elif st: l+=1
    n=len(rows)
    return (w/n*100 if n else 0), ((w*rw - l)/n if n else 0)

def report(label, rows):
    if not rows:
        print(f"\n{label}: (none)"); return
    print(f"\n{label} (n={len(rows)}):")
    best = max(exp_at(rows,x)[1] for x in (2,3,4,5,6))
    for tp in (2.0,3.0,4.0,5.0,6.0):
        wr,e = exp_at(rows,tp)
        print(f"   TP {tp:.1f}  win {wr:5.1f}%  exp {e:+.3f}R"
              + ("  <== best" if e==best else ""))

print("\n" + "="*64)
print(f"15m GRIND — {len(sigs)} signals, {N_COINS} coins, ~30d, SL {SL_MULT}")
print("="*64)
report("OVERALL", sigs)
report("very-early + 1h-aligned", [r for r in sigs if r[1]=="very early" and r[2]])
report("aligned (any freshness)", [r for r in sigs if r[2]])
print(f"\nDone in {time.time()-t0:.0f}s.")
