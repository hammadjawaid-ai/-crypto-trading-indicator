"""🎮 DEMO GEN 17.3 — THE SIX (2026-10-14 evening): the ⭐ star seat follows the
phone's four-rule read, the GO REVIVED seat follows the fire read, the star's
old rr law is gone, exits unchanged, header, ghosts."""
import ast
import builtins
import io
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"F:\Trading Indicator"
sys.path.insert(0, ROOT)
import demo_account as da  # noqa: E402

W = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
A = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
D = open(os.path.join(ROOT, "demo_account.py"), encoding="utf-8").read()
fails = []

# ── roster / ladder / exits ──
if set(da.CLASS_W) != {"go_revived", "arrival_t1", "strong_trigger", "early_lane", "star_prime", "elite_star"}:
    fails.append(f"roster must be THE SIX: {sorted(da.CLASS_W)}")
if da.CLASS_W.get("elite_star") != 102 or da.CLASS_W["elite_star"] != min(da.CLASS_W.values()):
    fails.append("⭐ star is the 6th seat (102, lowest rung)")
if da.RR_OPEN_BOUNDS != {}:
    fails.append(f"the star's demo-only rr law must be gone (same rules as the phone): {da.RR_OPEN_BOUNDS}")
if "elite_star" not in da.SMART_EXIT_SKIP or da.lev_for("elite_star") != 10.0:
    fails.append("star seat: plain SL / TP1 exits at flat 10x")
if da.NEAR_TP_SRC != {"go_revived", "arrival_t1"}:
    fails.append("near-TP bank stays GO REVIVED + T1 only")
if "elite_star" in da.CONF_GATE or any(s == "elite_star" for s, _ in da.TIME_CLOSED) or "elite_star" in da.LONG_ONLY:
    fails.append("no demo-side conf / clock / side rule on the star — the four-rule read is the whole gate")

# ── seating: both sides, no conf, rr beyond the old 1.2 bound ──
mk = lambda sym, src, score, side="LONG", conf=None, stop=0.97, tp1=1.02: {
    "symbol": sym, "base": sym[:-4], "side": side, "entry": 1.0, "stop": stop, "tp1": tp1, "tp2": 1.06,
    "score": score, "conf": conf, "src": src}
r = da.rank_candidates({"elite_star": [mk("AAAUSDT", "elite_star", 80), mk("BBBUSDT", "elite_star", 80, side="SHORT", stop=1.03, tp1=0.98)]}, {})
if sorted(c["symbol"] for c in r) != ["AAAUSDT", "BBBUSDT"]:
    fails.append(f"star seats both sides without a conf: {[c['symbol'] for c in r]}")
st = {"balance": 2000.0, "open": [], "closed": [], "equity_hist": [], "start": 2000.0, "started_at": time.time() - 86400}
cands = da.rank_candidates({"elite_star": [mk("CCCUSDT", "elite_star", 80, stop=0.97, tp1=1.054)]}, {})   # rr 1.8 at the fill
try:
    opened, _ = da.try_open(st, cands, lambda s: 1.0, active=set(), now=time.time())
    if len(opened) != 1 or not st["open"] or st["open"][0]["src"] != "elite_star" or st["open"][0]["lev"] != 10.0:
        fails.append(f"a star plan at rr 1.8 must seat now that the rr law is gone: {opened} {st['open']}")
except Exception as exc:
    fails.append(f"try_open raised: {type(exc).__name__}: {exc}")
# the exits: a star seat holds to SL / TP1 (no near-TP bank)
pos = {"symbol": "ZZZUSDT", "base": "ZZZ", "side": "LONG", "entry": 1.0, "stop": 0.97, "tp1": 1.10, "tp2": 1.20,
       "qty": 100.0, "peak": 1.09, "opened_at": time.time() - 3600, "src": "elite_star", "notional": 100.0, "lev": 10.0,
       "risk_usd": 3.0, "risk_pct": 0.15, "score": 85}
st2 = {"open": [pos], "closed": [], "balance": 2000.0, "starting_balance": 2000.0, "equity_hist": []}
ev = da.manage(st2, lambda s: 1.05, None)
if any(e == "close" for e, _ in ev) or st2["open"][0]["stop"] != 0.97:
    fails.append(f"star seat must hold to SL / TP1 with the stop intact: {ev}")

# ── worker wiring ──
for need, lab in (("_sg9 = (_gate9 if TG_GATES else _star_gate(\n                                    _pmx, time.time(), _btc_day_pct()))", "star read computed for the seat (phone gates on or off)"),
                  ('"seat": bool(_sg9[0]),\n                                 "gate_read": _sg9[1],', "star feed carries the read"),
                  ("_rgd = _revived_gate(\n                                        _ew, _ew_px, _ew_now,\n                                        _btc_day_pct())", "GO REVIVED seat reads the fire"),
                  ('if _rgd[0]:\n                                    _DEMO_GO.append(dict(\n                                        _rv_sig, src="go_revived",', "GO feed only on a passed read"),
                  ('"elite_star": ([dict(d) for d in _DEMO_STARS\n                            if d.get("seat") and d.get("entry")', "star pool takes passed reads only"),
                  ('("elite_star", "elite_star")):     # GEN 17.3', "form list"),
                  ('"star_prime", "elite_star")\n                             else "strong_trigger"),   # GEN 17.3', "re-entry whitelist")):
    if need not in W:
        fails.append(f"wiring missing: {lab}")
# the read sits before the star record, inside the star branch; the seat flag sits in the GEN 11 feed
i_sg = W.find("_sg9 = (_gate9 if TG_GATES else _star_gate(")
i_rec = W.find('store.record_signal("elite_star",\n                                                _st_sig)')
i_feed = W.find('"seat": bool(_sg9[0]),')
if not (0 < i_sg < i_rec < i_feed < i_rec + 2500):
    fails.append(f"star read / record / feed order wrong: {i_sg} {i_rec} {i_feed}")
# the GO gate sits inside the go_revived tier block, after the record
i_go_rec = W.find('store.record_signal("go_revived", _rv_sig)')
i_rgd = W.find("_rgd = _revived_gate(")
if not (0 < i_go_rec < i_rgd < i_go_rec + 1200):
    fails.append("GO REVIVED seat read must follow the tier record")
# the phone side is untouched: bell gate calls and mutes as deployed in 394d805
for keep in ("_gate9 = _star_gate(_pmx, time.time(),", "_rg9 = _revived_gate(", "_gl9 = _golive_gate(", "TG_GATES = True",
             "TG_TRIGKR_PRIME = False", "_MUTE_RULES(_fmt_apex_v2(_sig2, _px2, _rv2)"):
    if keep not in W:
        fails.append(f"phone wiring changed: {keep}")
# one-shot cut-over still in place
if "demo_account.close_before(" not in W:
    fails.append("cut-over call vanished")

# ── header ──
for need in ("🎮 DEMO $2,000 — GEN 17.3 · THE SIX", "<b>THE SIX, in order:</b>", "<b>6. ⭐ ELITE STAR</b>",
             "seats only when its Telegram fire read ", "heat ≥25 · BTC day ≤ +1.5% · ", "a muted \"\n        \"star takes no seat"):
    if need not in A:
        fails.append(f"header missing: {need[:50]}")
for gone in ("the plain star fire stays off the money", "moonshot, elite star, early movers", "GEN 17.2 · THE FIVE"):
    if gone in A:
        fails.append(f"stale header text: {gone}")
try:
    ast.parse(A)
except SyntaxError as exc:
    fails.append(f"app.py syntax: {exc}")


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


for name, src in (("agent_worker", W), ("demo_account", D)):
    g = ghosts(src)
    if g:
        fails.append(f"{name} ghosts: {g}")
print("DEMO GEN 17.3:", "ALL PASS" if not fails else fails)
