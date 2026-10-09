"""Print ORDER — is the higher close AFTER a failed first bounce and a new low (the
08 Oct 23:15 PKT case) better than the first print? Per dump: the sequence of
prints (first higher close with no new low; re-armed by a new low; max 3 within
6h). Per print order: the alt basket trade (next open, stop under the low -
0.25 ATR, TP 1.5R, 8h, fees), the raw 8h basket return, and BTC's OWN trade and
8h return with the same rule ("go all in with BTC reclaiming")."""
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
t0 = time.time()
B = pd.read_csv(os.path.join(D, "BTCUSDT.csv")).drop_duplicates("ot").sort_values("ot").reset_index(drop=True)
bo, bh, bl, bc = (B[k].astype(float).to_numpy() for k in ("o", "h", "l", "c"))
bt = B["ot"].to_numpy()
N = len(B)
btr = np.maximum(bh - bl, np.maximum(abs(bh - np.roll(bc, 1)), abs(bl - np.roll(bc, 1))))
batr = pd.Series(btr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
hi12 = pd.Series(bh).rolling(48).max().to_numpy()
dd = bc / hi12 - 1.0
shocks, last = [], -10 ** 9
for i in range(700, N - 40):
    if dd[i] <= -0.02 and dd[i - 1] > -0.02 and i - last >= 96:
        shocks.append(i)
        last = i
O, H, L, C, A = [], [], [], [], []
for f in sorted(glob.glob(os.path.join(D, "*USDT.csv"))):
    if os.path.basename(f) == "BTCUSDT.csv":
        continue
    k = pd.read_csv(f).drop_duplicates("ot").set_index("ot").sort_index()
    if len(k) < 5000:
        continue
    k = k.reindex(bt)
    o, h, l, c = (k[x].astype(float).to_numpy() for x in ("o", "h", "l", "c"))
    tr = np.maximum(h - l, np.maximum(abs(h - np.roll(c, 1)), abs(l - np.roll(c, 1))))
    O.append(o); H.append(h); L.append(l); C.append(c); A.append(pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy())
O, H, L, C, A = (np.vstack(x) for x in (O, H, L, C, A))
valid = ~np.isnan(C)
M = O.shape[0]


def basket(i0, ie):
    j = ie + 1
    e = O[:, j]
    stop = np.nanmin(L[:, i0:ie + 1], axis=1) - 0.25 * A[:, ie]
    risk = e - stop
    ok = valid[:, j] & (risk >= 0.003 * e) & (risk <= 0.15 * e) & ~np.isnan(A[:, ie])
    tp = e + 1.5 * risk
    px = C[:, j + 31].copy(); done = np.zeros(M, dtype=bool)
    for k in range(j, j + 32):
        s_ = (~done) & (L[:, k] <= stop); px[s_] = stop[s_]; done |= s_
        t_ = (~done) & (H[:, k] >= tp); px[t_] = tp[t_]; done |= t_
    pct = (px / e - 1 - FEE)[ok]
    raw = (C[:, j + 31] / e - 1)[ok]
    return pct.mean(), (pct > 0).mean(), np.median(raw)


def btc_trade(i0, ie):
    j = ie + 1
    e = bo[j]
    stop = bl[i0:ie + 1].min() - 0.25 * batr[ie]
    risk = e - stop
    if risk <= 0.002 * e:
        return None
    tp = e + 1.5 * risk
    px = bc[j + 31]
    for k in range(j, j + 32):
        if bl[k] <= stop:
            px = stop; break
        if bh[k] >= tp:
            px = tp; break
    return px / e - 1 - FEE, (px - e) / risk - FEE * e / risk, bc[j + 31] / e - 1, bh[j:j + 32].max() / e - 1


rows = []
for i0 in shocks:
    low, printed_low, last_print, order = bl[i0], None, -1, 0
    for i in range(i0 + 1, min(i0 + 24, N - 40)):
        if bl[i] < low:
            low = bl[i]
        elif bc[i] > bh[i - 1] and bl[i] >= low and (printed_low is None or low < printed_low) and i > last_print and order < 3:
            order += 1; printed_low = low; last_print = i
            bp, bpos, braw = basket(i0, i)
            bt_ = btc_trade(i0, i)
            rows.append(dict(t=bt[i0], order=order, pct=bp, pos=bpos, raw=braw, lag=(i - i0) * 15,
                             btc_pct=bt_[0] if bt_ else np.nan, btc_r=bt_[1] if bt_ else np.nan,
                             btc_raw=bt_[2] if bt_ else np.nan, btc_mfe=bt_[3] if bt_ else np.nan))
R = pd.DataFrame(rows)
print(f"shocks {len(shocks)} · prints {len(R)} · compute {time.time() - t0:.0f}s")
print(f"\n{'print':6s} {'n':>4s} {'basket%':>8s} {'coinwin':>7s} {'raw8h med':>9s} | {'BTC trade%':>10s} {'BTC R':>6s} {'BTC win':>7s} {'BTC raw8h':>9s} {'BTC best8h':>10s}")
for k_, g in R.groupby("order"):
    print(f"#{k_:<5d} {len(g):4d} {g.pct.mean() * 100:+8.2f} {g.pos.mean() * 100:6.0f}% {g.raw.median() * 100:+9.2f} | "
          f"{g.btc_pct.mean() * 100:+10.2f} {g.btc_r.mean():+6.2f} {(g.btc_pct > 0).mean() * 100:6.0f}% {g.btc_raw.median() * 100:+9.2f} {g.btc_mfe.median() * 100:+10.2f}")
only1 = R.groupby("t")["order"].max()
print(f"\ndumps with exactly one print: {(only1 == 1).sum()} · two: {(only1 == 2).sum()} · three: {(only1 == 3).sum()}")
g2 = R[R.order == 2]
print(f"second prints: baskets positive {(g2.pct > 0).mean() * 100:.0f}% · BTC trade positive {(g2.btc_pct > 0).mean() * 100:.0f}% · "
      f"thirds basket {'/'.join(f'{x * 100:+.1f}' for x in np.array_split(g2.sort_values('t').pct.to_numpy(), 3).__iter__() and [p.mean() for p in np.array_split(g2.sort_values('t').pct.to_numpy(), 3)])}")
