"""🏦 TP1 HIT line in the board cards (2026-10-12): the helper against a
throw-away desk DB, the three card call sites, read-only, fail-soft."""
import ast
import io
import os
import shutil
import sqlite3
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"F:\Trading Indicator"
A = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
fails = []
D = os.path.join(ROOT, ".tmp_tp1_card_test")
shutil.rmtree(D, ignore_errors=True)
os.makedirs(D)
DB = os.path.join(D, "desk.db")
con = sqlite3.connect(DB)
con.execute("CREATE TABLE shadow_trades (id INTEGER PRIMARY KEY, tier TEXT, symbol TEXT, side TEXT, opened_at REAL, "
            "tp1_hit INTEGER, status TEXT, exit_reason TEXT, pnl_r REAL)")
T0 = 1_800_000_000.0
rows = [("elite_star", "XLMUSDT", "LONG", T0 + 120, 1, "CLOSED", "TP2", 1.46),      # star fire -> banked TP2
        ("elite_star", "SUIUSDT", "LONG", T0 + 120, 0, "OPEN", None, None),          # star fire, TP1 not yet
        ("elite_conv", "FETUSDT", "LONG", T0 - 7200, 1, "OPEN", None, None),         # conviction fire 2h before its GO, past TP1
        ("go_live", "FETUSDT", "LONG", T0 + 60, 0, "OPEN", None, None),              # the GO entry itself, not yet
        ("go_revived", "NEOUSDT", "long", T0 + 30, 1, "CLOSED", "TP1_LOCK", 0.62),  # lower-case side on purpose
        ("elite_star", "XLMUSDT", "LONG", T0 + 30 * 3600, 1, "CLOSED", "TP2", 2.0)]  # a later fire, outside the window
con.executemany("INSERT INTO shadow_trades (tier, symbol, side, opened_at, tp1_hit, status, exit_reason, pnl_r) VALUES (?,?,?,?,?,?,?,?)", rows)
con.commit()
con.close()


class _WS:
    DB_PATH = DB


ns = {"time": time, "_ws_c": _WS}
for n in ast.parse(A).body:
    if isinstance(n, ast.FunctionDef) and n.name == "_desk_tp1_line":
        exec(compile(ast.Module(body=[n], type_ignores=[]), n.name, "exec"), ns)
    elif isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_TP1_CARD_TIERS" for t in n.targets):
        exec(compile(ast.Module(body=[n], type_ignores=[]), "c", "exec"), ns)
line = ns["_desk_tp1_line"]

m = line(("elite_star",), "XLMUSDT", "LONG", T0)
if "🏦 TP1 HIT on the desk — ⭐ ELITE STAR trade opened" not in m or "closed TP2 +1.46R" not in m:
    fails.append(f"star closed TP2 line wrong: {m!r}")
if line(("elite_star",), "SUIUSDT", "LONG", T0) != "":
    fails.append("TP1 not reached must print nothing")
# GO LIVE card: own tier has no hit yet, the conviction fire 2h earlier did -> fire tier line, with the look-back
g = line(("go_live", "elite_conv"), "FETUSDT", "LONG", T0 + 60, before_s=124 * 60 + 3600)
if "💎 ELITE CONVICTION trade opened" not in g or "still open on the desk, trailing past TP1" not in g:
    fails.append(f"GO LIVE fallback to the fire tier wrong: {g!r}")
if line(("go_live", "elite_conv"), "FETUSDT", "LONG", T0 + 60, before_s=1800) != "":
    fails.append("without the look-back the 2h-earlier fire must not match")
# revived card: own tier closed at the TP1 lock; side case-insensitive
r = line(("go_revived", "elite_star"), "NEOUSDT", "LONG", T0)
if "⭐⚡ GO REVIVED trade opened" not in r or "closed TP1_LOCK +0.62R" not in r:
    fails.append(f"revived line wrong: {r!r}")
# a fire 30h later must not be picked for the earlier card
if "+2.00R" in line(("elite_star",), "XLMUSDT", "LONG", T0):
    fails.append("window leaked a later trade")
# fail-soft on a missing DB
_WS.DB_PATH = os.path.join(D, "nope.db")
if line(("elite_star",), "XLMUSDT", "LONG", T0) != "":
    fails.append("missing DB must return ''")
shutil.rmtree(D, ignore_errors=True)

# call sites
for need, lab in (('+ _desk_tp1_line(("elite_star",), _sym, _sd, _ts)', "star card"),
                  ('(_src_c, "elite_star" if _ex.get("star") else "elite_conv"),', "GO cards own tier first"),
                  ("before_s=float(_mins or 0) * 60 + 3600)", "GO cards look back to the fire"),
                  ('f"file:{_ws_c.DB_PATH}?mode=ro", uri=True)', "read-only")):
    if need not in A:
        fails.append(f"missing: {lab}")
i_h = A.find("def _desk_tp1_line(")
i_s = A.find("def _render_star_board(")
i_r = A.find("def _render_revived_board(")
if not (0 < i_h < i_s < i_r):
    fails.append("helper must sit before the boards")
try:
    ast.parse(A)
except SyntaxError as exc:
    fails.append(f"app.py syntax: {exc}")
print(m, "\n", g, "\n")
print("TP1 CARD:", "ALL PASS" if not fails else fails)
