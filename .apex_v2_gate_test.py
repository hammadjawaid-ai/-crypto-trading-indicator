"""Guard (2026-11-01, user): 🏆💎 APEX V2 GATED — three-rule read at the fire (BTC day within
±1.5% · stop 2–4% · not 17–21 PKT), stamped on every apex_v2 record; a PASS opens the desk tier
apex_v2_gated and rings a thread bell whose 1H VERDICT answers in the thread; the ungated bell
stays muted; the TP1 ping roster knows the gated stream; the page labels both ledgers.
Run: python .apex_v2_gate_test.py  (exit 0 = green)."""
import ast
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
W = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
A = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
fails = []
tree = ast.parse(W)
consts = {}
for n in tree.body:
    if isinstance(n, ast.Assign):
        for t in n.targets:
            if isinstance(t, ast.Name) and t.id in ("TG_APEX_V2_GATED", "APEX_V2_GATE_REC", "APEX_V2_LIVE_REC", "TP1_STREAMS"):
                try:
                    consts[t.id] = ast.literal_eval(n.value)
                except Exception:
                    consts[t.id] = None
if consts.get("TG_APEX_V2_GATED") is not True:
    fails.append("TG_APEX_V2_GATED must be True")
if "apex_v2_gated" not in (consts.get("TP1_STREAMS") or {}):
    fails.append("TP1 roster must carry apex_v2_gated")
if "apex_v2" not in (consts.get("TP1_STREAMS") or {}):
    fails.append("TP1 roster must keep apex_v2 (unchanged)")

# the gate read, exec'd with stubs
defs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
for name in ("_apex_v2_gate", "_fmt_apex_v2_gated", "_fmt_apex_v2_verdict", "_fmt_apex_v2"):
    if name not in defs:
        fails.append(f"{name} missing")
import time as _time   # noqa: E402
ns = {"time": _time, "APEX_V2_GATE_REC": consts.get("APEX_V2_GATE_REC") or "REC", "APEX_V2_LIVE_REC": consts.get("APEX_V2_LIVE_REC") or "LIVEREC"}
exec(compile(ast.get_source_segment(W, defs["_apex_v2_gate"]), "<gate>", "exec"), ns)
gate = ns["_apex_v2_gate"]
T_1400 = (1_700_000_000 // 86400) * 86400 + 9 * 3600      # 09:00 UTC = 14:00 PKT
T_1800 = (1_700_000_000 // 86400) * 86400 + 13 * 3600     # 13:00 UTC = 18:00 PKT
sig = {"entry": 100.0, "stop": 97.0, "tp1": 106.0}        # stop 3%
ns["_btc_day_pct"] = lambda: 0.4
ok, line = gate(sig, T_1400)
if not ok or "✅ BTC" not in line or "✅ stop 3.0%" not in line or "✅ 14 PKT" not in line:
    fails.append(f"pass case wrong: {ok} {line[:120]}")
ns["_btc_day_pct"] = lambda: 2.1
if gate(sig, T_1400)[0]:
    fails.append("BTC +2.1% must fail")
ns["_btc_day_pct"] = lambda: -1.9
if gate(sig, T_1400)[0]:
    fails.append("BTC −1.9% must fail")
ns["_btc_day_pct"] = lambda: None
if not gate(sig, T_1400)[0]:
    fails.append("unreadable BTC must pass (every gate's law)")
ns["_btc_day_pct"] = lambda: 0.0
if gate({"entry": 100.0, "stop": 98.5, "tp1": 103.0}, T_1400)[0]:
    fails.append("stop 1.5% must fail")
if gate({"entry": 100.0, "stop": 95.0, "tp1": 110.0}, T_1400)[0]:
    fails.append("stop 5% must fail")
if not gate({"entry": 100.0, "stop": 96.0, "tp1": 108.0}, T_1400)[0]:
    fails.append("stop 4.0% must pass (inclusive)")
ok18, line18 = gate(sig, T_1800)
if ok18 or "⚠️ 18 PKT" not in line18:
    fails.append(f"18 PKT must fail with the clock flag: {line18[:100]}")
if not gate(sig, T_1800 + 3 * 3600)[0]:
    fails.append("21 PKT must pass (window is 17–21 exclusive of 21)")
if gate({"entry": 100.0, "stop": 97.0, "tp1": 106.0}, (1_700_000_000 // 86400) * 86400 + 12 * 3600)[0]:
    fails.append("17 PKT must fail")

# the bell + verdict text
class _RS:
    @staticmethod
    def pkt_hm(ts): return "14:05"
    @staticmethod
    def rec(c): return "2 trades · 50% · +0.3R"
    @staticmethod
    def tier_rec(t, d, n): return (2, 1, 0.3)
    @staticmethod
    def stamp_now(n): return "01 Nov 14:05 PKT"
ns["rung_stats"] = _RS
exec(compile(ast.get_source_segment(W, defs["_fmt_apex_v2_gated"]), "<bell>", "exec"), ns)
exec(compile(ast.get_source_segment(W, defs["_fmt_apex_v2_verdict"]), "<verdict>", "exec"), ns)
s2 = {"symbol": "XUSDT", "base": "X", "side": "LONG", "entry": 100.0, "stop": 97.0, "tp1": 106.0, "tp2": 110.0, "score": 92.6, "heat": 36}
txt = ns["_fmt_apex_v2_gated"](s2, 100.5, "read: ✅ BTC +0.40% today · ✅ stop 3.0% · ✅ 14 PKT — REC", 1_700_000_000)
for need in ("🏆💎 *APEX V2 GATED — X LONG · TAKE · 14:05 PKT*", "read: ✅ BTC", "entry `100`", "live `100.5`", "SL `97`", "TP1 `106`", "TP2 `110`",
             "1H VERDICT answers in this thread", "forward ledger (gated tier since 01 Nov)", "14 Oct 78-day replay"):
    if need not in txt:
        fails.append(f"bell missing: {need}")
ew = {"base": "X", "side": "LONG", "oneh": "LIVE"}
v = ns["_fmt_apex_v2_verdict"](ew, 0.31)
if "🟢 LIVE" not in v or "31%" not in v or "(APEX V2 gated)" not in v:
    fails.append(f"LIVE verdict text wrong: {v[:120]}")
v = ns["_fmt_apex_v2_verdict"](dict(ew, oneh="DEAD"), -0.05)
if "🔴 DEAD" not in v or "no add" not in v:
    fails.append("DEAD verdict text wrong")

# wiring at the fire site
i0 = W.find("    for _av2 in apex:")
i1 = W.find("    for p in sst1:", i0)
blk = W[i0:i1]
order = [blk.find(x) for x in ('_gok2, _grd2 = _apex_v2_gate(_sig2, time.time())', '_sig2["gate"] = "pass" if _gok2 else "muted"',
                                'store.record_signal("apex_v2", _sig2)', 'shadow_trader.open_from_signal("apex_v2", _sig2, _px2)',
                                '_ego_add(dict(_sig2), fam="apexv2")', 'store.record_signal("apex_v2_gated", _sig2)',
                                'shadow_trader.open_from_signal("apex_v2_gated", _sig2, _px2)', 'if TG_APEX_V2_GATED and not _bstock_quiet(_sym2):',
                                '_fmt_apex_v2_gated(_sig2, _px2, _grd2, time.time())', '_ewb2["buzzed"] = True', '_ewb2["tg_ids"] = _idg2',
                                '_MUTE_RULES(_fmt_apex_v2(_sig2, _px2, _rv2)')]
if any(o < 0 for o in order):
    fails.append(f"fire-site wiring missing: {order}")
elif order[:-1] != sorted(order[:-1]):
    fails.append("fire-site order wrong: read → stamp → record apex_v2 → open → watch → gated record → gated open → bell → mark")
if blk.count('_MUTE_RULES(_fmt_apex_v2(_sig2, _px2, _rv2)') != 1:
    fails.append("the ungated bell line must stay exactly as it was (muted)")
# the verdict reply branch sits before the widened elif and only for buzzed apexv2
j0 = W.find('elif _ew.get("buzzed") and _ew.get("fam") == "apexv2":')
j1 = W.find('elif _ew.get("buzzed") or _ew.get("appr"):')
if not (0 < j0 < j1):
    fails.append("apexv2 verdict branch must come before the widened elif")
vb = W[j0:j1]
if "_fmt_apex_v2_verdict(_ew, _prg)" not in vb or 'reply_to=_ew.get("tg_ids")' not in vb:
    fails.append("apexv2 verdict must reply in the bell's thread")
# page
if '"apex_v2_gated": "🏆💎 APEX V2 GATED' not in A or "the comparison ledger" not in A:
    fails.append("page labels missing")
try:
    ast.parse(A)
except SyntaxError as exc:
    fails.append(f"app.py syntax: {exc}")
if fails:
    print("FAIL")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("OK — APEX V2 gated: read exec'd (BTC / stop / clock), bell + verdict text, fire-site order, thread reply, roster, page")
