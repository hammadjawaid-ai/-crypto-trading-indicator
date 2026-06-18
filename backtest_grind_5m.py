"""5m GRIND early-detection backtest (user spec, 2026-06-18).

Tests the user's idea: catch grinds EARLIER on the 5m clock (7-candle
window, 1-2 opposite candles tolerated but PENALIZED by their close
strength), then filter with trend + volume surge to see whether the
earlier entry actually produces a tradeable edge — and whether the
filtering lifts win rate the way the user hopes.

Mirrors velocity_burst.detect_grind's close-strength _run/_score, on 5m.
Scale-out exit (SL 1.2 / TP1 1.5 / TP2 2.5 ATR), AFTER 0.06%/leg fees.
Walk-forward, no lookahead. Compares 4 gates so we can SEE where (if
anywhere) the edge lives:
   raw  ->  +volume surge  ->  +trend(EMA40)  ->  +both (user's combo)
plus a close-strength bucket split.
"""
import sys, io, time
import numpy as np, pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client

N_COINS = 25
LIMIT = 4000               # ~14 days of 5m
FORWARD = 48               # 4h on 5m
W = 7
SL_ATR, TP1_ATR, TP2_ATR = 1.2, 1.5, 2.5
NET_MIN = 0.8              # 5m moves are smaller than 15m
FEE_LEG, TURNOVER = 0.0006, 2.0

syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]

def atr_series(df, n=20):
    h, l, c = df["high"], df["low"], df["close"]; pc = c.shift(1)
    tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def score_grind(o, h, l, c, t, side):
    """Mirror detect_grind: close-strength weighted, opposite candles
    penalized by THEIR body (strong opposite breaks the run)."""
    dir_cnt = 0; close_strs = []; counter_bodies = []
    for i in range(t - W + 1, t + 1):
        rng = max(h[i] - l[i], 1e-12)
        body = abs(c[i] - o[i]) / rng
        if side == "LONG":
            is_dir = c[i] > o[i]; close_pos = (c[i] - l[i]) / rng
        else:
            is_dir = c[i] < o[i]; close_pos = (h[i] - c[i]) / rng
        if is_dir:
            dir_cnt += 1; close_strs.append(close_pos * (0.4 + 0.6 * body))
        else:
            counter_bodies.append(body)
    cs = sum(close_strs) / len(close_strs) if close_strs else 0.0
    cb = sum(counter_bodies) / len(counter_bodies) if counter_bodies else 0.0
    net_abs = abs((c[t] / c[t - W] - 1.0) * 100) if c[t - W] > 0 else 0.0
    sc = float(np.clip(35 + cs * 35 + (dir_cnt - 3) * 4
                       + min(15, net_abs * 2.5) - cb * 18, 0, 100))
    return dir_cnt, sc

# gate -> list[(net_r, booked_partial, score)]
GATES = ("raw", "vol", "trend", "both")
acc = {g: [] for g in GATES}
t0 = time.time()
for ci, sym in enumerate(syms):
    try:
        df = binance_client.get_klines(sym, "5m", limit=LIMIT)
    except Exception:
        continue
    if df is None or len(df) < 400:
        continue
    df = df.reset_index(drop=True)
    o, h, l, c = (df[x].astype(float).to_numpy() for x in
                  ("open", "high", "low", "close"))
    v = df["volume"].astype(float).to_numpy()
    atr = atr_series(df).to_numpy()
    e20 = df["close"].ewm(span=20, adjust=False).mean().to_numpy()
    e40 = df["close"].ewm(span=40, adjust=False).mean().to_numpy()
    vma = pd.Series(v).rolling(20).mean().to_numpy()
    n = len(df)
    for t in range(210, n - FORWARD - 1):
        a = float(atr[t] or 0)
        if a <= 0 or c[t - W] <= 0:
            continue
        net = (c[t] / c[t - W] - 1.0) * 100
        if net >= NET_MIN and c[t] > e20[t]:
            side = "LONG"; dirc, sc = score_grind(o, h, l, c, t, "LONG")
        elif net <= -NET_MIN and c[t] < e20[t]:
            side = "SHORT"; dirc, sc = score_grind(o, h, l, c, t, "SHORT")
        else:
            continue
        # user spec: 7-candle window, >=5 directional (1-2 opposite ok)
        if dirc < 5 or sc < 50:
            continue
        vol_surge = vma[t] > 0 and v[t] > 1.5 * vma[t]
        trend_ok = (c[t] > e40[t]) if side == "LONG" else (c[t] < e40[t])
        # simulate scale-out once
        entry = c[t]
        stop = entry - SL_ATR*a if side == "LONG" else entry + SL_ATR*a
        tp1 = entry + TP1_ATR*a if side == "LONG" else entry - TP1_ATR*a
        tp2 = entry + TP2_ATR*a if side == "LONG" else entry - TP2_ATR*a
        PART = 0.5*(TP1_ATR/SL_ATR); RUN = 0.5*(TP2_ATR/SL_ATR)
        phase = "pre"; tp1_hit = False; res = None
        for fb in range(t + 1, min(t + FORWARD + 1, n)):
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
                        res = PART + RUN; break
            else:
                hbe = (fl <= entry) if side == "LONG" else (fh >= entry)
                h2 = (fh >= tp2) if side == "LONG" else (fl <= tp2)
                if hbe:
                    res = PART; break
                if h2:
                    res = PART + RUN; break
        if res is None:
            res = PART if tp1_hit else 0.0
        atr_pct = a / entry
        feeR = (FEE_LEG * TURNOVER) / (SL_ATR * max(atr_pct, 1e-9))
        net_r = res - feeR
        rec = (net_r, tp1_hit, sc)
        acc["raw"].append(rec)
        if vol_surge:
            acc["vol"].append(rec)
        if trend_ok:
            acc["trend"].append(rec)
        if vol_surge and trend_ok:
            acc["both"].append(rec)
    print(f"  [{ci+1}/{N_COINS}] {sym:12} raw={len(acc['raw'])} "
          f"both={len(acc['both'])} ({time.time()-t0:.0f}s)", flush=True)

def rep(label, rows):
    if not rows:
        print(f"  {label:28}: (none)"); return
    n = len(rows); exp = sum(r[0] for r in rows)/n
    green = sum(1 for r in rows if r[1])/n*100
    print(f"  {label:28}: n={n:5}  booked-partial {green:5.1f}%  "
          f"exp {exp:+.3f}R")

print("\n" + "=" * 72)
print(f"5m GRIND early-detection — {N_COINS} coins ~14d, AFTER fees")
print("  7-candle, >=5 dir, close-strength>=50, opposite-strength penalized")
print("  scale-out SL1.2/TP1 1.5/TP2 2.5 ATR")
print("=" * 72)
for g in GATES:
    rep({"raw": "RAW 5m grind",
         "vol": "+ volume surge (>1.5x)",
         "trend": "+ trend (EMA40 aligned)",
         "both": "+ BOTH (user's combo)"}[g], acc[g])
print("\n--- '+both' by close-strength bucket ---")
both = acc["both"]
for lo, hi in ((50, 60), (60, 70), (70, 80), (80, 101)):
    rep(f"  score {lo}-{hi-1}", [r for r in both if lo <= r[2] < hi])
print(f"\nDone in {time.time()-t0:.0f}s.")
