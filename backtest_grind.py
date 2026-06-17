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
        # SCALE-OUT simulation: half off at TP1 (+1.0 ATR), then move
        # stop to breakeven and let the runner go to TP2 (+2.5 ATR).
        # R unit = 1.2-ATR initial risk. Half-position each leg:
        #   full stop before TP1        -> -1.0R
        #   TP1 hit, runner stops at BE -> +0.417R (kept the partial)
        #   TP1 hit, runner hits TP2    -> +1.458R
        entry = c_now
        stop = entry - SL_MULT*a if side == "LONG" else entry + SL_MULT*a
        tp1 = entry + 1.0*a if side == "LONG" else entry - 1.0*a
        tp2 = entry + 2.5*a if side == "LONG" else entry - 2.5*a
        PART = 0.5*(1.0/SL_MULT)      # +0.417R booked at TP1 (half)
        RUN = 0.5*(2.5/SL_MULT)       # +1.042R if runner hits TP2
        phase = "pre"; tp1_hit = False; res = None
        for fb in range(1, FORWARD+1):
            fh = float(high.iloc[t+fb]); fl = float(low.iloc[t+fb])
            if phase == "pre":
                hit_stop = (fl <= stop) if side == "LONG" else (fh >= stop)
                hit_tp1 = (fh >= tp1) if side == "LONG" else (fl <= tp1)
                if hit_stop:            # pessimistic: stop first
                    res = -1.0; break
                if hit_tp1:
                    tp1_hit = True; phase = "runner"
                    hit_tp2 = (fh >= tp2) if side == "LONG" else (fl <= tp2)
                    if hit_tp2:
                        res = PART + RUN; break
            else:  # runner, stop at breakeven
                hit_be = (fl <= entry) if side == "LONG" else (fh >= entry)
                hit_tp2 = (fh >= tp2) if side == "LONG" else (fl <= tp2)
                if hit_be:
                    res = PART; break
                if hit_tp2:
                    res = PART + RUN; break
        if res is None:
            res = PART if tp1_hit else 0.0
        sigs.append((side, fresh, aligned, res, tp1_hit))
    print(f"  [{idx+1}/{N_COINS}] {sym:12} cum {len(sigs)} "
          f"({time.time()-t0:.0f}s)")

# rows: (side, fresh, aligned, res_R, tp1_hit)
def scaleout(rows):
    if not rows:
        return 0, 0.0, 0.0
    n = len(rows)
    green = sum(1 for r in rows if r[4]) / n * 100      # booked partial
    exp = sum(r[3] for r in rows) / n
    full_win = sum(1 for r in rows if r[3] > 0.5) / n * 100  # runner ran
    return green, exp, full_win

def report(label, rows):
    if not rows:
        print(f"\n{label}: (none)"); return
    g, e, fw = scaleout(rows)
    print(f"\n{label} (n={len(rows)}):")
    print(f"   GREEN rate (booked +1ATR partial): {g:5.1f}%")
    print(f"   runner-to-TP2 rate:               {fw:5.1f}%")
    print(f"   expectancy:                        {e:+.3f}R")

print("\n" + "="*64)
print(f"15m GRIND SCALE-OUT — {len(sigs)} sigs, {N_COINS} coins, ~30d")
print("  half off +1.0ATR -> stop to breakeven -> runner +2.5ATR")
print("="*64)
report("OVERALL", sigs)
report("very-early + 1h-aligned (THE BOARD)",
       [r for r in sigs if r[1]=="very early" and r[2]])
report("aligned (any freshness)", [r for r in sigs if r[2]])
print(f"\nDone in {time.time()-t0:.0f}s.")
