"""🚦 Telegram gates (2026-10-14): the three reads standalone, their wiring,
the four mutes, the star record stamp, ghosts."""
import ast
import builtins
import calendar
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"F:\Trading Indicator"
sys.path.insert(0, ROOT)
import rung_stats  # noqa: E402
import buzz_clock  # noqa: E402

W = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
fails = []
ns = {"rung_stats": rung_stats, "buzz_clock": buzz_clock, "time": __import__("time")}
for n in ast.parse(W).body:
    if isinstance(n, ast.FunctionDef) and n.name in ("_stop_pct", "_gate_bits", "_star_gate", "_revived_gate", "_golive_gate"):
        exec(compile(ast.Module(body=[n], type_ignores=[]), n.name, "exec"), ns)
    elif isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in (
            "TG_GATES", "STAR_GATE_REC", "REVIVED_GATE_REC", "REVIVED_ENTRY_OK", "REVIVED_ENTRY_NO", "GOLIVE_GATE_REC",
            "TG_TRIGKR_PRIME", "TG_LEG2_PRIME", "TG_STAR_PRIME", "TG_CONV_PRIME", "STAR_BTC_MAX", "GATE_BTC_MIN") for t in n.targets):
        exec(compile(ast.Module(body=[n], type_ignores=[]), "c", "exec"), ns)
if ns.get("TG_GATES") is not True:
    fails.append("TG_GATES must start ON")
if ns.get("STAR_BTC_MAX") != 1.5 or ns.get("GATE_BTC_MIN") != -1.5:
    fails.append("BTC thresholds must be +1.5 / -1.5 (user call 2026-10-14)")
sg, rg, gg = ns["_star_gate"], ns["_revived_gate"], ns["_golive_gate"]
T1740 = float(calendar.timegm((2026, 10, 14, 12, 40, 0)))   # 17:40 PKT
T0240 = float(calendar.timegm((2026, 10, 14, 21, 40, 0)))   # 02:40 PKT (01–05)
T1440 = float(calendar.timegm((2026, 10, 14, 9, 40, 0)))    # 14:40 PKT (13–17)
T2240 = float(calendar.timegm((2026, 10, 14, 17, 40, 0)))   # 22:40 PKT (21–01)

# ⭐ star read
card = {"symbol": "XLMUSDT", "side": "LONG", "entry": 0.2, "stop": 0.19, "heat": 41, "conf": 40}
ok, line = sg(card, T1740, btc=0.85)
if not ok or "✅ heat 41" not in line or "✅ BTC +0.85% today" not in line or "✅ 17–21 PKT" not in line or "✅ stop 5.0%" not in line or "gated set 71% / +0.45R (146)" not in line:
    fails.append(f"star pass read wrong: {ok} {line}")
for bad, why in ((dict(card, heat=12), "⚠️ heat 12"), (dict(card, stop=0.18), "⚠️ stop 10.0%")):
    ok, line = sg(bad, T1740, btc=0.85)
    if ok or why not in line:
        fails.append(f"star must fail on {why}: {ok} {line}")
if sg(card, T1740, btc=2.3)[0] or "⚠️ BTC +2.30% today" not in sg(card, T1740, btc=2.3)[1]:
    fails.append("star must fail on BTC > +1.5%")
if sg(card, T0240, btc=0.5)[0] or "⚠️ 01–05 PKT" not in sg(card, T0240, btc=0.5)[1]:
    fails.append("star must fail at 01–05 PKT")
ok, line = sg(dict(card, heat=None), T1740, btc=None)
if not ok or "🟡 heat ?" not in line or "🟡 BTC today ?" not in line:
    fails.append(f"unknown inputs must pass with 🟡: {line}")

# ⭐⚡ revived read
ew = {"symbol": "AAVEUSDT", "side": "LONG", "entry0": 100.0, "stop": 96.0, "tp1": 105.0, "conf": 40, "score": 82, "tier": "HIGH", "fired_at": T1740}
ok, line, entry = rg(ew, 103.0, T1740 + 5400, btc=0.5)
if not ok or "✅ conf 40" not in line or "✅ HIGH card" not in line or "✅ score 82" not in line or "fired" in line:
    fails.append(f"revived pass read wrong: {line}")
if not entry.startswith("✅ entry cell") or "0.50R left now" not in entry:
    fails.append(f"entry cell line wrong: {entry}")
if rg(dict(ew, conf=70), 103.0, T1740 + 5400, btc=0.5)[0] or rg(dict(ew, tier="MAX"), 103.0, T1740 + 5400, btc=0.5)[0] \
        or rg(dict(ew, score=92), 103.0, T1740 + 5400, btc=0.5)[0] or rg(ew, 103.0, T1740 + 5400, btc=-2.0)[0]:
    fails.append("revived gate must fail on conf 65-84 / MAX / score 90+ / BTC < -1.5%")
if not rg(dict(ew, fired_at=T1440), 103.0, T1440 + 5400, btc=0.5)[0]:
    fails.append("a 13–17 PKT fire must PASS — the clock rule was dropped 2026-10-14 evening (user: 'yes drop it')")
if "70% / +0.54R (93)" not in ns.get("REVIVED_GATE_REC", ""):
    fails.append("revived record line must carry the four-rule cell")
if not rg(ew, 104.5, T1740 + 5400, btc=0.5)[2].startswith("⚠️ hold only"):
    fails.append("0.125R left must read hold only")
if not rg(ew, 103.0, T2240, btc=0.5)[2].startswith("⚠️ hold only"):
    fails.append("a GO at 22:40 PKT must read hold only")
if not rg(dict(ew, conf=None, score=None), 103.0, T1740 + 5400, btc=None)[0]:
    fails.append("unknown conf / score / BTC must pass the revived gate")

# 💎⚡ GO LIVE read
ew2 = {"side": "LONG", "entry0": 100.0, "stop": 97.0, "tier": "HIGH"}
ok, line = gg(ew2, btc=0.2)
if not ok or "✅ HIGH card" not in line or "✅ stop 3.0%" not in line or "gated set 65% / +1.27R (23)" not in line:
    fails.append(f"go live pass read wrong: {line}")
if gg(dict(ew2, tier="MAX"), btc=0.2)[0] or gg(dict(ew2, stop=94.0), btc=0.2)[0] or gg(ew2, btc=-3.0)[0]:
    fails.append("go live gate must fail on MAX / stop >= 5% / BTC < -1.5%")

# wiring
for need, lab in (('_gate9 = _star_gate(_pmx, time.time(),', "star gate call"),
                  ('if _star9 and TG_GATES and not _gate9[0]:\n                            ok, _m9, _ids9 = False, "gated", None', "muted star never sends, never threads"),
                  ('"gate": (("pass" if _gate9[0] else', "star record stamp"),
                  ('_rg9 = _revived_gate(', "revived gate call"),
                  ('if TG_GATES and not _rg9[0]:\n                                                _bell9 = f"gated: {_rg9[1]}"', "revived gated stamp"),
                  ('_gl9 = _golive_gate(', "go live gate call"),
                  ('if TG_GATES and not _gl9[0]:\n                                                _bell9 = f"gated: {_gl9[1]}"', "go live gated stamp"),
                  ('"conf": p.get("conf"), "score": p.get("score"),\n             "entry0": None', "watch entry carries conf + score"),
                  ('_MUTE_RULES(_fmt_apex_v2(_sig2, _px2, _rv2)', "APEX V2 muted"),
                  ('if key_prefix not in (() if TG_RULES else', "moonshot muted"),
                  ('ok, _ = _MUTE_RULES(\n                        f"⚡🔮 *KR-STRONG PREMIUM — "', "premium muted"),
                  ("TG_TRIGKR_PRIME = False", "TRIG×KR×PRIME muted")):
    if need not in W:
        fails.append(f"wiring missing: {lab}")
# the star's GO reply stays as it was: the thread send for a LIVE fire is untouched
if 'elif _ew.get("buzzed"):\n                                        _ok9, _m9x, _ = tg.send_thread(\n                                            _go9,\n                                            reply_to=_ew.get("tg_ids"))' not in W:
    fails.append("the star's GO reply (ungated) changed")
for keep in ("TG_STAR_PRIME = True", "TG_LEG2_PRIME = True", "TG_CONV_PRIME = True"):
    if keep not in W:
        fails.append(f"must stay on: {keep}")
# a muted star must still record + open its desk trade: the record block is after the send and unconditional on ok
i_send = W.find('ok, _m9, _ids9 = False, "gated", None')
i_rec = W.find('store.record_signal("elite_star",\n                                                _st_sig)')
if not (0 < i_send < i_rec):
    fails.append("star record must follow the (possibly muted) send")


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


g = ghosts(W)
if g:
    fails.append(f"agent_worker ghosts: {g}")
print(sg(card, T1740, btc=0.85)[1], "\n")
print("\n".join(rg(ew, 103.0, T1740 + 5400, btc=0.5)[1:]), "\n")
print("TG GATES:", "ALL PASS" if not fails else fails)
