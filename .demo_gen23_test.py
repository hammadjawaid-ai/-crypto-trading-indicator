"""Guard — 🎮 DEMO GEN 23 (user 2026-11-23: "Reset the demo trading again. We will have for crypto and for Stocks."):
the two rosters and his order, the gated coin star, APEX V2 shorts only, the conviction revival, the light rule
(🟢 🟡 ⚪ open, 🔴 opens nothing and adds nothing), the adds (a star seat on its GO, a confirmed-entry seat on a star /
the star's GO / a revival, two at most), the 8x seat on a wide stop, the 85% close, the cut-over to a fresh $5,000
book, the light read from the desk, and the wiring in the desk feed, the worker and the page. No network, no Telegram.
Run: .venv/Scripts/python.exe .demo_gen23_test.py
"""
import calendar
import io
import json
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="demogen23_")
os.environ["WORKER_DB_PATH"] = os.path.join(TMP, "worker.db")
import config                  # noqa: E402
import demo_account as da      # noqa: E402
import shadow_trader as sh     # noqa: E402
import tg_roster as tr         # noqa: E402
import worker_store as ws      # noqa: E402

da.STATE_FILE = os.path.join(TMP, "demo.json")
PASS, FAIL = 0, []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("  ✅", name)
    else:
        FAIL.append(name)
        print("  ❌", name, detail)


def at(y, mo, d, h_pkt, m=0):
    return float(calendar.timegm((y, mo, d, 0, 0, 0))) + (h_pkt - 5) * 3600 + m * 60


NOW = at(2026, 11, 24, 10)                       # 10:00 PKT, the 09–13 window
STK = sorted(config.BSTOCK_PERP)[0]
STK2 = sorted(config.BSTOCK_PERP)[1]
COIN, COIN2, COIN3 = "SOLUSDT", "NEARUSDT", "WLDUSDT"
px = {}
live = lambda s: px.get(s, 0.0)
GREEN = lambda src, sym, side, ts: ("🟢", "09–13 PKT 80% (5, thin)")
YELLOW = lambda src, sym, side, ts: ("🟡", "09–13 PKT 62% (8, thin)")
WHITE = lambda src, sym, side, ts: ("⚪", "09–13 PKT no closed trade yet")
RED = lambda src, sym, side, ts: ("🔴", "09–13 PKT 40% (10)")


def fresh():
    return {"gen": da.GEN, "balance": 5000.0, "start": 5000.0, "started_at": NOW, "open": [], "closed": [], "equity_hist": []}


def sig(sym=COIN, side="LONG", entry=100.0, stop=None, tp1=None, **kw):
    lng = side == "LONG"
    d = {"symbol": sym, "base": sym.replace("USDT", ""), "side": side, "entry": entry,
         "stop": stop if stop is not None else (96.0 if lng else 104.0),
         "tp1": tp1 if tp1 is not None else (106.0 if lng else 94.0), "tp2": 110.0 if lng else 90.0,
         "score": 90.0, "conf": 80.0, "burst": 0.0, "fired_at": NOW - 5}
    d.update(kw)
    px.setdefault(sym, entry)
    return d


def ranked(pools):
    return da.rank_candidates(pools, {})


def opened(pools, light=GREEN, st=None, now=NOW):
    st = fresh() if st is None else st
    da.try_open(st, ranked(pools), live, now=now, light_fn=light)
    return st


print("1. the book and the two rosters")
check("GEN 23 on a fresh $5,000 book, coins and stocks", da.GEN == 23 and da.START_BAL == 5000.0 and da.STOCKS_ONLY is False and da.CUTOVER_DATE == "2026-11-23")
check("coins, in his order: gated star · confirmed entry · conviction revival · APEX V2 shorts · star × take-now · second leg × PRIME",
      da.ROSTER["coin"] == ("elite_star", "elite_confirm", "go_revived", "apex_v2", "star_takenow", "leg2_prime"))
check("stocks, in his order: star · conviction revival · strong trigger", da.ROSTER["stock"] == ("elite_star", "go_revived", "trig_strong"))
check("the ladder keeps that order inside each class",
      all(da.CLASS_W[a] > da.CLASS_W[b] for r in da.ROSTER.values() for a, b in zip(r, r[1:])) and da.CLASS_W["star_go"] < min(da.CLASS_W[s] for r in da.ROSTER.values() for s in r))
check("every seat is one full seat at 10x by the book", all(da.lev_for(s) == 10.0 and da.seat_size({"src": s})[0] == 1.0 for r in da.ROSTER.values() for s in r)
      and da.seat_size({"src": "star_go"})[0] is None)
check("the GEN 22 clock book is off, the strong trigger is back", not da.NO_ENTRY_WINDOWS and not da.WINDOW_LEV and not da.WINDOW_MAX_NEW and not da.WINDOW_PICK
      and not da.ADD_WINDOWS and not da.ADD_PAIRS and not da.STREAM_OFF)

print("2. who may take a seat")
check("a coin star seats only when the gate passed it", len(ranked({"elite_star": [sig(gate="pass")]})) == 1 and len(ranked({"elite_star": [sig(gate="1317-pass")]})) == 1
      and ranked({"elite_star": [sig(gate="muted")]}) == [] and ranked({"elite_star": [sig(gate="1317-muted")]}) == [] and ranked({"elite_star": [sig()]}) == [])
check("a stock star seats on every fire", len(ranked({"elite_star": [sig(STK)]})) == 1)
check("APEX V2: shorts only, coins only", len(ranked({"apex_v2": [sig(side="SHORT")]})) == 1 and ranked({"apex_v2": [sig(side="LONG")]}) == []
      and ranked({"apex_v2": [sig(STK, side="SHORT")]}) == [])
check("a conviction revival seats on both classes; a star's revival opens no seat", len(ranked({"go_revived": [sig()]})) == 1 and len(ranked({"go_revived": [sig(STK)]})) == 1
      and ranked({"go_revived": [sig(star=True)]}) == [] and ranked({"go_revived": [sig(STK, star=True)]}) == [])
check("the confirmed entry, star × take-now and second leg × PRIME seat on coins, not on stocks",
      all(len(ranked({s: [sig()]})) == 1 and ranked({s: [sig(STK)]}) == [] for s in ("elite_confirm", "star_takenow", "leg2_prime")))
check("the strong trigger seats on stocks, not on coins", len(ranked({"trig_strong": [sig(STK)]})) == 1 and ranked({"trig_strong": [sig()]}) == [])
check("a stream that is on neither roster takes no seat", ranked({"elite_conv": [sig()], "prime_trig": [sig()], "apex_v2_gated": [sig()]}) == [])
_o = ranked({"leg2_prime": [sig("AUSDT")], "star_takenow": [sig("BUSDT")], "apex_v2": [sig("CUSDT", side="SHORT")], "go_revived": [sig("DUSDT")],
             "elite_confirm": [sig("EUSDT")], "elite_star": [sig("FUSDT", gate="pass")], "trig_strong": [sig(STK)]})
check("offered together, the seats are filled in his order", [c["src"] for c in _o] == ["elite_star", "elite_confirm", "go_revived", "apex_v2", "star_takenow", "leg2_prime", "trig_strong"], [c["src"] for c in _o])
_o = ranked({"elite_confirm": [sig(stop=95.0)], "elite_star": [sig(gate="pass", stop=96.5)]})
check("a star and a confirmed entry on one name make one card, on the star's plan", len(_o) == 1 and _o[0]["src"] == "elite_star" and _o[0]["stop"] == 96.5 and set(_o[0]["plans"]) == {"elite_star", "elite_confirm"})

print("3. the light rule")
for nm, lf in (("🟢", GREEN), ("🟡", YELLOW), ("⚪ (no closed trade yet)", WHITE)):
    st = opened({"elite_confirm": [sig()]}, lf)
    check(f"{nm} opens a seat, and the seat remembers its light", len(st["open"]) == 1 and st["open"][0]["src"] == "elite_confirm" and st["open"][0]["light"].startswith(lf(0, 0, 0, 0)[0]), st.get("skip_log"))
st = opened({"elite_confirm": [sig()]}, RED)
check("🔴 opens nothing, and the book says why with the record", not st["open"] and len(st["skip_log"]) == 1 and "🔴 window" in st["skip_log"][0]["why"] and "40% (10)" in st["skip_log"][0]["why"], st.get("skip_log"))


def _boom(*a):
    raise RuntimeError("db locked")


st = opened({"elite_confirm": [sig()]}, _boom)
check("a light that cannot be read opens nothing", not st["open"] and "could not be read" in st["skip_log"][0]["why"], st.get("skip_log"))
_seen = []
st = opened({"go_revived": [sig(COIN2, side="SHORT", fired_at=NOW - 900)]}, lambda *a: (_seen.append(a), ("🟢", "x"))[1])
check("the light is asked for the stream, the name, the side and the fire's time", _seen == [("go_revived", COIN2, "SHORT", NOW - 900)], _seen)
st = opened({"elite_confirm": [sig(stop=95.0)], "elite_star": [sig(gate="pass", stop=96.5)]},
            lambda src, sym, side, ts: RED() if False else (("🔴", "red for the star") if src == "elite_star" else ("🟢", "green for the entry")))
check("the star's window is 🔴 but the confirmed entry's is not: the seat opens as a confirmed entry, on its own plan",
      len(st["open"]) == 1 and st["open"][0]["src"] == "elite_confirm" and st["open"][0]["stop"] == 95.0 and st["open"][0]["light"] == "🟢 green for the entry", st["open"])
da.LIGHT_RULE = False
st = opened({"elite_confirm": [sig()]}, RED)
check("LIGHT_RULE = False: the light is not read (the switch)", len(st["open"]) == 1)
da.LIGHT_RULE = True

print("4. added margin")
st = opened({"elite_star": [sig(gate="pass")]})
check("a gated star opens one full seat: $250 margin, $2,500 position", len(st["open"]) == 1 and abs(st["open"][0]["margin"] - 250) < 0.01 and abs(st["open"][0]["notional"] - 2500) < 0.01)
st = opened({"star_go": [sig(entry=101.0, fired_at=NOW + 600)]}, st=st, now=NOW + 600)
check("the star's GO adds one seat of margin to the star seat, the stop and TP1 kept", len(st["open"]) == 1 and abs(st["open"][0]["margin"] - 500) < 2 and st["open"][0]["add_srcs"] == ["star_go"]
      and st["open"][0]["stop"] == 96.0 and st["open"][0]["tp1"] == 106.0 and len(da.STREAM_ADDS) == 1, st["open"])
st = opened({"star_go": [sig(fired_at=NOW + 1200)], "elite_confirm": [sig(fired_at=NOW + 1200)], "go_revived": [sig(fired_at=NOW + 1200)]}, st=st, now=NOW + 1200)
check("nothing else adds to a star seat (a confirmed entry and a revival do not; the GO only once)", abs(st["open"][0]["margin"] - 500) < 2 and len(st["open"][0]["adds"]) == 1, st["open"][0].get("add_srcs"))
st = opened({"star_go": [sig(COIN2)]})
check("the star's GO on a name the demo does not hold opens nothing and logs nothing", not st["open"] and not st.get("skip_log"), st.get("skip_log"))
st = opened({"elite_confirm": [sig()]})
st = opened({"elite_star": [sig(gate="pass", fired_at=NOW + 300)]}, st=st, now=NOW + 300)
check("an elite star on a held confirmed-entry seat adds a seat of margin", len(st["open"]) == 1 and st["open"][0]["src"] == "elite_confirm" and abs(st["open"][0]["margin"] - 500) < 2 and st["open"][0]["add_srcs"] == ["elite_star"])
st = opened({"go_revived": [sig(fired_at=NOW + 600)]}, st=st, now=NOW + 600)
check("a conviction revival adds the second", abs(st["open"][0]["margin"] - 750) < 4 and st["open"][0]["add_srcs"] == ["elite_star", "go_revived"], st["open"][0])
check("a fire that added margin is not also logged as a seat not taken", not st.get("skip_log"), st.get("skip_log"))
st = opened({"star_go": [sig(fired_at=NOW + 900)]}, st=st, now=NOW + 900)
check("two adds a position at most: the star's GO after them adds nothing", da.ADD_MAX == 2 and abs(st["open"][0]["margin"] - 750) < 4 and len(st["open"][0]["adds"]) == 2)
st = opened({"elite_confirm": [sig()]})
st = opened({"go_revived": [sig(fired_at=NOW + 300)]}, RED, st=st, now=NOW + 300)
check("a stream in a 🔴 window adds no margin", abs(st["open"][0]["margin"] - 250) < 0.01 and not st["open"][0].get("add_srcs"))
st = opened({"go_revived": [sig(fired_at=NOW + 600)]}, st=st, now=NOW + 600)
check("… and adds once its window is no longer red", abs(st["open"][0]["margin"] - 500) < 2 and st["open"][0]["add_srcs"] == ["go_revived"])
st = opened({"go_revived": [sig(COIN3)]})
check("a conviction revival on a name not held opens its own seat", len(st["open"]) == 1 and st["open"][0]["src"] == "go_revived")
st = opened({"elite_confirm": [sig()]})
st = opened({"go_revived": [sig(side="SHORT", fired_at=NOW + 300)]}, st=st, now=NOW + 300)
check("no add from the other side, and no second seat on the name", len(st["open"]) == 1 and abs(st["open"][0]["margin"] - 250) < 0.01)
st = opened({"elite_star": [sig(STK)]})
st = opened({"star_go": [sig(STK, fired_at=NOW + 300)]}, st=st, now=NOW + 300)
check("stocks: a star seat takes its GO's add too", len(st["open"]) == 1 and abs(st["open"][0]["margin"] - 500) < 2 and st["open"][0]["add_srcs"] == ["star_go"])

print("5. the stop rule's stop: 10x, or 8x when it is wide")
st = opened({"apex_v2": [sig(side="SHORT", stop=107.0)]})
check("a 7% stop opens at 10x", len(st["open"]) == 1 and st["open"][0]["lev"] == 10.0 and abs(st["open"][0]["notional"] - 2500) < 0.01)
st = opened({"apex_v2": [sig(side="SHORT", stop=108.0)]})
check("the rule's 8% stop opens at 8x on the same $250 ($2,000 position, $160 at risk)", len(st["open"]) == 1 and st["open"][0]["lev"] == 8.0 and abs(st["open"][0]["margin"] - 250) < 0.01
      and abs(st["open"][0]["notional"] - 2000) < 0.01 and abs(st["open"][0]["risk_usd"] - 160) < 0.01, st["open"])
st = opened({"apex_v2": [sig(side="SHORT", stop=110.5)]})
check("a stop past the 8x guard (10%) takes no seat", not st["open"] and "too wide for 8x" in st["skip_log"][0]["why"], st.get("skip_log"))

print("6. the exit: the stop, or everything at 85% of the way to TP1")
check("the 85% close covers every stream of both rosters", da.NEAR_TP_TOUCH == 0.85 and all(s in da.NEAR_TP_TOUCH_SRC and s in da.SMART_EXIT_SKIP for r in da.ROSTER.values() for s in r)
      and not da.LADDER_SRC and da.REENTRY_ON is False)
st = opened({"apex_v2": [sig(side="SHORT")]})
px[COIN] = 94.8                                  # 87% of the way from 100 to 94
ev = da.manage(st, live)
check("a coin short closes in full at the 85% level, booked there", not st["open"] and len(ev) == 1 and abs(st["closed"][-1]["exit"] - 94.9) < 1e-9 and "85% of the way to TP1" in st["closed"][-1]["reason"]
      and st["closed"][-1]["pnl"] > 0, st["closed"][-1:])
px[COIN] = 100.0
st = opened({"leg2_prime": [sig()]})
px[COIN] = 95.9
ev = da.manage(st, live)
check("a coin long through its stop closes at the stop", not st["open"] and st["closed"][-1]["exit"] == 96.0 and st["closed"][-1]["reason"] == "stop" and st["closed"][-1]["pnl"] < 0, st["closed"][-1:])
px[COIN] = 100.0

print("7. the cut-over")
json.dump({"gen": 22, "balance": 4569.0, "start": 5000.0, "open": [
    {"symbol": STK, "base": STK.replace("USDT", ""), "side": "LONG", "entry": 100.0, "stop": 96.0, "tp1": 106.0, "tp2": None, "qty": 25.0,
     "notional": 2500.0, "lev": 10.0, "margin": 250.0, "src": "elite_confirm", "opened_at": NOW - 7200, "fees": 1.4}], "closed": [], "equity_hist": []},
    io.open(da.STATE_FILE, "w", encoding="utf-8"))
check("before the cut-over the old file is 'pending'", da.cutover_pending() is True)
da.save(fresh())
check("a new-generation book is never saved over the old ledger before the cut-over (the seat taken at the signal, the cycle's own save)",
      json.load(io.open(da.STATE_FILE, encoding="utf-8"))["gen"] == 22 and len(json.load(io.open(da.STATE_FILE, encoding="utf-8"))["open"]) == 1)
px[STK] = 0.0                                    # the old seat's price cannot be read
ev = da.cutover_fresh_book(live)
check("a seat whose price cannot be read makes the cut-over wait: nothing closed, nothing archived, the old book intact",
      ev == [] and da.cutover_pending() is True and not [f for f in os.listdir(TMP) if ".gen22_" in f]
      and len(json.load(io.open(da.STATE_FILE, encoding="utf-8"))["open"]) == 1)
da.save(fresh())
check("… and the cycle's save in that state still leaves it alone", json.load(io.open(da.STATE_FILE, encoding="utf-8"))["gen"] == 22)
px[STK] = 101.0
ev = da.cutover_fresh_book(live)
bk = da.load()
arch = [f for f in os.listdir(TMP) if ".gen22_" in f]
check("the GEN 22 seat closes at the live price into its own ledger, which is archived", len(ev) == 1 and ev[0][1]["exit"] == 101.0 and "GEN 23 cut-over" in ev[0][1]["reason"] and len(arch) == 1
      and json.load(io.open(os.path.join(TMP, arch[0]), encoding="utf-8"))["gen"] == 22, (ev, arch))
check("the fresh book: GEN 23, $5,000, nothing open, nothing closed", bk["gen"] == 23 and bk["balance"] == 5000.0 and bk["start"] == 5000.0 and not bk["open"] and not bk["closed"])
check("the cut-over runs once, and nothing is pending after it", da.cutover_fresh_book(live) == [] and da.cutover_pending() is False)
_b2 = fresh()
_b2["balance"] = 5123.0
da.save(_b2)
check("after the cut-over the book saves as always", da.load()["balance"] == 5123.0)
px[STK] = 100.0

print("8. the light, read from the desk (tg_roster.demo_light)")
con = ws._open()
ROWS = [
    # coin confirmed entry since the rule, 09–13 PKT: longs 1 of 4, shorts 3 of 3
    *[("elite_confirm", COIN, "LONG", at(2026, 11, 19, 10) + i * 600, 1.0 if i == 0 else -1.0) for i in range(4)],
    *[("elite_confirm", COIN2, "SHORT", at(2026, 11, 20, 11) + i * 600, 0.5) for i in range(3)],
    ("elite_confirm", COIN, "LONG", at(2026, 11, 10, 10), 1.0), ("elite_confirm", COIN, "LONG", at(2026, 11, 11, 10), 1.0),   # before the rule: not read
    ("elite_confirm", COIN, "LONG", at(2026, 11, 19, 18), 1.0),                                                               # another window
    ("tok:elite_confirm", STK, "LONG", at(2026, 11, 19, 10), 1.0),                                                            # the other class
    # APEX V2 since the rule, 17–21 PKT: shorts 5 of 6 with small wins (a losing record), one long
    *[("apex_v2", COIN, "SHORT", at(2026, 11, 20, 18) + i * 300, 0.05 if i < 5 else -1.0) for i in range(6)],
    ("apex_v2", COIN, "LONG", at(2026, 11, 20, 18), -1.0),
    # the revival, 13–17: two of three (67% → 🟡)
    *[("go_revived", COIN, "LONG", at(2026, 11, 21, 14) + i * 300, 0.4 if i < 2 else -1.0) for i in range(3)],
    # a stock strong trigger, 21–01
    ("tok:trig_strong", STK, "SHORT", at(2026, 11, 20, 22), 0.6), ("trig_strong", COIN, "SHORT", at(2026, 11, 20, 22), -1.0),
    # coin stars 05–09: the gate passed one (won) and muted one (lost)
    ("elite_star", COIN, "LONG", at(2026, 11, 21, 6), 0.8), ("elite_star", COIN2, "LONG", at(2026, 11, 21, 7), -1.0),
    # stock stars 05–09: every fire counts
    ("tok:elite_star", STK, "LONG", at(2026, 11, 21, 6), 0.8), ("tok:elite_star", STK2, "LONG", at(2026, 11, 21, 7), -1.0)]
for tier, sym, side, o, r in ROWS:
    con.execute("INSERT INTO shadow_trades (tier, symbol, side, entry, stop, opened_at, status, closed_at, pnl_r) VALUES (?,?,?,?,?,?,?,?,?)",
                (tier, sym, side, 100.0, 96.0, o, "CLOSED", o + 3600, r))
con.execute("INSERT INTO signals (ts, stream, symbol, base, side, extra) VALUES (?, 'elite_star', ?, 'SOL', 'LONG', ?)", (at(2026, 11, 21, 6) - 5, COIN, '{"gate": "pass"}'))
con.execute("INSERT INTO signals (ts, stream, symbol, base, side, extra) VALUES (?, 'elite_star', ?, 'NEAR', 'LONG', ?)", (at(2026, 11, 21, 7) - 5, COIN2, '{"gate": "muted"}'))
con.commit()
con.close()
tr._BELL_CACHE.clear()
T10, T18, T14, T22, T06, T02 = at(2026, 11, 24, 10), at(2026, 11, 24, 18), at(2026, 11, 24, 14), at(2026, 11, 24, 22), at(2026, 11, 24, 6), at(2026, 11, 24, 2)
check("the cell is this stream, this class, this side, this window, since the stop rule: coin confirmed-entry longs 09–13 are 🔴 25% (4)",
      tr.demo_light("elite_confirm", COIN, "LONG", T10, NOW) == ("🔴", "09–13 PKT longs 25% (4, thin)"), tr.demo_light("elite_confirm", COIN, "LONG", T10, NOW))
check("… its shorts in the same window are 🟢 100% (3)", tr.demo_light("elite_confirm", COIN, "SHORT", T10, NOW) == ("🟢", "09–13 PKT shorts 100% (3, thin)"), tr.demo_light("elite_confirm", COIN, "SHORT", T10, NOW))
check("… another window reads its own trade, and a window with none is ⚪", tr.demo_light("elite_confirm", COIN, "LONG", T18, NOW)[0] == "🟢"
      and tr.demo_light("elite_confirm", COIN, "LONG", T14, NOW) == ("⚪", "13–17 PKT longs no closed trade yet"))
check("a winning rate on a record that lost money is 🟡, never 🟢 (APEX V2 shorts 83% / −0.13R)", tr.demo_light("apex_v2", COIN, "SHORT", T18, NOW) == ("🟡", "17–21 PKT shorts 83% (6, thin)"), tr.demo_light("apex_v2", COIN, "SHORT", T18, NOW))
check("67% is 🟡", tr.demo_light("go_revived", COIN, "LONG", T14, NOW)[0] == "🟡")
check("the strong trigger reads the stock tier, not the coin one", tr.demo_light("trig_strong", STK, "SHORT", T22, NOW) == ("🟢", "21–01 PKT shorts 100% (1, thin)"), tr.demo_light("trig_strong", STK, "SHORT", T22, NOW))
check("a coin star reads its gated fires only (the muted loser is not in it); a stock star reads every fire",
      tr.demo_light("elite_star", COIN, "LONG", T06, NOW) == ("🟢", "05–09 PKT longs 100% (1, thin)") and tr.demo_light("elite_star", STK, "LONG", T06, NOW) == ("🔴", "05–09 PKT longs 50% (2, thin)"),
      (tr.demo_light("elite_star", COIN, "LONG", T06, NOW), tr.demo_light("elite_star", STK, "LONG", T06, NOW)))
check("the star's GO reads the star's light", tr.demo_light("star_go", COIN, "LONG", T06, NOW) == tr.demo_light("elite_star", COIN, "LONG", T06, NOW))
check("the light matches the window cell printed on the bell", ("09–13 PKT 🟢 100% (3, thin)" in tr.before_after("elite_confirm", COIN2, "SHORT", T10))
      and ("09–13 PKT 🔴 25% (4, thin)" in tr.before_after("elite_confirm", COIN, "LONG", T10)), tr.before_after("elite_confirm", COIN, "LONG", T10))
try:
    tr.demo_light("elite_conv", COIN, "LONG", T10, NOW)
    _raised = False
except KeyError:
    _raised = True
check("a stream with no record of its own raises, so the demo refuses rather than guesses", _raised)
check("every stream of both rosters has a light", all(s in tr.DEMO_BELL and tr.DEMO_BELL[s] in tr.BELL_TIER for r in da.ROSTER.values() for s in r) and "star_go" in tr.DEMO_BELL)
st = opened({"elite_confirm": [sig(fired_at=T10)]}, tr.demo_light, now=T10)
check("end to end on the desk's rows: a coin confirmed-entry long at 10:00 PKT opens nothing", not st["open"] and "🔴 window" in st["skip_log"][0]["why"] and "25% (4, thin)" in st["skip_log"][0]["why"], st.get("skip_log"))
st = opened({"elite_confirm": [sig(COIN2, side="SHORT", fired_at=T10)]}, tr.demo_light, now=T10)
check("… and the short at the same hour opens", len(st["open"]) == 1 and st["open"][0]["light"] == "🟢 09–13 PKT shorts 100% (3, thin)", st.get("skip_log"))

print("9. the desk feed")
import types                   # noqa: E402
calls = []
_keep_store, _keep_hook = sh.store, sh.DEMO_HOOK
sh.store = types.SimpleNamespace(MIN_RISK_FRAC=0.003, desk_tier=lambda tier, sym: ("tok:" + tier) if sym in config.TOKENIZED_STOCKS else tier,
                                 shadow_has_open=lambda tier, sym: False, shadow_open=lambda *a, **k: None)
sh.DEMO_HOOK = lambda feed: calls.append(dict(feed))
del sh.DEMO_FEED[:]
base = {"side": "LONG", "stop": 96.0, "tp1": 106.0, "tp2": 110.0, "score": 91}
for tier in ("elite_star", "elite_confirm", "go_revived", "apex_v2", "star_takenow", "leg2_prime", "trig_strong", "elite_conv", "apex_v2_gated", "prime_trig"):
    sh.open_from_signal(tier, dict(base, symbol=COIN, gate="pass", star=(tier == "go_revived"), tier="FAST"), 100.0)
    sh.open_from_signal(tier, dict(base, symbol=STK), 100.0)
got = sorted((c["symbol"] == STK, c["src"]) for c in calls)
check("coin seats of his six streams and stock seats of his three are offered, nothing else",
      got == sorted([(False, s) for s in sh.DEMO_FEED_COIN] + [(True, s) for s in sh.DEMO_FEED_STOCK])
      and sh.DEMO_FEED_COIN == set(da.ROSTER["coin"]) and sh.DEMO_FEED_STOCK == set(da.ROSTER["stock"]), got)
_c = {(c["symbol"], c["src"]): c for c in calls}
check("the offer carries the gate's stamp, the star flag and the GO's speed", _c[(COIN, "elite_star")]["gate"] == "pass" and _c[(COIN, "go_revived")]["star"] is True
      and _c[(COIN, "go_revived")]["go_tier"] == "FAST" and _c[(STK, "go_revived")]["star"] is False and _c[(COIN, "apex_v2")]["go_tier"] is None)
sh.open_from_signal("elite_confirm", dict(base, symbol=COIN3, mirror_of="conviction_v2"), 100.0)
check("a mirrored seat is never offered", (COIN3, "elite_confirm") not in {(c["symbol"], c["src"]) for c in calls[len(_c):]})
n0 = len(sh.DEMO_FEED)
sh.demo_offer({"symbol": COIN, "side": "LONG", "src": "star_go"})
check("demo_offer puts the entry on the feed and calls the hook", len(sh.DEMO_FEED) == n0 + 1 and calls[-1]["src"] == "star_go")
sh.store, sh.DEMO_HOOK = _keep_store, _keep_hook

print("10. the worker and the page")
W = io.open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
check("both demo paths hand try_open the light", W.count("light_fn=_demo_light") == 2 and "def _demo_light(src, symbol, side, ts):" in W and "return tg_roster.demo_light(src, symbol, side, ts)" in W)
check("the pools are every stream on the ladder", "for _s21 in demo_account.CLASS_W}" in W)
i_inst = W.index("def _demo_instant(feed):")
check("the seat taken at the signal waits for the cut-over; the cycle prints when the cut-over is waiting",
      "if demo_account.cutover_pending():\n                return\n            _st_i = demo_account.load()" in W[i_inst:i_inst + 2600]
      and W.count("demo_account.cutover_pending()") == 2 and "cut-over waiting" in W)
i_go = W.index('"src": "star_go", "fired_at": _ew_now')
check("the star's GO is offered to the demo when the phone heard the star", 'if _ew.get("star") and _ew.get("buzzed"):' in W[i_go - 900:i_go] and "shadow_trader.demo_offer({" in W[i_go - 900:i_go])
A = io.open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
check("the page says GEN 23, both rosters, the light rule, the 8x seat and the 85% close",
      "🎮 DEMO $5,000 — GEN 23 · COINS + STOCKS" in A and "GEN 22 · STOCKS ONLY" not in A and "<b>The light rule:</b>" in A and "opens at 8x" in A
      and "the 85% close" in A and "Fresh $5,000 book since 23 Nov" in A and "_p.get('light')" in A)

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("FAIL:", f)
sys.exit(1 if FAIL else 0)
