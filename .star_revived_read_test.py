"""⭐⚡ GO REVIVED star fire-read line (2026-10-18): the five line cases, the memo
write / adoption / persistence, the bell selection (star vs conviction), the
GO stamp fields, the card chip, ghosts."""
import ast
import builtins
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"F:\Trading Indicator"
W = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
A = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
fails = []
ns = {}
for n in ast.parse(W).body:
    if isinstance(n, ast.FunctionDef) and n.name == "_star_revived_line":
        exec(compile(ast.Module(body=[n], type_ignores=[]), n.name, "exec"), ns)
    elif isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ("STAR_REV_RANG_REC", "STAR_REV_MUTED_REC", "STAR_REV_ALL_REC") for t in n.targets):
        exec(compile(ast.Module(body=[n], type_ignores=[]), "c", "exec"), ns)
line = ns["_star_revived_line"]
bits = "✅ heat 41 · ✅ BTC +0.85% today · ✅ 17–21 PKT · ✅ stop 5.0%"
cases = ((dict(star_gate="pass", star_read=bits), "⭐ fire read: RANG — " + bits, "80% / +0.64R (46)"),
         (dict(star_gate="1317-pass", star_read=bits), "⭐ fire read: RANG — ", "FAST 87% / +0.74R (30)"),
         (dict(star_gate="muted", star_read="⚠️ stop 9.4%"), "⭐ fire read: MUTED — this star never rang — ⚠️ stop 9.4%", "58% / +0.12R (55)"),
         (dict(star_gate="1317-muted", star_read="⚠️ heat 12"), "⭐ fire read: FAILED (rang only via the 13–17 ungated window) — ⚠️ heat 12", "58% / +0.12R (55)"),
         (dict(), "⭐ fire read: unknown", "68% / +0.36R (101)"),
         (dict(star_gate="off"), "⭐ fire read: gates were off", "68% / +0.36R (101)"))
for ew, head, rec in cases:
    out = line(ew)
    if not out.startswith(head) or rec not in out:
        fails.append(f"line for {ew}: {out}")
for need, lab in (('_STAR_READS[_key9] = {"ts": time.time(),', "fire bell writes the memo"),
                  ('_ewb["star_gate"], _ewb["star_read"] = _lab9, _bits9', "fire bell stamps existing watch entries"),
                  ('_sr = _STAR_READS.get((sym, side))', "watch entry adopts the memo"),
                  ('"star_reads": {f"{k[0]}|{k[1]}": v', "memo persisted with the watch"),
                  ('for k, v in (_d.get("star_reads") or {}).items():', "memo restored at start"),
                  ("+ (_star_revived_line(_ew)\n                                                       if _ew.get(\"star\") else _rg9[1])", "star bell gets the fire-read line, conviction keeps the card rules"),
                  ('"star_gate": _ew.get("star_gate"),\n                            "star_read": _ew.get("star_read"),\n                            "bell": _bell9})', "GO stamp carries the read")):
    if need not in W:
        fails.append(f"worker missing: {lab}")
# the memo write must not depend on the send succeeding: it sits after both branches, inside `if _star9`
i_send = W.find("ok, _m9, _ids9 = tg.send_thread(_msg9)")
i_memo = W.find('_STAR_READS[_key9] = {"ts": time.time(),')
i_elif = W.find("                    elif TG_RULES:\n")
if not (0 < i_send < i_memo < i_elif):
    fails.append("memo write must follow the send decision for every star, rung or muted")
# the muted star still rings on revival: the gate the revived bell applies is unchanged (card rules)
if '_bell9 = f"gated: {_rg9[1]}"' not in W or "_rgd = _revived_gate(" not in W:
    fails.append("revived gate / demo read changed")
if 'if _ex.get("star") and _sg:' not in A or '"⭐ fire read: MUTED, never rang"' not in A or '"⭐ fire read: RANG"' not in A:
    fails.append("revived card chip missing")
i_chip = A.find('if _ex.get("star") and _sg:'); i_rb = A.find("def _render_revived_board("); i_t1 = A.find("def _render_t1_board(")
if not (0 < i_rb < i_chip < i_t1):
    fails.append("the chip must live inside the GO REVIVED board")
try:
    ast.parse(A)
except SyntaxError as exc:
    fails.append(f"app.py syntax: {exc}")


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
for ew, _, _ in cases[:4]:
    print(line(ew))
print("STAR REVIVED READ:", "ALL PASS" if not fails else fails)
