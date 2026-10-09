"""🌊⬆️ BOTTOM STUDY — can a BTC capitulation-bottom confirmation + an alt basket
entry earn across every dump in the 13-month 15m cache (.dip_kl, 161 coins)?

User 2026-10-09 ("BTC dumped to 80.3k … from 11pm all the alts bounced, DOT 14%,
ONDO 10-12%, ETHFI 11% … why are you not notifying me such trades … look at the
ema bol sar vol macd rsi"). Last night measured: median alt bounce 7% from the
22:15-23:00 PKT lows, 78% of coins >= 5%, starts within the hour.

DESIGN
  shock   BTC 15m close <= -SHOCK vs its rolling 12h high (first crossing, one
          per 24h). The "low" is the running minimum after the crossing.
  signal  first bar within 6h of the crossing where a confirmation prints:
            hh    close above the previous bar's high, no new low on the bar
            rsi   RSI14 crosses back above 30 after being below
            macd  MACD(12,26,9) histogram rises two bars off a negative trough
            bb    close back inside after a lower-band (20,2) pierce
            ema   close back above EMA20
            sar   parabolic SAR flips bullish
            vclx  volume-climax bar (>= 2.5x 7d median) then a close above its mid
            hind  the bar after the actual low (hindsight ceiling, not tradable)
  trade   every coin (or a selector's 10): entry = next 15m open; stop = the
          coin's low since the crossing - 0.25 ATR14; TP = 1.5R; time exit 8h;
          fees 0.11%; stop checked before TP within a bar.
  judge   per shock the basket result (mean % net, share of coins > 0), the
          per-coin R; thirds by time; drop-3-best shocks; vs RANDOM entries
          (same coins, same rules, random bars away from shocks).
  nights  features at the signal bar (depth, RSI at the low, climax ratio,
          PKT hour, 24h trend, first bounce bar) split against the basket
          result — does anything tell a bounce night from a continuation?
"""
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
SHOCK = float(sys.argv[1]) if len(sys.argv) > 1 else 0.02
FEE = 0.0011
PK = 5 * 3600
rng = np.random.default_rng(7)
t0 = time.time()

# ───────── BTC + indicators ─────────
B = pd.read_csv(os.path.join(D, "BTCUSDT.csv"))
B = B.drop_duplicates("ot").sort_values("ot").reset_index(drop=True)
bo, bh, bl, bc, bv = (B[k].astype(float).to_numpy() for k in ("o", "h", "l", "c", "v"))
bt = B["ot"].to_numpy()
N = len(B)
s = pd.Series(bc)
ema20 = s.ewm(span=20, adjust=False).mean().to_numpy()
d = s.diff()
up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
rsi = (100 - 100 / (1 + up / dn.replace(0, np.nan))).fillna(50).to_numpy()
macd = (s.ewm(span=12, adjust=False).mean() - s.ewm(span=26, adjust=False).mean())
hist = (macd - macd.ewm(span=9, adjust=False).mean()).to_numpy()
bbm = s.rolling(20).mean()
bbs = s.rolling(20).std()
bb_lo = (bbm - 2 * bbs).to_numpy()
tr = np.maximum(bh - bl, np.maximum(abs(bh - np.roll(bc, 1)), abs(bl - np.roll(bc, 1))))
atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
vmed = pd.Series(bv).rolling(672, min_periods=200).median().to_numpy()
volx = bv / np.where(vmed > 0, vmed, np.nan)
hi12 = pd.Series(bh).rolling(48).max().to_numpy()
c24 = s.pct_change(96).to_numpy()
# parabolic SAR (0.02 / 0.2)
sar_up = np.zeros(N, dtype=bool)
sar = bl[0]; ep = bh[0]; af = 0.02; bull = True
for i in range(1, N):
    sar = sar + af * (ep - sar)
    if bull:
        sar = min(sar, bl[i - 1], bl[i - 2] if i >= 2 else bl[i - 1])
        if bl[i] < sar:
            bull, sar, ep, af = False, ep, bl[i], 0.02
        elif bh[i] > ep:
            ep, af = bh[i], min(af + 0.02, 0.2)
    else:
        sar = max(sar, bh[i - 1], bh[i - 2] if i >= 2 else bh[i - 1])
        if bh[i] > sar:
            bull, sar, ep, af = True, ep, bh[i], 0.02
        elif bl[i] < ep:
            ep, af = bl[i], min(af + 0.02, 0.2)
    sar_up[i] = bull
dd = bc / hi12 - 1.0

# ───────── shocks ─────────
shocks = []
last = -10 ** 9
for i in range(700, N - 40):
    if dd[i] <= -SHOCK and dd[i - 1] > -SHOCK and i - last >= 96:
        shocks.append(i)
        last = i
print(f"BTC bars {N} · {pd.to_datetime(bt[0], unit='ms')} -> {pd.to_datetime(bt[-1], unit='ms')} · "
      f"shocks (<= -{SHOCK * 100:.1f}% vs 12h high, one per 24h): {len(shocks)}")

# ───────── signals per shock ─────────
H6 = 24


def signal_bars(i0):
    """entry-signal bar index per signal name (None if not within 6h)."""
    out = {}
    runlow = bl[i0]
    rsi_was_low = rsi[i0] < 30
    below_bb = bc[i0] < bb_lo[i0]
    trough = hist[i0]
    clx_bar = None
    lowbar = i0
    for i in range(i0 + 1, min(i0 + H6, N - 40)):
        if bl[i] < runlow:
            runlow, lowbar = bl[i], i
        if rsi[i] < 30:
            rsi_was_low = True
        if bc[i] < bb_lo[i]:
            below_bb = True
        if hist[i] < trough:
            trough = hist[i]
        if volx[i] >= 2.5 and bc[i] < bo[i]:
            clx_bar = i
        if "hh" not in out and bc[i] > bh[i - 1] and bl[i] >= runlow:
            out["hh"] = i
        if "rsi" not in out and rsi_was_low and rsi[i] > 30 and rsi[i - 1] <= 30:
            out["rsi"] = i
        if "macd" not in out and hist[i - 1] > trough and hist[i] > hist[i - 1] and hist[i] < 0 and i >= i0 + 2:
            out["macd"] = i
        if "bb" not in out and below_bb and bc[i] > bb_lo[i] and bc[i - 1] <= bb_lo[i - 1]:
            out["bb"] = i
        if "ema" not in out and bc[i] > ema20[i] and bc[i - 1] <= ema20[i - 1]:
            out["ema"] = i
        if "sar" not in out and sar_up[i] and not sar_up[i - 1]:
            out["sar"] = i
        if "vclx" not in out and clx_bar is not None and i > clx_bar and bc[i] > (bh[clx_bar] + bl[clx_bar]) / 2:
            out["vclx"] = i
    # hindsight: the bar after the actual low within the 6h window
    out["hind"] = min(lowbar + 1, N - 41)
    out["_low"] = lowbar
    return out


# ───────── coins ─────────
coins = {}
for f in sorted(glob.glob(os.path.join(D, "*USDT.csv"))):
    sym = os.path.basename(f)[:-4]
    if sym == "BTCUSDT":
        continue
    k = pd.read_csv(f).drop_duplicates("ot").set_index("ot").sort_index()
    if len(k) < 5000:
        continue
    k = k.reindex(bt)
    o, h, l, c, v = (k[x].astype(float).to_numpy() for x in ("o", "h", "l", "c", "v"))
    trc = np.maximum(h - l, np.maximum(abs(h - np.roll(c, 1)), abs(l - np.roll(c, 1))))
    a = pd.Series(trc).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    h12 = pd.Series(h).rolling(48).max().to_numpy()
    coins[sym] = (o, h, l, c, v, a, h12)
print(f"coins: {len(coins)} · prep {time.time() - t0:.0f}s")


def coin_trade(sym, i0, ie):
    """R and % of entering sym at the open after bar ie (shock crossing i0)."""
    o, h, l, c, v, a, h12 = coins[sym]
    j = ie + 1
    if j + 32 >= N or np.isnan(o[j]) or np.isnan(a[ie]):
        return None
    e = o[j]
    low_since = np.nanmin(l[i0:ie + 1])
    stop = low_since - 0.25 * a[ie]
    risk = e - stop
    if not (0.003 * e <= risk <= 0.15 * e):
        return None
    tp = e + 1.5 * risk
    for k in range(j, j + 32):
        if l[k] <= stop:
            px = stop
            break
        if h[k] >= tp:
            px = tp
            break
    else:
        px = c[j + 31]
    pct = px / e - 1 - FEE
    r = (px - e) / risk - FEE * e / risk
    depth = low_since / h12[ie] - 1 if h12[ie] > 0 else np.nan
    rel1h = (c[ie] / c[ie - 4] - 1) - (bc[ie] / bc[ie - 4] - 1) if ie >= 4 and not np.isnan(c[ie - 4]) else np.nan
    return pct, r, depth, rel1h


SIGS = ("hh", "rsi", "macd", "bb", "ema", "sar", "vclx", "hind")
SELS = ("basket", "deep10", "strong10")
rows = []
for i0 in shocks:
    sb = signal_bars(i0)
    for sig in SIGS:
        ie = sb.get(sig)
        if ie is None:
            continue
        res = []
        for sym in coins:
            t = coin_trade(sym, i0, ie)
            if t is not None:
                res.append((sym,) + t)
        if len(res) < 20:
            continue
        df = pd.DataFrame(res, columns=["sym", "pct", "r", "depth", "rel1h"])
        feats = {"depth_btc": float(bl[sb["_low"]] / hi12[i0] - 1), "rsi_low": float(rsi[sb["_low"]]),
                 "volx_low": float(np.nanmax(volx[i0:sb["_low"] + 1])), "hour_pkt": int(((bt[ie] / 1000 + PK) // 3600) % 24),
                 "trend24": float(c24[i0]), "lag_bars": int(ie - sb["_low"]), "wait_bars": int(ie - i0),
                 "bounce1": float(bc[ie] / bl[sb["_low"]] - 1)}
        for sel in SELS:
            if sel == "basket":
                sub = df
            elif sel == "deep10":
                sub = df.nsmallest(10, "depth")
            else:
                sub = df.nlargest(10, "rel1h")
            rows.append(dict(shock=i0, t=bt[i0], sig=sig, sel=sel, n=len(sub), pct=sub["pct"].mean(),
                             r=sub["r"].mean(), win=(sub["pct"] > 0).mean(), **feats))
R = pd.DataFrame(rows)
R.to_csv(os.path.join(ROOT, ".bottom_rows.csv"), index=False)

# ───────── random baseline ─────────
bad = np.zeros(N, dtype=bool)
for i0 in shocks:
    bad[max(0, i0 - 48):i0 + 96] = True
cands = np.where(~bad[700:N - 40])[0] + 700
rnd = []
for i0 in shocks:
    for _ in range(2):
        ie = int(rng.choice(cands))
        res = [coin_trade(sym, ie - 4, ie) for sym in coins]
        res = [x for x in res if x is not None]
        if len(res) >= 20:
            rnd.append((np.mean([x[0] for x in res]), np.mean([x[1] for x in res]), np.mean([x[0] > 0 for x in res])))
rnd = pd.DataFrame(rnd, columns=["pct", "r", "win"])
print(f"RANDOM baseline (same coins, same rules, random bars away from shocks, n={len(rnd)}): basket "
      f"{rnd.pct.mean() * 100:+.2f}% · {rnd.r.mean():+.3f}R · coin win {rnd.win.mean() * 100:.0f}% · "
      f"share of baskets > 0: {(rnd.pct > 0).mean() * 100:.0f}%")
print(f"compute {time.time() - t0:.0f}s\n")


def thirds(x):
    x = list(x)
    if len(x) < 9:
        return "n/a"
    k = len(x) // 3
    return "/".join(f"{np.mean(p) * 100:+.1f}" for p in (x[:k], x[k:2 * k], x[2 * k:]))


print(f"{'signal':6s} {'sel':9s} {'n':>4s} {'basket%':>8s} {'R/coin':>7s} {'coinwin':>7s} {'bask>0':>6s} {'thirds (%)':>20s} {'drop3':>7s} {'median%':>8s}")
for sig in SIGS:
    for sel in SELS:
        g = R[(R.sig == sig) & (R.sel == sel)].sort_values("t")
        if len(g) < 10:
            continue
        d3 = g.pct.sort_values().iloc[:-3].mean() if len(g) > 3 else np.nan
        print(f"{sig:6s} {sel:9s} {len(g):4d} {g.pct.mean() * 100:+8.2f} {g.r.mean():+7.3f} {g.win.mean() * 100:6.0f}% "
              f"{(g.pct > 0).mean() * 100:5.0f}% {thirds(g.pct):>20s} {d3 * 100:+7.2f} {g.pct.median() * 100:+8.2f}")

# ───────── night features: what separates bounce nights? (signal hh, basket) ─────────
g = R[(R.sig == "hh") & (R.sel == "basket")].copy()
print(f"\nNIGHT FEATURES on signal=hh, basket (n={len(g)}): basket% by split")
for feat, cut, lab in (("depth_btc", -0.03, "BTC depth <= -3% vs > -3%"), ("rsi_low", 25, "RSI at low < 25 vs >= 25"),
                       ("volx_low", 2.0, "climax volume >= 2x vs < 2x"), ("trend24", 0.0, "24h trend < 0 vs >= 0"),
                       ("lag_bars", 2, "signal within 2 bars of the low vs later"), ("bounce1", 0.01, "first bounce >= 1% vs <"),
                       ("wait_bars", 8, "signal within 2h of the crossing vs later")):
    a = g[g[feat] <= cut] if feat in ("depth_btc", "trend24") else (g[g[feat] < cut] if feat in ("rsi_low", "volx_low", "lag_bars", "wait_bars") else g[g[feat] >= cut])
    b = g.drop(a.index)
    if feat == "volx_low":
        a, b = g[g[feat] >= cut], g[g[feat] < cut]
    if feat in ("lag_bars", "wait_bars"):
        a, b = g[g[feat] <= cut], g[g[feat] > cut]
    print(f"  {lab:44s}: {a.pct.mean() * 100:+.2f}% (n={len(a)}, baskets>0 {(a.pct > 0).mean() * 100:.0f}%)  vs  "
          f"{b.pct.mean() * 100:+.2f}% (n={len(b)}, {(b.pct > 0).mean() * 100:.0f}%)")
hrs = g.groupby(pd.cut(g.hour_pkt, [-1, 4, 8, 12, 16, 20, 24], labels=["21-05", "05-09", "09-13", "13-17", "17-21", "21-24"]))["pct"].agg(["mean", "count"])
print("  by PKT window of the signal:", {k: f"{v['mean'] * 100:+.2f}% (n={int(v['count'])})" for k, v in hrs.iterrows()})
