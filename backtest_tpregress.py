"""🔎 WHAT CHANGED — the Aug-30 TP swap, tested on a full year.

The user's read: "confidence score previously at 28th august was so good,
everything was working, now things are falling."

Git says the personal watch shipped 2026-08-29 (c3212db) with:
    SL  = swing low(10) - 0.25*ATR, 4*ATR cap, plan fallback
    TP1 = entry + 1.00 x R          ← exactly 1:1
and on 2026-08-30 the TP was replaced twice in one day:
    dd6c828  TP1 = 1.25R on strength entries, 1.00R when quiet
    cd9cd2e  TP1 = the 24h-high benchmark, CLIPPED to
             [0.75R, 1.25R] quiet   /   [1.00R, 2.50R] strong

The stop engine did not meaningfully change (114a1a9 only routed the
same swing-low maths through smart_stop). So the TP is the one real
geometry change — and the clip floor of 0.75R means quiet entries can
now be handed a target SMALLER than their own risk.

This replays all three policies over the SAME fires on the SAME bars,
so the only difference is the target. Reads the klines cached by
backtest_conflong.py under .longkl/ — no refetching.
"""
import io
import json
import os
import sys

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import numpy as np
import pandas as pd

import config

FEE = 0.00055
MAX_HOLD = 48
CACHE = ".longkl"

POLICIES = [
    ("A  1:1 flat        (Aug 29 ORIGINAL)", "orig"),
    ("B  1.25R / 1.0R    (Aug 30 dd6c828)", "x125"),
    ("C  benchmark clip  (Aug 30 cd9cd2e — LIVE NOW)", "bench"),
    ("D  1.5R flat       (never shipped)", "r15"),
    ("E  2.0R flat       (never shipped)", "r20"),
]

rows = []
for sym in getattr(config, "PERSONAL_WATCH", []):
    path = os.path.join(CACHE, f"{sym}_1h.csv")
    if not os.path.exists(path):
        continue
    d = pd.read_csv(path, index_col=0, parse_dates=True)
    if len(d) < 300:
        continue
    o = d["open"].to_numpy(); h = d["high"].to_numpy()
    lo = d["low"].to_numpy(); c = d["close"].to_numpy()
    v = d["volume"].to_numpy()
    ema = d["close"].ewm(span=20, adjust=False).mean().to_numpy()
    tr = h - lo
    n = len(c)

    for i in range(120, n - MAX_HOLD - 2):
        vma = float(v[i - 20:i].mean())
        if not (c[i] > o[i] and c[i] > c[i - 1] and c[i] > ema[i]
                and vma > 0 and v[i] > 1.2 * vma):
            continue
        if sum(1 for k in range(i - 5, i)
               if c[k] < o[k] or c[k] < ema[k]) < 2:
            continue
        entry = float(o[i + 1])
        atr = float(tr[i - 13:i + 1].mean())
        if entry <= 0 or atr <= 0:
            continue
        # the stop, exactly as the ORIGINAL shipped it (unchanged since)
        sl = float(lo[i - 9:i + 1].min()) - 0.25 * atr
        if not (0 < entry - sl <= 4 * atr):
            sl = entry - 1.5 * atr
        r = entry - sl
        if r <= 0:
            continue

        atr_hist = [float(tr[j - 14:j].mean())
                    for j in range(max(15, i - 99), i + 1)]
        atr_now = float(tr[i - 13:i + 1].mean())
        strong = (sum(1 for x in atr_hist if x < atr_now)
                  / len(atr_hist) >= 0.6) if atr_hist else False

        bench = float(h[i - 23:i + 1].max())
        br = (bench - entry) / r
        blo, bhi = (1.0, 2.5) if strong else (0.75, 1.25)
        clip = min(max(br, blo), bhi) if br > 0 else blo

        mult = {"orig": 1.0,
                "x125": 1.25 if strong else 1.0,
                "bench": clip,
                "r15": 1.5,
                "r20": 2.0}

        # one forward walk; first-touch index for stop and each target
        fh = h[i + 1:i + 1 + MAX_HOLD]
        fl = lo[i + 1:i + 1 + MAX_HOLD]
        if not len(fh):
            continue
        stop_hits = np.nonzero(fl <= sl)[0]
        i_stop = int(stop_hits[0]) if len(stop_hits) else 10**9
        last_c = float(c[min(i + MAX_HOLD, n - 1)])
        fee_r = 2 * FEE * entry / r

        rec = {"sym": sym, "ts": str(d.index[i]), "strong": bool(strong)}
        for _, key in POLICIES:
            tp = entry + mult[key] * r
            tp_hits = np.nonzero(fh >= tp)[0]
            i_tp = int(tp_hits[0]) if len(tp_hits) else 10**9
            if i_stop <= i_tp and i_stop < 10**9:      # stop first (tie=stop)
                net = -1.0 - fee_r
            elif i_tp < 10**9:
                net = mult[key] - fee_r
            else:
                net = (last_c - entry) / r - fee_r
            rec[key] = round(net, 4)
        rows.append(rec)

rows.sort(key=lambda x: x["ts"])
t = len(rows) // 3
for k, x in enumerate(rows):
    x["third"] = "T1" if k < t else ("T2" if k < 2 * t else "T3")
with open(".tpregress_rows.jsonl", "w", encoding="utf-8") as f:
    for x in rows:
        f.write(json.dumps(x) + "\n")


def stat(sel, key):
    n = len(sel)
    if not n:
        return 0, 0.0, 0.0
    w = sum(1 for x in sel if x[key] > 0) / n * 100
    return n, w, sum(x[key] for x in sel) / n


print("=" * 84)
print(f"🔎 SAME {len(rows)} FIRES, SAME STOP, ONLY THE TARGET CHANGES")
print(f"   {rows[0]['ts'][:10]} → {rows[-1]['ts'][:10]}")
print("=" * 84)
print(f"  {'policy':<48} {'win':>7} {'per trade':>11}   T1 / T2 / T3")
for label, key in POLICIES:
    n, w, e = stat(rows, key)
    th = "  ".join(f"{stat([x for x in rows if x['third'] == t3], key)[2]:+.3f}"
                   for t3 in ("T1", "T2", "T3"))
    print(f"  {label:<48} {w:6.1f}% {e:+10.3f}R   {th}")

print("\n  ── split by strength (the clip only bites the quiet ones) ──")
for grp, name in ((True, "STRONG entries"), (False, "QUIET entries")):
    sel = [x for x in rows if x["strong"] is grp]
    print(f"\n  {name}  (n={len(sel)})")
    for label, key in POLICIES:
        n, w, e = stat(sel, key)
        print(f"    {label:<46} {w:6.1f}% {e:+10.3f}R")
print("=" * 84)
