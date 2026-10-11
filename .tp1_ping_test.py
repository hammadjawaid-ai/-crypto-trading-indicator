"""🏦 TP1 HIT ping (2026-10-12): roster-only watch list, stream line, one ping
per coin+side+TP1, resolved memo, premium stamp, ghosts."""
import ast
import builtins
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"F:\Trading Indicator"
W = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
fails = []
ns = {}
for n in ast.parse(W).body:
    if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "TP1_STREAMS" for t in n.targets):
        exec(compile(ast.Module(body=[n], type_ignores=[]), "c", "exec"), ns)
T = ns.get("TP1_STREAMS") or {}
want = {"elite_star", "elite_agrade", "trig_hot", "kr_premium_bell", "apex_v2", "moonshot", "star_prime",
        "conv_prime", "trigkr_prime", "leg2_prime", "go_revived", "go_live"}
if set(T) != want:
    fails.append(f"watch list is not the phone roster: {sorted(set(T) ^ want)}")
for muted in ("conviction_v2", "elite_confirm", "personal_watch", "personal_watch_early", "elite_conv", "kr_strong", "early_lane", "prime"):
    if muted in T:
        fails.append(f"muted / silent stream in the TP1 watch: {muted}")
for k, v in T.items():
    if "_" in v or not v.strip():
        fails.append(f"label with an underscore (Markdown v1) or empty: {k} -> {v!r}")

# wiring
i_loop = W.find("for _rg_stream in TP1_STREAMS:")
i_by = W.find("_rg_by.setdefault(")
i_done = W.find("if (_rg_src, _rg_sym, _rg_side, int(_rg_ts)) in _RG_DONE:")
i_key = W.find('f"tp1hit:{_rg_sym}:{_rg_side}:{_rg_tp1:g}"')
i_from = W.find('f"from: {_rg_from or TP1_STREAMS.get(_rg_src, _rg_src)}\\n"')
i_plan = W.find('f"fire entry `{_rg_ent:g}` · SL `{_rg_stp:g}` · "')
i_stop = W.find("_RG_DONE.add((_rg_src, _rg_sym, _rg_side, int(_rg_ts)))\n                continue    # stop did its job")
if not (0 < i_loop < i_by < i_done < i_key < i_from < i_plan < i_stop):
    fails.append(f"ride-guard wiring order wrong: loop {i_loop} by {i_by} done {i_done} key {i_key} from {i_from} plan {i_plan} stop {i_stop}")
if 'for _rg_stream in ("elite_confirm", "personal_watch",' in W:
    fails.append("old four-stream watch list still present")
if 'f"tp1hit:{_rg_sym}:{_rg_side}:{int(_rg_ts)}"' in W:
    fails.append("old per-record key still present (would ping once per stream)")
# the from-line builds labels from the table with fire times
if 'f"{TP1_STREAMS.get(_s, _s)} fired "\n                        f"{rung_stats.pkt_hm(_t)} PKT"' not in W:
    fails.append("from-line must print the label and the PKT fire time")
# premium stamp right after the premium send, records only
i_prem = W.find('f"Bank at TP1._")\n                    n_alerts += 1 if ok else 0\n')
i_stamp = W.find('store.record_signal("kr_premium_bell", _sp2)')
if not (0 < i_prem < i_stamp < i_prem + 600):
    fails.append("premium stamp missing or misplaced")
if W.count("⚡🔮 *KR-STRONG PREMIUM — ") != 1 or "83.1% / " not in W:
    fails.append("the premium bell text must be untouched")


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
# a rendered sample of the line, from the same expressions the worker uses
import time
sys.path.insert(0, ROOT)
import rung_stats
_by = [(1791536820.0, "elite_star"), (1791536880.0, "star_prime")]
line = " · ".join(f"{T.get(s, s)} fired {rung_stats.pkt_hm(t)} PKT" for t, s in sorted(_by))
sample = ("🏦 *XLM LONG — TP1 HIT* `0.200409` — BANK 100% HERE (the plan). Re-enter only on a fresh 🟢 confirm or re-fire.\n"
          f"from: {line}\nfire entry `0.1976` · SL `0.194029` · TP1 `0.200409`")
if sample.count("*") % 2 or sample.count("`") % 2 or "_" in sample:
    fails.append("sample ping markdown unbalanced")
print(sample, "\n")
print("TP1 PING:", "ALL PASS" if not fails else fails)
