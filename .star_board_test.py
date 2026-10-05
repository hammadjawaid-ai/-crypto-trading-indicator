"""💎⭐ ELITE STAR openable board — wiring checks (defined at module level, called
before the DECISION DESK header on the Paper Trader page only, reads the star
stream + verdict/GO/A-grade stamps, opens through paper_bot exactly like the
PRIME cards, unique button keys) + an AST ghost scan of app.py."""
import ast
import builtins
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
A = open(r"F:\Trading Indicator\app.py", encoding="utf-8").read()
fails = []
tree = ast.parse(A)
defs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
if "_render_star_board" not in defs:
    fails.append("renderer not defined at module level")
i_def = A.find("def _render_star_board(pb_state, live_prices=None) -> None:")
i_bm = A.find("def _render_brain_memory(pb_state, live_prices=None, best_zone_only=False):")
i_call = A.find("_render_star_board(pb_state, live_prices)")
i_desk = A.find('st.markdown("### ✳️ DECISION DESK — live forward proof")')
if not (0 < i_def < i_bm < i_call < i_desk):
    fails.append(f"placement wrong: def {i_def} bm {i_bm} call {i_call} desk {i_desk}")
if "    if not best_zone_only:   # 💎⭐ the openable star board leads the desk area" not in A:
    fails.append("board must be skipped on the Best Trade Zone page")
body = A[i_def:i_bm]
for need, lab in (("stream='elite_star' AND ts>=?", "star fires of the last 24h"),
                  ("stream='elite_1h'", "1H verdict stamp"), ("stream='star_go'", "GO stamp"),
                  ("stream='elite_agrade'", "A-grade chip"),
                  ("tier='elite_star' AND status='CLOSED'", "forward ledger"),
                  ("binance_client.prime_prices([r[1] for r in _cards])", "one ticker call for the cards"),
                  ('key=f"star_open_{_sym}_{_i}"', "unique button key"),
                  ('"_unified_source": "elite_star"', "open source tag"),
                  ("paper_bot.open_position(pb_state, _alert, _live)", "opens through paper_bot"),
                  ("paper_bot.save_state(PAPER_BOT_FILE, pb_state)", "saves the paper state"),
                  ("st.rerun()", "rerun after open"),
                  ('_c2.caption("✓ open")', "already-open guard"),
                  ("_openable = (pb_state is not None and _live and not _stopped", "openable guard")):
    if need not in body:
        fails.append(f"missing: {lab}")
# the board never writes to the worker DB
if "mode=ro" not in body or "INSERT" in body.upper().replace("INSERTED", ""):
    fails.append("board must read the worker DB read-only")
# ghost scan
assigned, loads = set(), set()
for n in ast.walk(tree):
    if isinstance(n, ast.Name):
        (assigned if isinstance(n.ctx, ast.Store) else loads).add(n.id)
    elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        assigned.add(n.name)
        if not isinstance(n, ast.ClassDef):
            for a in n.args.args + n.args.kwonlyargs + ([n.args.vararg] if n.args.vararg else []) + ([n.args.kwarg] if n.args.kwarg else []):
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
        for t in ast.walk(n.target):
            if isinstance(t, ast.Name):
                assigned.add(t.id)
    elif isinstance(n, (ast.With, ast.AsyncWith)):
        for it in n.items:
            if it.optional_vars:
                for t in ast.walk(it.optional_vars):
                    if isinstance(t, ast.Name):
                        assigned.add(t.id)
ghosts = sorted(g for g in loads - assigned if not hasattr(builtins, g) and g not in ("Any", "__file__"))
if ghosts:
    fails.append(f"app.py ghosts: {ghosts}")
print("STAR BOARD:", "ALL PASS" if not fails else fails)
