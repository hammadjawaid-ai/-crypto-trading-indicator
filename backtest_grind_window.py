"""Grind candle-WINDOW sweep (user q 2026-06-18): does 5 or 6 candles
beat 7, on 5m vs 15m, with 1-2 opposites tolerated?

For each window W, require >= W-2 directional candles (so 1-2 opposite
allowed), close-strength score >= 50, net move, > EMA20. Scale-out exit
(SL 1.2 / TP1 1.5 / TP2 2.5 ATR), AFTER 0.06%/leg fees. Reports the
'+trend' gate (EMA40 aligned) since that's what's actually tradeable.
Walk-forward, no lookahead.
"""
import sys, io, time
import numpy as np, pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client

N_COINS = 25
SL_ATR, TP1_ATR, TP2_ATR = 1.2, 1.5, 2.5
FEE_LEG, TURNOVER = 0.0006, 2.0
WINDOWS = (5, 6, 7)
TFS = (("5m", 4000, 48, 0.8), ("15m", 2880, 32, 1.0))

syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]

def atr_series(df, n=20):
    h, l, c = df["high"], df["low"], df["close"]; pc = c.shift(1)
    tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def score_grind(o, h, l, c, t, side, W):
    dir_cnt = 0; close_strs = []; counter_bodies = []
    for i in range(t - W + 1, t + 1):
        rng = max(h[i] - l[i], 1e-12); body = abs(c[i] - o[i]) / rng
        if side == "LONG":
            is_dir = c[i] > o[i]; cp = (c[i] - l[i]) / rng
        else:
            is_dir = c[i] < o[i]; cp = (h[i] - c[i]) / rng
        if is_dir:
            dir_cnt += 1; close_strs.append(cp * (0.4 + 0.6 * body))
        else:
            counter_bodies.append(body)
    cs = sum(close_strs)/len(close_strs) if close_strs else 0.0
    cb = sum(counter_bodies)/len(counter_bodies) if counter_bodies else 0.0
    na = abs((c[t]/c[t-W]-1.0)*100) if c[t-W] > 0 else 0.0
    sc = float(np.clip(35 + cs*35 + (dir_cnt-3)*4 + min(15, na*2.5) - cb*18, 0, 100))
    return dir_cnt, sc

def simulate(side, entry, a, h, l, t, n, FORWARD):
    stop = entry - SL_ATR*a if side == "LONG" else entry + SL_ATR*a
    tp1 = entry + TP1_ATR*a if side == "LONG" else entry - TP1_ATR*a
    tp2 = entry + TP2_ATR*a if side == "LONG" else entry - TP2_ATR*a
    PART = 0.5*(TP1_ATR/SL_ATR); RUN = 0.5*(TP2_ATR/SL_ATR)
    phase = "pre"; tp1_hit = False; res = None
    for fb in range(t+1, min(t+FORWARD+1, n)):
        fh, fl = h[fb], l[fb]
        if phase == "pre":
            hs = (fl <= stop) if side == "LONG" else (fh >= stop)
            ht = (fh >= tp1) if side == "LONG" else (fl <= tp1)
            if hs:
                res = -1.0; break
            if ht:
                tp1_hit = True; phase = "runner"
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
        res = PART if tp1_hit else 0.0
    return res, tp1_hit

acc = {}  # (tf, W) -> list[(net_r, booked)]
t0 = time.time()
for ci, sym in enumerate(syms):
    for tf, LIMIT, FORWARD, NET_MIN in TFS:
        try:
            df = binance_client.get_klines(sym, tf, limit=LIMIT)
        except Exception:
            continue
        if df is None or len(df) < 300:
            continue
        df = df.reset_index(drop=True)
        o, h, l, c = (df[x].astype(float).to_numpy() for x in
                      ("open", "high", "low", "close"))
        atr = atr_series(df).to_numpy()
        e20 = df["close"].ewm(span=20, adjust=False).mean().to_numpy()
        e40 = df["close"].ewm(span=40, adjust=False).mean().to_numpy()
        n = len(df)
        for W in WINDOWS:
            key = (tf, W); acc.setdefault(key, [])
            for t in range(210, n - FORWARD - 1):
                a = float(atr[t] or 0)
                if a <= 0 or c[t-W] <= 0:
                    continue
                net = (c[t]/c[t-W]-1.0)*100
                if net >= NET_MIN and c[t] > e20[t]:
                    side = "LONG"
                elif net <= -NET_MIN and c[t] < e20[t]:
                    side = "SHORT"
                else:
                    continue
                dirc, sc = score_grind(o, h, l, c, t, side, W)
                if dirc < (W - 2) or sc < 50:   # 1-2 opposites allowed
                    continue
                trend_ok = (c[t] > e40[t]) if side == "LONG" else (c[t] < e40[t])
                if not trend_ok:
                    continue
                res, booked = simulate(side, c[t], a, h, l, t, n, FORWARD)
                feeR = (FEE_LEG*TURNOVER)/(SL_ATR*max(a/c[t], 1e-9))
                acc[key].append((res - feeR, booked))
    print(f"  [{ci+1}/{N_COINS}] {sym:12} ({time.time()-t0:.0f}s)", flush=True)

print("\n" + "=" * 64)
print("GRIND CANDLE-WINDOW SWEEP — +trend gate, AFTER fees, scale-out")
print("  require >= W-2 directional (1-2 opposites ok) + score>=50")
print("=" * 64)
print(f"{'TF':>4} {'window':>7} {'n':>6} {'booked%':>8} {'exp(R)':>9}")
for tf, _l, _f, _nm in TFS:
    for W in WINDOWS:
        rows = acc.get((tf, W), [])
        if not rows:
            print(f"{tf:>4} {W:>7} {'0':>6}"); continue
        nn = len(rows); exp = sum(r[0] for r in rows)/nn
        bk = sum(1 for r in rows if r[1])/nn*100
        print(f"{tf:>4} {W:>7} {nn:>6} {bk:>7.1f}% {exp:>+8.3f}R")
    print()
print(f"Done in {time.time()-t0:.0f}s.")
