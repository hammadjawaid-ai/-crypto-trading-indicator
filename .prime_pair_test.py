"""⭐🥇 STAR × PRIME / 💎🥇 ELITE × PRIME — band rule, message format, wiring,
names, ghost scan. The two helpers run standalone from the worker's AST."""
import ast
import builtins
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"F:\Trading Indicator"
sys.path.insert(0, ROOT)
import rung_stats  # noqa: E402

W = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
A = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
U = open(os.path.join(ROOT, "auditor.py"), encoding="utf-8").read()
fails = []
tree = ast.parse(W)
ns = {"rung_stats": rung_stats}
for n in tree.body:
    if isinstance(n, ast.FunctionDef) and n.name in ("_conf_band", "_fmt_prime_pair"):
        exec(compile(ast.Module(body=[n], type_ignores=[]), n.name, "exec"), ns)
    elif isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in (
            "STAR_PRIME_REC", "CONV_PRIME_REC", "STAR_PRIME_BANDS", "CONV_PRIME_BANDS", "TG_STAR_PRIME", "TG_CONV_PRIME") for t in n.targets):
        exec(compile(ast.Module(body=[n], type_ignores=[]), "consts", "exec"), ns)
band, fmt = ns["_conf_band"], ns["_fmt_prime_pair"]

# band rule
for c, want in ((40, "40-54"), (54.9, "40-54"), (55, "55-64"), (64, "55-64"), (65, "65-74"), (74.9, "65-74"), (75, "75-84"), (84, "75-84"), (85, "85+"), (98, "85+"), (None, None), ("x", None), (5.5e12, None), (-1, None)):
    if band(c) != want:
        fails.append(f"band({c}) = {band(c)}, wanted {want}")
if ns["STAR_PRIME_BANDS"] != ("40-54", "55-64", "75-84", "85+") or ns["CONV_PRIME_BANDS"] != ("40-54", "55-64", "65-74"):
    fails.append("band lists do not match the user's call")
if not (ns["TG_STAR_PRIME"] is True and ns["TG_CONV_PRIME"] is True):
    fails.append("both switches must start ON")

# messages (forward ledger reads the real store path; fail-soft either way)
NOW = 1791108000.0
sig = {"symbol": "AAVEUSDT", "base": "AAVE", "side": "LONG", "entry": 184.04, "stop": 176.774, "tp1": 188.712, "tp2": 192.449, "tier": "HIGH", "score": 82, "conf": 40}
m1 = fmt("star", sig, 184.5, NOW)
for need in ("⭐🥇 *STAR × PRIME — AAVE LONG · TAKE · ", "⭐ star fire + 🥇 PRIME on the same coin and side",
             "entry `184.04` · live `184.5` · SL `176.774` · TP1 `188.712` · TP2 `192.449` · 🎯 conf 40 (40-54 band)",
             "pair record (desk 09 Sep → 28 Sep): 76% / +0.48R (33) vs star alone 57% / +0.15R (171) · this band 92% / +0.58R (12) · longs 73% / +0.44R (22)",
             "forward ledger (⭐🥇 pair): ", "refreshed ", "bands outside your list record silently"):
    if need not in m1:
        fails.append(f"star pair message missing {need!r}")
m2 = fmt("conv", dict(sig, side="SHORT", conf=70, tp2=None), 183.9, NOW)
for need in ("💎🥇 *ELITE × PRIME — AAVE SHORT · TAKE · ", "💎 elite conviction fire + 🥇 PRIME",
             "🎯 conf 70 (65-74 band)", "pair record (desk 01 Sep → 28 Sep): 60% / +0.28R (85) vs elite alone 41% / +0.06R (750) · this band 67% / +0.70R (6) · shorts 59% / +0.36R (39)",
             "forward ledger (💎🥇 pair): "):
    if need not in m2:
        fails.append(f"conv pair message missing {need!r}")
if "TP2" in m2:
    fails.append("no-TP2 plan must not print TP2")
m3 = fmt("star", dict(sig, conf=None), 184.5, NOW)
if "🎯 conf ? (? band)" not in m3 or "this band —" not in m3:
    fails.append("unreadable conf must print ? and —")
for m in (m1, m2, m3):
    if m.count("*") % 2 or m.count("`") % 2 or m.count("_") % 2 or "\ufffd" in m:
        fails.append("markdown/encoding unbalanced")

# wiring
i_push = W.rfind("        _push_elite(list(_ec_buzz))\n")
i_blk = W.find("    # ⭐🥇 / 💎🥇 PRIME PAIRS — pairing pass.")
i_conv2 = W.find('    # 💯 CONVICTION v2 (user 2026-08-23: "remove kronos its not even')
if not (0 < i_push < i_blk < i_conv2):
    fails.append(f"pairing pass misplaced: push {i_push} block {i_blk} conv2 {i_conv2}")
blk = W[i_blk:i_conv2]
for need, lab in (('("star", "elite_star", "star_prime", STAR_PRIME_BANDS,\n                 TG_STAR_PRIME)', "star pair config"),
                  ('("conv", "elite_conv", "conv_prime", CONV_PRIME_BANDS,\n                 TG_CONV_PRIME)', "conv pair config"),
                  ('if (_kind == "conv" and store.seen_between(\n                            "elite_star", _sym_pp, _sd_pp,', "a star never rings both"),
                  ('"prime", _sym_pp, _sd_pp,\n                            _ts_pp - PRIME_PAIR_BEFORE,\n                            _ts_pp + PRIME_PAIR_AFTER)', "2h-before / 30-min-after window"),
                  ('f"{_tier_pp}:{_sym_pp}:{_sd_pp}", 3 * 3600)', "3h key per coin+side per bell"),
                  ("store.record_signal(_tier_pp, _sig_pp)\n                    shadow_trader.open_from_signal(_tier_pp, _sig_pp, _px_pp)", "records + desk open for every band"),
                  ('"band-out" if _band_pp not in _bands_pp else', "band filter on the bell only"),
                  ('"off" if not _on_pp else', "switch gates the bell only"),
                  ("+ _kr_note(_sig_pp))", "kronos line")):
    if need not in blk:
        fails.append(f"wiring missing: {lab}")
if blk.index("store.record_signal(_tier_pp, _sig_pp)") > blk.index('if _bell_pp == "due":'):
    fails.append("the record must happen before the bell decision")
for need in ('"star_prime": "⭐🥇 STAR × PRIME', '"conv_prime": "💎🥇 ELITE × PRIME'):
    if need not in A:
        fails.append(f"app name missing: {need}")
for need in ('    "star_prime": "star_prime",\n', '    "conv_prime": "conv_prime",\n'):
    if need not in U:
        fails.append(f"auditor map missing: {need.strip()}")


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
print(m1, "\n\n" + m2, "\n")
print("PRIME PAIRS:", "ALL PASS" if not fails else fails)
