"""🎮 GEN 19 — THE FIVE, GATED (2026-11-07): roster + ladder, the ⭐ star book (≥69% cells by side ×
window, shorts' heat rule, 17–21 shorts' BTC-day rule, floor half / cap double), the revival LATE-only half
seat, the pairs at full, seat sizing by multiplier, the desk-ladder exit (BE at +1R → TP1 lock → 1.2R trail
→ TP2 / 48h, never a TP1 bank), no add-on, the cut-over to a fresh $2,000 book, worker wiring, page header.
Run: .venv\\Scripts\\python.exe .demo_gen19_test.py
"""
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
tmp = tempfile.mkdtemp(prefix="gen19_")
da.STATE_FILE = os.path.join(tmp, "demo.json")
FIVE = {"elite_star", "star_prime", "star_trig", "conv_revival", "star_apexv2"}


import time as _time
_TODAY = _time.gmtime()          # the seats are "opened today" so the 72h stale-seat note never fires (2026-11-10 fix)


def T(h_pkt, d=None):
    """PKT hour on today's UTC date -> epoch (UTC = PKT − 5)."""
    y, m, dd = _TODAY.tm_year, _TODAY.tm_mon, (_TODAY.tm_mday if d is None else d)
    return float(calendar.timegm((y, m, dd, (h_pkt - 5) % 24, 0, 0)))


T07, T11, T15, T19, T23 = T(7), T(11), T(15), T(19), T(23)
T03 = T07 - 4 * 3600             # 03:00 PKT the same morning (01–05 window)
if da.GEN != 19 or da.START_BAL != 2000.0:
    fails.append(f"GEN/START_BAL: {da.GEN} {da.START_BAL}")
if set(da.CLASS_W) != FIVE:
    fails.append(f"roster: {sorted(da.CLASS_W)}")
if not (da.CLASS_W["elite_star"] > da.CLASS_W["star_prime"] > da.CLASS_W["star_trig"] > da.CLASS_W["conv_revival"] > da.CLASS_W["star_apexv2"]):
    fails.append("ladder order")
for s in FIVE:
    if da.lev_for(s) != 10.0:
        fails.append(f"lev {s}")
if da.NEAR_TP_SRC or da.ADDON_SRC or da.CONF_GATE or da.TIME_CLOSED or da.CLOCK_GATED or da.LONG_ONLY or da.RR_OPEN_BOUNDS:
    fails.append("fade bank / add-on / conf gate / time gate / clock gate / long-only / rr bounds must all be off")
if da.LADDER_SRC != FIVE or da.TRAIL_R != 1.2 or da.LADDER_HOLD_H != 48.0:
    fails.append(f"ladder constants: {da.LADDER_SRC} {da.TRAIL_R} {da.LADDER_HOLD_H}")
if da.SMART_EXIT_SKIP != FIVE:
    fails.append("kronos smart exit must skip the five")
# ⭐ the star book
want = {("LONG", "05-09"): (1.0, "full"), ("LONG", "09-13"): (1.0, "full"), ("LONG", "13-17"): None, ("LONG", "17-21"): (1.0, "full"),
        ("LONG", "21-01"): (0.5, "half"), ("LONG", "01-05"): None, ("SHORT", "05-09"): (1.0, "full"), ("SHORT", "09-13"): None,
        ("SHORT", "13-17"): (0.5, "half"), ("SHORT", "17-21"): (1.0, "full"), ("SHORT", "21-01"): (0.5, "half"), ("SHORT", "01-05"): None}
if da.STAR_BOOK != want:
    fails.append(f"STAR_BOOK: {da.STAR_BOOK}")
for side, t, heat, btc, mult, word in (("LONG", T07, 50, -1.0, 1.0, "full"), ("LONG", T11, 90, 3.0, 1.0, "full"),   # longs: no heat / BTC rule
                                        ("LONG", T15, 50, -1.0, None, None), ("LONG", T19, 50, -1.0, 1.0, "full"),   # 19.1
                                        ("LONG", T19, 90, 3.0, 1.0, "full"),                                          # no heat / BTC rule on longs
                                        ("LONG", T23, 50, -1.0, 0.5, "half"), ("LONG", T03, 50, -1.0, None, None),   # 19.1
                                        ("SHORT", T07, 50, 0.5, 1.0, "full"), ("SHORT", T07, 90, 0.5, 0.5, "half"),
                                        ("SHORT", T11, 50, -1.0, None, None), ("SHORT", T15, 50, -1.0, 0.5, "half"),
                                        ("SHORT", T15, 20, -1.0, 0.5, "half"),                         # floor half
                                        ("SHORT", T19, 55, -1.2, 2.0, "double"), ("SHORT", T19, 55, 0.8, 0.5, "half"),
                                        ("SHORT", T19, 85, -1.0, 1.0, "full"),                         # double × heat-out half
                                        ("SHORT", T19, 55, None, 1.0, "full"),                          # BTC unreadable: the cell
                                        ("SHORT", T23, 50, -1.0, 0.5, "half"), ("SHORT", T03, 50, -1.0, None, None)):
    m, w, why = da.star_seat(side, t, heat, btc)
    if m != mult or w != word:
        fails.append(f"star_seat {side} {da.pkt_window4(t)} heat {heat} btc {btc}: {m} {w} ({why}) wanted {mult} {word}")
for src, extra, mult in (("conv_revival", {"go_tier": "LATE"}, 0.5), ("conv_revival", {"go_tier": "FAST"}, None),
                         ("conv_revival", {}, None), ("star_prime", {}, 1.0), ("star_trig", {}, 1.0), ("star_apexv2", {}, 1.0),
                         ("strong_trigger", {}, None), ("prime_trig", {}, None)):
    m = da.seat_size(dict({"src": src, "side": "LONG"}, **extra), T07)[0]
    if m != mult:
        fails.append(f"seat_size {src} {extra}: {m} wanted {mult}")


def fresh():
    return {"gen": 19, "balance": 2000.0, "start": 2000.0, "started_at": T07, "open": [], "closed": [], "equity_hist": []}


def cand(src, sym="AAAUSDT", side="LONG", entry=100.0, stop=96.0, tp1=106.0, tp2=110.0, **kw):
    c = {"symbol": sym, "base": sym.replace("USDT", ""), "side": side, "entry": entry, "stop": stop, "tp1": tp1, "tp2": tp2,
         "score": 90.0, "conf": 80.0, "burst": 0.0, "src": src, "rank": 99.0, "top": 1}
    c.update(kw)
    return c


px = {k: 100.0 for k in ("AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT", "EEEUSDT", "FFFUSDT")}
live = lambda s: px.get(s, 0.0)
# roster guard + the sizing inputs ride the candidate
if da.rank_candidates({"strong_trigger": [cand("strong_trigger")], "prime_trig": [cand("prime_trig", "BBBUSDT")]}, {}):
    fails.append("the roster guard must drop STRONG TRIGGER / PRIME × STRONG TRIGGER")
rk = da.rank_candidates({"elite_star": [cand("elite_star", heat=55, btc_day=-1.2)], "conv_revival": [cand("conv_revival", "BBBUSDT", go_tier="LATE")]}, {})
if len(rk) != 2 or rk[0]["src"] != "elite_star" or rk[0].get("heat") != 55 or rk[0].get("btc_day") != -1.2 or rk[1].get("go_tier") != "LATE":
    fails.append(f"rank_candidates must carry heat / btc_day / go_tier: {rk}")
# seats at 07:00 PKT: LONG star full $100, STAR × TRIGGER full, revival LATE half $50, revival FAST none, SHORT star heat 90 half
st = fresh()
opened, _ = da.try_open(st, [cand("elite_star", heat=50, btc_day=-1.0), cand("star_trig", "BBBUSDT"),
                             cand("conv_revival", "CCCUSDT", go_tier="LATE"), cand("conv_revival", "DDDUSDT", go_tier="FAST"),
                             cand("elite_star", "EEEUSDT", "SHORT", 100.0, 104.0, 94.0, 90.0, heat=90, btc_day=0.5),
                             cand("star_apexv2", "FFFUSDT")], live, now=T07)
got = {p["symbol"]: (p["src"], p["size"], round(p["margin"]), round(p["notional"]), p["lev"]) for p in opened}
want_open = {"AAAUSDT": ("elite_star", "full", 100, 1000, 10.0), "BBBUSDT": ("star_trig", "full", 100, 999, 10.0),
             "CCCUSDT": ("conv_revival", "half", 50, 500, 10.0), "EEEUSDT": ("elite_star", "half", 50, 500, 10.0),
             "FFFUSDT": ("star_apexv2", "full", 100, 999, 10.0)}
if set(got) != set(want_open) or any(abs(got[k][2] - want_open[k][2]) > 1 or abs(got[k][3] - want_open[k][3]) > 6 or got[k][:2] != want_open[k][:2] for k in want_open):
    fails.append(f"opens at 07:00 PKT: {got}")
if "DDDUSDT" in got:
    fails.append("a FAST revival must not seat")
# 19:00 PKT: LONG star full (19.1); SHORT star heat 55 + BTC down = DOUBLE $200 / $2,000
st2 = fresh()
o2, _ = da.try_open(st2, [cand("elite_star", heat=55, btc_day=-1.2), cand("elite_star", "BBBUSDT", "SHORT", 100.0, 104.0, 94.0, 90.0, heat=55, btc_day=-1.2)],
                    live, now=T19)
got2 = {p["symbol"]: (p["size"], round(p["margin"]), round(p["notional"])) for p in o2}
if got2.get("AAAUSDT", (None,))[0] != "full" or got2.get("BBBUSDT") is None or got2["BBBUSDT"][0] != "double"         or abs(got2["BBBUSDT"][1] - 200.0) > 1 or abs(got2["BBBUSDT"][2] - 2000.0) > 8:
    fails.append(f"19:00 PKT: {got2}")
# 23:00 PKT: LONG star half $50 (19.1)
st2b = fresh()
o2b, _ = da.try_open(st2b, [cand("elite_star", heat=55, btc_day=-1.2)], live, now=T23)
if len(o2b) != 1 or o2b[0]["size"] != "half" or abs(o2b[0]["margin"] - 50.0) > 0.5:
    fails.append(f"23:00 PKT long: {[(p['size'], p['margin']) for p in o2b]}")
# 15:00 PKT: no long star; a short star seats half
st3 = fresh()
o3, _ = da.try_open(st3, [cand("elite_star", heat=55, btc_day=-1.2), cand("elite_star", "BBBUSDT", "SHORT", 100.0, 104.0, 94.0, 90.0, heat=55, btc_day=-1.2)],
                    live, now=T15)
if [(p["symbol"], p["size"]) for p in o3] != [("BBBUSDT", "half")]:
    fails.append(f"15:00 PKT: {[(p['symbol'], p['size']) for p in o3]}")
# 🪜 the ladder on a LONG: +1R -> BE; TP1 -> lock, no bank; trail; stop out at the lock with a profit
st4 = fresh()
o4, _ = da.try_open(st4, [cand("elite_star", heat=50, btc_day=-1.0)], live, now=T07)
p = st4["open"][0]
da._clock = lambda: T07 + 600
px["AAAUSDT"] = 104.0
ev = da.manage(st4, live, None)
if ev or not p.get("be_set") or abs(p["stop"] - 100.0) > 1e-9:
    fails.append(f"+1R must move the stop to entry, nothing closes: {ev} {p.get('be_set')} {p['stop']}")
px["AAAUSDT"] = 106.5
ev = da.manage(st4, live, None)
if ev or not p.get("tp1_lock") or abs(p["stop"] - 106.0) > 1e-9 or st4["open"] != [p]:
    fails.append(f"TP1 must lock the stop at TP1 and keep the seat (no bank): {ev} {p.get('tp1_lock')} {p['stop']}")
px["AAAUSDT"] = 109.0
ev = da.manage(st4, live, None)
if ev or abs(p["stop"] - 106.0) > 1e-9:          # trail = 109 − 1.2×4 = 104.2 < the lock
    fails.append(f"trail below the lock must not lower it: {ev} {p['stop']}")
px["AAAUSDT"] = 105.9
ev = da.manage(st4, live, None)
if len(ev) != 1 or ev[0][0] != "close" or "TP1 lock" not in ev[0][1]["reason"] or abs(ev[0][1]["exit"] - 106.0) > 1e-9 or ev[0][1]["pnl"] <= 55:
    fails.append(f"a dip through the lock closes at the lock with the profit: {ev}")
# a bigger run: trail above the lock, then TP2 closes at TP2
st5 = fresh()
px["AAAUSDT"] = 100.0
da.try_open(st5, [cand("elite_star", heat=50, btc_day=-1.0)], live, now=T07)
p5 = st5["open"][0]
px["AAAUSDT"] = 106.5          # past TP1 (an exact touch is a lock-out on the desk too)
da.manage(st5, live, None)
px["AAAUSDT"] = 112.0            # peak 112 → trail 107.2 > the 106 lock
ev = da.manage(st5, live, None)
if len(ev) != 1 or ev[0][1]["reason"] != "TP2" or abs(ev[0][1]["exit"] - 110.0) > 1e-9:
    fails.append(f"TP2 must close at TP2: {ev}")
# SHORT ladder: +1R → BE, TP1 lock, stop out at the lock
st6 = fresh()
px["BBBUSDT"] = 100.0
da.try_open(st6, [cand("elite_star", "BBBUSDT", "SHORT", 100.0, 104.0, 94.0, 90.0, heat=50, btc_day=-1.0)], live, now=T07)
p6 = st6["open"][0]
px["BBBUSDT"] = 96.0
da.manage(st6, live, None)
if not p6.get("be_set") or abs(p6["stop"] - 100.0) > 1e-9:
    fails.append(f"short +1R → BE: {p6.get('be_set')} {p6['stop']}")
px["BBBUSDT"] = 93.0
da.manage(st6, live, None)
if not p6.get("tp1_lock") or abs(p6["stop"] - 94.0) > 1e-9:
    fails.append(f"short TP1 lock: {p6.get('tp1_lock')} {p6['stop']}")
px["BBBUSDT"] = 94.5
ev = da.manage(st6, live, None)
if len(ev) != 1 or "TP1 lock" not in ev[0][1]["reason"] or ev[0][1]["pnl"] <= 0:
    fails.append(f"short lock-out: {ev}")
# stop before anything: a plain stop closes at the stop
st7 = fresh()
px["AAAUSDT"] = 100.0
da.try_open(st7, [cand("elite_star", heat=50, btc_day=-1.0)], live, now=T07)
px["AAAUSDT"] = 95.0
ev = da.manage(st7, live, None)
if len(ev) != 1 or ev[0][1]["reason"] != "stop" or abs(ev[0][1]["exit"] - 96.0) > 1e-9:
    fails.append(f"plain stop: {ev}")
# 48h cut at live
st8 = fresh()
px["AAAUSDT"] = 100.0
da.try_open(st8, [cand("elite_star", heat=50, btc_day=-1.0)], live, now=T07)
px["AAAUSDT"] = 101.0
da._clock = lambda: T07 + 49 * 3600
ev = da.manage(st8, live, None)
if len(ev) != 1 or "48h" not in ev[0][1]["reason"] or abs(ev[0][1]["exit"] - 101.0) > 1e-9:
    fails.append(f"48h cut: {ev}")
da._clock = lambda: T07 + 600
# no add-on ever
st9 = fresh()
px["AAAUSDT"] = 100.0
da.try_open(st9, [cand("elite_star", heat=50, btc_day=-1.0)], live, now=T07)
px["AAAUSDT"] = 102.0
if any(e == "add" for e, _ in da.manage(st9, live, None, addon_fn=lambda s, d: {"oneh": "LIVE", "go": "FAST"})):
    fails.append("the add-on is off in GEN 19")
# cut-over: an old GEN 18 file with an open seat → closed at live into the archive, fresh GEN 19 $2,000 book, once
old = {"gen": 18, "balance": 1616.23, "start": 2000.0, "started_at": 1.0, "open": [
    {"symbol": "AAAUSDT", "base": "AAA", "side": "LONG", "entry": 100.0, "stop": 96.0, "tp1": 106.0, "tp2": None, "qty": 10.0,
     "notional": 1000.0, "lev": 10.0, "margin": 100.0, "risk_usd": 40.0, "risk_pct": 0.02, "burst": 0.0, "risk0": 4.0,
     "src": "strong_trigger", "score": 90.0, "agree": 1, "srcs": "strong_trigger", "opened_at": 1.0, "fees": 0.55, "tp1_banked": 0.0,
     "be_set": False, "peak": 100.0}], "closed": [{"pnl": 5.0}], "equity_hist": []}
with open(da.STATE_FILE, "w", encoding="utf-8") as f:
    json.dump(old, f)
px["AAAUSDT"] = 103.0
out = da.cutover_fresh_book(live)
fresh_state = da.load()
arch = [f for f in os.listdir(tmp) if ".gen18_" in f]
if len(out) != 1 or out[0][0] != "close" or abs(out[0][1]["pnl"] - (30.0 - 10.0 * 103.0 * da.FEE)) > 0.01 or "GEN 19 cut-over" not in out[0][1]["reason"]:
    fails.append(f"cut-over close: {out}")
if fresh_state.get("gen") != 19 or fresh_state.get("balance") != 2000.0 or fresh_state.get("open") or fresh_state.get("closed") or fresh_state.get("cutover_closed") != 1:
    fails.append(f"fresh book: {fresh_state}")
if len(arch) != 1:
    fails.append(f"archive missing: {os.listdir(tmp)}")
if da.cutover_fresh_book(live) or da.cutover_gen18(live):
    fails.append("cut-over must run once (and keep the GEN 18 name as an alias)")
# worker + page wiring
W = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
A = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
for need, lab in (("demo_account.cutover_fresh_book(_live)", "cut-over call"),
                  ('"star_trig": ([dict(d) for d in _DEMO_ST', "STAR × TRIGGER pool"),
                  ('"star_apexv2": ([dict(d) for d in _DEMO_SV2', "STAR × APEX V2 pool"),
                  ('src="star_trig"', "STAR × TRIGGER feed"), ('src="star_apexv2"', "STAR × APEX V2 feed"),
                  ('go_tier=str(_ew.get("go") or "").upper()', "revival GO tier on the feed"),
                  ('"btc_day": _btc_day_pct(),', "BTC day on the star feed"), ('"heat": _pmx.get("heat"),\n                                 "btc_day"', "heat on the star feed"),
                  ("_dz_events = demo_account.manage(_dz, _live, _dz_kr)", "manage without the add-on"),
                  ('("star_trig", "star_trig")', "form read for star_trig"), ('("star_apexv2", "star_apexv2")', "form read for star_apexv2"),
                  ("*DEMO $2,000 GEN19*", "demo bell tag")):
    if need not in W:
        fails.append(f"worker wiring missing: {lab}")
for gone, lab in (("addon_fn=_dz_star_state", "add-on lookup passed"), ("def _dz_star_state", "add-on lookup fn"),
                  ("*DEMO $1500 GEN9*", "old demo tag"), ("demo_account.cutover_gen18(_live)", "old cut-over call")):
    if gone in W:
        fails.append(f"worker still has: {lab}")
i_pools = W.find("_dz_pools = {")
j_pools = W.find("_dz_active = set()", i_pools)
pools = W[i_pools:j_pools]
for gone in ('"strong_trigger": (', '"prime_trig": (', '"go_revived": (', '"arrival_t1": (', '"early_lane": ('):
    if gone in pools:
        fails.append(f"old pool still fed: {gone}")
for need in ('"elite_star": (', '"star_prime": (', '"star_trig": (', '"conv_revival": (', '"star_apexv2": ('):
    if need not in pools:
        fails.append(f"pool missing: {need}")
if W.find("demo_account.cutover_fresh_book(_live)") > W.find("_dz = demo_account.load()"):
    fails.append("cut-over must run before load()")
if "GEN 19 · THE FIVE, GATED" not in A or "roster history (GEN 17 → 19)" not in A:
    fails.append("page header / roster history missing")
print("GEN 19:", "ALL PASS" if not fails else fails)
sys.exit(1 if fails else 0)
