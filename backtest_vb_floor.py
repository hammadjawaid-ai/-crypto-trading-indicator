"""Can the velocity-burst 'proven' floor drop from 90 to ~85 WITH
validation? (user ask 2026-06-18)

Raw bands: 80-89 = -0.10R (loses), 90+ = +0.16R. So a naive drop to 85
lets losers in. This tests whether the 85-89 band, FILTERED by proven
validators (deep-trend EMA200, 1h-trend, not-already-extended), becomes
positive — i.e. catch it earlier but only flag the validated ones.

Exit: TP 2.0 / SL 1.2 ATR single target (matches the velocity backtest),
AFTER 0.06%/leg fees. Walk-forward, 60/40 IS/OOS. Trust only OOS.
"""
import sys, io, time
import numpy as np, pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client, indicators, velocity_burst

N_COINS = 18
LIMIT = 1500
FWD = 24
TP_ATR, SL_ATR = 2.0, 1.2
FEE_LEG, TURNOVER = 0.0006, 2.0
SPLIT = 0.60

syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]

def outcome(side, entry, a, h, l, t, n):
    stop = entry - SL_ATR*a if side == "LONG" else entry + SL_ATR*a
    tp = entry + TP_ATR*a if side == "LONG" else entry - TP_ATR*a
    for fb in range(t+1, min(t+FWD+1, n)):
        fh, fl = h[fb], l[fb]
        hs = (fl <= stop) if side == "LONG" else (fh >= stop)
        ht = (fh >= tp) if side == "LONG" else (fl <= tp)
        if hs and ht:
            return -1.0          # pessimistic: stop first
        if hs:
            return -1.0
        if ht:
            return TP_ATR/SL_ATR  # +1.667R
    return 0.0

# bucket -> {IS:[], OOS:[]}
BUCKETS = ("raw 80-84", "raw 85-89", "raw 90+",
           "85-89 +deep", "85-89 +h1trend", "85-89 +fresh",
           "85-89 +deep+fresh", "85+ +deep+fresh")
acc = {b: {"IS": [], "OOS": []} for b in BUCKETS}
t0 = time.time()
for ci, sym in enumerate(syms):
    try:
        df = indicators.enrich(binance_client.get_klines(sym, "1h", limit=LIMIT))
    except Exception:
        continue
    if df is None or len(df) < 400:
        continue
    h = df["high"].to_numpy(); l = df["low"].to_numpy(); c = df["close"].to_numpy()
    atr = df["atr"].to_numpy(); et = df["ema_trend"].to_numpy()
    ef = df["ema_fast"].to_numpy(); es = df["ema_slow"].to_numpy()
    vol = df["volume"].to_numpy()
    vma = pd.Series(vol).rolling(20).mean().to_numpy()
    n = len(df); split = int(n*SPLIT)
    for t in range(210, n - FWD - 1):
        a = float(atr[t] or 0)
        if a <= 0:
            continue
        sc, side, _ = velocity_burst.lane_velocity_burst(df.iloc[:t+1])
        if side not in ("LONG", "SHORT") or sc < 80:
            continue
        r = outcome(side, c[t], a, h, l, t, n)
        feeR = (FEE_LEG*TURNOVER)/(SL_ATR*max(a/c[t], 1e-9))
        nr = r - feeR
        seg = "IS" if t < split else "OOS"
        deep = (c[t] > et[t]) if side == "LONG" else (c[t] < et[t])
        h1 = (ef[t] > es[t]) if side == "LONG" else (ef[t] < es[t])
        move5 = abs((c[t]/c[t-5]-1)*100) if c[t-5] > 0 else 99
        fresh = move5 < 8.0   # not already run too far
        if sc < 85:
            acc["raw 80-84"][seg].append(nr)
        elif sc < 90:
            acc["raw 85-89"][seg].append(nr)
            if deep:
                acc["85-89 +deep"][seg].append(nr)
            if h1:
                acc["85-89 +h1trend"][seg].append(nr)
            if fresh:
                acc["85-89 +fresh"][seg].append(nr)
            if deep and fresh:
                acc["85-89 +deep+fresh"][seg].append(nr)
        else:
            acc["raw 90+"][seg].append(nr)
        if sc >= 85 and deep and fresh:
            acc["85+ +deep+fresh"][seg].append(nr)
    print(f"  [{ci+1}/{N_COINS}] {sym:12} ({time.time()-t0:.0f}s)", flush=True)

def st(rows):
    if not rows:
        return (0, 0.0, 0.0)
    nn = len(rows); exp = sum(rows)/nn
    win = sum(1 for r in rows if r > 0)/nn*100
    return (nn, win, exp)

print("\n" + "="*72)
print("VELOCITY-BURST FLOOR sweep — TP2.0/SL1.2, AFTER fees, 60/40 IS/OOS")
print("="*72)
print(f"{'bucket':>20} | {'IS n':>5} {'IS win':>7} {'IS exp':>8} | "
      f"{'OOS n':>5} {'OOS win':>8} {'OOS exp':>8}")
for b in BUCKETS:
    isn, isw, ise = st(acc[b]["IS"]); on, ow, oe = st(acc[b]["OOS"])
    print(f"{b:>20} | {isn:>5} {isw:>6.1f}% {ise:>+7.3f}R | "
          f"{on:>5} {ow:>7.1f}% {oe:>+7.3f}R")
print(f"\nDone in {time.time()-t0:.0f}s.")
