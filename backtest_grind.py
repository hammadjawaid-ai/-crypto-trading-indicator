"""Walk-forward backtest for the CANDLE-STRENGTH GRIND detector.

Faithfully mirrors velocity_burst.detect_grind (the 2026-06-12 rebuild):
over the last 7 15m candles, count directional bars, weight by how
strongly each closes in its range ((c-l)/range for LONG), require
net>=1.0% and price>EMA20. SHORT mirrors. Then simulates the SCAN's
actual grind plan:

    SL  = 1.2 ATR   (risk unit = 1R)
    TP1 = 1.5 ATR   (book half) -> stop to breakeven
    TP2 = 2.5 ATR   (runner)

No lookahead. Splits results by close-strength score bucket and by
30m-equiv alignment so we can see whether strong closes actually
predict follow-through (the whole point of the redefinition).
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
TP1_MULT = 1.5
TP2_MULT = 2.5
W = 7                 # grind window (matches detect_grind)

print(f"Fetching top {N_COINS}…")
syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]

def atr_series(df, n=20):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def score_grind(o, h, l, c, t, side):
    """EXACT mirror of detect_grind._run + _score for bar t."""
    dir_cnt = 0
    close_strs = []
    counter_bodies = []
    for i in range(t - W + 1, t + 1):
        rng = max(h[i] - l[i], 1e-12)
        body = abs(c[i] - o[i]) / rng
        if side == "LONG":
            is_dir = c[i] > o[i]
            close_pos = (c[i] - l[i]) / rng
        else:
            is_dir = c[i] < o[i]
            close_pos = (h[i] - c[i]) / rng
        if is_dir:
            dir_cnt += 1
            close_strs.append(close_pos * (0.4 + 0.6 * body))
        else:
            counter_bodies.append(body)
    cs = sum(close_strs) / len(close_strs) if close_strs else 0.0
    cb = sum(counter_bodies) / len(counter_bodies) if counter_bodies else 0.0
    net_abs = abs((c[t] / c[t - W] - 1.0) * 100) if c[t - W] > 0 else 0.0
    sc = float(np.clip(35 + cs * 35 + (dir_cnt - 3) * 4
                       + min(15, net_abs * 2.5) - cb * 18, 0, 100))
    return dir_cnt, cs, sc

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
    o = df["open"].astype(float).to_numpy()
    h = df["high"].astype(float).to_numpy()
    l = df["low"].astype(float).to_numpy()
    c = df["close"].astype(float).to_numpy()
    atr = atr_series(df).to_numpy()
    ema20 = df["close"].ewm(span=20, adjust=False).mean().to_numpy()
    # 30m-equiv trend proxy: 15m EMA40 ~ 30m EMA20, EMA100 ~ 30m EMA50
    ema40 = df["close"].ewm(span=40, adjust=False).mean().to_numpy()
    ema100 = df["close"].ewm(span=100, adjust=False).mean().to_numpy()
    n = len(df)
    for t in range(210, n - FORWARD - 1):
        a = float(atr[t] or 0)
        if a <= 0 or c[t - W] <= 0:
            continue
        net = (c[t] / c[t - W] - 1.0) * 100
        # detect (mirror detect_grind gates)
        if net >= 1.0 and c[t] > ema20[t]:
            dl, _csl, sc = score_grind(o, h, l, c, t, "LONG")
            if dl >= 3 and sc >= 50:
                side = "LONG"
            else:
                continue
        elif net <= -1.0 and c[t] < ema20[t]:
            ds, _css, sc = score_grind(o, h, l, c, t, "SHORT")
            if ds >= 3 and sc >= 50:
                side = "SHORT"
            else:
                continue
        else:
            continue
        # 30m-equiv alignment: trend not against + 4/6 30m candles run our way
        if side == "LONG":
            trend_ok = c[t] > ema40[t]
        else:
            trend_ok = c[t] < ema40[t]
        h30_dir = 0
        for k in range(1, 7):
            a_i, b_i = t - 2 * (k - 1), t - 2 * k
            if b_i < 0:
                break
            up = c[a_i] > c[b_i]
            if (side == "LONG" and up) or (side == "SHORT" and not up):
                h30_dir += 1
        aligned = trend_ok and h30_dir >= 4
        # STRICT-RUN slice (the earlier +0.116R candidate): firm run
        # net>=2.5% over 8 candles + >=5 directional, plus "very early"
        # (last-4-candle move still small, <4%).
        net8 = (c[t] / c[t - 8] - 1.0) * 100 if c[t - 8] > 0 else 0.0
        if side == "LONG":
            dir8 = sum(1 for i in range(t - 7, t + 1) if c[i] > c[i - 1])
            strict_run = net8 >= 2.5 and dir8 >= 5
        else:
            dir8 = sum(1 for i in range(t - 7, t + 1) if c[i] < c[i - 1])
            strict_run = net8 <= -2.5 and dir8 >= 5
        move4 = abs((c[t] / c[t - 4] - 1.0) * 100) if c[t - 4] > 0 else 99.0
        very_early = move4 < 4.0
        # scale-out plan (matches scan): SL 1.2 / TP1 1.5 / TP2 2.5 ATR
        entry = c[t]
        if side == "LONG":
            stop = entry - SL_MULT * a
            tp1 = entry + TP1_MULT * a
            tp2 = entry + TP2_MULT * a
        else:
            stop = entry + SL_MULT * a
            tp1 = entry - TP1_MULT * a
            tp2 = entry - TP2_MULT * a
        PART = 0.5 * (TP1_MULT / SL_MULT)   # +0.625R booked at TP1 (half)
        RUN = 0.5 * (TP2_MULT / SL_MULT)    # +1.042R if runner hits TP2
        phase = "pre"; tp1_hit = False; res = None
        for fb in range(1, FORWARD + 1):
            fh = h[t + fb]; fl = l[t + fb]
            if phase == "pre":
                hit_stop = (fl <= stop) if side == "LONG" else (fh >= stop)
                hit_tp1 = (fh >= tp1) if side == "LONG" else (fl <= tp1)
                if hit_stop:
                    res = -1.0; break
                if hit_tp1:
                    tp1_hit = True; phase = "runner"
                    hit_tp2 = (fh >= tp2) if side == "LONG" else (fl <= tp2)
                    if hit_tp2:
                        res = PART + RUN; break
            else:
                hit_be = (fl <= entry) if side == "LONG" else (fh >= entry)
                hit_tp2 = (fh >= tp2) if side == "LONG" else (fl <= tp2)
                if hit_be:
                    res = PART; break
                if hit_tp2:
                    res = PART + RUN; break
        if res is None:
            res = PART if tp1_hit else 0.0
        sigs.append((side, aligned, res, tp1_hit, sc, strict_run, very_early))
    print(f"  [{idx+1}/{N_COINS}] {sym:12} cum {len(sigs)} "
          f"({time.time()-t0:.0f}s)")

def scaleout(rows):
    if not rows:
        return 0, 0.0, 0.0
    n = len(rows)
    green = sum(1 for r in rows if r[3]) / n * 100      # booked partial
    exp = sum(r[2] for r in rows) / n
    full = sum(1 for r in rows if r[2] > 0.7) / n * 100  # runner ran
    return green, exp, full

def report(label, rows):
    if not rows:
        print(f"\n{label}: (none)"); return
    g, e, fw = scaleout(rows)
    print(f"\n{label} (n={len(rows)}):")
    print(f"   GREEN rate (booked +1.5ATR partial): {g:5.1f}%")
    print(f"   runner-to-TP2 rate:                  {fw:5.1f}%")
    print(f"   expectancy:                           {e:+.3f}R")

print("\n" + "="*64)
print(f"15m CANDLE-STRENGTH GRIND — {len(sigs)} sigs, {N_COINS} coins, ~30d")
print("  >=3/7 dir candles + close-strength score>=50 + net>=1% + >EMA20")
print("  SL 1.2 / TP1 1.5 (half) -> BE -> TP2 2.5 ATR")
print("="*64)
report("ALL fired (any score/align)", sigs)
_al = [r for r in sigs if r[1]]   # 30m-aligned only
report("30m-ALIGNED (any score)", _al)
print("\n--- 30m-ALIGNED, by close-strength score bucket ---")
report("  score 50-59 + 30m", [r for r in _al if 50 <= r[4] < 60])
report("  score 60-69 + 30m", [r for r in _al if 60 <= r[4] < 70])
report("  score 70-79 + 30m", [r for r in _al if 70 <= r[4] < 80])
report("  score 80+   + 30m", [r for r in _al if r[4] >= 80])
print("\n--- STRICT-RUN slice (the +0.116R candidate) ---")
report("  strict-run + 30m-aligned",
       [r for r in sigs if r[5] and r[1]])
report("  strict-run + 30m-aligned + very-early",
       [r for r in sigs if r[5] and r[1] and r[6]])
print(f"\nDone in {time.time()-t0:.0f}s.")
