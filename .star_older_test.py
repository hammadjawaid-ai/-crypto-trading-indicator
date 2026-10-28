"""Guard (2026-10-28, user): (1) the ⭐ star card's status is decided by the 15m candle path
since the fire — TP1 printed → 🏆 TP1 HIT, stop printed → 🔴 — not by the live price alone;
(2) 🕰 OLDER, STILL RUNNING list renders right under the recent star cards, read-only. The pure
path reader is exec'd on synthetic candles (the NIGHT case: wick through TP1, then back).
Run: python .star_older_test.py  (exit 0 = green)."""
import ast
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
A = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
fails = []
tree = ast.parse(A)
defs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
for name in ("_path_since_frame", "_star_path_since", "_render_star_older"):
    if name not in defs:
        fails.append(f"{name} not defined at module level")
i_helper = A.find("def _path_since_frame(")
i_sb = A.find("def _render_star_board(pb_state, live_prices=None) -> None:")
i_rev = A.find("def _render_revived_board(")
i_call = A.find("_render_star_board(pb_state, live_prices)\n")
i_call2 = A.find("_render_star_older(pb_state, live_prices)")
if not (0 < i_helper < i_sb < i_rev):
    fails.append("helpers must sit before the star board, outside the compared segment")
if not (0 < i_call < i_call2 < i_call + 200):
    fails.append("the older list must be called right after the star board")
sb = A[i_sb:i_rev]
for need, lab in (("_pres, _pts, _pmax = _star_path_since(_sym, _sd, float(_ts), _e, _stp, _t1)", "card asks the path"),
                  ('if _pres == "TP1":', "TP1-printed branch"),
                  ('_status = (f"🏆 TP1 HIT — printed {_hp} PKT on the candles"', "TP1 HIT wording"),
                  ("_prog = max(float(_prog or 0.0), 1.0)", "no Open after TP1"),
                  ('elif _pres == "SL" and not _stopped:', "stop-printed branch"),
                  ('_scol, _stopped = "#ff5c5c", True', "stop printed blocks Open"),
                  ("_openable = (pb_state is not None and _live and not _stopped", "openable guard kept")):
    if need not in sb:
        fails.append(f"star card missing: {lab}")
ol = ast.get_source_segment(A, defs["_render_star_older"]) if "_render_star_older" in defs else ""
for need, lab in (("stream='elite_star' AND ts>=? AND ts<?", "24h–7d window"),
                  ("(_now - 7 * 86400, _now - 24 * 3600)", "window bounds"),
                  ("_skip = {(r[0], (r[1] or \"\").upper()) for r in _recent}", "recent pairs excluded"),
                  ('if _pres == "TP1":', "resolved TP1 dropped"), ('if _pres == "SL":', "resolved stop dropped"),
                  ("tier='elite_star' AND opened_at>=?", "desk seat lookup"),
                  ("mode=ro", "read-only"), ("_rows[:15]", "capped at 15"),
                  ("above its entry at the 24h mark 70% / +0.38R, below it 47% / −0.18R", "the measured read")):
    if need not in ol:
        fails.append(f"older list missing: {lab}")
for bad in ("INSERT", "UPDATE ", "DELETE", "tg.send", "paper_bot.open_position"):
    if bad in ol:
        fails.append(f"older list must not {bad.strip()}")

# exec the pure path reader on synthetic 15m candles
src = ast.get_source_segment(A, defs["_path_since_frame"]) if "_path_since_frame" in defs else ""
ns = {}
exec(compile(src, "<path>", "exec"), ns)
import pandas as pd   # noqa: E402
f = ns["_path_since_frame"]
t0 = 1_700_000_000
idx = pd.to_datetime([(t0 + 900 * k) * 1000 for k in range(-2, 12)], unit="ms")
def frame(highs, lows):
    return pd.DataFrame({"open": [100.0] * len(idx), "high": highs, "low": lows, "close": [100.0] * len(idx)}, index=idx)
# NIGHT: long, entry 100, stop 95, TP1 110; bar 5 wicks to 111 then price sits at 101 (live would say ~10%)
H = [101] * 14; L = [99] * 14; H[5 + 2] = 111.0
r = f(frame(H, L), "LONG", t0, 100.0, 95.0, 110.0)
if r[0] != "TP1" or abs(r[1] - (t0 + 900 * 5)) > 1 or r[2] is None or abs(r[2] - 1.1) > 1e-9:
    fails.append(f"NIGHT case must read TP1 at bar 5 with best 1.1: {r}")
# stop first, then TP1 → SL
H2 = [101] * 14; L2 = [99] * 14; L2[3 + 2] = 94.0; H2[6 + 2] = 112.0
if f(frame(H2, L2), "LONG", t0, 100.0, 95.0, 110.0)[0] != "SL":
    fails.append("stop before TP1 must read SL")
# same bar both → SL
H3 = [101] * 14; L3 = [99] * 14; H3[4 + 2] = 112.0; L3[4 + 2] = 94.0
if f(frame(H3, L3), "LONG", t0, 100.0, 95.0, 110.0)[0] != "SL":
    fails.append("same-bar TP1+stop must read SL")
# neither → None with max_prog
r4 = f(frame([104] * 14, [99] * 14), "LONG", t0, 100.0, 95.0, 110.0)
if r4[0] is not None or abs(r4[2] - 0.4) > 1e-9:
    fails.append(f"neither printed must read None with best 0.4: {r4}")
# short mirror: TP1 below
H5 = [101] * 14; L5 = [99] * 14; L5[4 + 2] = 89.0
if f(frame(H5, L5), "SHORT", t0, 100.0, 105.0, 90.0)[0] != "TP1":
    fails.append("short TP1 (low through target) must read TP1")
# candles before the fire's own bar are ignored
H6 = [101] * 14; L6 = [99] * 14; H6[0] = 120.0
if f(frame(H6, L6), "LONG", t0, 100.0, 95.0, 110.0)[0] is not None:
    fails.append("a pre-fire candle must not count")
try:
    ast.parse(A)
except SyntaxError as exc:
    fails.append(f"app.py syntax: {exc}")
if fails:
    print("FAIL")
    for x in fails:
        print(" -", x)
    sys.exit(1)
print("OK — star card status follows the candle path (TP1 HIT / stop printed); older still-running list under the cards, read-only")
