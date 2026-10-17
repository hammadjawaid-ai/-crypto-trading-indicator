"""🕐 clock cells (2026-10-17): verdict rules, window mapping, the four lines,
card + bell wiring, label-not-gate, ghosts."""
import ast
import builtins
import calendar
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"F:\Trading Indicator"
sys.path.insert(0, ROOT)
import clock_cells as cc  # noqa: E402

W = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
A = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
fails = []
T = lambda h, m=0: float(calendar.timegm((2026, 10, 17, (h - 5) % 24, m, 0)))   # PKT hour -> epoch
# windows
for h, w in ((5, "05–09"), (8, "05–09"), (9, "09–13"), (13, "13–17"), (17, "17–21"), (21, "21–01"), (0, "21–01"), (1, "01–05"), (4, "01–05")):
    if cc.window_of(T(h)) != w:
        fails.append(f"window_of {h}:00 PKT -> {cc.window_of(T(h))}, want {w}")
# star verdicts
for h, side, want in ((6, "LONG", "TAKE"), (22, "LONG", "TAKE"), (14, "LONG", "THIN"), (2, "LONG", "DON'T"), (18, "SHORT", "TAKE"), (10, "SHORT", "THIN"), (3, "SHORT", "DON'T")):
    e, c, d = cc.verdict(cc.STAR_CELLS, side, T(h))
    if c != want:
        fails.append(f"star {side} {h}:00 PKT -> {c} ({d}), want {want}")
# revived verdicts (by the fire's window)
for h, side, want in ((10, "LONG", "TAKE"), (22, "LONG", "TAKE"), (14, "LONG", "DON'T"), (6, "LONG", "HALF"), (18, "SHORT", "TAKE"), (22, "SHORT", "THIN"), (2, "LONG", "HALF")):
    e, c, d = cc.verdict(cc.REVIVED_CELLS, side, T(h))
    if c != want:
        fails.append(f"revived {side} fired {h}:00 PKT -> {c} ({d}), want {want}")
# ⭐⚡ ELITE GO cells (user 2026-10-17: "do this for elite go as well")
for h, side, want in ((18, "LONG", "TAKE"), (22, "LONG", "TAKE"), (14, "LONG", "THIN"), (6, "LONG", "THIN"), (18, "SHORT", "THIN"), (10, "SHORT", "THIN")):
    e, c, d = cc.verdict(cc.ELITE_GO_CELLS, side, T(h))
    if c != want:
        fails.append(f"elite go {side} fired {h}:00 PKT -> {c} ({d}), want {want}")
eg = cc.elite_go_line("LONG", T(18))
if not eg.startswith("🕐 🟢 TAKE — fired 17–21 PKT longs 82% / +0.60R (17)") or "ELITE GO record" not in eg:
    fails.append(f"elite go line: {eg}")
for need, lab in (('if _ew.get("oneh") == "LIVE" and _ew.get("star"):\n                                        # 🕐 ELITE GO clock line', "elite go bell line, LIVE stars only"),
                  ("+ clock_cells.elite_go_line(\n                                                _ew[\"side\"],", "elite go bell call")):
    if need not in W:
        fails.append(f"worker missing: {lab}")
if "+ clock_cells.elite_go_line(_sd, _ts) + \"</span>\")\n                   if (_vt and str(_vt[-1]).upper() == \"LIVE\" and _gt) else \"\")" not in A:
    fails.append("star card must carry the ELITE GO line only on LIVE + GO cards")
i_eg = W.find('if _ew.get("oneh") == "LIVE" and _ew.get("star"):\n                                        # 🕐 ELITE GO clock line')
i_dead = W.find('if _ew.get("oneh") == "DEAD":\n                                        # GO REVIVED is its own bell')
if not (0 < i_eg < i_dead):
    fails.append("the ELITE GO line must be added to _go9 before the bell branches (branches untouched)")
# 💎⚡ GO LIVE cells on the conviction cards (user 2026-10-18)
for h, side, want in ((22, "LONG", "TAKE"), (22, "SHORT", "DON'T"), (6, "LONG", "THIN"), (10, "SHORT", "THIN")):
    e, c, d = cc.verdict(cc.GOLIVE_CELLS, side, T(h))
    if c != want:
        fails.append(f"go live {side} fired {h}:00 PKT -> {c} ({d}), want {want}")
gl = cc.golive_line("LONG", T(22))
if not gl.startswith("🕐 🟢 TAKE — fired 21–01 PKT longs 68% / +1.13R (19)") or "GO LIVE record" not in gl:
    fails.append(f"go live line: {gl}")
if "no record" not in cc.golive_line("SHORT", T(10)):
    fails.append("a missing cell must read 'no record'")
if ("+ (clock_cells.revived_line if _sect == \"rev\"\n                       else clock_cells.golive_line)(_sd, float(_ts) - float(_mins or 0) * 60)") not in A:
    fails.append("revived board must pick revived cells for the rev section and GO LIVE cells for the live section")
# the 13–17 caution says PASSED / FAILED
if ('+ (" · read PASSED — would have rung anyway"\n                                       if (not TG_GATES or _gate9[0]) else\n                                       " · read FAILED — ringing ONLY because "\n                                       "13–17 PKT is ungated (unmuted star)")') not in W:
    fails.append("13–17 caution must say whether the read passed or failed")
# ⭐ card gate chip (user 2026-10-18: tally the board with the phone)
for need in ('_gs = str(_ex.get("gate") or "")', '_chips.append("🔔 RANG — read passed")', '_chips.append("🔕 MUTED on the phone — " + (_gr or "read failed"))',
             '_chips.append("🔔 RANG — 13–17 PKT ungated window, read passed")', '_chips.append("🔔 RANG (unmuted) — 13–17 PKT ungated window, read FAILED: " + (_gr or ""))'):
    if need not in A:
        fails.append(f"star card gate chip missing: {need[:50]}")
i_chip = A.find('_gs = str(_ex.get("gate") or "")'); i_sb = A.find("def _render_star_board("); i_rb = A.find("def _render_revived_board(")
if not (0 < i_sb < i_chip < i_rb):
    fails.append("the gate chip must live inside the ⭐ star board")
# lines
s = cc.star_line("LONG", T(6)); r = cc.revived_line("SHORT", T(18))
if not s.startswith("🕐 🟢 TAKE — 05–09 PKT longs 75% / +0.52R (20)") or "09 Sep → 14 Oct" not in s:
    fails.append(f"star line: {s}")
if not r.startswith("🕐 🟢 TAKE — fired 17–21 PKT shorts 79% / +0.62R (19)") or "13 Sep → 14 Oct" not in r:
    fails.append(f"revived line: {r}")
d = cc.star_line("LONG", T(14))
if "THIN" not in d or "thin, no time call" not in d:
    fails.append(f"thin cell must say so: {d}")
n = cc.revived_line("LONG", T(14))
if "DON'T" not in n or "the time, not the card" not in n:
    fails.append(f"don't cell must blame the time: {n}")
if cc.verdict(cc.STAR_CELLS, "LONG", T(2))[2].endswith("closed by the gate") is False:
    fails.append("01–05 star must read closed by the gate")
# wiring
for need, lab in (("import clock_cells\n", "worker import"),
                  ("+ clock_cells.star_line(\n                                        _pmx.get(\"side\"), time.time())", "star bell line"),
                  ("+ clock_cells.revived_line(\n                                                        _ew[\"side\"],", "revived bell line")):
    if need not in W:
        fails.append(f"worker missing: {lab}")
for need, lab in (("import clock_cells\n", "app import"),
                  ("+ clock_cells.star_line(_sd, _ts) + \"</span>\"", "star card line"),
                  ("else clock_cells.golive_line)(_sd, float(_ts) - float(_mins or 0) * 60)", "revived / GO LIVE card line (fire time)")):
    if need not in A:
        fails.append(f"app missing: {lab}")
# 🕐 13–17 PKT = the one UNGATED window for the ⭐ bell (user 2026-10-17), phone only
ns = {}
for n_ in ast.parse(W).body:
    if isinstance(n_, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "STAR_UNGATED_1317" for t in n_.targets):
        exec(compile(ast.Module(body=[n_], type_ignores=[]), "c", "exec"), ns)
if ns.get("STAR_UNGATED_1317") is not True:
    fails.append("STAR_UNGATED_1317 must be ON (user 2026-10-17)")
for need, lab in (('_w1317 = (_star9 and STAR_UNGATED_1317\n                                  and clock_cells.window_of(time.time()) == "13–17")', "window flag"),
                  ('if _star9 and TG_GATES and not _gate9[0] and not _w1317:\n                            ok, _m9, _ids9 = False, "gated", None', "muting skips the 13–17 window"),
                  ('if _w1317:\n                                # 🕐 the ungated window rings with a caution', "caution line in the window"),
                  ('"gate": ((("1317-pass" if _gate9[0] else\n                                           "1317-muted") if _w1317 else', "record stamps 1317-pass / 1317-muted")):
    if need not in W:
        fails.append(f"13–17 ungated wiring missing: {lab}")
if "STAR_SKIP_1317_LONG" in W or "skipped-1317" in W:
    fails.append("the earlier phone skip must be gone")
i_w = W.find("_w1317 = (_star9 and STAR_UNGATED_1317")
i_seat = W.find("_sg9 = (_gate9 if TG_GATES else _star_gate(")
i_rec = W.find('store.record_signal("elite_star",\n                                                _st_sig)')
if not (0 < i_w < i_seat < i_rec):
    fails.append("the window flag must sit in the send block, before the demo seat read and the record")
if "_w1317" in W[i_seat:W.find('"gate": ((("1317-pass"')]:
    fails.append("the demo seat must not read the phone window flag")
c_l, c_s = cc.star_1317_caution("LONG"), cc.star_1317_caution("SHORT")
if not c_l.startswith("🕐 ⚠️ 13–17 PKT — UNGATED window") or "33% / -0.40R (9)" not in c_l or "68% / +0.25R (25)" not in c_l:
    fails.append(f"long caution text: {c_l}")
if "86% / +0.43R (7)" not in c_s or "caution" not in c_s:
    fails.append(f"short caution text: {c_s}")
# label, never a gate: the gate functions and the sends are untouched
for keep in ("_gate9 = _star_gate(_pmx, time.time(),", 'if _star9 and TG_GATES and not _gate9[0] and not _w1317:\n                            ok, _m9, _ids9 = False, "gated", None',
             "_rgd = _revived_gate(", 'if TG_GATES and not _rg9[0]:\n                                                _bell9 = f"gated: {_rg9[1]}"'):
    if keep not in W:
        fails.append(f"gate wiring changed: {keep[:40]}")
if "clock_cells" in W[W.find("def _star_gate("):W.find("def _golive_gate(")]:
    fails.append("clock cells must not enter the gate functions")
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
print(s); print(r); print(d); print(n)
print("CLOCK CELLS:", "ALL PASS" if not fails else fails)
