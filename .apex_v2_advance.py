"""APEX V2 — can it be advanced before it goes back on the channel? (user 2026-11-01)
Read-only study on a backup. Every APEX V2 fire (stream apex_v2, 22 Sep →) replayed on the
15m candles from the fire (plan stop / TP1, 48h, 0.14% fees) with the desk's own closed trade
beside it, then split by: partner co-fires (2h before → 30 min after), the 1h verdict
(apexv2_1h LIVE / DEAD — a HOLD read), PKT window, heat band, APEX score band, conf band (from
the desk row), BTC day, stop width, TP1 distance, side. The same splits run on the wide APEX
tier restricted to the V2 shape (STRONG · score 90–94 · heat < 75) since 14 Sep as the
robustness sample, because 142 fires cannot certify a stack on their own.
Run: .venv\\Scripts\\python.exe .apex_v2_advance.py [backup_dir]
"""
import json
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
BK = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, ".state_backup_1025")
exec(open(os.path.join(ROOT, ".go_fast_success.py"), encoding="utf-8").read().split("def main():")[0])   # candles()
FEE = 0.0014
PARTNERS = ("prime", "elite_conv", "one_trade", "trig_strong", "elite_star", "kr_approved", "eagle_heat",
            "second_leg", "personal_watch", "early_strong", "kr_strong")
con = sqlite3.connect(f"file:{os.path.join(BK, 'worker.db')}?mode=ro", uri=True)
btc = candles("BTCUSDT"); btc["d"] = (btc.c / btc.c.shift(96) - 1) * 100; bot = btc.ot.to_numpy()
part = {p: pd.read_sql(f"select ts, symbol, side from signals where stream='{p}' and ts>=1788000000", con) for p in PARTNERS}
v1h = pd.read_sql("select ts, symbol, side, tier from signals where stream='apexv2_1h'", con)
APX = pd.read_sql("select ts, symbol, side, extra from signals where stream='apex' and ts>=1788000000", con)
APX["ex"] = APX.extra.apply(lambda x: json.loads(x or "{}") if x else {})


def replay(d, ts, side, entry, stop, tp1):
    """-> (net R, hit, prog60) from the first 15m bar at/after the fire; None when unusable."""
    sd = 1 if side == "LONG" else -1
    ot = d.ot.to_numpy(); i = int(np.searchsorted(ot, int(ts * 1000)))
    if i + 8 >= len(ot) or ot[i] - int(ts * 1000) > 900_000:
        return None
    e = float(d.o.iat[i]); risk = abs(e - stop)
    if risk <= 0 or (sd == 1 and not stop < e < tp1) or (sd == -1 and not stop > e > tp1):
        return None
    hi, lo, cl = (d[x].to_numpy()[i:i + 192] for x in "hlc")
    sl = lo <= stop if sd == 1 else hi >= stop; tp = hi >= tp1 if sd == 1 else lo <= tp1
    ksl = int(np.argmax(sl)) if sl.any() else 10 ** 9; ktp = int(np.argmax(tp)) if tp.any() else 10 ** 9
    fee = FEE * e / risk
    prog60 = (cl[3] - e) * sd / abs(tp1 - e) if len(cl) > 3 else np.nan
    if ksl <= ktp and ksl < 10 ** 9:
        return (-1 - fee, "sl", prog60)
    if ktp < 10 ** 9:
        return (abs(tp1 - e) / risk - fee, "tp", prog60)
    if len(cl) < 192:
        return None
    return ((cl[-1] - e) * sd / risk - fee, "time", prog60)


def build(stream, since, v2_shape=False):
    sig = pd.read_sql(f"select ts, symbol, side, entry, stop, tp1, extra from signals where stream='{stream}' and ts>={since} order by ts", con)
    sh = pd.read_sql(f"select symbol, side, opened_at, status, pnl_r, tp1_hit, conf, heat from shadow_trades where tier='{stream}'", con)
    rows, cache = [], {}
    for r in sig.itertuples(index=False):
        ex = json.loads(r.extra or "{}") if r.extra else {}
        if v2_shape and not (str(ex.get("tier")) == "STRONG" and ex.get("score") is not None and 90 <= float(ex.get("score")) < 95):
            continue
        if not (r.entry and r.stop and r.tp1):
            continue
        if r.symbol not in cache:
            cache[r.symbol] = candles(r.symbol)
        d = cache[r.symbol]
        if d is None:
            continue
        out = replay(d, r.ts, r.side, float(r.entry), float(r.stop), float(r.tp1))
        if out is None:
            continue
        m = sh[(sh.symbol == r.symbol) & (sh.side == r.side) & ((sh.opened_at - r.ts).abs() <= 900)]
        dk = m.iloc[0] if len(m) else None
        bi = int(np.searchsorted(bot, int(r.ts * 1000), side="right")) - 1
        row = dict(ts=r.ts, sym=r.symbol, side=r.side, r=out[0], hit=out[1], prog60=out[2],
                   desk_r=(dk.pnl_r if dk is not None and dk.status == "CLOSED" else np.nan),
                   conf=(dk.conf if dk is not None else np.nan), heat=ex.get("heat", dk.heat if dk is not None else np.nan),
                   score=ex.get("score"), tier=ex.get("tier"), btc=float(btc.d.iat[bi]) if bi >= 0 else np.nan,
                   pkt=int((r.ts // 3600 + 5) % 24), stop_pct=abs(float(r.entry) - float(r.stop)) / float(r.entry) * 100,
                   rr=abs(float(r.tp1) - float(r.entry)) / abs(float(r.entry) - float(r.stop)))
        am = APX[(APX.symbol == r.symbol) & (APX.side == r.side) & ((APX.ts - r.ts).abs() <= 1800)]
        aex = am.iloc[(am.ts - r.ts).abs().argsort().iloc[0]].ex if len(am) else ex
        row["edges"] = tuple(aex.get("edges") or ()); row["apex_n"] = aex.get("apex"); row["conf"] = aex.get("conf", row["conf"])
        vm = v1h[(v1h.symbol == r.symbol) & (v1h.side == r.side) & (v1h.ts > r.ts) & (v1h.ts <= r.ts + 2 * 3600)]
        row["v1h"] = vm.tier.iloc[0] if len(vm) else ("LIVE" if (out[2] == out[2] and out[2] >= 0.10) else "DEAD" if out[2] == out[2] else "?")
        row["v1h_src"] = "stamp" if len(vm) else "candles"
        for p, pf in part.items():
            w = pf[(pf.symbol == r.symbol) & (pf.side == r.side) & (pf.ts >= r.ts - 2 * 3600) & (pf.ts <= r.ts + 1800)]
            row["p_" + p] = len(w) > 0
        row["p_n"] = sum(row["p_" + p] for p in PARTNERS)
        rows.append(row)
    return pd.DataFrame(rows)


def cell(g, col="r"):
    g = g[g[col].notna()]
    if len(g) == 0:
        return "—"
    x = g[col].to_numpy(float)
    return f"{(x > 0).mean() * 100:3.0f}% / {x.mean():+.2f}R (n={len(x)})"


def split(F, mask, label, base_label="rest", min_n=10):
    a, b = F[mask], F[~mask]
    if len(a) < min_n:
        return f"  {label:38s} thin (n={len(a)})"
    lift = a.r.mean() - b.r.mean() if len(b) else np.nan
    h = len(a) // 2
    halves = f"halves {a.iloc[:h].r.mean():+.2f}/{a.iloc[h:].r.mean():+.2f}" if h >= 5 else "halves —"
    return f"  {label:38s} {cell(a):26s} vs {base_label} {cell(b):26s} lift {lift:+.2f}R · {halves} · desk {cell(a, 'desk_r')}"


def report(F, title):
    print(f"\n════ {title}: {len(F)} fires with candles · {pd.Timestamp(F.ts.min(), unit='s').date()} → {pd.Timestamp(F.ts.max(), unit='s').date()} ════")
    print(f"  {'ALL (replay from the fire)':38s} {cell(F)}   desk {cell(F, 'desk_r')}")
    print("— 1h verdict (HOLD read: known only an hour in) —")
    for v in ("LIVE", "DEAD"):
        print(split(F, F.v1h == v, f"1h {v}"))
    print("— partners 2h before → 30 min after (same coin+side) —")
    for p in PARTNERS:
        print(split(F, F["p_" + p], f"with {p}", "without"))
    print(split(F, F.p_n == 0, "no partner at all", "any partner"))
    print(split(F, F.p_n >= 3, "3+ partners", "fewer"))
    print("— clock (PKT) —")
    for lo, hi, lab in ((1, 5, "01-05"), (5, 9, "05-09"), (9, 13, "09-13"), (13, 17, "13-17"), (17, 21, "17-21"), (21, 25, "21-01")):
        m = (F.pkt >= lo) & (F.pkt < hi) if lab != "21-01" else ((F.pkt >= 21) | (F.pkt < 1))
        print(split(F, m, f"fired {lab} PKT"))
    print("— heat —")
    for lo, hi, lab in ((0, 25, "<25"), (25, 50, "25-49"), (50, 75, "50-74"), (75, 101, "75+")):
        print(split(F, (F.heat.astype(float) >= lo) & (F.heat.astype(float) < hi), f"heat {lab}"))
    print("— APEX score —")
    for lo, hi, lab in ((0, 90, "<90"), (90, 92, "90-91.9"), (92, 94, "92-93.9"), (94, 101, "94+")):
        print(split(F, (F.score.astype(float) >= lo) & (F.score.astype(float) < hi), f"score {lab}"))
    print("— conf (desk row) —")
    for lo, hi, lab in ((0, 55, "40-54"), (55, 65, "55-64"), (65, 75, "65-74"), (75, 101, "75+")):
        print(split(F, (F.conf.astype(float) >= lo) & (F.conf.astype(float) < hi), f"conf {lab}"))
    print(split(F, F.conf.isna(), "conf unknown"))
    print("— edges on the APEX card / agreeing systems —")
    for en in ("SST1", "SST2", "ELITE", "FORECAST", "TRUE", "KR", "SNIPER", "TRIGGER", "PRIME"):
        m = F.edges.apply(lambda t: any(str(x).upper().startswith(en) for x in t))
        if m.sum() >= 10:
            print(split(F, m, f"edge {en}"))
    for k in (3, 4, 5):
        print(split(F, F.apex_n.astype(float) == k, f"{k} systems agree"))
    print(split(F, F.apex_n.astype(float) >= 6, "6+ systems agree"))
    print("— BTC day / geometry / side —")
    print(split(F, F.btc <= -1.5, "BTC day ≤ −1.5%")); print(split(F, F.btc.between(-1.5, 1.5), "BTC day −1.5..+1.5%")); print(split(F, F.btc > 1.5, "BTC day > +1.5%"))
    print(split(F, F.stop_pct < 2, "stop < 2%")); print(split(F, F.stop_pct.between(2, 4), "stop 2-4%")); print(split(F, F.stop_pct > 4, "stop > 4%"))
    print(split(F, F.rr < 1.2, "TP1 < 1.2R")); print(split(F, F.rr.between(1.2, 2), "TP1 1.2-2R")); print(split(F, F.rr > 2, "TP1 > 2R"))
    print(split(F, F.side == "LONG", "LONG", "SHORT"))


V2 = build("apex_v2", 1790000000)
V2.to_csv(os.path.join(ROOT, ".apex_v2_advance_rows.csv"), index=False)
report(V2, "APEX V2 (stream apex_v2)")
WIDE = build("apex", 1789000000, v2_shape=True)
WIDE.to_csv(os.path.join(ROOT, ".apex_wide_v2shape_rows.csv"), index=False)
report(WIDE, "ROBUSTNESS — wide APEX tier in the V2 shape (STRONG · 90–94 · heat<75) since 14 Sep")
print("\n— stacks worth a look (V2 cell → the same cell on the wide sample) —")
cands = {
    "LIVE at 1h (hold read, not an entry)": lambda F: F.v1h == "LIVE",
    "with 💎 elite_conv": lambda F: F.p_elite_conv, "with 👑 one_trade": lambda F: F.p_one_trade, "with 🥇 prime": lambda F: F.p_prime,
    "with 💥 trig_strong": lambda F: F.p_trig_strong, "with ⭐ elite_star": lambda F: F.p_elite_star,
    "SHORT": lambda F: F.side == "SHORT", "heat 25-74": lambda F: F.heat.astype(float).between(25, 74.999),
    "conf 65+": lambda F: F.conf.astype(float) >= 65, "BTC day ≤ +1.5%": lambda F: F.btc <= 1.5,
    "not 21-05 PKT": lambda F: ~((F.pkt >= 21) | (F.pkt < 5)), "13-21 PKT": lambda F: F.pkt.between(13, 20),
    "elite_conv + BTC≤1.5 + not 21-05": lambda F: F.p_elite_conv & (F.btc <= 1.5) & ~((F.pkt >= 21) | (F.pkt < 5)),
    "any of conv/one_trade/prime": lambda F: F.p_elite_conv | F.p_one_trade | F.p_prime,
    "conv/one_trade/prime + 13-21 PKT": lambda F: (F.p_elite_conv | F.p_one_trade | F.p_prime) & F.pkt.between(13, 20),
    "one_trade + BTC −1.5..+1.5": lambda F: F.p_one_trade & F.btc.between(-1.5, 1.5),
    "BTC −1.5..+1.5 + heat 50-74": lambda F: F.btc.between(-1.5, 1.5) & F.heat.astype(float).between(50, 74.999),
    "BTC −1.5..+1.5 + stop 2-4%": lambda F: F.btc.between(-1.5, 1.5) & F.stop_pct.between(2, 4),
    "4+ systems agree": lambda F: F.apex_n.astype(float) >= 4,
    "conf 65+ (APEX card)": lambda F: F.conf.astype(float) >= 65,
    "edge ELITE on the card": lambda F: F.edges.apply(lambda t: any(str(x).upper().startswith("ELITE") for x in t)),
}
for lab, fn in cands.items():
    a, b = V2[fn(V2)], WIDE[fn(WIDE)]
    print(f"  {lab:38s} V2 {cell(a):26s} · wide {cell(b):26s} · wide halves {b.iloc[:len(b)//2].r.mean() if len(b) >= 10 else float('nan'):+.2f}/{b.iloc[len(b)//2:].r.mean() if len(b) >= 10 else float('nan'):+.2f}")
