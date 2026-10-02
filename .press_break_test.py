"""PRESSED & BROKE — near logic, formatter render, wiring in worker/app/auditor."""
import ast
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
W = open("F:/Trading Indicator/agent_worker.py", encoding="utf-8").read()
A = open("F:/Trading Indicator/app.py", encoding="utf-8").read()
U = open("F:/Trading Indicator/auditor.py", encoding="utf-8").read()
tree = ast.parse(W)
ns = {}
for name in ("_trigger_near", "_fmt_press_break"):
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), name, "exec"), ns)
ns["TRIG_NEAR_PCT"] = 0.004
near, fmt = ns["_trigger_near"], ns["_fmt_press_break"]
fails = []
# near = within 0.4% on the approach side, not through
a_l = {"trigger": 100.0, "side": "LONG"}; a_s = {"trigger": 100.0, "side": "SHORT"}
for a, px, want in ((a_l, 99.7, True), (a_l, 99.5, False), (a_l, 100.0, False), (a_l, 100.3, False),
                    (a_s, 100.3, True), (a_s, 100.5, False), (a_s, 100.0, False), (a_s, 99.7, False)):
    if near(a, px) != want:
        fails.append(f"near({a['side']}, {px}) != {want}")
# render
a = {"base": "XLM", "side": "LONG", "src": "⚡ STRONG", "trigger": 0.2266, "stop": 0.218541, "tp1": 0.230499, "tp2": 0.2345, "conf": 68, "burst": 72.4}
m = fmt(a, 0.2268, 23.4)
for need in ("🔶💥 *PRESSED & BROKE — XLM LONG*", "pressed the number `0.2266` for 23 min", "entry `0.2268`", "TP2 `0.2345`", "🎯 conf 68", "🔥 burst 72", "its own desk tier"):
    if need not in m:
        fails.append(f"missing {need!r}")
if m.count("*") % 2 or m.count("`") % 2 or m.count("_") % 2:
    fails.append("unbalanced markdown in the bell")
m2 = fmt({"base": "ADA", "side": "SHORT", "src": "💎 ELITE HIGH", "trigger": 0.26, "stop": 0.27, "tp1": 0.25}, 0.2598, 4.0)
if "TP2" in m2 or "conf" in m2:
    fails.append("no-TP2 / no-conf variant wrong")
# wiring: pressed stamp sits in the not-passed branch before its continue
i_stamp = W.find('if not a.get("pressed") and _trigger_near(a, px):')
i_cont = W.find("continue", i_stamp)
i_vk = W.find("# volume kick on the forming 15m bar")
if not (0 < i_stamp < i_cont < i_vk):
    fails.append("pressed stamp not wired before the break path")
# wiring: pressed-first break records + opens + bells, before the trig_strong record
i_pb = W.find('store.record_signal("press_break", _sig_pb)')
i_ts = W.find('store.record_signal("trig_strong", _sig_t)')
blk = W[i_pb - 2500:i_pb + 900]
if not (0 < i_pb < i_ts):
    fails.append("press_break record not wired before the trig_strong record")
for need in ('shadow_trader.open_from_signal(\n                            "press_break", _sig_pb, px)', 'f"pressbrk:{a[\'symbol\']}:"', "tg.send(_fmt_press_break(a, px, _pb_min)", "+ _kr_note(a))", '_src_pb[:1] in ("💎", "⚡", "🔥")'):
    if need not in blk:
        fails.append(f"break wiring missing {need[:40]!r}")
if '"pressed": bool(a.get("pressed")),' not in W or '"pressed_at": a.get("pressed_at")}' not in W:
    fails.append("pressed state not published to .armed_levels.json")
# app board + registries
for need in ("#### 🔶 PRESSING — openable now", "tier='press_break'", '"press_break": "🔶💥 PRESSED & BROKE', "pressing for {_mins:.0f} min", "benchmark, every ⚡/🔥/💎 break since the log started"):
    if need not in A:
        fails.append(f"app missing {need[:40]!r}")
if A.find("#### 🔶 PRESSING") < A.find("#### 💥 THE NUMBERS"):
    fails.append("PRESSING board should render after THE NUMBERS")
if '"press_break": "press_break",' not in U:
    fails.append("auditor tier missing")
print(m, "\n")
print("PRESSED & BROKE:", "ALL PASS" if not fails else fails)
