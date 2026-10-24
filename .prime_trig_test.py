"""💥🥇 PRIME × STRONG TRIGGER (2026-10-19): the PRIME read helper, the records-only
pass wiring (anchor PRIME, partner trig_strong, window, key, stamp, no bell), the
page's tier list + label, ghosts."""
import ast
import builtins
import calendar
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"F:\Trading Indicator"
sys.path.insert(0, ROOT)
import buzz_clock  # noqa: E402
import rung_stats  # noqa: E402

W = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
A = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
fails = []
ns = {"buzz_clock": buzz_clock, "rung_stats": rung_stats}
for n in ast.parse(W).body:
    if isinstance(n, ast.FunctionDef) and n.name in ("_prime_read", "_gate_bits", "_stop_pct"):
        exec(compile(ast.Module(body=[n], type_ignores=[]), n.name, "exec"), ns)
    elif isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ("PRIME_READ_REC", "STAR_BTC_MAX", "TG_PRIME_TRIG", "PRIME_TRIG_REC") for t in n.targets):
        exec(compile(ast.Module(body=[n], type_ignores=[]), "c", "exec"), ns)
read = ns["_prime_read"]
if ns.get("TG_PRIME_TRIG") is not True:
    fails.append("TG_PRIME_TRIG must be True (bell on since 2026-10-24)")
T18 = float(calendar.timegm((2026, 10, 19, 13, 0, 0)))   # 18:00 PKT (17–21)
T15 = float(calendar.timegm((2026, 10, 19, 10, 0, 0)))   # 15:00 PKT (13–17)
T03 = float(calendar.timegm((2026, 10, 18, 22, 0, 0)))   # 03:00 PKT (01–05)
good = {"entry": 100.0, "stop": 96.0, "tp1": 105.0}
ok, line = read(good, T18, 0.5)
if not ok or "✅ TP1 1.25R away" not in line or "✅ stop 4.0%" not in line or "✅ BTC +0.50% today" not in line or "✅ 17–21 PKT" not in line or not line.endswith(ns["PRIME_READ_REC"]):
    fails.append(f"good read: {ok} {line}")
ok, line = read(dict(good, tp1=110.0), T18, 0.5)
if ok or "⚠️ TP1 2.50R away" not in line:
    fails.append(f"wide TP1 must fail: {line}")
ok, line = read(dict(good, stop=98.0, tp1=102.5), T18, 0.5)
if ok or "⚠️ stop 2.0%" not in line:
    fails.append(f"tight stop must fail: {line}")
ok, line = read(good, T15, 0.5)
if ok or "⚠️ 13–17 PKT" not in line:
    fails.append(f"13–17 must fail: {line}")
ok, line = read(good, T03, 0.5)
if ok or "⚠️ 01–05 PKT" not in line:
    fails.append(f"01–05 must fail: {line}")
ok, line = read(good, T18, 2.2)
if ok or "⚠️ BTC +2.20% today" not in line:
    fails.append(f"hot BTC must fail: {line}")
ok, line = read(good, T18, None)
if not ok or "🟡 BTC today ?" not in line:
    fails.append(f"unknown BTC must pass as 🟡: {line}")
ok, line = read({"entry": None, "stop": 1, "tp1": 2}, T18, 0.0)
if "🟡 TP1 distance ?" not in line:
    fails.append(f"unreadable plan must be 🟡: {line}")
# the pass
blk = W[W.find("# 💥🥇 PRIME × STRONG TRIGGER — records-only pass"):W.find("# 💯 CONVICTION v2")]
if not blk or len(blk) < 500:
    fails.append("records-only pass block missing")
for need, lab in (('store.recent_by_stream("prime", 80)', "anchor = PRIME"),
                  ('"trig_strong", _sym_pt, _sd_pt,\n                        _ts_pt - PRIME_PAIR_BEFORE,\n                        _ts_pt + PRIME_PAIR_AFTER)', "partner window"),
                  ('f"prime_trig:{_sym_pt}:{_sd_pt}", int(3.0 * 3600)', "3h re-fire key"),
                  ("_rd_pt = _prime_read(_sig_pt, _now_pt, _btc_pt)", "read computed"),
                  ('_sig_pt["read"] = "pass" if _rd_pt[0] else "fail"', "read stamped"),
                  ('store.record_signal("prime_trig", _sig_pt)', "record"),
                  ('shadow_trader.open_from_signal("prime_trig", _sig_pt, _px_pt)', "desk open"),
                  ("if _now_pt - _ts_pt > PRIME_PAIR_FRESH:", "freshness")):
    if need not in blk:
        fails.append(f"pass missing: {lab}")
if "tg.send(_fmt_prime_trig(" not in blk or "_DEMO_PT.append(dict(_sig_pt, src=\"prime_trig\"" not in blk:
    fails.append("the pass must ring the bell and feed the demo (2026-10-24)")
if "_paired_pp" in blk:
    fails.append("the PRIME anchor must not share the elite pairs' one-bell set")
# the existing pair pass is untouched
if 'store.record_signal(_tier_pp, _sig_pp)\n                    shadow_trader.open_from_signal(_tier_pp, _sig_pp, _px_pp)' not in W:
    fails.append("existing pair pass changed")
# page
if '"prime_trig",   # 💥🥇 records-only tier' not in A or '"prime_trig": "💥🥇 PRIME × STRONG TRIGGER — 🥇 PRIME fire + 💥 "' not in A:
    fails.append("page tier list / label missing")


def ghosts(src):
    t = ast.parse(src)
    assigned, loads = set(), set()
    for n_ in ast.walk(t):
        if isinstance(n_, ast.Name):
            (assigned if isinstance(n_.ctx, ast.Store) else loads).add(n_.id)
        elif isinstance(n_, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assigned.add(n_.name)
            if not isinstance(n_, ast.ClassDef):
                for a in n_.args.args + n_.args.kwonlyargs + n_.args.posonlyargs + ([n_.args.vararg] if n_.args.vararg else []) + ([n_.args.kwarg] if n_.args.kwarg else []):
                    assigned.add(a.arg)
        elif isinstance(n_, (ast.Import, ast.ImportFrom)):
            for al in n_.names:
                assigned.add((al.asname or al.name).split(".")[0])
        elif isinstance(n_, ast.ExceptHandler) and n_.name:
            assigned.add(n_.name)
        elif isinstance(n_, ast.Lambda):
            for a in n_.args.args:
                assigned.add(a.arg)
        elif isinstance(n_, ast.comprehension):
            for tt in ast.walk(n_.target):
                if isinstance(tt, ast.Name):
                    assigned.add(tt.id)
        elif isinstance(n_, (ast.With, ast.AsyncWith)):
            for it in n_.items:
                if it.optional_vars:
                    for tt in ast.walk(it.optional_vars):
                        if isinstance(tt, ast.Name):
                            assigned.add(tt.id)
    return sorted(g for g in loads - assigned if not hasattr(builtins, g) and g not in ("Any", "__file__"))


g = ghosts(W)
if g:
    fails.append(f"agent_worker ghosts: {g}")
print(read(good, T18, 0.5)[1])
print("PRIME × TRIG:", "ALL PASS" if not fails else fails)
