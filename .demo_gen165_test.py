"""GEN 16.5 — PRESSED & BROKE priority-1 longs-only seat + the PKT time gate:
longs of star / strong trigger / TRIG×KR / early lane / early movers only in
the 🟢 13-21 / 🟡 05-13 windows; shorts per stream off the desk ledger (star
closed 09-13 / 21-01 / 01-05, trigger + TRIG×KR closed 09-13 / 17-21, early
lanes open all day). Pure engine tests with a pinned clock + feed wiring."""
import calendar
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"F:\Trading Indicator")
import demo_account as da

fails = []
U = lambda h, m=0: float(calendar.timegm((2026, 10, 4, h, m, 0)))   # UTC clock


def P(h, m=0):          # PKT wall-clock -> epoch
    return U((h - 5) % 24, m)


# ---- constants ----
if da.CLASS_W.get("press_break") != 107 or max(da.CLASS_W.values()) != 107:
    fails.append(f"press_break must be rung 1: {da.CLASS_W}")
if da.LONG_ONLY != {"press_break"}:
    fails.append(f"LONG_ONLY wrong: {da.LONG_ONLY}")
if da.TIME_GATED != {"elite_star", "strong_trigger", "strig_kr", "early_lane", "early_movers"}:
    fails.append(f"TIME_GATED wrong: {da.TIME_GATED}")
for src in ("elite_star", "strong_trigger", "strig_kr", "early_lane", "early_movers"):
    if da.TIME_CLOSED.get((src, "LONG")) != {"21-01", "01-05"}:
        fails.append(f"{src} LONG closed windows wrong: {da.TIME_CLOSED.get((src, 'LONG'))}")
if da.TIME_CLOSED[("elite_star", "SHORT")] != {"09-13", "21-01", "01-05"}:
    fails.append("star short windows wrong")
if da.TIME_CLOSED[("strong_trigger", "SHORT")] != {"09-13", "17-21"} or da.TIME_CLOSED[("strig_kr", "SHORT")] != {"09-13", "17-21"}:
    fails.append("trigger short windows wrong")
if da.TIME_CLOSED[("early_lane", "SHORT")] or da.TIME_CLOSED[("early_movers", "SHORT")]:
    fails.append("early lanes shorts must have no closed window")
if any(s in ("press_break", "moonshot") for s, _ in da.TIME_CLOSED):
    fails.append("press_break / moonshot must not be time-gated")
if "press_break" not in da.SMART_EXIT_SKIP or da.lev_for("press_break") != 10.0:
    fails.append("press_break exit-skip / leverage not wired")
if "press_break" in da.CONF_GATE or "press_break" in da.SPARE_RESERVE:
    fails.append("press_break must have no conf band and no spare reserve")

# ---- the PKT clock ----
for ts, h, w4, col in ((P(15), 15, "13-17", "green"), (P(8), 8, "05-09", "yellow"), (P(23), 23, "21-01", "red"), (P(4, 30), 4, "01-05", "red"),
                       (P(5), 5, "05-09", "yellow"), (P(21), 21, "21-01", "red"), (P(20, 59), 20, "17-21", "green"), (P(13), 13, "13-17", "green"),
                       (P(12, 59), 12, "09-13", "yellow"), (P(0, 30), 0, "21-01", "red"), (P(1), 1, "01-05", "red"), (P(17), 17, "17-21", "green")):
    if da.pkt_hour(ts) != h or da.pkt_window4(ts) != w4 or da.pkt_window(ts) != col:
        fails.append(f"clock: {h}h -> {da.pkt_hour(ts)} / {da.pkt_window4(ts)} / {da.pkt_window(ts)}, wanted {h} / {w4} / {col}")
GATE = [
    ("elite_star", "LONG", P(23), False), ("elite_star", "LONG", P(3), False), ("elite_star", "LONG", P(15), True), ("elite_star", "LONG", P(8), True),
    ("strong_trigger", "LONG", P(4, 30), False), ("strig_kr", "LONG", P(23), False), ("early_lane", "LONG", P(23), False), ("early_movers", "long", P(23), False),
    ("elite_star", "SHORT", P(18), True), ("elite_star", "SHORT", P(6), True), ("elite_star", "SHORT", P(14), True),
    ("elite_star", "SHORT", P(10), False), ("elite_star", "SHORT", P(23), False), ("elite_star", "SHORT", P(2), False),
    ("strong_trigger", "SHORT", P(18), False), ("strong_trigger", "SHORT", P(10), False), ("strong_trigger", "SHORT", P(23), True),
    ("strong_trigger", "SHORT", P(2), True), ("strong_trigger", "SHORT", P(6), True), ("strong_trigger", "SHORT", P(14), True),
    ("strig_kr", "SHORT", P(18), False), ("strig_kr", "SHORT", P(23), True),
    ("early_lane", "SHORT", P(18), True), ("early_lane", "SHORT", P(23), True), ("early_movers", "SHORT", P(10), True),
    ("press_break", "LONG", P(23), True), ("moonshot", "LONG", P(23), True), ("moonshot", "SHORT", P(10), True),
]
for src, side, ts, ok in GATE:
    if da.time_gate_ok(src, side, ts) != ok:
        fails.append(f"time_gate_ok({src}, {side}, {da.pkt_hour(ts)}h PKT) != {ok}")


def cand(src, side="LONG", conf=70, sym=None, score=80):
    if side == "LONG":
        entry, stop, tp1 = 100.0, 96.75, (103.5 if src == "elite_star" else 106.0)
    else:
        entry, stop, tp1 = 100.0, 103.25, (96.5 if src == "elite_star" else 94.0)
    return {"symbol": sym or f"{src[:4].upper()}{side[0]}USDT", "base": "X", "side": side, "entry": entry,
            "stop": stop, "tp1": tp1, "tp2": None, "score": score, "conf": conf}


def opens(src, side, ts, conf=70):
    st = {"balance": 2000.0, "open": [], "closed": []}
    r = da.rank_candidates({src: [cand(src, side, conf)]}, {})
    if not r:
        return "no-rank"
    op, _ = da.try_open(st, r, lambda s: 100.0, now=ts)
    return bool(op)


# ---- PRESSED & BROKE: longs seat at any hour and any conf, shorts never ----
for ts in (P(15), P(8), P(23), P(4, 30)):
    if opens("press_break", "LONG", ts) is not True:
        fails.append(f"press_break LONG refused at {da.pkt_hour(ts)}h PKT")
if opens("press_break", "LONG", P(15), conf=None) is not True:
    fails.append("press_break LONG with no conf must still seat (no band)")
if opens("press_break", "SHORT", P(15)) != "no-rank":
    fails.append("press_break SHORT must be refused by the roster")

# ---- the time gate through the whole engine (rank + try_open) ----
ENGINE = [
    ("elite_star", "LONG", 98, [(P(15), True), (P(8), True), (P(23), False), (P(4, 30), False)]),
    ("strong_trigger", "LONG", 98, [(P(15), True), (P(23), False)]),
    ("strig_kr", "LONG", 98, [(P(8), True), (P(2), False)]),
    ("early_lane", "LONG", 98, [(P(15), True), (P(23), False)]),
    ("early_movers", "LONG", 98, [(P(8), True), (P(3), False)]),
    ("elite_star", "SHORT", 98, [(P(18), True), (P(6), True), (P(10), False), (P(23), False), (P(2), False)]),
    ("strong_trigger", "SHORT", 98, [(P(23), True), (P(2), True), (P(18), False), (P(10), False)]),
    ("strig_kr", "SHORT", 98, [(P(23), True), (P(18), False)]),
    ("early_lane", "SHORT", 98, [(P(18), True), (P(23), True), (P(10), True)]),
    ("early_movers", "SHORT", 98, [(P(18), True), (P(2), True)]),
    ("moonshot", "LONG", 60, [(P(15), True), (P(23), True), (P(2), True)]),
]
for src, side, cf, cases in ENGINE:
    for ts, want in cases:
        got = opens(src, side, ts, conf=cf)
        if got != want:
            fails.append(f"{src} {side} at {da.pkt_hour(ts)}h PKT -> {got}, wanted {want}")
# a momentum re-entry (chain>0) is gated too
st = {"balance": 2000.0, "open": [], "closed": []}
r = da.rank_candidates({"elite_star": [dict(cand("elite_star"), chain=1)]}, {})
if r and da.try_open(st, r, lambda s: 100.0, now=P(23))[0]:
    fails.append("re-entry slipped through the red window")
# default clock = live time (no now) still works
st = {"balance": 2000.0, "open": [], "closed": []}
da.try_open(st, da.rank_candidates({"press_break": [cand("press_break")]}, {}), lambda s: 100.0)
if not st["open"] or abs(st["open"][0]["opened_at"] - da._clock()) > 5:
    fails.append("opened_at must follow the engine clock")

# ---- priority: press_break outranks the star on equal merit; no spare reserve ----
rk = da.rank_candidates({"elite_star": [cand("elite_star", sym="AUSDT", conf=98)],
                         "press_break": [cand("press_break", sym="BUSDT", conf=98)]}, {})
if [c["symbol"] for c in rk][:2] != ["BUSDT", "AUSDT"]:
    fails.append(f"ladder order wrong: {[c['symbol'] for c in rk]}")
st = {"balance": 2000.0, "open": [], "closed": []}
pool = {"press_break": [cand("press_break", sym=f"P{i}USDT", conf=90) for i in range(19)]}
da.try_open(st, da.rank_candidates(pool, {}), lambda s: 100.0, now=P(15))
n19 = len(st["open"])
op, _ = da.try_open(st, da.rank_candidates({"press_break": [cand("press_break", sym="LASTUSDT", conf=90)]}, {}), lambda s: 100.0, now=P(15))
if n19 < 16:   # no 5-seat spare reserve for a priority stream (the 20th seat is collateral-blocked by fees, pre-existing)
    fails.append(f"press_break should fill seats freely: {n19} then {bool(op)}")

# ---- worker feed wiring ----
W = open(r"F:\Trading Indicator\agent_worker.py", encoding="utf-8").read()
A = open(r"F:\Trading Indicator\app.py", encoding="utf-8").read()
for need, lab in (("_DEMO_PB: list = []", "module list"),
                  ('if (a.get("side") or "").upper() == "LONG":\n                            _DEMO_PB.append(dict(_sig_pb,', "LONG-only feed at the press site"),
                  ('"press_break": ([dict(d) for d in _DEMO_PB', "pool"),
                  ('("press_break", "press_break")', "form map"),
                  ('"early_lane", "strig_kr",\n                              "press_break")', "reopen allowlist"),
                  ("_DEMO_PB[:] = [d for d in _DEMO_PB", "prune")):
    if need not in W:
        fails.append(f"worker wiring missing: {lab}")
i_rec = W.find('store.record_signal("press_break", _sig_pb)')
i_feed = W.find("_DEMO_PB.append(dict(_sig_pb,")
if not (0 < i_rec < i_feed < i_rec + 700):
    fails.append("demo feed must sit right after the press_break desk record")
if "GEN 16.5 · THE PRIORITY FOUR" not in A or "TIME GATE (2026-10-04)" not in A:
    fails.append("app caption not updated")
print("GEN 16.5:", "ALL PASS" if not fails else fails)
