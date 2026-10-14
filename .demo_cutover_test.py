"""🎮 GEN 17 cut-over (user 2026-10-14: "close the ones that are open and with
new stream start with them"): close_before semantics on a toy ledger and on
the real 09:17 backup, worker wiring, idempotence, ghosts."""
import ast
import builtins
import calendar
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"F:\Trading Indicator"
sys.path.insert(0, ROOT)
import demo_account as da  # noqa: E402

W = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
D = open(os.path.join(ROOT, "demo_account.py"), encoding="utf-8").read()
fails = []

CUT = float(da.DEMO_RESET_BEFORE)
D0 = calendar.timegm((2026, 10, 14, 0, 0, 0))
if not (D0 <= CUT < D0 + 86400):
    fails.append(f"DEMO_RESET_BEFORE must sit inside 2026-10-14 UTC: {CUT}")
if "GEN 17 cut-over" not in D or "closed at live" not in D:
    fails.append("close reason must say GEN 17 cut-over / closed at live")


def seat(sym, side, entry, qty, opened_at, src):
    return {"symbol": sym, "base": sym.replace("USDT", ""), "side": side, "entry": entry,
            "qty": qty, "opened_at": opened_at, "src": src, "stop": entry * 0.95, "tp1": entry * 1.05,
            "fees": 0.0, "lev": 10, "margin": entry * qty / 10, "notional": entry * qty}


# toy ledger: two old seats (one winning long, one losing short), one new-roster seat
st = {"balance": 2000.0, "open": [seat("AAAUSDT", "LONG", 100.0, 10.0, CUT - 2 * 86400, "elite_star"),
                                  seat("BBBUSDT", "SHORT", 50.0, 20.0, CUT - 86400, "press_break"),
                                  seat("CCCUSDT", "LONG", 10.0, 100.0, CUT + 600, "go_revived")],
      "closed": []}
px = {"AAAUSDT": 105.0, "BBBUSDT": 52.5, "CCCUSDT": 9.0}
ev = da.close_before(st, CUT, lambda s: px.get(s))
if len(ev) != 2 or any(e[0] != "close" for e in ev):
    fails.append(f"expected two close events: {ev}")
if [p["symbol"] for p in st["open"]] != ["CCCUSDT"]:
    fails.append(f"only the new-roster seat may stay open: {[p['symbol'] for p in st['open']]}")
if len(st["closed"]) != 2 or any("GEN 17 cut-over" not in c["reason"] for c in st["closed"]):
    fails.append(f"closed records / reason wrong: {st['closed']}")
exp_pnl = (10.0 * 5.0 - 10.0 * 105.0 * da.FEE) + (20.0 * -2.5 - 20.0 * 52.5 * da.FEE)
if abs(st["balance"] - (2000.0 + exp_pnl)) > 0.01:
    fails.append(f"balance must carry both closes with fees: {st['balance']} vs {2000.0 + exp_pnl}")
rec = {c["symbol"]: c for c in st["closed"]}
if rec["AAAUSDT"]["exit"] != 105.0 or rec["AAAUSDT"]["pnl"] <= 0 or rec["BBBUSDT"]["pnl"] >= 0:
    fails.append(f"exit at live / signed pnl wrong: {rec}")
for k in ("symbol", "base", "side", "entry", "exit", "qty", "pnl", "reason", "src", "opened_at", "closed_at"):
    if k not in rec["AAAUSDT"]:
        fails.append(f"closed record missing {k}")
# second pass: nothing left to do
if da.close_before(st, CUT, lambda s: px.get(s)):
    fails.append("second pass must be a no-op")
# unreadable price: that seat waits, the others close
st2 = {"balance": 1000.0, "open": [seat("AAAUSDT", "LONG", 100.0, 1.0, CUT - 3600, "moonshot"),
                                   seat("BBBUSDT", "LONG", 50.0, 1.0, CUT - 3600, "moonshot")], "closed": []}
ev2 = da.close_before(st2, CUT, lambda s: {"AAAUSDT": None, "BBBUSDT": 51.0}.get(s))
if len(ev2) != 1 or [p["symbol"] for p in st2["open"]] != ["AAAUSDT"]:
    fails.append(f"unreadable price must leave that seat for the next tick: {ev2} {st2['open']}")
# switch off
st3 = {"balance": 1000.0, "open": [seat("AAAUSDT", "LONG", 100.0, 1.0, CUT - 3600, "moonshot")], "closed": []}
if da.close_before(st3, 0, lambda s: 101.0) or len(st3["open"]) != 1:
    fails.append("ts=0 must do nothing")

# the real 09:17 backup: every seat is older than the cut — all nine close, balance moves by the marks
bk = os.path.join(ROOT, ".state_backup_1014", ".demo_account.json")
if os.path.exists(bk):
    real = json.load(open(bk, encoding="utf-8"))
    n_open, bal0, n_closed = len(real["open"]), real["balance"], len(real["closed"])
    if any(float(p["opened_at"]) >= CUT for p in real["open"]):
        fails.append("backup has a seat newer than the cut (unexpected)")
    ev3 = da.close_before(real, CUT, lambda s: next((p["entry"] * 1.01 for p in [] ), None) or 0 or None)
    if ev3 or len(real["open"]) != n_open:
        fails.append("no price -> nothing closes")
    marks = {p["symbol"]: p["entry"] * (1.01 if p["side"] == "LONG" else 0.99) for p in real["open"]}
    ev3 = da.close_before(real, CUT, lambda s: marks.get(s))
    if len(ev3) != n_open or real["open"] or len(real["closed"]) != n_closed + n_open:
        fails.append(f"backup: expected {n_open} closes, got {len(ev3)}, open left {len(real['open'])}")
    if real["balance"] <= bal0:
        fails.append("+1% marks on every seat must lift the balance")
    print(f"backup replay: {n_open} seats closed at +1% marks -> balance {bal0:.2f} -> {real['balance']:.2f}")
else:
    print("(backup state not present — real-ledger replay skipped)")

# wiring: the cut-over runs right before manage(), inside the demo block, with the worker's live reader
i_cut = W.find("demo_account.close_before(")
i_mng = W.find("_dz_events = demo_account.manage(_dz, _live, _dz_kr)")
if not (0 < i_cut < i_mng) or i_mng - i_cut > 700:
    fails.append(f"close_before must run just before manage(): cut {i_cut} manage {i_mng}")
if "_dz, demo_account.DEMO_RESET_BEFORE, _live)" not in W:
    fails.append("worker must pass the module switch and the live reader")
if W.count("demo_account.close_before(") != 1:
    fails.append("exactly one cut-over call")
# the GEN 17.2 roster is untouched
if set(da.CLASS_W) != {"go_revived", "arrival_t1", "strong_trigger", "early_lane", "star_prime", "elite_star"}:   # GEN 17.3: six
    fails.append(f"roster changed: {sorted(da.CLASS_W)}")


def ghosts(src):
    t = ast.parse(src)
    assigned, loads = set(), set()
    for n in ast.walk(t):
        if isinstance(n, ast.Name):
            (assigned if isinstance(n.ctx, ast.Store) else loads).add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assigned.add(n.name)
            if not isinstance(n, ast.ClassDef):
                for a in n.args.args + n.args.kwonlyargs + n.args.posonlyargs + ([n.args.vararg] if n.args.vararg else []) + ([n.args.kwarg] if n.args.kwarg else []):
                    assigned.add(a.arg)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names:
                assigned.add((al.asname or al.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            assigned.add(n.name)
        elif isinstance(n, ast.Lambda):
            for a in n.args.args:
                assigned.add(a.arg)
        elif isinstance(n, ast.comprehension):
            for tt in ast.walk(n.target):
                if isinstance(tt, ast.Name):
                    assigned.add(tt.id)
        elif isinstance(n, (ast.With, ast.AsyncWith)):
            for it in n.items:
                if it.optional_vars:
                    for tt in ast.walk(it.optional_vars):
                        if isinstance(tt, ast.Name):
                            assigned.add(tt.id)
    return sorted(g for g in loads - assigned if not hasattr(builtins, g) and g not in ("Any", "__file__"))


for name, src in (("agent_worker", W), ("demo_account", D)):
    g = ghosts(src)
    if g:
        fails.append(f"{name} ghosts: {g}")
print("cut at", time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(CUT)), "=", time.strftime("%H:%M PKT", time.gmtime(CUT + 5 * 3600)))
print("DEMO CUT-OVER:", "ALL PASS" if not fails else fails)
