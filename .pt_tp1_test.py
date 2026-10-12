"""🧪 Paper Trader TP1 marker (2026-10-12): the helper standalone + the two
call sites + the closed-table column."""
import ast
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"F:\Trading Indicator"
A = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
fails = []


class _PB:
    PARTIAL_TAKE_R = 1.5


ns = {"fmt_price": lambda v: f"{float(v):g}", "paper_bot": _PB}
src = None
for n in ast.walk(ast.parse(A)):
    if isinstance(n, ast.FunctionDef) and n.name == "_paper_tp1_mark":
        src = ast.get_source_segment(A, n)
        break
if not src:
    fails.append("_paper_tp1_mark not found")
else:
    import textwrap
    exec(textwrap.dedent(src), ns)
    mark = ns["_paper_tp1_mark"]
    base = {"side": "LONG", "entry": 1.0, "stop": 0.95, "target": 1.1, "target_2": 1.2}
    if mark(base, 1.05) != "":
        fails.append("below TP1, nothing")
    if mark(base, 1.1) != "🏦 at TP1 1.1 now — books on the next tick":
        fails.append(f"at TP1 live: {mark(base, 1.1)!r}")
    ch = dict(base, chasing_tp2=True, original_target=1.1, target=1.2, stop=1.1)
    if mark(ch, 1.15) != "🏦 TP1 HIT 1.1 · stop locked at TP1, riding to TP2 1.2":
        fails.append(f"chase upgrade: {mark(ch, 1.15)!r}")
    if mark(ch, 1.05) != "🏦 TP1 HIT 1.1 · stop locked at TP1, riding to TP2 1.2":
        fails.append("chase marker must persist when price falls back")
    pt = dict(base, partial_taken=True)
    if mark(pt, 1.05) != "💰 partial banked at +1.5R":
        fails.append(f"partial: {mark(pt, 1.05)!r}")
    sh = {"side": "SHORT", "entry": 1.0, "stop": 1.05, "target": 0.9}
    if mark(sh, 0.9) != "🏦 at TP1 0.9 now — books on the next tick" or mark(sh, 0.95) != "":
        fails.append("short side logic")
    if mark({"side": "LONG"}, None) != "" or mark({}, "x") != "":
        fails.append("fail-soft on garbage")

for need, lab in (('_tp1_txt = _paper_tp1_mark(p, cur)   # 🏦 TP1 (user 2026-10-12)', "open card computes the marker"),
                  ('+ (("<br><span style=\'color:#ffd700\'>" + _tp1_txt + "</span>")', "open card prints it"),
                  ('"TP1": ("💰 partial" if c.get("partial") else', "closed table column"),
                  ('"🏦 hit" if (c.get("exit_reason") == "target"', "closed table hit rule")):
    if need not in A:
        fails.append(f"missing: {lab}")
i_h = A.find("def _paper_tp1_mark(")
i_l = A.find("def _live_paper_positions():")
if not (0 < i_h < i_l):
    fails.append("helper must sit right before _live_paper_positions")
try:
    ast.parse(A)
except SyntaxError as exc:
    fails.append(f"app.py syntax: {exc}")
print("PAPER TP1:", "ALL PASS" if not fails else fails)
