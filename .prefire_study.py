"""PRE-FIRE ALIGNMENT STUDY (user 2026-10-05: "why can't we pick coins that are about
to fire, having momentum + trend + volume together, just before the spike?").

Part A — 2,144 trigger_fire breaks (Aug 15 - Sep 28): does the state of the 15m tape
in the bars BEFORE the break bar (momentum building, volume rising but not spiked,
1h trend aligned, pressing close to the number, coil tightness) sort the breaks
that reach TP1 from the ones that stop? Entry = the trigger (the system's entry).
Part B — 1,104 pb_armed levels: from arming, scan every 15m bar before the break;
when the alignment first appears, (1) how often does the number actually break
within 4h vs an unaligned bar, (2) what does ENTERING AT THAT BAR (before the
break) earn vs waiting for the break, with the plan's own stop/TP1.
Candles: .dip_kl (160 coins, 15m, to 2026-10-03). Fees 2 x 0.055%. Battery:
thirds, drop-3-best-days, day-weighted. Pure replay, nothing live touched."""
import io
import json
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
os.chdir(r"F:\Trading Indicator")
S = r"C:\Users\HAMMAD~1.JAW\AppData\Local\Temp\claude\F--Trading-Indicator\761b8a7a-ac27-4b70-b7c6-e365893054c0\scratchpad"
FEE = 0.00055
HZ = 192                       # 48h of 15m bars
_c = {}


def kl(sym):
    if sym not in _c:
        p = f".dip_kl/{sym}.csv"
        if not os.path.exists(p):
            _c[sym] = None
        else:
            d = pd.read_csv(p).drop_duplicates("ot").sort_values("ot")
            _c[sym] = {k: d[k].to_numpy(float) for k in ("ot", "o", "h", "l", "c", "v")}
            _c[sym]["ot"] /= 1000.0
    return _c[sym]


def atr(b, i, n=14):
    s = max(1, i - n)
    tr = np.maximum(b["h"][s:i], b["c"][s - 1:i - 1]) - np.minimum(b["l"][s:i], b["c"][s - 1:i - 1])
    return float(tr.mean()) if len(tr) else np.nan


def ema(x, n):
    k = 2.0 / (n + 1)
    e = np.empty_like(x)
    e[0] = x[0]
    for i in range(1, len(x)):
        e[i] = x[i] * k + e[i - 1] * (1 - k)
    return e


def features(b, i, side, trigger):
    """State at the CLOSE of bar i-1 (everything strictly before bar i)."""
    if i < 700:
        return None
    sgn = 1.0 if side == "LONG" else -1.0
    c, v, h, l = b["c"], b["v"], b["h"], b["l"]
    a = atr(b, i)
    if not a or a <= 0:
        return None
    mom3 = sgn * (c[i - 1] - c[i - 4]) / a            # 45 min of drift toward the number
    mom8 = sgn * (c[i - 1] - c[i - 9]) / a            # 2h drift
    base_v = float(np.median(v[i - 673:i - 1])) or 1e-12
    vol2 = float(v[i - 3:i - 1].mean()) / base_v       # last 2 bars vs the 7d median bar
    vol1 = float(v[i - 2]) / (float(v[i - 10:i - 2].mean()) or 1e-12)   # acceleration
    e80 = ema(c[i - 400:i], 80)                        # ~20 x 1h
    slope = sgn * (e80[-1] - e80[-9]) / a
    above = sgn * (c[i - 1] - e80[-1]) > 0
    dist = abs(trigger - c[i - 1]) / trigger * 100
    on_side = (c[i - 1] < trigger) if side == "LONG" else (c[i - 1] > trigger)
    near = 0
    for j in range(i - 13, i - 1):
        px = h[j] if side == "LONG" else l[j]
        if abs(trigger - px) / trigger <= 0.004 and ((px <= trigger) if side == "LONG" else (px >= trigger)):
            near += 1
    coil = (h[i - 13:i - 1].max() - l[i - 13:i - 1].min()) / a
    # the break bar itself (LATE information, for contrast only)
    bb_vol = float(v[i]) / base_v
    bb_body = sgn * (c[i] - b["o"][i]) / a
    gap = (b["o"][i] > trigger) if side == "LONG" else (b["o"][i] < trigger)
    return dict(mom3=mom3, mom8=mom8, vol2=vol2, vol1=vol1, slope=slope, above=above, dist=dist,
                on_side=on_side, near=near, coil=coil, bb_vol=bb_vol, bb_body=bb_body, gap=gap)


def settle(b, i, side, entry, stop, tp, risk, hz=HZ):
    """Plain SL/TP1 from bar i (inclusive), stop first inside a bar, gaps at the open."""
    j = min(i + hz, len(b["c"]))
    if j - i < 2:
        return None
    sgn = 1.0 if side == "LONG" else -1.0
    o, h, l, c = b["o"][i:j], b["h"][i:j], b["l"][i:j], b["c"][i:j]
    sl = (l <= stop) if sgn > 0 else (h >= stop)
    tph = (h >= tp) if sgn > 0 else (l <= tp)
    fs = int(np.argmax(sl)) if sl.any() else 10 ** 9
    ft = int(np.argmax(tph)) if tph.any() else 10 ** 9
    fee_r = 2 * FEE * entry / risk
    if fs <= ft and fs < 10 ** 9:
        px = o[fs] if ((sgn > 0 and o[fs] < stop) or (sgn < 0 and o[fs] > stop)) else stop
        rs = "SL"
    elif ft < 10 ** 9:
        px = o[ft] if ((sgn > 0 and o[ft] > tp) or (sgn < 0 and o[ft] < tp)) else tp
        rs = "TP"
    else:
        px, rs = c[-1], "TIME"
    return rs, sgn * (px - entry) / risk - fee_r


def aligned(f, loose=False):
    """Momentum building toward the number but NOT spiking, volume rising but not
    spiked, 1h trend on our side, price pressing within reach, on the approach side."""
    if f is None or not f["on_side"]:
        return False
    if loose:
        return f["mom3"] >= 0.15 and f["vol2"] >= 1.15 and f["slope"] > 0 and f["dist"] <= 2.5
    return (0.3 <= f["mom3"] <= 1.5 and 1.3 <= f["vol2"] <= 3.0 and f["slope"] > 0
            and f["above"] and f["dist"] <= 1.5)


db = sqlite3.connect(S + r"\worker.db")
T0 = pd.Timestamp("2026-08-15", tz="UTC").timestamp()


def thirds(x, col):
    if len(x) < 9:
        return "-"
    o = x.sort_values("ts")
    return "".join("+" if p.mean() > 0 else "-" for p in np.array_split(o[col].to_numpy(), 3))


def d3(x, col):
    g = x.groupby("day")[col].sum().sort_values(ascending=False)
    k = x[~x.day.isin(g.index[:3])]
    return k[col].mean() if len(k) else np.nan


def dayw(x, col):
    return x.groupby("day")[col].mean().mean() if len(x) else np.nan


def row(lab, x, col="r"):
    if not len(x):
        print(f"{lab:<48} n=0")
        return
    print(f"{lab:<48} n={len(x):>4} | win {(x[col] > 0).mean() * 100:5.1f}%  avg {x[col].mean():+.3f}R  thirds {thirds(x, col):>3}  -3days {d3(x, col):+.3f}  day-wt {dayw(x, col):+.3f}")


# ================================ PART A ================================
tf = pd.read_sql("select ts, symbol, side, extra from signals where stream='trigger_fire' order by ts", db)
rows = []
seen = {}
for r in tf.itertuples():
    ex = json.loads(r.extra or "{}")
    key = (r.symbol, r.side, round(float(ex.get("trigger") or 0), 8))
    if key in seen and r.ts - seen[key] < 6 * 3600:
        continue
    seen[key] = r.ts
    b = kl(r.symbol)
    if b is None:
        continue
    try:
        trig, stop, tp1 = float(ex["trigger"]), float(ex["stop"]), float(ex["tp1"])
    except Exception:
        continue
    risk = abs(trig - stop)
    if risk / trig < 0.003 or risk <= 0 or (tp1 - trig) * (1 if r.side == "LONG" else -1) <= 0:
        continue
    i = int(np.searchsorted(b["ot"], r.ts, side="right")) - 1      # bar containing the fire
    if i < 700 or i + 2 >= len(b["ot"]):
        continue
    f = features(b, i, r.side, trig)
    if f is None:
        continue
    out = settle(b, i, r.side, trig, stop, tp1, risk)
    if out is None:
        continue
    rec = dict(ts=r.ts, day=pd.Timestamp(r.ts, unit="s").strftime("%m-%d"), symbol=r.symbol, side=r.side,
               src=(ex.get("src") or "")[:1], burst=ex.get("burst"), score=ex.get("score"), rr=abs(tp1 - trig) / risk,
               rs=out[0], r=out[1], **f)
    rec["align"] = aligned(f)
    rec["align_loose"] = aligned(f, loose=True)
    rows.append(rec)
A = pd.DataFrame(rows)
A.to_csv(S + r"\prefire_A.csv", index=False)
print(f"PART A — breaks with candles: {len(A)} (of {len(tf)} records, {len(seen)} distinct) · {A.day.nunique()} days · {A.symbol.nunique()} coins\n")
row("ALL breaks, entry at the number", A)
row("  LONG", A[A.side == "LONG"])
row("  SHORT", A[A.side == "SHORT"])
print("\n--- the three-align state in the bars BEFORE the break ---")
row("  ALIGNED (mom 0.3-1.5 ATR, vol 1.3-3x, trend up, <1.5%)", A[A["align"]])
row("  not aligned", A[~A["align"]])
row("  ALIGNED loose (mom>=.15, vol>=1.15, trend, <2.5%)", A[A["align_loose"]])
row("  not aligned loose", A[~A["align_loose"]])
print("\n--- one factor at a time (pre-break) ---")
for lab, m in (("momentum building 0.3-1.5 ATR", A.mom3.between(0.3, 1.5)), ("momentum flat <0.3", A.mom3 < 0.3), ("momentum already >1.5 ATR (spiking)", A.mom3 > 1.5),
               ("volume 1.3-3x", A.vol2.between(1.3, 3)), ("volume <1.0x (quiet)", A.vol2 < 1.0), ("volume >3x (already spiked)", A.vol2 > 3),
               ("1h trend aligned (slope>0 & above)", (A.slope > 0) & A.above), ("1h trend against", A.slope < 0),
               ("pressing: 3+ of last 12 bars within 0.4%", A.near >= 3), ("no pressing", A.near == 0),
               ("coil tight (12-bar range <3 ATR)", A.coil < 3), ("coil wide (>6 ATR)", A.coil > 6),
               ("close within 0.5% of the number", A.dist <= 0.5), ("1-3% away", A.dist.between(1, 3))):
    row(f"  {lab}", A[m])
print("\n--- for contrast: the break bar itself (LATE information) ---")
for lab, m in (("break-bar volume >3x", A.bb_vol > 3), ("break-bar volume <1.5x", A.bb_vol < 1.5), ("gap-through open", A.gap), ("pressed-first (no gap)", ~A.gap),
               ("live burst at fire >=85", pd.to_numeric(A.burst, errors="coerce") >= 85), ("live burst at fire <85", pd.to_numeric(A.burst, errors="coerce") < 85)):
    row(f"  {lab}", A[m])
print("\n--- by source ---")
for s, lab in (("\u26a1", "strong coil"), ("\U0001F525", "2nd leg"), ("\U0001F48E", "elite")):
    row(f"  {lab}: all", A[A.src == s])
    row(f"  {lab}: aligned loose", A[(A.src == s) & A["align_loose"]])

# ================================ PART B ================================
pb = pd.read_sql("select ts, symbol, side, extra from signals where stream='pb_armed' order by ts", db)
lv = {}
for r in pb.itertuples():
    ex = json.loads(r.extra or "{}")
    try:
        key = (r.symbol, r.side, round(float(ex["trigger"]), 8))
    except Exception:
        continue
    if key not in lv:
        lv[key] = (r.ts, ex)
Bq = []
for (sym, side, trig), (ts, ex) in lv.items():
    b = kl(sym)
    if b is None:
        continue
    try:
        stop, tp1 = float(ex["stop"]), float(ex["tp1"])
    except Exception:
        continue
    risk = abs(trig - stop)
    sgn = 1 if side == "LONG" else -1
    if risk / trig < 0.003 or risk <= 0 or (tp1 - trig) * sgn <= 0:
        continue
    i0 = int(np.searchsorted(b["ot"], ts, side="right"))
    if i0 < 700:
        continue
    j_end = min(i0 + HZ, len(b["c"]) - HZ - 2)
    if j_end <= i0:
        continue
    brk = None
    first_al = None
    first_loose = None
    n_al = n_bars = 0
    for j in range(i0, j_end):
        hit = (b["h"][j] >= trig) if sgn > 0 else (b["l"][j] <= trig)
        if hit:
            brk = j
            break
        f = features(b, j, side, trig)
        n_bars += 1
        if f is None:
            continue
        if aligned(f, loose=True):
            n_al += 1
            if first_loose is None:
                first_loose = (j, f)
        if aligned(f) and first_al is None:
            first_al = (j, f)
    rec = dict(ts=ts, day=pd.Timestamp(ts, unit="s").strftime("%m-%d"), symbol=sym, side=side, risk_pct=risk / trig * 100,
               broke=brk is not None, bars_to_break=(brk - i0) if brk is not None else None,
               aligned_before=first_al is not None, loose_before=first_loose is not None, n_bars=n_bars, n_al=n_al)
    if brk is not None:
        entry_b = b["o"][brk] if ((sgn > 0 and b["o"][brk] > trig) or (sgn < 0 and b["o"][brk] < trig)) else trig
        out = settle(b, brk, side, entry_b, stop, tp1, risk)
        rec["r_break"] = out[1] if out else np.nan
    for tag, fa in (("strict", first_al), ("loose", first_loose)):
        if fa is not None:
            j, f = fa
            e_pre = b["c"][j - 1]
            out = settle(b, j, side, e_pre, stop, tp1, risk)
            rec[f"r_pre_{tag}"] = out[1] if out else np.nan
            rec[f"pre_{tag}_bars_to_break"] = (brk - j) if brk is not None else None
            rec[f"pre_{tag}_broke_4h"] = (brk is not None and brk - j <= 16)
    Bq.append(rec)
B = pd.DataFrame(Bq)
B.to_csv(S + r"\prefire_B.csv", index=False)
print(f"\n\nPART B — armed levels with candles: {len(B)} (of {len(lv)} distinct) · broke within 48h: {B.broke.mean() * 100:.0f}%")
for tag in ("strict", "loose"):
    m = B[f"aligned_before" if tag == "strict" else "loose_before"]
    sub = B[m]
    print(f"\n--- alignment ({tag}) appeared before any break: {len(sub)} levels ({len(sub) / len(B) * 100:.0f}%) ---")
    if len(sub):
        print(f"  P(break within 4h of the alignment bar) = {sub[f'pre_{tag}_broke_4h'].mean() * 100:.0f}%  vs  P(break within 4h of arming) overall = {(B.bars_to_break.fillna(999) <= 16).mean() * 100:.0f}%")
        print(f"  P(ever broke within 48h | aligned) = {sub.broke.mean() * 100:.0f}%  vs  not aligned = {B[~m].broke.mean() * 100:.0f}%")
        x = sub.rename(columns={f"r_pre_{tag}": "r"})
        row(f"  ENTER AT THE ALIGNMENT BAR (before the break), plan stop/TP1", x)
        y = sub[sub.broke].rename(columns={"r_break": "r"})
        row(f"  same levels, enter at the break instead (only the ones that broke)", y)
        z = sub[~sub.broke].rename(columns={f"r_pre_{tag}": "r"})
        row(f"  aligned levels that NEVER broke (pre-entry outcome)", z)
w = B[B.broke].rename(columns={"r_break": "r"})
row("\nALL armed levels that broke, enter at the break", w)
# random-bar control: alignment is 'rare' how often?
print(f"\nhow common is the loose alignment? {B.n_al.sum()} aligned bars out of {B.n_bars.sum()} pre-break bars = {B.n_al.sum() / max(1, B.n_bars.sum()) * 100:.1f}% of the time while a level is armed")
