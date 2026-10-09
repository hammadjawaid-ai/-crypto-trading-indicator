"""⭐⚡ GO REVIVED board — wiring checks (module-level renderer, called right
under the star board on the Paper Trader page only, reads the two GO stamp
streams filtered to the DEAD-verdict class, opens through paper_bot like the
star board, unique button keys, read-only DB) + the worker's go_revived tier +
names + AST ghost scan of app.py and agent_worker.py."""
import ast
import builtins
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
A = open(r"F:\Trading Indicator\app.py", encoding="utf-8").read()
W = open(r"F:\Trading Indicator\agent_worker.py", encoding="utf-8").read()
U = open(r"F:\Trading Indicator\auditor.py", encoding="utf-8").read()
fails = []
tree = ast.parse(A)
defs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
if "_render_revived_board" not in defs:
    fails.append("renderer not defined at module level")
i_def = A.find("def _render_revived_board(pb_state, live_prices=None) -> None:")
i_bm = A.find("def _render_brain_memory(pb_state, live_prices=None, best_zone_only=False):")
i_star_call = A.find("_render_star_board(pb_state, live_prices)")
i_call = A.find("_render_revived_board(pb_state, live_prices)")
i_desk = A.find('st.markdown("### ✳️ DECISION DESK — live forward proof")')
if not (0 < i_def < i_bm < i_star_call < i_call < i_desk):
    fails.append(f"placement wrong: def {i_def} bm {i_bm} star {i_star_call} call {i_call} desk {i_desk}")
body = A[i_def:i_bm]
for need, lab in (("WHERE stream IN ('star_go', \"\n                \"'elite_go') AND ts>=? ORDER BY ts DESC", "both GO streams, last 24h"),
                  ('if str(_ex.get("oneh") or "").upper() != "DEAD":', "revived class only"),
                  ("tier='go_revived' AND status='CLOSED'", "forward ledger = go_revived tier"),
                  ("binance_client.prime_prices([r[1] for r, _ in _cards])", "one ticker call for the cards"),
                  ('key=f"revived_open_{_sym}_{_i}"', "unique button key"),
                  ('"_unified_source": "go_revived"', "open source tag"),
                  ("paper_bot.open_position(pb_state, _alert, _live)", "opens through paper_bot"),
                  ("paper_bot.save_state(PAPER_BOT_FILE, pb_state)", "saves the paper state"),
                  ("st.rerun()", "rerun after open"),
                  ('_c2.caption("✓ open")', "already-open guard"),
                  ("_openable = (pb_state is not None and _live and not _stopped", "openable guard"),
                  ('"🔔 bell ✓"', "bell chip"), ('f"🔕 no bell: {_bell}"', "no-bell chip"),
                  ("no closes yet", "empty ledger line"),
                  ('"✅ LONG·FAST class 79% / +1.15%" if (_lng and str(_tier or \'\').upper() == \'FAST\')', "class chip on every card")):
    if need not in body:
        fails.append(f"missing: {lab}")
if "mode=ro" not in body or "INSERT" in body.upper().replace("INSERTED", ""):
    fails.append("board must read the worker DB read-only")
if '"go_revived": "⭐⚡ GO REVIVED' not in A:
    fails.append("app tier name missing")
if '    "go_revived": "go_revived",\n' not in U:
    fails.append("auditor map missing")
# worker: tp2 on the stamp, the tier opened at the GO price for rung bells only
for need, lab in (('"tp2": _ew.get("tp2"),\n                            "bell": _bell9})', "tp2 on the GO stamp"),
                  ('if (_ew.get("oneh") == "DEAD"\n                                and (_ew.get("star") or _ew.get("appr"))\n                                and (not REVIVED_LONG_FAST', "tier gated like the bell (long + fast)"),
                  ('store.record_signal("go_revived", _rv_sig)', "go_revived record"),
                  ('shadow_trader.open_from_signal(\n                                    "go_revived", _rv_sig, _ew_px)', "go_revived desk open at the GO price"),
                  ('"fire_entry": _e0}', "fire entry kept on the record")):
    if need not in W:
        fails.append(f"worker missing: {lab}")
if not (0 < W.find('"bell": _bell9})') < W.find('store.record_signal("go_revived", _rv_sig)') < W.find('if _ew["go"] == "FAST" and _ew.get("star"):')):
    fails.append("go_revived tier must sit between the stamp and the chase tier")


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


for name, src in (("app.py", A), ("agent_worker.py", W)):
    g = ghosts(src)
    if g:
        fails.append(f"{name} ghosts: {g}")
print("GO REVIVED BOARD:", "ALL PASS" if not fails else fails)
