"""🏇 BOUNCE RIDER — "catch them when they move" (user 2026-10-09: DOT / APT /
ONDO / TIA kept going for hours after the 23:00 PKT low). Not the bottom, not
calm + 2h: enter a coin INSIDE the first hours after a BTC dump once its own
momentum is visible.

Per BTC dump (>= 2% vs 12h high, one per 24h, 165 of them), from the crossing
for WINDOW_H hours, bar by bar, a coin qualifies the first time ALL hold:
  - up >= MOVE from its post-crossing low (the bounce is visible)
  - its 1h return beats BTC's 1h return by >= REL (it leads)
  - 1h quote volume >= VOLX x its 7-day hourly median (real participation)
  - it closes at a new high since the crossing (not a dead-cat wick)
Trade: next open, stop = post-crossing low - 0.25 ATR, TP 1.5R, 8h time exit,
fees 0.11%. Variants over MOVE / REL / VOLX / WINDOW; vs RANDOM moments and vs
the same rule with NO dump (a plain momentum rule any day). Also: what the
08-Oct-style names would have done (entries at +3% in the first hour)."""
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
rng = np.random.default_rng(11)
t0 = time.time()
B = pd.read_csv(os.path.join(D, "BTCUSDT.csv")).drop_duplicates("ot").sort_values("ot").reset_index(drop=True)
bh, bl, bc = (B[k].astype(float).to_numpy() for k in ("h", "l", "c"))
bt = B["ot"].to_numpy()
N = len(B)
hi12 = pd.Series(bh).rolling(48).max().to_numpy()
dd = bc / hi12 - 1.0
br1 = bc / np.roll(bc, 4) - 1.0
shocks, last = [], -10 ** 9
for i in range(700, N - 60):
    if dd[i] <= -0.02 and dd[i - 1] > -0.02 and i - last >= 96:
        shocks.append(i)
        last = i
syms, O, H, L, C, V, A = [], [], [], [], [], [], []
for f in sorted(glob.glob(os.path.join(D, "*USDT.csv"))):
    sym = os.path.basename(f)[:-4]
    if sym == "BTCUSDT":
        continue
    k = pd.read_csv(f).drop_duplicates("ot").set_index("ot").sort_index()
    if len(k) < 5000:
        continue
    k = k.reindex(bt)
    o, h, l, c, v = (k[x].astype(float).to_numpy() for x in ("o", "h", "l", "c", "v"))
    tr = np.maximum(h - l, np.maximum(abs(h - np.roll(c, 1)), abs(l - np.roll(c, 1))))
    syms.append(sym); O.append(o); H.append(h); L.append(l); C.append(c); V.append(v * c)
    A.append(pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy())
O, H, L, C, V, A = (np.vstack(x) for x in (O, H, L, C, V, A))
M = len(syms)
R1 = C / np.roll(C, 4, axis=1) - 1.0                                   # 1h return
V1 = V + np.roll(V, 1, axis=1) + np.roll(V, 2, axis=1) + np.roll(V, 3, axis=1)   # 1h quote volume
VMED = pd.DataFrame(V1.T).rolling(672, min_periods=200).median().to_numpy().T   # 7d hourly median
VX = V1 / np.where(VMED > 0, VMED, np.nan)
print(f"coins {M} · shocks {len(shocks)} · prep {time.time() - t0:.0f}s")


def rider(i0, move, rel, volx, window_bars, start_bar=1):
    """all qualifying (coin, entry bar) in the window; one entry per coin."""
    out = []
    lows = L[:, i0].copy()
    highs = C[:, i0].copy()
    taken = np.zeros(M, dtype=bool)
    for i in range(i0 + 1, min(i0 + window_bars, N - 40)):
        lows = np.fmin(lows, L[:, i])
        if i - i0 >= start_bar:
            cond = ((C[:, i] / lows - 1 >= move) & (R1[:, i] - br1[i] >= rel) & (VX[:, i] >= volx)
                    & (C[:, i] >= highs) & ~taken & ~np.isnan(C[:, i]))
            for m in np.where(cond)[0]:
                out.append((m, i, lows[m]))
                taken[m] = True
        highs = np.fmax(highs, C[:, i])
    return out


def settle(m, ie, low):
    j = ie + 1
    if j + 32 >= N or np.isnan(O[m, j]) or np.isnan(A[m, ie]):
        return None
    e = O[m, j]
    stop = low - 0.25 * A[m, ie]
    risk = e - stop
    if not (0.003 * e <= risk <= 0.15 * e):
        return None
    tp = e + 1.5 * risk
    px = C[m, j + 31]
    for k in range(j, j + 32):
        if L[m, k] <= stop:
            px = stop; break
        if H[m, k] >= tp:
            px = tp; break
    return px / e - 1 - FEE, (px - e) / risk - FEE * e / risk


def run(move, rel, volx, window_h, shock_list, label):
    res, per = [], []
    for i0 in shock_list:
        ent = rider(i0, move, rel, volx, int(window_h * 4))
        rr = [settle(m, ie, lo) for m, ie, lo in ent]
        rr = [x for x in rr if x is not None]
        res += rr
        if rr:
            per.append((bt[i0], np.mean([x[0] for x in rr]), len(rr)))
    if len(res) < 30:
        print(f"{label:34s} n={len(res)} (too few)")
        return
    p = np.array([x[0] for x in res]); r = np.array([x[1] for x in res])
    per = pd.DataFrame(per, columns=["t", "pct", "n"]).sort_values("t")
    k = len(per) // 3
    th = "/".join(f"{x * 100:+.1f}" for x in (per.pct.iloc[:k].mean(), per.pct.iloc[k:2 * k].mean(), per.pct.iloc[2 * k:].mean())) if k else "n/a"
    d3 = per.pct.sort_values().iloc[:-3].mean() if len(per) > 3 else np.nan
    print(f"{label:34s} trades {len(p):5d} · win {(p > 0).mean() * 100:3.0f}% · {p.mean() * 100:+.2f}% · {r.mean():+.3f}R · "
          f"dumps {len(per)} ({per.n.mean():.0f}/dump) · dumps>0 {(per.pct > 0).mean() * 100:.0f}% · thirds {th} · drop3 {d3 * 100:+.2f}")


print(f"\n{'variant':34s}")
for move, rel, volx, wh in ((0.03, 0.015, 1.5, 3), (0.03, 0.015, 1.5, 6), (0.02, 0.01, 1.5, 3), (0.04, 0.02, 2.0, 3),
                            (0.03, 0.03, 1.5, 3), (0.05, 0.02, 1.5, 6), (0.03, 0.015, 1.0, 3)):
    run(move, rel, volx, wh, shocks, f"move>={move:.0%} rel>={rel:.1%} vol>={volx:.1f}x {wh}h")
# control 1: the same rule on random non-dump starts (plain momentum, any day)
bad = np.zeros(N, dtype=bool)
for i0 in shocks:
    bad[max(0, i0 - 48):i0 + 96] = True
cands = np.where(~bad[700:N - 60])[0] + 700
rand_starts = list(rng.choice(cands, size=len(shocks), replace=False))
run(0.03, 0.015, 1.5, 3, rand_starts, "CONTROL same rule, no dump")
# 08-Oct style: entries only in the first hour after the dump's low, at >= +3%
print("\nfirst-hour-after-the-low variant (entry window 60 min after the running low is set):")


def rider_lowwin(i0, move=0.03, rel=0.015, volx=1.5):
    out = []
    lows = L[:, i0].copy(); taken = np.zeros(M, dtype=bool)
    blow, blow_at = bl[i0], i0
    for i in range(i0 + 1, min(i0 + 24, N - 40)):
        if bl[i] < blow:
            blow, blow_at = bl[i], i
        lows = np.fmin(lows, L[:, i])
        if 1 <= i - blow_at <= 4:
            cond = ((C[:, i] / lows - 1 >= move) & (R1[:, i] - br1[i] >= rel) & (VX[:, i] >= volx) & ~taken & ~np.isnan(C[:, i]))
            for m in np.where(cond)[0]:
                out.append((m, i, lows[m])); taken[m] = True
    return out


res, per = [], []
for i0 in shocks:
    rr = [settle(m, ie, lo) for m, ie, lo in rider_lowwin(i0)]
    rr = [x for x in rr if x is not None]
    res += rr
    if rr:
        per.append((bt[i0], np.mean([x[0] for x in rr]), len(rr)))
p = np.array([x[0] for x in res]); r = np.array([x[1] for x in res]); per = pd.DataFrame(per, columns=["t", "pct", "n"])
print(f"  trades {len(p)} · win {(p > 0).mean() * 100:.0f}% · {p.mean() * 100:+.2f}% · {r.mean():+.3f}R · dumps {len(per)} · dumps>0 {(per.pct > 0).mean() * 100:.0f}%")
print(f"\ncompute {time.time() - t0:.0f}s")
