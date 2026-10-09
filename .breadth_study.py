"""🌊 BREADTH THRUST — does "every coin" know the bottom when BTC alone does not?

After each BTC dump >= 2% vs its 12h high (same 165 shocks as .bottom_study.py),
look bar by bar for a MARKET-WIDE print: the share of coins whose 15m close is
above their previous bar's high (B_hh), and the share whose 1h return is >=
+1.5% (B_1h). Signal = first bar within 6h where breadth >= THR. Same alt trade
as the bottom study (next open, stop = low since the crossing - 0.25 ATR, TP
1.5R, 8h, fees) + the raw 8h basket return, vs the BTC-only higher-close rule
and the hindsight ceiling. Also: breadth at the 08 Oct fake (21:15 PKT) vs the
real print (23:15 PKT) from the forensic CSV is reported by .bottom_1008 — here
we only need history."""
import glob
import io
import os
import sys
import time

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"F:\Trading Indicator"
D = os.path.join(ROOT, ".dip_kl")
FEE = 0.0011
PK = 5 * 3600
t0 = time.time()

B = pd.read_csv(os.path.join(D, "BTCUSDT.csv")).drop_duplicates("ot").sort_values("ot").reset_index(drop=True)
bo, bh, bl, bc = (B[k].astype(float).to_numpy() for k in ("o", "h", "l", "c"))
bt = B["ot"].to_numpy()
N = len(B)
hi12 = pd.Series(bh).rolling(48).max().to_numpy()
dd = bc / hi12 - 1.0
shocks, last = [], -10 ** 9
for i in range(700, N - 40):
    if dd[i] <= -0.02 and dd[i - 1] > -0.02 and i - last >= 96:
        shocks.append(i)
        last = i

syms, O, H, L, C, A = [], [], [], [], [], []
for f in sorted(glob.glob(os.path.join(D, "*USDT.csv"))):
    sym = os.path.basename(f)[:-4]
    if sym == "BTCUSDT":
        continue
    k = pd.read_csv(f).drop_duplicates("ot").set_index("ot").sort_index()
    if len(k) < 5000:
        continue
    k = k.reindex(bt)
    o, h, l, c = (k[x].astype(float).to_numpy() for x in ("o", "h", "l", "c"))
    tr = np.maximum(h - l, np.maximum(abs(h - np.roll(c, 1)), abs(l - np.roll(c, 1))))
    a = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    syms.append(sym); O.append(o); H.append(h); L.append(l); C.append(c); A.append(a)
O, H, L, C, A = (np.vstack(x) for x in (O, H, L, C, A))
M = len(syms)
prevH = np.roll(H, 1, axis=1)
hh_mat = (C > prevH)                                    # coin printed a higher close
r1h = C / np.roll(C, 4, axis=1) - 1.0
up_mat = r1h >= 0.015
valid = ~np.isnan(C)
B_hh = np.where(valid, hh_mat, False).sum(0) / np.maximum(valid.sum(0), 1)
B_1h = np.where(valid, up_mat, False).sum(0) / np.maximum(valid.sum(0), 1)
print(f"coins {M} · shocks {len(shocks)} · prep {time.time() - t0:.0f}s")


def trade_all(i0, ie):
    j = ie + 1
    e = O[:, j]
    low_since = np.nanmin(L[:, i0:ie + 1], axis=1)
    stop = low_since - 0.25 * A[:, ie]
    risk = e - stop
    ok = valid[:, j] & (risk >= 0.003 * e) & (risk <= 0.15 * e) & ~np.isnan(A[:, ie])
    tp = e + 1.5 * risk
    px = C[:, j + 31].copy()
    done = np.zeros(M, dtype=bool)
    for k in range(j, j + 32):
        hit_s = (~done) & (L[:, k] <= stop)
        px[hit_s] = stop[hit_s]; done |= hit_s
        hit_t = (~done) & (H[:, k] >= tp)
        px[hit_t] = tp[hit_t]; done |= hit_t
    pct = px / e - 1 - FEE
    r = (px - e) / risk - FEE * e / risk
    raw = C[:, j + 31] / e - 1
    return pct[ok], r[ok], raw[ok]


def first_bar(i0, cond):
    for i in range(i0 + 1, min(i0 + 24, N - 40)):
        if cond(i):
            return i
    return None


def hh_bar(i0):
    runlow = bl[i0]
    for i in range(i0 + 1, min(i0 + 24, N - 40)):
        if bl[i] < runlow:
            runlow = bl[i]
        elif bc[i] > bh[i - 1] and bl[i] >= runlow:
            return i
    return None


def low_bar(i0):
    seg = bl[i0:i0 + 24]
    return i0 + int(np.argmin(seg))


rules = {"btc_hh": lambda i0: hh_bar(i0), "hindsight": lambda i0: min(low_bar(i0) + 1, N - 41)}
for thr in (0.4, 0.5, 0.6, 0.7):
    rules[f"B_hh>={int(thr * 100)}"] = (lambda th: (lambda i0: first_bar(i0, lambda i: B_hh[i] >= th)))(thr)
for thr in (0.3, 0.4, 0.5, 0.6):
    rules[f"B_1h>={int(thr * 100)}"] = (lambda th: (lambda i0: first_bar(i0, lambda i: B_1h[i] >= th)))(thr)
# combined: breadth thrust AND BTC not making a new low on that bar
rules["B_hh>=50&btc_hh"] = lambda i0: (lambda a, b: max(a, b) if a is not None and b is not None else None)(
    first_bar(i0, lambda i: B_hh[i] >= 0.5), hh_bar(i0))

print(f"\n{'rule':16s} {'n':>4s} {'basket%':>8s} {'R/coin':>7s} {'coinwin':>7s} {'bask>0':>6s} {'raw8h med%':>10s} {'thirds':>18s} {'lag(min) med':>12s}")
rows = []
for name, fn in rules.items():
    res = []
    for i0 in shocks:
        ie = fn(i0)
        if ie is None:
            continue
        pct, r, raw = trade_all(i0, ie)
        if len(pct) < 20:
            continue
        res.append((bt[i0], pct.mean(), r.mean(), (pct > 0).mean(), np.median(raw), (ie - low_bar(i0)) * 15, B_hh[ie], B_1h[ie]))
    if len(res) < 10:
        print(f"{name:16s} {len(res):4d}  (too few)")
        continue
    g = pd.DataFrame(res, columns=["t", "pct", "r", "win", "raw", "lag", "bhh", "b1h"]).sort_values("t")
    k = len(g) // 3
    th = "/".join(f"{x * 100:+.1f}" for x in (g.pct.iloc[:k].mean(), g.pct.iloc[k:2 * k].mean(), g.pct.iloc[2 * k:].mean()))
    print(f"{name:16s} {len(g):4d} {g.pct.mean() * 100:+8.2f} {g.r.mean():+7.3f} {g.win.mean() * 100:6.0f}% {(g.pct > 0).mean() * 100:5.0f}% "
          f"{g.raw.median() * 100:+9.2f} {th:>18s} {g.lag.median():10.0f}")
    rows.append(dict(rule=name, n=len(g), pct=g.pct.mean(), r=g.r.mean(), pos=(g.pct > 0).mean()))
# breadth at the BTC higher-close print: does the LEVEL of breadth sort the outcome?
res = []
for i0 in shocks:
    ie = hh_bar(i0)
    if ie is None:
        continue
    pct, r, raw = trade_all(i0, ie)
    if len(pct) >= 20:
        res.append((B_hh[ie], B_1h[ie], pct.mean(), np.median(raw)))
g = pd.DataFrame(res, columns=["bhh", "b1h", "pct", "raw"])
print("\nAt the BTC higher-close print, basket% by breadth quartile (share of coins also printing a higher close):")
g["q"] = pd.qcut(g.bhh, 4, labels=["lowest", "low", "high", "highest"], duplicates="drop")
print(g.groupby("q")["pct"].agg(["mean", "count"]).assign(mean=lambda x: (x["mean"] * 100).round(2)).to_string())
print("by 1h-up breadth quartile:")
g["q2"] = pd.qcut(g.b1h, 4, labels=["lowest", "low", "high", "highest"], duplicates="drop")
print(g.groupby("q2")["pct"].agg(["mean", "count"]).assign(mean=lambda x: (x["mean"] * 100).round(2)).to_string())
print(f"\ncompute {time.time() - t0:.0f}s")
