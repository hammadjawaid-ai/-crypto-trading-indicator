"""Can we make CONVERGENCE a real edge? (user ask 2026-06-18)

The current convergence bonuses (reversal pre-warn + BTC corr + 4h stack)
select WORSE trades than baseline. This tests whether the PROVEN
ingredients — deep-trend (EMA200), multi-timeframe agreement, higher
score bar — lift pattern_scout fires instead. Walk-forward, 60/40
in-sample/out-of-sample, scale-out R AFTER fees. Only trust gates that
hold OOS.
"""
import sys, io, time, os
import numpy as np, pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client, indicators, pattern_scout

N_COINS = int(os.environ.get("BT_COINS", "12"))
SAMPLE = 6
WARMUP = 210
FWD = 24
SL_ATR, TP1_ATR, TP2_ATR = 1.2, 1.5, 2.5
FEE_LEG, TURNOVER = 0.0006, 2.0
SPLIT = 0.60

syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]

def sim(side, entry, a, h, l, t, n):
    stop = entry - SL_ATR*a if side == "LONG" else entry + SL_ATR*a
    tp1 = entry + TP1_ATR*a if side == "LONG" else entry - TP1_ATR*a
    tp2 = entry + TP2_ATR*a if side == "LONG" else entry - TP2_ATR*a
    PART, RUN = 0.5*(TP1_ATR/SL_ATR), 0.5*(TP2_ATR/SL_ATR)
    phase, tp1hit, res = "pre", False, None
    for fb in range(t+1, min(t+FWD+1, n)):
        fh, fl = h[fb], l[fb]
        if phase == "pre":
            hs = (fl <= stop) if side == "LONG" else (fh >= stop)
            ht = (fh >= tp1) if side == "LONG" else (fl <= tp1)
            if hs:
                res = -1.0; break
            if ht:
                tp1hit = True; phase = "run"
                h2 = (fh >= tp2) if side == "LONG" else (fl <= tp2)
                if h2:
                    res = PART+RUN; break
        else:
            hbe = (fl <= entry) if side == "LONG" else (fh >= entry)
            h2 = (fh >= tp2) if side == "LONG" else (fl <= tp2)
            if hbe:
                res = PART; break
            if h2:
                res = PART+RUN; break
    if res is None:
        res = PART if tp1hit else 0.0
    return res

GATES = ("baseline", "+deep", "+mtf", "+score80", "+deep+mtf", "+deep+mtf+s80")
acc = {g: {"IS": [], "OOS": []} for g in GATES}
t0 = time.time()
for ci, sym in enumerate(syms):
    try:
        d1 = indicators.enrich(binance_client.get_klines(sym, "1h", limit=1100))
        d4 = indicators.enrich(binance_client.get_klines(sym, "4h", limit=400))
    except Exception:
        continue
    if d1 is None or len(d1) < 400:
        continue
    h = d1["high"].to_numpy(); l = d1["low"].to_numpy()
    c = d1["close"].to_numpy(); atr = d1["atr"].to_numpy()
    ef = d1["ema_fast"].to_numpy(); es = d1["ema_slow"].to_numpy()
    et = d1["ema_trend"].to_numpy()
    # 4h trend (ema_fast>ema_slow) indexed by time
    d4t = d4.index; d4_up = (d4["ema_fast"] > d4["ema_slow"]).to_numpy()
    n = len(d1); split = int(n*SPLIT)
    for t in range(WARMUP, n - FWD - 1, SAMPLE):
        a = float(atr[t] or 0)
        if a <= 0:
            continue
        try:
            ps = pattern_scout.scan_one(sym, d1.iloc[:t+1], pct_24h=0)
        except Exception:
            continue
        score = float(ps.get("score") or 0); side = ps.get("side")
        if score < 70 or side not in ("LONG", "SHORT"):
            continue
        deep = (c[t] > et[t]) if side == "LONG" else (c[t] < et[t])
        h1ok = (ef[t] > es[t]) if side == "LONG" else (ef[t] < es[t])
        ts = d1.index[t]; pos = d4t.searchsorted(ts, side="right") - 1
        h4ok = (bool(d4_up[pos]) == (side == "LONG")) if pos >= 0 else False
        mtf = h1ok and h4ok
        s80 = score >= 80
        r = sim(side, c[t], a, h, l, t, n)
        feeR = (FEE_LEG*TURNOVER)/(SL_ATR*max(a/c[t], 1e-9))
        nr = r - feeR
        seg = "IS" if t < split else "OOS"
        acc["baseline"][seg].append(nr)
        if deep:
            acc["+deep"][seg].append(nr)
        if mtf:
            acc["+mtf"][seg].append(nr)
        if s80:
            acc["+score80"][seg].append(nr)
        if deep and mtf:
            acc["+deep+mtf"][seg].append(nr)
        if deep and mtf and s80:
            acc["+deep+mtf+s80"][seg].append(nr)
    print(f"  [{ci+1}/{N_COINS}] {sym:12} ({time.time()-t0:.0f}s)", flush=True)

def st(rows):
    if not rows:
        return (0, 0.0, 0.0)
    n = len(rows); exp = sum(rows)/n
    win = sum(1 for r in rows if r > 0)/n*100
    return (n, win, exp)

print("\n" + "="*72)
print("CONVERGENCE v2 — proven-ingredient gates, scale-out, AFTER fees")
print("  (win% = trade booked any positive R; OOS is the one that counts)")
print("="*72)
print(f"{'gate':>15} | {'IS n':>5} {'IS win':>7} {'IS exp':>8} | "
      f"{'OOS n':>5} {'OOS win':>8} {'OOS exp':>8}")
for g in GATES:
    isn, isw, ise = st(acc[g]["IS"]); on, ow, oe = st(acc[g]["OOS"])
    print(f"{g:>15} | {isn:>5} {isw:>6.1f}% {ise:>+7.3f}R | "
          f"{on:>5} {ow:>7.1f}% {oe:>+7.3f}R")
print(f"\nDone in {time.time()-t0:.0f}s.")
