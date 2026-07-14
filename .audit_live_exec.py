"""OFFLINE AUDIT of the agentic live executor — every critical path,
real preflight/gate math, mocked exchange (zero network, zero orders)."""
import io
import os
import sys
import time

os.environ["LIVE_EXECUTOR"] = "1"          # arm the module under test
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import live_broker as lb
import live_executor as lx
import shadow_trader

FAILS = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name
          + (f"  [{detail}]" if detail else ""))
    if not cond:
        FAILS.append(name)


# ---- mocks: no network ever ------------------------------------------------
calls = {"opened": [], "stops": [], "emergency": 0}
EQ = {"v": 1200.0}
lb.is_ready = lambda: (True, "live")
lb.account_balance = lambda: {"equity": EQ["v"]}
lb.sync_positions = lambda s: {"drift": 0}
lb.is_tradeable_on_bybit = lambda sym: True
lx._set_exchange_stop = lambda *a, **k: calls["stops"].append(a)
lb.emergency_stop_all = (
    lambda s: calls.__setitem__("emergency", calls["emergency"] + 1))


def fake_open(state, alert, live, confirmed=False):
    ok, why, prev = lb.preflight(state, alert, live)   # REAL sizing math
    if not ok:
        raise RuntimeError(why)
    pos = {"symbol": alert["symbol"], "base": alert["base"],
           "side": alert["side"], "entry": float(live),
           "stop": prev["stop"], "target": prev["target"],
           "qty": prev["qty"], "notional": prev["notional"],
           "leverage": prev["leverage"], "margin": prev["margin"],
           "opened_at": time.time()}
    state["open"].append(pos)
    state["trades_opened_total"] = int(
        state.get("trades_opened_total") or 0) + 1
    calls["opened"].append((alert["symbol"], prev))
    return pos


def fake_close(state, sym, px, reason="x"):
    pos = next((p for p in state["open"] if p["symbol"] == sym), None)
    if pos is None:
        return None
    long = pos["side"] == "LONG"
    pnl = ((px - pos["entry"]) if long else (pos["entry"] - px)) * pos["qty"]
    cl = dict(pos)
    cl.update({"exit": px, "exit_at": time.time(), "exit_reason": reason,
               "pnl_usd": round(pnl, 2), "pnl_pct": 0.0})
    state["closed"].append(cl)
    state["open"] = [p for p in state["open"] if p["symbol"] != sym]
    return cl


lb.open_position = fake_open
lb.close_position_at = fake_close
shadow_trader.tier_records = lambda: [
    {"tier": "early_lane", "green": True},
    {"tier": "apex", "green": True},
    {"tier": "fresh", "green": False},        # deliberately NOT green
    {"tier": "early_movers", "green": True},
]

lx.STATE_PATH = os.path.join(os.path.dirname(__file__),
                             ".audit_live_exec_state.json")
if os.path.exists(lx.STATE_PATH):
    os.remove(lx.STATE_PATH)


def mk(sym, e=100.0, side="LONG", sc=88):
    return {"symbol": sym, "base": sym[:-4], "side": side, "entry": e,
            "stop": e * 0.97, "tp1": e * 1.03, "tp2": e * 1.06, "score": sc}


PX = {"AUSDT": 100.0, "BUSDT": 100.0, "CUSDT": 100.0, "DUSDT": 100.0,
      "EUSDT": 100.0, "LATEUSDT": 102.0}
fn = lambda s: PX.get(s)

print("== T1: arming + green gating + dedup ==")
out = lx.run_cycle({"early_lane": [mk("AUSDT")],
                    "apex": [mk("AUSDT"), mk("BUSDT")],
                    "fresh": [mk("CUSDT")],
                    "early_movers": []}, fn)
check("armed", out["armed"])
check("ARMED note once", any("ARMED" in n for n in out["notes"]))
syms = [o["symbol"] for o in out["opened"]]
check("dedup: AUSDT opened once", syms.count("AUSDT") == 1, str(syms))
check("AUSDT credited to early_lane",
      next(o["tier"] for o in out["opened"]
           if o["symbol"] == "AUSDT") == "early_lane")
check("BUSDT opened via apex", "BUSDT" in syms)
check("CUSDT blocked (fresh NOT green)", "CUSDT" not in syms)
check("exchange TP parked at TP2",
      abs(calls["opened"][0][1]["target"] - 106.0) < 1e-6,
      str(calls["opened"][0][1]["target"]))
check("leverage capped at 5", calls["opened"][0][1]["leverage"] <= 5)
_rd = calls["opened"][0][1]["qty"] * (100.0 - calls["opened"][0][1]["stop"])
check("risk <= 1% of equity (+rounding)", _rd <= 12.5, f"${_rd:.2f}")
check("state persisted", os.path.exists(lx.STATE_PATH))

print("== T2: zone gate (late entry refused) ==")
out2 = lx.run_cycle({"early_lane": [mk("LATEUSDT")]}, fn)
check("late candidate skipped (67% of move gone)",
      not out2["opened"], str([o["symbol"] for o in out2["opened"]]))

print("== T3: max concurrent = 3 ==")
out3 = lx.run_cycle({"early_lane": [mk("CUSDT"), mk("DUSDT"),
                                    mk("EUSDT")]}, fn)
n_open_now = 2 + len(out3["opened"])
check("only 1 more opened (2 held + 1 = 3 cap)",
      len(out3["opened"]) == 1,
      f"opened {[o['symbol'] for o in out3['opened']]}")

print("== T4: the ride ladder (BE -> TP1 lock -> trail -> TP2) ==")
PX["AUSDT"] = 102.9        # +0.97R — below +1R, nothing should move
o = lx.run_cycle({}, fn)
s = lb.load_state(lx.STATE_PATH)
pA = next(p for p in s["open"] if p["symbol"] == "AUSDT")
check("below +1R: stop untouched", abs(pA["stop"] - 97.0) < 1e-6,
      str(pA["stop"]))
PX["AUSDT"] = 103.2        # > +1R and > TP1(103) -> lock at TP1
o = lx.run_cycle({}, fn)
s = lb.load_state(lx.STATE_PATH)
pA = next(p for p in s["open"] if p["symbol"] == "AUSDT")
check("TP1 lock: stop jumped to 103", abs(pA["stop"] - 103.0) < 1e-6,
      str(pA["stop"]))
check("exchange stop mirrored", len(calls["stops"]) > 0)
PX["AUSDT"] = 105.9        # peak 105.9, trail=105.9-3.6=102.3 < 103 hold
o = lx.run_cycle({}, fn)
s = lb.load_state(lx.STATE_PATH)
pA = next(p for p in s["open"] if p["symbol"] == "AUSDT")
check("trail never loosens the lock", abs(pA["stop"] - 103.0) < 1e-6)
PX["AUSDT"] = 106.2        # >= TP2(106) -> ride complete
o = lx.run_cycle({}, fn)
check("TP2 exit fired",
      any(c["exit_reason"] == "TP2" for c in o["closed"]),
      str([c.get("exit_reason") for c in o["closed"]]))

print("== T5: daily loss halt ==")
s = lb.load_state(lx.STATE_PATH)
s["closed"].append({"symbol": "XUSDT", "pnl_usd": -70.0,
                    "exit_at": time.time(), "pnl_pct": 0})
lb.save_state(lx.STATE_PATH, s)   # NET day = -70 + 24 (T4 win) = -46,
#                                   below the -3% line ($36) -> must halt
out5 = lx.run_cycle({"early_lane": [mk("DUSDT")]}, fn)
check("no entries under daily halt", not out5["opened"])
check("halt note surfaced",
      any("loss limit" in n.lower() for n in out5["notes"]),
      str(out5["notes"]))
s = lb.load_state(lx.STATE_PATH)   # undo for next tests
s["closed"] = [c for c in s["closed"] if c["symbol"] != "XUSDT"]
lb.save_state(lx.STATE_PATH, s)

print("== T6: imported/manual positions are HANDS OFF ==")
s = lb.load_state(lx.STATE_PATH)
s["open"].append({"symbol": "MANUUSDT", "side": "LONG", "entry": 50.0,
                  "stop": 48.0, "target": 55.0, "qty": 1.0,
                  "opened_at": time.time() - 100 * 3600,   # way past 48h
                  "imported_from_exchange": True})
lb.save_state(lx.STATE_PATH, s)
PX["MANUUSDT"] = 30.0       # even deep underwater + expired
out6 = lx.run_cycle({}, fn)
s = lb.load_state(lx.STATE_PATH)
check("manual position NOT touched (no TIME close, no ladder)",
      any(p["symbol"] == "MANUUSDT" for p in s["open"])
      and not any(c["symbol"] == "MANUUSDT" for c in out6["closed"]))

print("== T7: unmanageable own position closed ==")
s = lb.load_state(lx.STATE_PATH)
s["open"].append({"symbol": "BROKUSDT", "side": "LONG", "entry": 10.0,
                  "stop": 10.0, "target": 11.0, "qty": 1.0,
                  "opened_at": time.time()})
lb.save_state(lx.STATE_PATH, s)
PX["BROKUSDT"] = 10.0
out7 = lx.run_cycle({}, fn)
check("risk<=0 position closed as UNMANAGED",
      any(c["exit_reason"] == "UNMANAGED" for c in out7["closed"]))

print("== T8: kill switch ==")
EQ["v"] = 1000.0            # -16.7% from 1200 -> below the -15% floor
out8 = lx.run_cycle({"early_lane": [mk("DUSDT")]}, fn)
check("kill switch fired", out8.get("killed") is True)
check("emergency_stop_all called", calls["emergency"] == 1)
check("no entries on kill cycle", not out8["opened"])
out9 = lx.run_cycle({"early_lane": [mk("DUSDT")]}, fn)
check("halt is PERMANENT (next cycle still halted)",
      any("HALTED" in n for n in out9["notes"]) and not out9["opened"])

print()
if FAILS:
    print(f"AUDIT FAILED — {len(FAILS)} failure(s): {FAILS}")
    sys.exit(1)
print("AUDIT CLEAN — all scenarios passed.")
os.remove(lx.STATE_PATH)
