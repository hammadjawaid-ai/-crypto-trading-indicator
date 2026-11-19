"""Guard — THE 92% CLOSE (2026-11-20): a demo seat and a Paper Trader position close in full once price has
travelled 92% of the way from the entry to TP1, booked at that level (never higher), the stop first, the fade bank
and a TP2 chase untouched, and both switches turn it off. No network, no Telegram.
Run: .venv/Scripts/python.exe .near_tp_test.py
"""
import calendar
import os
import sys
import tempfile
import time as _time

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="neartp_")
os.environ["WORKER_DB_PATH"] = os.path.join(TMP, "worker.db")
import demo_account as da      # noqa: E402
import paper_bot as pb         # noqa: E402

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


_TODAY = _time.gmtime()
T07 = float(calendar.timegm((_TODAY.tm_year, _TODAY.tm_mon, _TODAY.tm_mday, 2, 0, 0)))      # 07:00 PKT
M0 = T07 + 60.0
px = {}
live = lambda s: px.get(s, 0.0)


def seat(src="elite_confirm", sym="NVDABUSDT", side="LONG", stop=96.0, tp1=110.0):
    st = {"gen": da.GEN, "balance": 5000.0, "start": 5000.0, "started_at": T07, "open": [], "closed": [], "equity_hist": []}
    px[sym] = 100.0
    c = {"symbol": sym, "base": sym.replace("USDT", ""), "side": side, "entry": 100.0, "stop": stop, "tp1": tp1,
         "tp2": 120.0 if side == "LONG" else 80.0, "score": 90.0, "conf": 80.0, "burst": 0.0, "src": src, "rank": 99.0, "top": 1}
    da.try_open(st, [c], live, now=T07)
    return st


def K(rows):
    data = [(M0 + 60.0 * i, h, l, c) for i, h, l, c in rows]
    return lambda sym, start: [r for r in data if r[0] >= start]


check("the switch is 92% and covers the demo's streams", da.NEAR_TP_TOUCH == 0.92
      and {"elite_confirm", "go_revived", "elite_star", "trig_strong"} <= da.NEAR_TP_TOUCH_SRC)
st = seat()
check("a seat opened (entry 100, TP1 110: the 92% level is 109.2)", len(st["open"]) == 1 and st["open"][0]["tp1"] == 110.0, st["open"])
px["NVDABUSDT"] = 109.1
check("demo, long: 91% of the way is not closed", da.manage(st, live) == [] and len(st["open"]) == 1)
px["NVDABUSDT"] = 109.21
ev = da.manage(st, live)
check("demo, long: at 92% the whole seat closes, at the 92% level",
      len(ev) == 1 and ev[0][0] == "close" and abs(ev[0][1]["exit"] - 109.2) < 1e-9 and "92% of the way to TP1" in ev[0][1]["reason"]
      and ev[0][1]["pnl"] > 0 and st["open"] == [], ev)
st = seat()
px["NVDABUSDT"] = 111.5
ev = da.manage(st, live)
check("demo, long: a look that finds price beyond TP1 still books the 92% level (the order rested there)",
      len(ev) == 1 and abs(ev[0][1]["exit"] - 109.2) < 1e-9, ev)
st = seat(side="SHORT", stop=104.0, tp1=90.0)
px["NVDABUSDT"] = 90.9
check("demo, short: 91% of the way is not closed", da.manage(st, live) == [])
px["NVDABUSDT"] = 90.79
ev = da.manage(st, live)
check("demo, short: at 92% it closes at 90.8", len(ev) == 1 and abs(ev[0][1]["exit"] - 90.8) < 1e-9 and ev[0][1]["pnl"] > 0, ev)
st = seat()
px["NVDABUSDT"] = 95.0
ev = da.manage(st, live)
check("demo: the stop is still the stop", len(ev) == 1 and ev[0][1]["reason"] == "stop", ev)

# the watcher's candle walk
st = seat()
ev = da.walk(st, K([(0, 101.0, 99.5, 100.5), (1, 109.5, 100.0, 104.0)]), now=M0 + 200)
check("walk: a candle whose high reaches 92% closes the seat at the level, stamped with that candle",
      len(ev) == 1 and abs(ev[0][1]["exit"] - 109.2) < 1e-9 and abs(ev[0][1]["closed_at"] - (M0 + 60 + 59)) < 1e-6, ev)
st = seat()
ev = da.walk(st, K([(0, 109.5, 99.0, 99.2), (1, 99.5, 95.5, 96.0)]), now=M0 + 200)
check("walk: the case he described — 95% of the way, then down through the stop: a win at 92%, not a stop",
      len(ev) == 1 and abs(ev[0][1]["exit"] - 109.2) < 1e-9 and ev[0][1]["pnl"] > 0 and st["open"] == [], ev)
st = seat()
ev = da.walk(st, K([(0, 109.6, 95.5, 100.0)]), now=M0 + 200)
check("walk: the stop and the 92% level inside one candle books the stop (the bad side first)",
      len(ev) == 1 and ev[0][1]["reason"] == "stop", ev)
st = seat()
ev = da.walk(st, K([(0, 108.6, 100.0, 108.0), (1, 108.0, 105.5, 105.8)]), now=M0 + 200)
check("walk: the fade bank still covers a seat that peaks between 85% and 92% and rolls back",
      len(ev) == 1 and "near-TP bank" in ev[0][1]["reason"] and ev[0][1]["pnl"] > 0, ev)

# off switch and scope
keep = da.NEAR_TP_TOUCH
da.NEAR_TP_TOUCH = 0
st = seat()
px["NVDABUSDT"] = 109.5
off1 = da.manage(st, live)
px["NVDABUSDT"] = 110.0
off2 = da.manage(st, live)
da.NEAR_TP_TOUCH = keep
check("off (NEAR_TP_TOUCH = 0): 95% is held and TP1 banks at TP1 as before",
      off1 == [] and len(off2) == 1 and off2[0][1]["reason"] == "TP1 — banked 100%" and abs(off2[0][1]["exit"] - 110.0) < 1e-9, (off1, off2))
keep_src = set(da.NEAR_TP_TOUCH_SRC)
da.NEAR_TP_TOUCH_SRC = keep_src - {"elite_confirm"}
st = seat()
px["NVDABUSDT"] = 109.5
out = da.manage(st, live)
da.NEAR_TP_TOUCH_SRC = keep_src
check("a stream outside NEAR_TP_TOUCH_SRC keeps its full TP1", out == [] and len(st["open"]) == 1)

# ── the Paper Trader ──
def book():
    return {"balance": 1000.0, "risk_per_trade_pct": 1.0, "open": [], "closed": [], "leverage": 1.0}


def pos(side="LONG", **kw):
    p = {"symbol": "AAAUSDT", "base": "AAA", "side": side, "entry": 100.0, "stop": 85.0 if side == "LONG" else 115.0,
         "target": 110.0 if side == "LONG" else 90.0, "target_2": 0.0, "chase_tp2_eligible": False, "qty": 2.0,
         "original_qty": 2.0, "opened_at": T07}
    p.update(kw)
    return p


check("paper: the switch is 92%", pb.NEAR_TARGET == 0.92)
b = book()
b["open"].append(pos())
check("paper, long: 91% of the way stays open", pb.evaluate(b, {"AAAUSDT": 109.1}) == [] and len(b["open"]) == 1)
cl = pb.evaluate(b, {"AAAUSDT": 109.3})
check("paper, long: at 92% it closes at 109.2, counted as a target close, marked near_target",
      len(cl) == 1 and abs(cl[0]["exit"] - 109.2) < 1e-9 and cl[0]["exit_reason"] == "target" and cl[0].get("near_target") == 0.92
      and abs(cl[0]["pnl_usd"] - 18.4) < 1e-6 and b["open"] == [], cl)
b = book()
b["open"].append(pos())
cl = pb.evaluate(b, {"AAAUSDT": 112.0})
check("paper, long: price beyond the target still books the 92% level", len(cl) == 1 and abs(cl[0]["exit"] - 109.2) < 1e-9, cl)
b = book()
b["open"].append(pos("SHORT"))
cl = pb.evaluate(b, {"AAAUSDT": 90.7})
check("paper, short: at 92% it closes at 90.8", len(cl) == 1 and abs(cl[0]["exit"] - 90.8) < 1e-9 and cl[0]["pnl_usd"] > 0, cl)
b = book()
b["open"].append(pos())
cl = pb.evaluate(b, {"AAAUSDT": 84.0})
check("paper: the stop is still the stop", len(cl) == 1 and cl[0]["exit_reason"] == "stop" and "near_target" not in cl[0], cl)
b = book()
b["open"].append(pos(chase_tp2_eligible=True, target_2=120.0))
c1 = pb.evaluate(b, {"AAAUSDT": 109.5})
check("paper: a PREMIUM position that chases TP2 is not closed at 92%", c1 == [] and len(b["open"]) == 1 and not b["open"][0].get("chasing_tp2"))
pb.evaluate(b, {"AAAUSDT": 110.5})
check("paper: … and at TP1 it still locks TP1 and runs for TP2", len(b["open"]) == 1 and b["open"][0].get("chasing_tp2") is True
      and b["open"][0]["target"] == 120.0)
keep = pb.NEAR_TARGET
pb.NEAR_TARGET = 0
b = book()
b["open"].append(pos())
o1 = pb.evaluate(b, {"AAAUSDT": 109.5})
o2 = pb.evaluate(b, {"AAAUSDT": 110.0})
pb.NEAR_TARGET = keep
check("paper, off (NEAR_TARGET = 0): 95% is held and the target closes at the target",
      o1 == [] and len(o2) == 1 and abs(o2[0]["exit"] - 110.0) < 1e-9 and "near_target" not in o2[0], (o1, o2))

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("FAIL:", f)
sys.exit(1 if FAIL else 0)
