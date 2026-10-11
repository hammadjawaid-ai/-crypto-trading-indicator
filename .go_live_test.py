"""💎⚡ GO after a LIVE verdict for elite conviction fires (2026-10-12): bell
branch, text, desk tier, board section, names, auditor map, stars untouched."""
import ast
import builtins
import io
import os
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"F:\Trading Indicator"
sys.path.insert(0, ROOT)
import rung_stats  # noqa: E402

W = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
A = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
U = open(os.path.join(ROOT, "auditor.py"), encoding="utf-8").read()
fails = []
ns = {}
for n in ast.parse(W).body:
    if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ("TG_GO_LIVE", "GO_LIVE_LINE") for t in n.targets):
        exec(compile(ast.Module(body=[n], type_ignores=[]), "c", "exec"), ns)
if ns.get("TG_GO_LIVE") is not True:
    fails.append("TG_GO_LIVE must start ON")
if "61% / +0.69R (171)" not in ns.get("GO_LIVE_LINE", "") or "shorts 55% / +0.38R (42)" not in ns.get("GO_LIVE_LINE", ""):
    fails.append("class line must carry the measured cell with R, never win rate alone")

# the LIVE GO text as the phone gets it (go_text + the class line after the header)
ew = {"symbol": "AAVEUSDT", "base": "AAVE", "side": "LONG", "stop": 176.774, "tp1": 188.712, "tp2": 192.449,
      "tier": "HIGH", "star": False, "appr": True, "entry0": 184.04, "go": "FAST", "oneh": "LIVE",
      "fired_at": time.time() - 5400}
go9 = rung_stats.go_text(ew, 0.31, 5400, 185.5, time.time(), db_path=os.path.join(ROOT, ".no_such.db"))
msg = go9.replace("\n", "\n" + ns["GO_LIVE_LINE"] + "\n", 1)
lines = msg.split("\n")
if not lines[0].startswith("💎⚡ *GO — AAVE LONG · PROTECT · ") or "REVIVED" in lines[0]:
    fails.append(f"LIVE GO header wrong: {lines[0]}")
if lines[1] != ns["GO_LIVE_LINE"]:
    fails.append("class line must be the second line")
if "fire entry `184.04` · SL `176.774` · TP1 `188.712` · TP2 `192.449`" not in msg or "ignited within 4h (elite fires)" not in msg:
    fails.append("plan line / class label missing")
if msg.count("*") % 2 or msg.count("`") % 2 or "\ufffd" in msg:
    fails.append("markdown unbalanced")

# wiring: branch order inside the GO block, tier block placement, stars untouched
i_dead = W.find('if _ew.get("oneh") == "DEAD":\n                                        # GO REVIVED is its own bell')
i_thr = W.find('elif _ew.get("buzzed"):\n                                        _ok9, _m9x, _ = tg.send_thread(')
i_live = W.find('elif (_ew.get("oneh") == "LIVE"\n                                          and not _ew.get("star")):')
i_sent = W.find('if _bell9.startswith("sent"):\n                                        n_alerts += 1')
if not (0 < i_dead < i_thr < i_live < i_sent):
    fails.append(f"GO branch order wrong: dead {i_dead} thread {i_thr} live {i_live} sent {i_sent}")
blk = W[i_live:i_sent]
for need, lab in (('if not TG_GO_LIVE:', "switch"), ('else GO_LIVE_UNAPPR)', "unapproved tag"),
                  ('tg.send(_go9.replace(\n                                                "\\n", "\\n" + _cl9 + "\\n", 1))', "standalone send with the class line"),
                  ('"sent-standalone" if _ok9', "bell stamp")):
    if need not in blk:
        fails.append(f"LIVE branch missing: {lab}")
if "_bell9 = \"not-buzzed (LIVE fire not on the phone)\"" not in W:
    fails.append("default status must remain for stars without a thread")
i_rv = W.find('store.record_signal("go_revived", _rv_sig)')
i_lv = W.find('store.record_signal("go_live", _lv_sig)')
i_ch = W.find('if _ew["go"] == "FAST" and _ew.get("star"):')
if not (0 < i_rv < i_lv < i_ch):
    fails.append(f"go_live tier block misplaced: revived {i_rv} live {i_lv} chase {i_ch}")
if 'if _ew.get("oneh") == "LIVE" and not _ew.get("star"):' not in W or '"appr": bool(_ew.get("appr")),' not in W:
    fails.append("go_live tier must be LIVE + not star, approved or not, stamping appr")
if 'if not _ew.get("appr"):\n                                            _bell9 = ("not-approved (unapproved "' in W[W.find('elif (_ew.get("oneh") == "LIVE"'):W.find('elif (_ew.get("oneh") == "LIVE"') + 1500]:
    fails.append("unapproved fires must ring too (user 2026-10-12)")
# the star paths are byte-identical to HEAD: the verdict block and the DEAD/thread branches
head = subprocess.run(["git", "show", "HEAD:agent_worker.py"], capture_output=True, cwd=ROOT).stdout.decode("utf-8")
def seg(src, a, b):
    i = src.find(a); j = src.find(b, i)
    return src[i:j] if i >= 0 and j > i else None
for a, b, lab in (('if _ew.get("oneh") == "DEAD":\n                                        # GO REVIVED is its own bell', 'elif (_ew.get("oneh") == "LIVE"', "DEAD + thread branches"),
                  ("_ew[\"oneh\"] = (\"LIVE\" if _prg >= 0.10", "# ⭐ GO — certified HOLD bell", "verdict block"),
                  ('store.record_signal(\n                            "star_go" if _ew.get("star") else "elite_go", {', 'if _ew.get("oneh") == "LIVE" and not _ew.get("star"):', "stamp + go_revived tier")):
    now_, old_ = seg(W, a, b), seg(head, a, 'elif _ew.get("buzzed"):\n                                        _ok9, _m9x, _ = tg.send_thread(' if lab == "DEAD + thread branches" else b)
    if lab == "DEAD + thread branches":
        old_ = seg(head, a, 'if _bell9.startswith("sent"):')
        now_ = seg(W, a, 'elif (_ew.get("oneh") == "LIVE"')
        # HEAD's segment ends at the sent-check; ours ends at the new elif — compare the common prefix
        if old_ is None or now_ is None or not old_.startswith(now_.rstrip()) and old_.rstrip() != now_.rstrip():
            fails.append("DEAD / thread branches changed")
    elif lab == "stamp + go_revived tier":
        old_ = None
        for _end in ('if _ew.get("oneh") == "LIVE" and not _ew.get("star"):',
                     'if (_ew.get("oneh") == "LIVE" and not _ew.get("star")',
                     'if _ew["go"] == "FAST" and _ew.get("star"):'):
            old_ = seg(head, a, _end)
            if old_ is not None:
                break
        if old_ is None or now_ is None or old_.rstrip() != now_.rstrip():
            fails.append("stamp + go_revived tier changed vs HEAD")
    elif old_ != now_ or old_ is None:
        fails.append(f"{lab} changed vs HEAD")

# app: names, board section, both card kinds, auditor
for need in ('"go_live": "💎⚡ GO LIVE — entry at an elite conviction GO after "',
             'for _sect, _lst in (("rev", _cards), ("live", _cards_live)):',
             'elif _oneh == "LIVE" and not _ex.get("star"):',
             'st.markdown("#### 💎⚡ GO after a LIVE verdict — elite conviction, "',
             "FROM shadow_trades WHERE tier='go_live' AND status='CLOSED' ",
             '("⏱ 1H DEAD" if _sect == "rev" else "⏱ 1H LIVE")',
             'key=f"{_kp}_open_{_sym}_{_i}"', '"_unified_source": _src_c}',
             "binance_client.prime_prices([r[1] for r, _ in _cards + _cards_live])"):
    if need not in A:
        fails.append(f"app missing: {need[:60]}")
if "only the revived class" in A and "_cards_live" not in A:
    fails.append("old DEAD-only filter still in place")
if '    "go_live": "go_live",\n' not in U:
    fails.append("auditor map missing go_live")
# the board function still parses and the star board is untouched
try:
    ast.parse(A)
except SyntaxError as exc:
    fails.append(f"app.py syntax: {exc}")
head_app = subprocess.run(["git", "show", "HEAD:app.py"], capture_output=True, cwd=ROOT).stdout.decode("utf-8")
sb_now = seg(A, "def _render_star_board(", "def _render_revived_board(")
sb_old = seg(head_app, "def _render_star_board(", "def _render_revived_board(")
if sb_now != sb_old:
    fails.append("the ⭐ star board changed")


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
print(msg, "\n")
print("GO LIVE:", "ALL PASS" if not fails else fails)
