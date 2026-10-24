"""🎮 GEN 18 — THE FOUR (2026-10-22): roster + ladder, the star clock gate, the
⭐➕ add-on law (once, on 1H LIVE or GO FAST, 2 seats' margin, liquidation guard,
collateral, heat), the GEN 18 cut-over (old seats closed at live into the archived
ledger, fresh $2,000 book), worker wiring, page header."""
import calendar
import io
import json
import os
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"F:\Trading Indicator"
sys.path.insert(0, ROOT)
import demo_account as da  # noqa: E402

fails = []
tmp = tempfile.mkdtemp(prefix="gen18_")
da.STATE_FILE = os.path.join(tmp, "demo.json")
if da.GEN != 18 or da.START_BAL != 2000.0:
    fails.append(f"GEN/START_BAL: {da.GEN} {da.START_BAL}")
if set(da.CLASS_W) != {"elite_star", "strong_trigger", "star_prime", "conv_revival", "prime_trig"}:
    fails.append(f"roster: {sorted(da.CLASS_W)}")
if not (da.CLASS_W["elite_star"] > da.CLASS_W["strong_trigger"] > da.CLASS_W["star_prime"] > da.CLASS_W["conv_revival"] > da.CLASS_W["prime_trig"]):
    fails.append("ladder order")
for s in da.CLASS_W:
    if da.lev_for(s) != 10.0:
        fails.append(f"lev {s}")
if da.NEAR_TP_SRC != {"elite_star", "strong_trigger", "star_prime", "conv_revival", "prime_trig"} or da.LONG_ONLY or da.RR_OPEN_BOUNDS or da.DEMO_RESET_BEFORE:
    fails.append("fade bank must cover the four (2026-10-24); long-only / rr bounds / old cut-over off")
if da.CONF_GATE.get("strong_trigger") != ((65.0, 1000.0),) or "early_lane" in da.CONF_GATE:
    fails.append(f"conf gate: {da.CONF_GATE}")
if ("strong_trigger", "LONG") not in da.TIME_CLOSED or any(k[0] == "early_lane" for k in da.TIME_CLOSED):
    fails.append("strong trigger time gate must stay, early lane gone")
if da.ADDON_SRC != {"elite_star"} or da.ADDON_MARGIN_X != 2.0 or da.CLOCK_GATED != {"elite_star"}:
    fails.append("add-on / clock constants")
# clock gate: 15:00 PKT = 10:00 UTC (13–17 cell, star longs thin -> seats; strong trigger longs open);
# 23:00 PKT = 18:00 UTC long star -> 21–01 cell (desk 75%/+0.69R n=28 -> TAKE); 03:00 PKT -> DON'T
T_TAKE = float(calendar.timegm((2026, 10, 22, 10, 0, 0)))
T_NIGHT = float(calendar.timegm((2026, 10, 22, 18, 0, 0)))
T_RED = float(calendar.timegm((2026, 10, 22, 22, 0, 0)))
ok1, c1 = da.clock_ok("elite_star", "LONG", T_TAKE)
ok1b, c1b = da.clock_ok("elite_star", "LONG", T_NIGHT)
ok2, c2 = da.clock_ok("elite_star", "LONG", T_RED)
if not ok1 or c1 not in ("TAKE", "HALF", "THIN") or not ok1b or c1b != "TAKE" or ok2 or c2 != "DON'T":
    fails.append(f"clock gate: {ok1} {c1} / {ok1b} {c1b} / {ok2} {c2}")
if da.clock_ok("strong_trigger", "LONG", T_RED) != (True, None):
    fails.append("clock gate must touch the star only")


def fresh():
    return {"gen": 18, "balance": 2000.0, "start": 2000.0, "started_at": T_TAKE, "open": [], "closed": [], "equity_hist": []}


def cand(src, sym="AAAUSDT", side="LONG", conf=80.0, entry=100.0, stop=96.0, tp1=106.0):
    return {"symbol": sym, "base": sym.replace("USDT", ""), "side": side, "entry": entry, "stop": stop, "tp1": tp1, "tp2": 110.0,
            "score": 90.0, "conf": conf, "burst": 0.0, "src": src, "rank": 99.0, "top": 1}


px = {"AAAUSDT": 100.0, "BBBUSDT": 100.0, "CCCUSDT": 100.0, "DDDUSDT": 100.0, "EEEUSDT": 100.0}
live = lambda s: px.get(s, 0.0)
# opens: the four seat at margin = balance/20 (~$100 after the entry fees), 10x; a GO REVIVED candidate never
# reaches the ladder (rank_candidates is the roster guard); a red-clock star is refused
if da.rank_candidates({"go_revived": [cand("go_revived", "EEEUSDT")], "arrival_t1": [cand("arrival_t1", "EEEUSDT")]}, {}):
    fails.append("the roster guard must drop GO REVIVED / ARRIVAL T1")
if not da.rank_candidates({"conv_revival": [cand("conv_revival", "DDDUSDT")]}, {}):
    fails.append("conv_revival must rank")
st = fresh()
opened, _ = da.try_open(st, [cand("elite_star"), cand("strong_trigger", "BBBUSDT"), cand("star_prime", "CCCUSDT"),
                             cand("conv_revival", "DDDUSDT")], live, now=T_TAKE)
if sorted(p["src"] for p in opened) != ["conv_revival", "elite_star", "star_prime", "strong_trigger"]:
    fails.append(f"opens: {[p['src'] for p in opened]}")
if any(abs(p["margin"] - 100.0) > 0.3 or p["lev"] != 10.0 or abs(p["notional"] - 1000.0) > 3.0 for p in opened):
    fails.append(f"sizing: {[(p['src'], p['margin'], p['lev'], p['notional']) for p in opened]}")
star = next(p for p in opened if p["src"] == "elite_star")
if star.get("clock") not in ("TAKE", "HALF", "THIN") or star.get("adds") != []:
    fails.append(f"star seat stamps: {star.get('clock')} {star.get('adds')}")
st2 = fresh()
o2, _ = da.try_open(st2, [cand("elite_star")], live, now=T_RED)
if o2:
    fails.append("a red-clock star must not seat")
if da.rank_candidates({"strong_trigger": [cand("strong_trigger", conf=60.0)]}, {}) or not da.rank_candidates({"strong_trigger": [cand("strong_trigger", conf=80.0)]}, {}):
    fails.append("strong trigger conf 60 must not rank, conf 80 must (the conf gate lives in rank_candidates)")
# add-on: once, on 1H LIVE or GO FAST, +2 seats' margin at the live price, avg entry, liquidation guard
px["AAAUSDT"] = 102.0
ev = da.manage(st, live, None, addon_fn=lambda s, d: {"oneh": "LIVE", "go": None} if s == "AAAUSDT" else None)
adds = [r for e, r in ev if e == "add"]
p = next(q for q in st["open"] if q["symbol"] == "AAAUSDT")
m_after = p["margin"]
if len(adds) != 1 or not (298.0 <= p["margin"] <= 300.5) or not (2980.0 <= p["notional"] <= 3001.0) or p.get("added") != "1H LIVE":
    fails.append(f"add-on: {adds} margin={p['margin']} notional={p['notional']} added={p.get('added')}")
if not (100.0 < p["entry"] < 102.0) or abs(p["qty"] - (10.0 + adds[0]["notional"] / 102.0)) > 1e-6:
    fails.append(f"avg entry / qty after the add: {p['entry']} {p['qty']}")
if len(p.get("adds") or []) != 1 or p["adds"][0]["why"] != "1H LIVE" or abs(p["adds"][0]["px"] - 102.0) > 1e-9:
    fails.append(f"adds record: {p.get('adds')}")
ev2 = da.manage(st, live, None, addon_fn=lambda s, d: {"oneh": "LIVE", "go": "FAST"})
if any(e == "add" for e, _ in ev2) or abs(p["margin"] - m_after) > 1e-9:
    fails.append("add-on must happen once")
if any(q.get("adds") for q in st["open"] if q["src"] != "elite_star"):
    fails.append("only the star adds")
# GO FAST alone also adds; a DEAD / NO GO star does not
px["AAAUSDT"] = 100.0
st3 = fresh()
o3s, _ = da.try_open(st3, [cand("elite_star")], live, now=T_TAKE)
px["AAAUSDT"] = 101.0
if not o3s or not any(e == "add" for e, _ in da.manage(st3, live, None, addon_fn=lambda s, d: {"oneh": "DEAD", "go": "FAST"})):
    fails.append("GO FAST alone must add")
px["AAAUSDT"] = 100.0
st4 = fresh()
da.try_open(st4, [cand("elite_star")], live, now=T_TAKE)
if any(e == "add" for e, _ in da.manage(st4, live, None, addon_fn=lambda s, d: {"oneh": "DEAD", "go": None})):
    fails.append("DEAD + no GO must not add")
if st4["open"][0].get("added"):
    fails.append("a star without LIVE / GO FAST keeps its add-on open for later")
# liquidation guard: a 7% stop plan that ran +4% -> the averaged position's stop would sit past 8% at 10x -> no add
px["AAAUSDT"] = 100.0
st5 = fresh()
o5s, _ = da.try_open(st5, [cand("elite_star", stop=93.0)], live, now=T_TAKE)
px["AAAUSDT"] = 104.0
if not o5s or any(e == "add" for e, _ in da.manage(st5, live, None, addon_fn=lambda s, d: {"oneh": "LIVE"})) \
        or "8% guard" not in str(st5["open"][0].get("added")):
    fails.append(f"add-on must respect the 8% stop guard on the averaged position: {st5['open'][0].get('added') if st5['open'] else None}")
# collateral: the book's free margin is short of 2 seats -> no add, reason stamped
px["AAAUSDT"] = 100.0
st6 = fresh()
da.try_open(st6, [cand("elite_star")], live, now=T_TAKE)
st6["open"].append(dict(st6["open"][0], symbol="ZZZUSDT", base="ZZZ", src="strong_trigger", margin=1850.0, qty=0.0, notional=0.0, adds=[]))
px["AAAUSDT"] = 101.0
if any(e == "add" for e, _ in da.manage(st6, live, None, addon_fn=lambda s, d: {"oneh": "LIVE"})) \
        or "collateral" not in str(st6["open"][0].get("added")):
    fails.append(f"add-on must need free collateral: {st6['open'][0].get('added')}")
# cut-over: an old-gen file with open seats -> closed at live into the archive, fresh $2,000 book
old = {"gen": 16, "balance": 1616.23, "start": 2000.0, "started_at": 1.0, "open": [
    {"symbol": "AAAUSDT", "base": "AAA", "side": "LONG", "entry": 100.0, "stop": 96.0, "tp1": 106.0, "tp2": None, "qty": 10.0,
     "notional": 1000.0, "lev": 10.0, "margin": 100.0, "risk_usd": 40.0, "risk_pct": 0.02, "burst": 0.0, "risk0": 4.0,
     "src": "go_revived", "score": 90.0, "agree": 1, "srcs": "go_revived", "opened_at": 1.0, "fees": 0.55, "tp1_banked": 0.0,
     "be_set": False, "peak": 100.0}], "closed": [{"pnl": 5.0}], "equity_hist": []}
with open(da.STATE_FILE, "w", encoding="utf-8") as f:
    json.dump(old, f)
px["AAAUSDT"] = 103.0
out = da.cutover_gen18(live)
fresh_state = da.load()
arch = [f for f in os.listdir(tmp) if ".gen16_" in f]
if len(out) != 1 or out[0][0] != "close" or abs(out[0][1]["pnl"] - (30.0 - 10.0 * 103.0 * da.FEE)) > 0.01:
    fails.append(f"cut-over close: {out}")
if fresh_state.get("gen") != 18 or fresh_state.get("balance") != 2000.0 or fresh_state.get("open") or fresh_state.get("closed") or fresh_state.get("cutover_closed") != 1:
    fails.append(f"fresh book: {fresh_state}")
if len(arch) != 1:
    fails.append(f"archive missing: {os.listdir(tmp)}")
else:
    a = json.load(open(os.path.join(tmp, arch[0]), encoding="utf-8"))
    if a.get("open") or len(a.get("closed") or []) != 2 or "GEN 18 cut-over" not in a["closed"][-1]["reason"]:
        fails.append("archive must hold the closed seat")
if da.cutover_gen18(live):
    fails.append("cut-over must run once")
# an unpriced seat keeps the old file for the next tick
with open(da.STATE_FILE, "w", encoding="utf-8") as f:
    json.dump(old, f)
if da.cutover_gen18(lambda s: 0.0) != [] or json.load(open(da.STATE_FILE, encoding="utf-8")).get("gen") != 16:
    fails.append("unpriced seat must wait, file untouched")
# worker + page wiring
W = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
A = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
for need, lab in (("demo_account.cutover_gen18(_live)", "cut-over call"),
                  ('src="conv_revival"', "conviction revival feed"),
                  ('and str(_rgd[2]).startswith("✅")):', "entry-cell rule on the revival feed"),
                  ("addon_fn=_dz_star_state)", "add-on lookup passed"),
                  ("def _dz_star_state(sym, side):", "add-on lookup fn"),
                  ('"conv_revival": (', "conv pool"),
                  ('"prime_trig": ([dict(d) for d in _DEMO_PT', "prime_trig pool (GEN 18.2)"),
                  ('if _ev == "add":', "add event handled")):
    if need not in W:
        fails.append(f"worker wiring missing: {lab}")
i_pools = W.find("_dz_pools = {")
j_pools = W.find("_dz_active = set()", i_pools)
pools = W[i_pools:j_pools]
for gone in ('"go_revived": (', '"arrival_t1": (', '"early_lane": ('):
    if gone in pools:
        fails.append(f"old pool still fed: {gone}")
if W.find("demo_account.cutover_gen18(_live)") > W.find("_dz = demo_account.load()"):
    fails.append("cut-over must run before load()")
if "GEN 18 · THE FOUR" not in A or "⭐➕" not in A:
    fails.append("page header / add-on chip missing")
print("GEN 18:", "ALL PASS" if not fails else fails)
