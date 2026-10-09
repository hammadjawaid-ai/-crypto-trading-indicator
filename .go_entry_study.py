"""GO-entry stops — why the go_revived ledger bleeds and what a re-based stop does.
Every star_go stamp in the 09-28 desk copy (symbol, side, ts, fire entry0, fire
stop, tp1) replayed on the 15m cache: enter at the close of the GO bar, exits
(a) FIRE stop (what go_revived / star_go_chase do today), (b) IGNITION-BASE
stop = min low of the 4 bars before the GO bar - 0.25 ATR, (c) HALF: midway
between entry and the fire stop; TP1 = the fire's TP1 (bank), 24h time exit,
fees 0.11%; stop before TP inside a bar. Split DEAD->GO (revived) vs LIVE->GO
using the elite_1h stamp before the GO."""
import glob
import io
import json
import os
import sqlite3
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"F:\Trading Indicator"
D = os.path.join(ROOT, ".dip_kl")
DB = sys.argv[1]
FEE = 0.0011
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
gos = con.execute("SELECT ts, symbol, side, tier, score, entry, stop, tp1, extra FROM signals WHERE stream='star_go' ORDER BY ts").fetchall()
vd = defaultdict(list)
for s, d, ts, t in con.execute("SELECT symbol, side, ts, tier FROM signals WHERE stream='elite_1h'"):
    vd[(s, (d or "").upper())].append((float(ts), t))
cache = {}


def kl(sym):
    if sym not in cache:
        f = os.path.join(D, f"{sym}.csv")
        if not os.path.exists(f):
            cache[sym] = None
        else:
            k = pd.read_csv(f).drop_duplicates("ot").set_index("ot").sort_index()
            k.index = k.index // 1000
            tr = np.maximum(k["h"] - k["l"], np.maximum((k["h"] - k["c"].shift()).abs(), (k["l"] - k["c"].shift()).abs()))
            k["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
            cache[sym] = k
    return cache[sym]


rows = []
for ts, sym, side, tier, score, e0, stop, tp1, ex in gos:
    k = kl(sym)
    if k is None:
        continue
    side = (side or "").upper(); sg = 1 if side == "LONG" else -1
    bar = int(float(ts) // 900 * 900)
    if bar not in k.index:
        continue
    pos = k.index.get_loc(bar)
    if pos < 6 or pos + 96 >= len(k):
        continue
    e = float(k["c"].iloc[pos])
    stop_f = float(stop); tp = float(tp1)
    base = k["l"].iloc[pos - 4:pos].min() if sg == 1 else k["h"].iloc[pos - 4:pos].max()
    stop_b = base - sg * 0.25 * float(k["atr"].iloc[pos])
    stop_h = e - sg * abs(e - stop_f) / 2
    v = [t for t_, t in vd.get((sym, side), ()) if float(ts) - 3 * 3600 <= t_ <= float(ts)]
    oneh = v[-1] if v else "?"
    out = {}
    for lab, st in (("fire", stop_f), ("base", stop_b), ("half", stop_h)):
        risk = sg * (e - st)
        if risk <= 0 or risk < 0.002 * e:
            out[lab] = None
            continue
        px = float(k["c"].iloc[pos + 96])
        for j in range(pos + 1, pos + 97):
            lo, hi = float(k["l"].iloc[j]), float(k["h"].iloc[j])
            if (sg == 1 and lo <= st) or (sg == -1 and hi >= st):
                px = st; break
            if (sg == 1 and hi >= tp) or (sg == -1 and lo <= tp):
                px = tp; break
        pct = sg * (px / e - 1) - FEE
        r = sg * (px - e) / risk - FEE * e / risk
        out[lab] = (pct, r, risk / e)
    rows.append((ts, sym, side, tier, oneh, out))
print(f"star_go stamps replayed: {len(rows)} (of {len(gos)})")


def cell(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return "—"
    p = np.array([x[0] for x in xs]); r = np.array([x[1] for x in xs]); rk = np.array([x[2] for x in xs])
    return f"{(p > 0).mean() * 100:4.0f}% win · {p.mean() * 100:+.2f}% · {r.mean():+.2f}R · risk {np.median(rk) * 100:.1f}% (n={len(p)})"


for lab in ("fire", "base", "half"):
    print(f"\nstop = {lab:4s}: ALL      {cell([o[lab] for *_, o in rows])}")
    print(f"            DEAD->GO {cell([o[lab] for *_, oneh, o in rows if oneh == 'DEAD'])}")
    print(f"            LIVE->GO {cell([o[lab] for *_, oneh, o in rows if oneh == 'LIVE'])}")
    print(f"            FAST     {cell([o[lab] for _, _, _, t, _, o in rows if t == 'FAST'])}  ·  LATE {cell([o[lab] for _, _, _, t, _, o in rows if t == 'LATE'])}")
    print(f"            LONG     {cell([o[lab] for _, _, d, _, _, o in rows if d == 'LONG'])}  ·  SHORT {cell([o[lab] for _, _, d, _, _, o in rows if d == 'SHORT'])}")
