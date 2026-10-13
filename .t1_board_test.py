"""⚡🔥 ARRIVAL T1 board (2026-10-13): placement, data source, openable cards,
no verdict / GO coupling, the star and GO boards untouched."""
import ast
import io
import os
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"F:\Trading Indicator"
A = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
fails = []
i_def = A.find("def _render_t1_board(pb_state, live_prices=None) -> None:")
i_rev = A.find("def _render_revived_board(pb_state, live_prices=None) -> None:")
i_pair = A.find("_PAIR_SPLIT_TIERS = (")
if not (0 < i_rev < i_def < i_pair):
    fails.append(f"T1 board must sit after the revived board and before the pair split: rev {i_rev} t1 {i_def} pair {i_pair}")
fn = A[i_def:i_pair]
for need, lab in (("FROM signals WHERE stream='trig_hot' AND ts>=? ", "cards come from the trig_hot stream"),
                  ("FROM shadow_trades WHERE tier='trig_hot' AND status='CLOSED' ", "forward ledger is the trig_hot tier"),
                  ("tier='trig_hot' AND status='OPEN'", "open count"),
                  ('_desk_tp1_line(("trig_hot",), _sym, _sd, _ts)', "TP1 line on the card"),
                  ('key=f"t1_open_{_sym}_{_i}"', "unique button key"),
                  ('"_unified_source": "trig_hot"}', "open source tag"),
                  ('"chase_tp2_eligible": False', "plain TP1 plan on open"),
                  ("binance_client.prime_prices([r[1] for r in _cards])", "one ticker call"),
                  ("ORDER BY ts DESC", "newest first"),
                  ("arrived HOT: {_v2}x vol · {_m3} ATR drift", "arrival chip")):
    if need not in fn:
        fails.append(f"T1 board missing: {lab}")
for gone in ("elite_1h", "star_go", "elite_go", "elite_agrade", "GO REVIVED", "1H LIVE", "1H DEAD"):
    if gone in fn:
        fails.append(f"T1 board must not couple to the elite GO: {gone}")
# call site order: star < revived < T1 < desk header
i_sc = A.find("_render_star_board(pb_state, live_prices)")
i_rc = A.find("_render_revived_board(pb_state, live_prices)")
i_tc = A.find("_render_t1_board(pb_state, live_prices)")
i_desk = A.find('st.markdown("### ✳️ DECISION DESK — live forward proof")')
if not (0 < i_sc < i_rc < i_tc < i_desk):
    fails.append(f"call order wrong: star {i_sc} revived {i_rc} t1 {i_tc} desk {i_desk}")
if '"trig_hot": "⚡🔥 ARRIVAL T1"}' not in A:
    fails.append("TP1 line label for the T1 tier missing")
# star + revived boards byte-identical to HEAD
head = subprocess.run(["git", "show", "HEAD:app.py"], capture_output=True, cwd=ROOT).stdout.decode("utf-8")
def seg(src, a, b):
    i = src.find(a); j = src.find(b, i)
    return src[i:j] if i >= 0 and j > i else None
if seg(A, "def _render_star_board(", "def _render_revived_board(") != seg(head, "def _render_star_board(", "def _render_revived_board("):
    fails.append("the ⭐ star board changed")
_rv_now = (seg(A, "def _render_revived_board(", "def _render_t1_board(") or "").rstrip()
_rv_old = (seg(head, "def _render_revived_board(", "def _render_t1_board(") or seg(head, "def _render_revived_board(", "_PAIR_SPLIT_TIERS = (") or "").rstrip()
if _rv_now != _rv_old:
    fails.append("the GO REVIVED board changed")
try:
    ast.parse(A)
except SyntaxError as exc:
    fails.append(f"app.py syntax: {exc}")
print("T1 BOARD:", "ALL PASS" if not fails else fails)
