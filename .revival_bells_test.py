"""Revival bells (2026-10-19): the dresser, the conviction entry-cell gate, the
LATE ELITE GO skip, star LATE revivals still ringing, ghosts."""
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

W = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
fails = []
ns = {"rung_stats": rung_stats}
for n in ast.parse(W).body:
    if isinstance(n, ast.FunctionDef) and n.name == "_revival_dress":
        exec(compile(ast.Module(body=[n], type_ignores=[]), n.name, "exec"), ns)
    elif isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ("STAR_REV_CLASS_REC", "CONV_REV_CLASS_REC") for t in n.targets):
        exec(compile(ast.Module(body=[n], type_ignores=[]), "c", "exec"), ns)
dress = ns["_revival_dress"]
NOW = float(calendar.timegm((2026, 10, 19, 12, 2, 0)))     # 17:02 PKT
msg = ("⭐⚡ *GO — OP SHORT · REVIVED · PROTECT · 17:02 PKT (3.1h after the fire)*\n"
       "read: ✅ HIGH card · ✅ score 84 — gated set …\n"
       "✅ entry cell — 0.3–0.6R left to TP1 · 0.58R left now\n"
       "🕐 🟢 TAKE — fired 13–17 PKT shorts …\n"
       "class: ⚠️ SHORT — shorts entered at the GO measured 48% / −1.92% / −0.16R (42): size down or pass\n"
       "fire entry `0.1361` · SL `0.144629` · TP1 `0.128551`\n"
       "ignited: +34% of the path · live `0.1335`\n"
       "holding it: hold to TP1 / TP2")
ew = {"star": True, "base": "OP", "side": "SHORT", "go": "FAST"}
out = dress(msg, ew, 3.1 * 3600, NOW)
L = out.split("\n")
if L[0] != "⭐ *STAR REVIVAL — OP SHORT · FAST · 17:02 PKT (3.1h after the fire)*":
    fails.append(f"star header: {L[0]}")
if "class: FAST — star revivals FAST 72% / +0.45R (58) · LATE 63% / +0.24R (43)" not in out or "shorts entered at the GO" in out:
    fails.append(f"star class line must replace the generic one: {out}")
if L.index(next(l for l in L if l.startswith("class:"))) != L.index(next(l for l in L if l.startswith("fire entry"))) - 1:
    fails.append("class line must sit right above the plan")
if "✅ entry cell" not in out or "🕐 🟢 TAKE" not in out or "read: ✅ HIGH card" not in out:
    fails.append("the read, entry and clock lines must survive")
out2 = dress(msg.replace("⭐⚡", "💎⚡"), {"star": False, "base": "MEGA", "side": "SHORT", "go": "LATE"}, 18.6 * 3600, NOW).split("\n")
if out2[0] != "💎 *CONVICTION REVIVAL — MEGA SHORT · LATE · 17:02 PKT (18.6h after the fire)*" or not any(l.startswith("class: LATE — conviction revivals FAST 57% / +0.63R (28) · LATE 21% / -0.15R (14)") for l in out2):
    fails.append(f"conviction dress: {out2[:3]}")
if dress("broken", {}, "x", NOW) != "broken":
    fails.append("dresser must fail soft")
# wiring
for need, lab in (('elif (TG_GATES and not _ew.get("star")\n                                                  and not str(_rg9[2]).startswith("✅")):', "conviction entry-cell gate"),
                  ('_bell9 = f"gated: entry cell not met — {_rg9[2]}"', "entry-cell stamp"),
                  ("_go9x = _revival_dress(_go9x, _ew, _age, _ew_now)\n                                                _ok9, _m9x = tg.send(_go9x)", "dress before the send"),
                  ('if _ew.get("go") == "LATE":\n                                            # ⭐⚡ LATE ELITE GO reply skipped', "LATE ELITE GO skip"),
                  ('_bell9 = "skipped (LATE elite GO reply)"', "LATE skip stamp")):
    if need not in W:
        fails.append(f"missing: {lab}")
# star LATE revivals still ring: no LATE condition between the revived gate and the send
i_gate = W.find('elif (TG_GATES and not _ew.get("star")\n                                                  and not str(_rg9[2]).startswith("✅")):')
i_send = W.find("_go9x = _revival_dress(_go9x, _ew, _age, _ew_now)")
if '"LATE"' in W[i_gate:i_send]:
    fails.append("star LATE revivals must still ring (user 2026-10-19)")
# the entry-cell gate must not touch stars, the demo seat, or the FAST ELITE GO reply
if "_rgd = _revived_gate(" not in W or '"seat": bool(_sg9[0])' not in W:
    fails.append("demo seat wiring changed")
if 'else:\n                                            _ok9, _m9x, _ = tg.send_thread(\n                                                _go9,\n                                                reply_to=_ew.get("tg_ids"))' not in W:
    fails.append("FAST ELITE GO reply must still send in the thread")


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
print("\n".join(L[:6]))
print("REVIVAL BELLS:", "ALL PASS" if not fails else fails)
