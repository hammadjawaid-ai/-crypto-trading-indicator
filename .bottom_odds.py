"""Raw odds after a BTC bottom confirmation (no stop / TP): what the alt basket
did 8h later and how far it bounced at best — the numbers for an honest 🌊
information bell. Plus: desk record of SHORT fires inside a BTC shock window
(the failure mode of last night: revived GO shorts rung at the low)."""
import glob
import io
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"F:\Trading Indicator"
D = os.path.join(ROOT, ".dip_kl")
DB = sys.argv[1]
PK = 5 * 3600

B = pd.read_csv(os.path.join(D, "BTCUSDT.csv")).drop_duplicates("ot").sort_values("ot").reset_index(drop=True)
bo, bh, bl, bc = (B[k].astype(float).to_numpy() for k in ("o", "h", "l", "c"))
bt = B["ot"].to_numpy()
N = len(B)
hi12 = pd.Series(bh).rolling(48).max().to_numpy()
dd = bc / hi12 - 1.0

coins = {}
for f in sorted(glob.glob(os.path.join(D, "*USDT.csv"))):
    sym = os.path.basename(f)[:-4]
    if sym == "BTCUSDT":
        continue
    k = pd.read_csv(f).drop_duplicates("ot").set_index("ot").sort_index()
    if len(k) < 5000:
        continue
    k = k.reindex(bt)
    coins[sym] = (k["o"].astype(float).to_numpy(), k["h"].astype(float).to_numpy(), k["c"].astype(float).to_numpy())


def shocks_at(thr):
    out, last = [], -10 ** 9
    for i in range(700, N - 40):
        if dd[i] <= -thr and dd[i - 1] > -thr and i - last >= 96:
            out.append(i)
            last = i
    return out


def hh_bar(i0):
    runlow, lowbar = bl[i0], i0
    hh = None
    for i in range(i0 + 1, min(i0 + 24, N - 40)):
        if bl[i] < runlow:
            runlow, lowbar = bl[i], i
        if hh is None and bc[i] > bh[i - 1] and bl[i] >= runlow:
            hh = i
    return hh, lowbar


def basket_raw(ie):
    """mean/median basket 8h close return and best bounce (max high) from the next open."""
    j = ie + 1
    rets, mfe = [], []
    for o, h, c in coins.values():
        if j + 32 >= N or np.isnan(o[j]) or np.isnan(c[j + 31]):
            continue
        rets.append(c[j + 31] / o[j] - 1)
        mfe.append(np.nanmax(h[j:j + 32]) / o[j] - 1)
    if len(rets) < 20:
        return None
    rets, mfe = np.array(rets), np.array(mfe)
    return dict(ret_med=np.median(rets), ret_mean=rets.mean(), up3=(rets >= 0.03).mean(), up5=(rets >= 0.05).mean(),
                dn2=(rets <= -0.02).mean(), mfe_med=np.median(mfe), mfe_ge5=(mfe >= 0.05).mean())


for thr in (0.02, 0.03):
    rows = []
    for i0 in shocks_at(thr):
        hh, lowbar = hh_bar(i0)
        if hh is None:
            continue
        r1 = basket_raw(hh)
        r2 = basket_raw(lowbar)
        if r1 and r2:
            rows.append(dict(t=bt[i0], hour=int(((bt[hh] / 1000 + PK) // 3600) % 24), depth=bl[lowbar] / hi12[i0] - 1,
                             **{f"hh_{k}": v for k, v in r1.items()}, **{f"low_{k}": v for k, v in r2.items()}))
    R = pd.DataFrame(rows)
    print(f"\nBTC shocks <= -{thr * 100:.0f}% vs 12h high with a higher-high close within 6h: n={len(R)}")
    print(f"  AFTER THE CONFIRMATION (entry next open, 8h, no stop): basket median return {R.hh_ret_med.median() * 100:+.2f}% "
          f"(mean of means {R.hh_ret_mean.mean() * 100:+.2f}%)")
    print(f"    shocks where the median coin was up >= 3% at 8h: {(R.hh_ret_med >= 0.03).mean() * 100:.0f}% · >= 5%: {(R.hh_ret_med >= 0.05).mean() * 100:.0f}% "
          f"· median coin DOWN >= 2%: {(R.hh_ret_med <= -0.02).mean() * 100:.0f}%")
    print(f"    best bounce within 8h, median coin: {R.hh_mfe_med.median() * 100:+.2f}% · shocks where the median coin's best bounce >= 5%: {(R.hh_mfe_med >= 0.05).mean() * 100:.0f}%")
    print(f"  AT THE TRUE LOW (hindsight): basket median return {R.low_ret_med.median() * 100:+.2f}% · up >= 5% share {(R.low_ret_med >= 0.05).mean() * 100:.0f}% · best bounce median {R.low_mfe_med.median() * 100:+.2f}%")
    deep = R[R.depth <= -0.035]
    print(f"  deep shocks (low <= -3.5% vs 12h high, like last night) n={len(deep)}: after confirmation median {deep.hh_ret_med.median() * 100:+.2f}% · "
          f"up>=5% {(deep.hh_ret_med >= 0.05).mean() * 100:.0f}% · down>=2% {(deep.hh_ret_med <= -0.02).mean() * 100:.0f}% · best-bounce median {deep.hh_mfe_med.median() * 100:+.2f}%")
    night = R[(R.hour >= 21) | (R.hour < 5)]
    print(f"  confirmations in 21-05 PKT n={len(night)}: median {night.hh_ret_med.median() * 100:+.2f}% · up>=5% {(night.hh_ret_med >= 0.05).mean() * 100:.0f}%")
    if thr == 0.02:
        R.to_csv(os.path.join(ROOT, ".bottom_odds_rows.csv"), index=False)
        q = R.hh_ret_med.quantile([0.1, 0.25, 0.5, 0.75, 0.9]).round(4).to_dict()
        print("  distribution of the median-coin 8h return after confirmation (quantiles):", {k: f"{v * 100:+.1f}%" for k, v in q.items()})
        print("  how rare is a +5.5% median close like last night?", f"{(R.hh_ret_med >= 0.055).mean() * 100:.1f}% of shocks")

# ───────── SHORT fires inside a BTC shock window (desk ledger copy) ─────────
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
tr = con.execute("SELECT tier, symbol, side, opened_at, pnl_r FROM shadow_trades WHERE status='CLOSED' AND pnl_r IS NOT NULL "
                 "AND tier IN ('elite_star','elite_conv','star_go_chase','apex_v2','trig_strong') AND entry>0 AND abs(entry-stop0)/entry>=0.005").fetchall()
sh = np.array([bt[i] / 1000 for i in shocks_at(0.02)])
print(f"\nDESK (09-28 copy): trades opened inside a BTC shock window (0-4h after a -2% crossing) vs outside")
for tier in ("elite_star", "elite_conv", "star_go_chase", "apex_v2"):
    for side in ("SHORT", "LONG"):
        ins, outs = [], []
        for t_, s_, d_, o_, r_ in tr:
            if t_ != tier or (d_ or "").upper() != side:
                continue
            o_ = float(o_)
            k = np.searchsorted(sh, o_) - 1
            inside = k >= 0 and 0 <= o_ - sh[k] <= 4 * 3600
            (ins if inside else outs).append(float(r_))
        f = lambda x: f"{(np.mean(np.array(x) > 0) * 100):.0f}% / {np.mean(x):+.2f}R (n={len(x)})" if x else "—"
        print(f"  {tier:14s} {side:5s}: in shock window {f(ins):28s} | outside {f(outs)}")
