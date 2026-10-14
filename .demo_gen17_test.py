"""🎮 DEMO GEN 17 — THE THREE (2026-10-14): roster, ladder, gates, feeds, pools,
re-entry whitelist, header; everything else off the money."""
import ast
import builtins
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"F:\Trading Indicator"
sys.path.insert(0, ROOT)
import demo_account as da  # noqa: E402

fails = []
THREE = {"go_revived", "arrival_t1", "strong_trigger", "early_lane"}   # GEN 17.1: four
if set(da.CLASS_W) != THREE:
    fails.append(f"roster must be exactly the three: {sorted(da.CLASS_W)}")
if not (da.CLASS_W["go_revived"] > da.CLASS_W["arrival_t1"] > da.CLASS_W["strong_trigger"] > da.CLASS_W["early_lane"]):
    fails.append("ladder must be GO REVIVED > ARRIVAL T1 > STRONG TRIGGER > EARLY LANE")
if da.SPARE_RESERVE:
    fails.append("no spare lanes in GEN 17")
if set(da.CONF_GATE) != {"strong_trigger", "early_lane"} or da.CONF_GATE["strong_trigger"] != ((65.0, 1000.0),) or da.CONF_GATE["early_lane"] != ((85.0, 1000.0),):
    fails.append(f"conf gates: strong_trigger 65+ and early_lane 85+: {da.CONF_GATE}")
if {s for s, _ in da.TIME_CLOSED} != {"strong_trigger", "early_lane"}:
    fails.append("time gates: strong_trigger + early_lane")
for s in THREE:
    if da.lev_for(s) != 10.0:
        fails.append(f"flat 10x expected for {s}")
if da.SMART_EXIT_SKIP != THREE:   # (the four)
    fails.append("plain SL / TP1-bank exits for the three")

# ranking: the ladder sorts first; a removed stream gets no seat even with a top score
mk = lambda sym, src, score, side="LONG", conf=None: {"symbol": sym, "base": sym[:-4], "side": side, "entry": 1.0, "stop": 0.97, "tp1": 1.02, "tp2": 1.04, "score": score, "conf": conf, "src": src}
pools = {"strong_trigger": [mk("AAAUSDT", "strong_trigger", 99, conf=80)],
         "arrival_t1": [mk("BBBUSDT", "arrival_t1", 60), mk("SHRTUSDT", "arrival_t1", 95, side="SHORT")],
         "go_revived": [mk("CCCUSDT", "go_revived", 50)],
         "early_lane": [mk("LANEUSDT", "early_lane", 70, conf=90), mk("LOWUSDT", "early_lane", 99, conf=80)],
         "press_break": [mk("DDDUSDT", "press_break", 99, conf=90)],
         "elite_star": [mk("EEEUSDT", "elite_star", 99, conf=70)],
         "moonshot": [mk("FFFUSDT", "moonshot", 99, conf=60)]}
ranked = da.rank_candidates(pools, {})
order = [c["src"] for c in ranked]
if order[:4] != ["go_revived", "arrival_t1", "strong_trigger", "early_lane"] or len(ranked) != 4:
    fails.append(f"ranking wrong: {order} ({len(ranked)})")
if any(c["symbol"] == "SHRTUSDT" for c in ranked):
    fails.append("arrival_t1 shorts must not seat")
# strong trigger below its band gets no seat
r2 = da.rank_candidates({"strong_trigger": [mk("GGGUSDT", "strong_trigger", 99, conf=60)]}, {})
if r2:
    fails.append("strong_trigger conf <65 must not seat")
# GO REVIVED needs no conf
r3 = da.rank_candidates({"go_revived": [mk("HHHUSDT", "go_revived", 50, conf=None)]}, {})
if len(r3) != 1:
    fails.append("go_revived must seat without a conf")

# 🎯 near-TP bank: GO REVIVED + ARRIVAL T1 only; strong trigger holds to SL / TP1
if getattr(da, "NEAR_TP_SRC", None) != {"go_revived", "arrival_t1"}:
    fails.append(f"NEAR_TP_SRC wrong: {getattr(da, 'NEAR_TP_SRC', None)}")
import time as _t
def _pos(src):
    return {"symbol": "ZZZUSDT", "base": "ZZZ", "side": "LONG", "entry": 1.0, "stop": 0.97, "tp1": 1.10, "tp2": 1.20,
            "qty": 100.0, "peak": 1.09, "opened_at": _t.time() - 3600, "src": src, "notional": 100.0, "lev": 10.0,
            "risk_usd": 3.0, "risk_pct": 0.15, "score": 85}
for src, should_close in (("go_revived", True), ("arrival_t1", True), ("strong_trigger", False), ("early_lane", False)):
    st = {"open": [_pos(src)], "closed": [], "balance": 2000.0, "starting_balance": 2000.0, "equity_hist": []}
    try:
        ev = da.manage(st, lambda s: 1.05, None)   # printed 90% of the path, now at 50%
    except Exception as exc:
        fails.append(f"manage() raised for {src}: {exc}"); continue
    closed = [r for e, r in ev if e == "close"]
    if should_close and not (len(closed) == 1 and "near-TP bank" in str(closed[0].get("reason"))):
        fails.append(f"{src}: near-TP bank must close it: {ev}")
    if not should_close and closed:
        fails.append(f"{src}: must hold to SL / TP1, got {closed[0].get('reason')}")
    # SL / TP1 intact on the held one
    if not should_close and st["open"] and (st["open"][0]["stop"] != 0.97 or st["open"][0]["tp1"] != 1.10):
        fails.append("stop / tp1 must stay intact before TP1")

# worker wiring
W = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
i_go_rec = W.find('store.record_signal("go_revived", _rv_sig)')
i_go_feed = W.find('_DEMO_GO.append(dict(\n                                    _rv_sig, src="go_revived",')
i_t1_tiers = W.find("for _tn in _tiers_a:\n                            store.record_signal(_tn, _sig_a)")
i_t1_feed = W.find('_DEMO_T1.append(dict(\n                                    _sig_a, src="arrival_t1",')
i_pools = W.find('        _dz_pools = {\n')
i_rank = W.find("_dz_ranked = demo_account.rank_candidates(_dz_pools, _dz_form)")
if not (0 < i_go_rec < i_go_feed < i_go_rec + 1200):
    fails.append("GO feed must sit right after the go_revived tier record")
if not (0 < i_t1_tiers < i_t1_feed < i_t1_tiers + 900) or "if _atier == 1:\n                            # 🎮 GEN 17 P2 seat feed" not in W:
    fails.append("T1 feed must sit after the arrival desk tiers, tier 1 only")
if not (0 < i_pools < i_rank):
    fails.append("pools must be built before ranking")
pools_src = W[i_pools:i_rank]
for key in ('"go_revived": ([dict(d) for d in _DEMO_GO', '"arrival_t1": ([dict(d) for d in _dz_t1', '"strong_trigger": ([f for f in _dz_fires', '"early_lane": (_g16(em_big, "early_lane")'):
    if key not in pools_src:
        fails.append(f"pool missing: {key[:30]}")
for gone in ('"press_break": (', '"moonshot": (', '"elite_star": (', '"early_movers": (', '"strig_kr": ('):
    if gone in pools_src:
        fails.append(f"removed stream still pooled: {gone}")
if '("go_revived", "arrival_t1",\n                              "strong_trigger", "early_lane")\n                             else "strong_trigger"),   # GEN 17.1' not in W:
    fails.append("momentum re-entry whitelist must be the three")
if '(("go_revived", "go_revived"),         # GEN 17' not in W or '("arrival_t1", "trig_hot")' not in W:
    fails.append("form list must map the three to their desk tiers")
if "_DEMO_GO: list = []" not in W or "_DEMO_T1: list = []" not in W:
    fails.append("feeds not declared")
# the bells / desk tiers of the removed streams are untouched: their record sites remain
for keep in ('record_signal("moonshot", p)', 'store.record_signal("elite_star",', '_DEMO_PB.append(dict(_sig_pb,', 'store.record_signal("press_break", _sig_pb)'):
    if keep not in W:
        fails.append(f"a removed stream's record site vanished: {keep}")
A = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
if "🎮 DEMO $2,000 — GEN 17.1 · THE FOUR" not in A or "<b>THE FOUR, in order:</b>" not in A or "<b>4. ⭐🚀 EARLY LANE conf ≥85</b>" not in A:
    fails.append("demo header not updated")
if "GEN 16.5 · THE PRIORITY FOUR" in A:
    fails.append("old header still present")


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
print("DEMO GEN 17:", "ALL PASS" if not fails else fails)
