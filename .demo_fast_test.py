"""Guard — the demo's fast paths (2026-11-18): the state lock, the atomic save, the one-minute candle walk
(TP1 / stop on highs and lows, the bad side first), the watcher's tick, the seat taken as the desk opens it, and
the 'seat not taken, and why' log. No network, no Telegram.
Run: .venv/Scripts/python.exe .demo_fast_test.py
"""
import calendar
import io
import json
import os
import sys
import tempfile
import threading
import time as _time

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="demofast_")
os.environ["WORKER_DB_PATH"] = os.path.join(TMP, "worker.db")
import demo_account as da      # noqa: E402
import demo_watch as dw        # noqa: E402
import shadow_trader as sh     # noqa: E402

da.STATE_FILE = os.path.join(TMP, "demo.json")
TT = float(da.NEAR_TP_TOUCH)                                  # the demo's near-TP close level (22.8)
R_NT = f"🎯 closed at {TT * 100:.0f}% of the way to TP1"
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


def T(h_pkt, m=0):
    return float(calendar.timegm((_TODAY.tm_year, _TODAY.tm_mon, _TODAY.tm_mday, (h_pkt - 5) % 24, m, 0)))


T07 = T(7)


def fresh():
    return {"gen": da.GEN, "balance": 5000.0, "start": 5000.0, "started_at": T07, "open": [], "closed": [], "equity_hist": []}


def cand(src, sym="NVDABUSDT", side="LONG", entry=100.0, stop=96.0, tp1=106.0, tp2=110.0, **kw):
    c = {"symbol": sym, "base": sym.replace("USDT", ""), "side": side, "entry": entry, "stop": stop, "tp1": tp1, "tp2": tp2,
         "score": 90.0, "conf": 80.0, "burst": 0.0, "src": src, "rank": 99.0, "top": 1}
    c.update(kw)
    return c


px = {"NVDABUSDT": 100.0, "SOXLBUSDT": 100.0, "MUBUSDT": 100.0}
live = lambda s: px.get(s, 0.0)
M0 = T07 + 60.0                                                   # the first full minute after a seat opened at T07


def seat(src="elite_star", sym="NVDABUSDT", side="LONG", stop=96.0, tp1=106.0):
    st = fresh()
    px[sym] = 100.0
    da.try_open(st, [cand(src, sym, side, 100.0, stop, tp1, 110.0 if side == "LONG" else 90.0)], live, now=T07)
    return st


def K(rows):
    """rows: [(minute index, high, low, close)] -> a klines_fn serving them for every symbol."""
    data = [(M0 + 60.0 * i, h, l, c) for i, h, l, c in rows]
    return lambda sym, start: [r for r in data if r[0] >= start]


# ── the lock ──
check("lock: taken, mine, released", da.lock() and da.lock_mine() and (da.unlock() or True) and not da.lock_mine())
da.lock()
got = []
th = threading.Thread(target=lambda: got.append(da.lock(timeout=0.3)))
th.start()
th.join()
check("lock: another thread cannot take it while it is held, and does not block for ever", got == [False])
check("lock: the holder taking it again does not deadlock (and one unlock frees it)", da.lock() is True and (da.unlock() or True) and not da.lock_mine())
got = []
th = threading.Thread(target=lambda: (got.append(da.lock(timeout=0.3)), da.unlock()))
th.start()
th.join()
check("lock: free again for the other thread", got == [True] and not da._LOCK.locked())
# ── the atomic save ──
st0 = fresh()
da.save(st0)
check("save is atomic: the file loads and no .tmp is left beside it", da.load()["balance"] == 5000.0 and not os.path.exists(str(da.STATE_FILE) + ".tmp"))
# ── the one-minute walk ──
st = seat()
n_hist = len(st["equity_hist"])
ev = da.walk(st, K([(0, 101.0, 99.5, 100.5), (1, 106.5, 100.0, 106.0)]), now=M0 + 200)
check("walk, long: the near-TP close books at its level (entry 100, TP1 106), stamped with the minute it happened",
      len(ev) == 1 and ev[0][1]["reason"] == R_NT and abs(ev[0][1]["exit"] - (100.0 + TT * 6.0)) < 1e-9 and not st["open"]
      and abs(ev[0][1]["closed_at"] - (M0 + 60 + 59)) < 1e-6, ev)
check("walk does not write the equity curve (the cycle does)", len(st["equity_hist"]) == n_hist, len(st["equity_hist"]))
st = seat()
ev = da.walk(st, K([(0, 100.5, 95.9, 99.0), (1, 107.0, 99.0, 106.5)]), now=M0 + 200)
check("walk: a one-minute wick through the stop is a STOP, even though price then ran to TP1 (the MVLL case)",
      len(ev) == 1 and ev[0][1]["reason"] == "stop" and abs(ev[0][1]["exit"] - 96.0) < 1e-9 and ev[0][1]["pnl"] < 0 and not st["open"], ev)
st = seat()
ev = da.walk(st, K([(0, 106.5, 95.5, 106.0)]), now=M0 + 200)
check("walk: stop and TP1 inside the same minute books the stop (the bad side first)", len(ev) == 1 and ev[0][1]["reason"] == "stop", ev)
st = seat(side="SHORT", stop=104.0, tp1=94.0)
ev = da.walk(st, K([(0, 100.4, 99.0, 99.5), (1, 104.2, 99.0, 100.0)]), now=M0 + 200)
check("walk, short: the high takes the stop", len(ev) == 1 and ev[0][1]["reason"] == "stop" and abs(ev[0][1]["exit"] - 104.0) < 1e-9, ev)
st = seat(side="SHORT", stop=104.0, tp1=94.0)
ev = da.walk(st, K([(0, 100.4, 93.8, 94.5)]), now=M0 + 200)
check("walk, short: the low takes the near-TP close (entry 100, TP1 94)", len(ev) == 1 and ev[0][1]["reason"] == R_NT and abs(ev[0][1]["exit"] - (100.0 - TT * 6.0)) < 1e-9, ev)
st = seat()
pre = lambda sym, start: [(T07 - 120.0, 120.0, 90.0, 100.0), (T07 - 60.0, 120.0, 90.0, 100.0)]
check("walk: candles from before the seat opened are not read", da.walk(st, pre, now=M0 + 200) == [] and len(st["open"]) == 1)
forming = lambda sym, start: [(M0, 100.5, 99.5, 100.0), (M0 + 60.0, 107.0, 95.0, 100.0)]
ev = da.walk(st, forming, now=M0 + 60 + 30)                       # the second candle is still forming
check("walk: a candle that has not closed yet is not read", ev == [] and len(st["open"]) == 1 and abs(st["open"][0]["walk_ts"] - (M0 + 60)) < 1e-6, st["open"][0].get("walk_ts"))
ev = da.walk(st, forming, now=M0 + 60 + 30)
check("walk: nothing is read twice", ev == [] and len(st["open"]) == 1)
ev = da.walk(st, forming, now=M0 + 200)
check("walk: the next pass picks up the minute once it has closed", len(ev) == 1 and ev[0][1]["reason"] == "stop", ev)
st = seat("trig_strong")
_tt_keep, da.NEAR_TP_TOUCH = da.NEAR_TP_TOUCH, 0.92      # at 85% the close fires before a fade can
ev = da.walk(st, K([(0, 105.2, 100.0, 105.0), (1, 105.0, 103.4, 103.5)]), now=M0 + 200)
da.NEAR_TP_TOUCH = _tt_keep
check("walk: with the close level at 92%, the near-TP bank (85% printed, back to 60%) still closes in profit", len(ev) == 1 and "near-TP bank" in ev[0][1]["reason"] and ev[0][1]["pnl"] > 0, ev)
check("walk: no seat, no candles, an error in the feed → nothing happens",
      da.walk(fresh(), K([(0, 1, 1, 1)]), now=M0) == [] and da.walk(seat(), lambda s, t: [], now=M0 + 200) == []
      and da.walk(seat(), lambda s, t: (_ for _ in ()).throw(RuntimeError("down")), now=M0 + 200) == [])
keep_clock = da._clock
st = seat()
da.walk(st, K([(0, 101.0, 99.5, 100.5)]), now=M0 + 200)
check("walk puts the clock back", da._clock is keep_clock and da._CLOSE_TS[0] is None)
# ── the watcher's tick ──
st = seat()
da.save(st)
ev = dw.tick(now=M0 + 200, klines_fn=K([(0, 106.5, 99.5, 106.0)]))
after = da.load()
check("watcher tick: the close is saved to the book and the lock is released", len(ev) == 1 and not after["open"] and len(after["closed"]) == 1 and not da._LOCK.locked(), ev)
st = seat()
da.save(st)
held = threading.Event()
done = threading.Event()


def _hold():
    da.lock()
    held.set()
    done.wait(5)
    da.unlock()


th = threading.Thread(target=_hold)
th.start()
held.wait(2)
t0 = _time.time()
ev = dw.tick(now=M0 + 200, klines_fn=K([(0, 106.5, 99.5, 106.0)]))
done.set()
th.join()
check("watcher tick: while the cycle holds the book the tick does nothing and gives up within seconds",
      ev == [] and len(da.load()["open"]) == 1 and _time.time() - t0 < 4.0, (ev, _time.time() - t0))
check("the watcher wakes every 5 minutes and reads 3-minute candles", dw.PERIOD_S == 300.0 and dw.BAR == "3m" and dw.BAR_S == 180.0, (dw.PERIOD_S, dw.BAR))
st = seat()
k3 = lambda sym, start: [r for r in [(M0, 106.5, 99.5, 106.0)] if r[0] >= start]
check("walk on 3-minute candles: a candle is not read until its three minutes are over", da.walk(st, k3, now=M0 + 100, bar_s=180.0) == [] and len(st["open"]) == 1)
ev = da.walk(st, k3, now=M0 + 181, bar_s=180.0)
check("walk on 3-minute candles: read once closed, the close stamped at the end of that candle",
      len(ev) == 1 and ev[0][1]["reason"] == R_NT and abs(ev[0][1]["closed_at"] - (M0 + 179)) < 1e-6, ev)
st = seat()
da.save(st)
seen = []
ev = dw.tick(now=M0 + 200, klines_fn=lambda sym, start: (seen.append(1) or [(M0, 100.5, 95.9, 100.0)]))
check("watcher tick on 3-minute candles: a wick inside the candle still takes the stop", len(ev) == 1 and ev[0][1]["reason"] == "stop" and seen == [1], ev)
dw.ON = False
check("demo_watch.ON = False: no tick, no thread", dw.tick(now=M0 + 200, klines_fn=K([(0, 106.5, 99.5, 106.0)])) == [] and dw.start() is False)
dw.ON = True
# ── the reasons log ──
st = fresh()
px["NVDABUSDT"] = 102.0                                            # 33% of the way from 100 to 106
da.try_open(st, [cand("elite_confirm")], live, now=T07)
lg = st.get("skip_log") or []
check("reasons log: a seat refused because price already ran says so, with the numbers",
      not st["open"] and len(lg) == 1 and lg[0]["base"] == "NVDAB" and lg[0]["src"] == "elite_confirm" and "already ran 33% of the way to TP1 (limit 25%)" in lg[0]["why"], lg)
da.try_open(st, [cand("elite_confirm")], live, now=T07 + 600)
check("reasons log: the same refusal is not repeated within the hour", len(st["skip_log"]) == 1)
da.try_open(st, [cand("elite_confirm")], live, now=T07 + 3700)
check("reasons log: … and is written again after it", len(st["skip_log"]) == 2)
px["NVDABUSDT"] = 100.0
st = fresh()
da.try_open(st, [cand("elite_star")], live, now=T(19))
check("reasons log: a shut window is named", len(st.get("skip_log") or []) == 1 and "17-21 PKT" in st["skip_log"][0]["why"] and "shut" in st["skip_log"][0]["why"], st.get("skip_log"))
st = fresh()
da.try_open(st, [cand("elite_confirm", stop=91.5)], live, now=T07)
check("reasons log: a stop too wide for 10x is named", len(st.get("skip_log") or []) == 1 and "too wide for 10x" in st["skip_log"][0]["why"], st.get("skip_log"))
st = seat("elite_confirm")
da.try_open(st, [cand("elite_confirm", fired_at=T07 - 30)], live, now=T07 + 600)
check("reasons log: the seat's own signal still in the feed is not logged as 'already holding'", not st.get("skip_log"), st.get("skip_log"))
da.try_open(st, [cand("trig_strong", fired_at=T07 + 3000)], live, now=T07 + 3060)
check("reasons log: a NEW signal on a held name is", len(st.get("skip_log") or []) == 1 and st["skip_log"][0]["why"] == "already holding this name", st.get("skip_log"))
st = fresh()
for i in range(da.SKIP_KEEP + 15):
    px["NVDABUSDT"] = 102.0
    da.try_open(st, [cand("elite_confirm", sym=f"S{i}BUSDT")], lambda s: 102.0, now=T07)
check("reasons log: the book keeps the last SKIP_KEEP lines", len(st["skip_log"]) == da.SKIP_KEEP and st["skip_log"][-1]["symbol"] == f"S{da.SKIP_KEEP + 14}BUSDT")
px["NVDABUSDT"] = 100.0
# ── the seat taken as the desk opens it ──
import types                   # noqa: E402
calls = []
_keep_store, _keep_hook = sh.store, sh.DEMO_HOOK
sh.store = types.SimpleNamespace(MIN_RISK_FRAC=0.003, desk_tier=lambda tier, sym: ("tok:" + tier) if sym.endswith("BUSDT") else tier,
                                 shadow_has_open=lambda tier, sym: False, shadow_open=lambda *a, **k: None)
sh.DEMO_HOOK = lambda feed: calls.append(dict(feed))
del sh.DEMO_FEED[:]
sig = {"symbol": "NVDABUSDT", "side": "LONG", "stop": 96.0, "tp1": 106.0, "tp2": 110.0, "score": 91}
sh.open_from_signal("elite_confirm", sig, 100.0)
sh.open_from_signal("elite_confirm", dict(sig, symbol="SOLUSDT"), 100.0)        # a coin: no demo offer, no hook
sh.open_from_signal("apex", dict(sig, symbol="MUBUSDT"), 100.0)                 # a stock under a tier off the demo's roster
check("desk hook: called once for a stock seat of a demo stream, with the offered plan",
      len(calls) == 1 and (calls[0]["symbol"], calls[0]["src"], calls[0]["entry"], calls[0]["stop"]) == ("NVDABUSDT", "elite_confirm", 100.0, 96.0), calls)
sh.DEMO_HOOK = lambda feed: (_ for _ in ()).throw(RuntimeError("boom"))
check("desk hook: an error inside it never stops the desk seat", sh.open_from_signal("go_revived", dict(sig, symbol="SOXLBUSDT"), 100.0) is True and len(sh.DEMO_FEED) == 2)
sh.store, sh.DEMO_HOOK = _keep_store, _keep_hook
# the worker's own hook, against this temp book
import agent_worker as aw      # noqa: E402
check("worker: the hook is wired, the watcher is started from cycle(), the demo block holds the lock from load to save",
      sh.DEMO_HOOK is aw._demo_instant and aw.DEMO_INSTANT is True and aw.demo_account is da)
W = io.open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
i_lock = W.index("        demo_account.lock()      # 🔒 2026-11-18")
i_load = W.index("        _dz = demo_account.load()\n")
i_save = W.index("        demo_account.save(_dz)\n        demo_account.unlock()\n")
i_cyc = W.index("def cycle() -> None:")
check("worker source: lock → load → … → save → unlock, in that order, and the watcher start sits at the top of cycle()",
      i_cyc < W.index("        if demo_watch.start():") < i_lock < i_load < i_save and W.count("demo_account.lock()") == 1 and W.count("demo_account.unlock()") == 2)
import binance_client as bc    # noqa: E402
_keep_px = bc.get_ticker_price
bc.get_ticker_price = lambda s: px.get(s, 0.0)
da.save(fresh())
da._clock = lambda: T07                                            # 07:00 PKT, an open window
aw._demo_instant({"symbol": "NVDABUSDT", "base": "NVDAB", "side": "LONG", "entry": 100.0, "stop": 96.0, "tp1": 106.0, "tp2": 110.0,
                  "score": 91.0, "burst": 0.0, "src": "elite_confirm", "fired_at": T07 - 5})
got = da.load()
check("instant seat: the demo opens the seat at the signal, at 10x, and frees the lock",
      len(got["open"]) == 1 and got["open"][0]["src"] == "elite_confirm" and got["open"][0]["lev"] == 10.0 and not da._LOCK.locked(), got["open"])
aw._demo_instant({"symbol": "NVDABUSDT", "base": "NVDAB", "side": "LONG", "entry": 100.5, "stop": 96.5, "tp1": 106.5, "tp2": 110.0,
                  "score": 91.0, "burst": 0.0, "src": "go_revived", "fired_at": T07 + 300})
got = da.load()
check("instant seat: a second elite-family signal on the held name adds its seat of margin at once",
      len(got["open"]) == 1 and abs(got["open"][0]["margin"] - 500) < 3 and got["open"][0].get("add_srcs") == ["go_revived"], got["open"])
da.save(fresh())
da._clock = lambda: T(15)                                          # 13–17: the seats are picked by win rate at the end of the cycle
aw._demo_instant({"symbol": "NVDABUSDT", "base": "NVDAB", "side": "LONG", "entry": 100.0, "stop": 96.0, "tp1": 106.0, "tp2": 110.0,
                  "score": 91.0, "burst": 0.0, "src": "elite_confirm", "fired_at": T(15) - 5})
check("instant seat: not in the 13–17 window", not da.load()["open"])
da._clock = lambda: T(19)
aw._demo_instant({"symbol": "NVDABUSDT", "base": "NVDAB", "side": "LONG", "entry": 100.0, "stop": 96.0, "tp1": 106.0, "tp2": 110.0,
                  "score": 91.0, "burst": 0.0, "src": "elite_confirm", "fired_at": T(19) - 5})
got = da.load()
check("instant seat: a shut window opens nothing and leaves its reason in the book", not got["open"] and len(got.get("skip_log") or []) == 1 and "shut" in got["skip_log"][0]["why"], got.get("skip_log"))
da.save(fresh())
da._clock = lambda: T07
da.lock()
aw._demo_instant({"symbol": "NVDABUSDT", "base": "NVDAB", "side": "LONG", "entry": 100.0, "stop": 96.0, "tp1": 106.0, "tp2": 110.0,
                  "score": 91.0, "burst": 0.0, "src": "elite_confirm", "fired_at": T07 - 5})
check("instant seat: inside the cycle's own demo block it does nothing and does not let go of the lock", not da.load()["open"] and da.lock_mine())
da.unlock()
aw.DEMO_INSTANT = False
aw._demo_instant({"symbol": "NVDABUSDT", "base": "NVDAB", "side": "LONG", "entry": 100.0, "stop": 96.0, "tp1": 106.0, "tp2": 110.0,
                  "score": 91.0, "burst": 0.0, "src": "elite_confirm", "fired_at": T07 - 5})
check("DEMO_INSTANT = False: the seat waits for the end of the cycle", not da.load()["open"])
aw.DEMO_INSTANT = True
bc.get_ticker_price = _keep_px
da._clock = keep_clock
A = io.open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
check("page: the demo shows the 'seats not taken, and why' list", "📝 Seats not taken, and why" in A and '_dz.get("skip_log")' in A)

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("FAIL:", f)
sys.exit(1 if FAIL else 0)
