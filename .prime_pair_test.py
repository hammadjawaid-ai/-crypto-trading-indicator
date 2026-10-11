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
import buzz_clock
ns = {"rung_stats": rung_stats, "buzz_clock": buzz_clock}
for n in tree.body:
    if isinstance(n, ast.FunctionDef) and n.name in ("_conf_band", "_fmt_prime_pair"):
        exec(compile(ast.Module(body=[n], type_ignores=[]), n.name, "exec"), ns)
    elif isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in (
            "STAR_PRIME_REC", "CONV_PRIME_REC", "TRIGKR_PRIME_REC", "LEG2_PRIME_REC", "PAIR_KINDS", "PAIR_WINDOWS", "PAIR_KEY_H", "STAR_PRIME_BANDS", "CONV_PRIME_BANDS",
            "TG_STAR_PRIME", "TG_CONV_PRIME", "TG_TRIGKR_PRIME", "TG_LEG2_PRIME") for t in n.targets):
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
import calendar
NOW = float(calendar.timegm((2026, 10, 11, 13, 40, 0)))   # 18:40 PKT -> 17–21 window
sig = {"symbol": "AAVEUSDT", "base": "AAVE", "side": "LONG", "entry": 184.04, "stop": 176.774, "tp1": 188.712, "tp2": 192.449, "tier": "HIGH", "score": 82, "conf": 40}
m1 = fmt("star", sig, 184.5, NOW)
for need in ("⭐🥇 *STAR × PRIME — AAVE LONG · TAKE · ", "⭐ star fire + 🥇 PRIME on the same coin and side",
             "entry `184.04` · live `184.5` · SL `176.774` · TP1 `188.712` · TP2 `192.449` · 🎯 conf 40 (40-54 band)",
             "pair record (desk 09 Sep → 28 Sep): 76% / +0.48R (33) vs star alone 57% / +0.15R (171) · this band 92% / +0.58R (12) · longs 73% / +0.44R (22)",
             "forward ledger (⭐🥇 pair): ", "refreshed ", "bands outside your list record silently"):
    if need not in m1:
        fails.append(f"star pair message missing {need!r}")
m2 = fmt("conv", dict(sig, side="SHORT", conf=70, tp2=None), 183.9, NOW)
if "window:" in m1 or "window:" in m2 or set(ns["PAIR_WINDOWS"]) != {"trigkr", "leg2"}:
    fails.append("the window line belongs to the two 2026-10-11 bells only; star / conv pair bells unchanged")
for need in ("💎🥇 *ELITE × PRIME — AAVE SHORT · TAKE · ", "💎 elite conviction fire + 🥇 PRIME",
             "🎯 conf 70 (65-74 band)", "pair record (desk 01 Sep → 28 Sep): 60% / +0.28R (85) vs elite alone 41% / +0.06R (750) · this band 67% / +0.70R (6) · shorts 59% / +0.36R (39)",
             "forward ledger (💎🥇 pair): "):
    if need not in m2:
        fails.append(f"conv pair message missing {need!r}")
if "TP2" in m2:
    fails.append("no-TP2 plan must not print TP2")
m3 = fmt("star", dict(sig, conf=None), 184.5, NOW)
m4 = fmt("trigkr", dict(sig, side="SHORT", conf=58), 183.9, NOW)
for need in ("💥🔮🥇 *TRIG × KR × PRIME — AAVE SHORT · TAKE · ", "💥🔮 TRIG × KR break + 🥇 PRIME",
             "pair record (desk 01 Sep → 28 Sep): 83% / +0.37R (23) vs TRIG × KR alone 70% / +0.05R (77) · every band rings; the desk splits the record by band · shorts 81% / +0.32R (16)",
             "forward ledger (💥🔮🥇 pair): ", "a thin count behind the pair record",
             "window: 🟢 17–21 PKT — this pair here 83% / +0.52R (6)"):
    if need not in m4:
        fails.append(f"trigkr pair message missing {need!r}")
m5 = fmt("leg2", dict(sig, conf=72), 184.5, NOW)
if not m5.startswith("🔥🥇 *SECOND LEG × PRIME — AAVE LONG · TAKE · ") or "73% / +0.47R (37) vs second leg alone 51% / +0.10R (358)" not in m5 or "longs 65% / +0.36R (23)" not in m5 or "window: 🟢 17–21 PKT — this pair here 89% / +0.72R (9)" not in m5:
    fails.append(f"leg2 pair message wrong:\n{m5}")
m6 = fmt("leg2", dict(sig, conf=72), 184.5, float(calendar.timegm((2026, 10, 11, 17, 40, 0))))   # 22:40 PKT -> 21–01 red
if "window: 🔴 21–01 PKT — this pair here 33% / -0.39R (6)" not in m6:
    fails.append("red window line wrong")
m7 = fmt("trigkr", dict(sig, conf=58), 184.5, float(calendar.timegm((2026, 10, 11, 9, 0, 0))))   # 14:00 PKT -> 13–17 thin
if "window: 🟡 13–17 PKT — this pair here 0% / -0.09R (1)" not in m7:
    fails.append("thin window line wrong")
if ns["PAIR_KEY_H"] != {"star": 1.0, "conv": 1.0, "trigkr": 3.0, "leg2": 3.0}:
    fails.append("pair keys: star/conv 1h (user 2026-10-12), trigkr/leg2 3h")
if not (ns["TG_TRIGKR_PRIME"] is True and ns["TG_LEG2_PRIME"] is True) or set(ns["PAIR_KINDS"]) != {"star", "conv", "trigkr", "leg2"}:
    fails.append("new pair switches / kinds wrong")
if "🎯 conf ? (? band)" not in m3 or "this band —" not in m3:
    fails.append("unreadable conf must print ? and —")
for m in (m1, m2, m3, m4, m5, m6, m7):
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
                  ('("trigkr", "trig_strong_kr", "trigkr_prime", None,\n                 TG_TRIGKR_PRIME)', "trigkr pair config"),
                  ('("leg2", "second_leg", "leg2_prime", None,\n                 TG_LEG2_PRIME)', "leg2 pair config"),
                  ('"band-out" if (_bands_pp is not None\n                                               and _band_pp not in _bands_pp) else', "band rule optional"),
                  ('_conf_pp = best_board.confidence(_sym_pp, _sd_pp)', "conf fallback at the pass"),
                  ('if (_kind == "conv" and store.seen_between(\n                            "elite_star", _sym_pp, _sd_pp,', "a star never rings both"),
                  ('"prime", _sym_pp, _sd_pp,\n                            _ts_pp - PRIME_PAIR_BEFORE,\n                            _ts_pp + PRIME_PAIR_AFTER)', "2h-before / 30-min-after window"),
                  ('f"{_tier_pp}:{_sym_pp}:{_sd_pp}",\n                            int(PAIR_KEY_H.get(_kind, 3.0) * 3600))', "per-kind key per coin+side"),
                  ("store.record_signal(_tier_pp, _sig_pp)\n                    shadow_trader.open_from_signal(_tier_pp, _sig_pp, _px_pp)", "records + desk open for every band"),
                  ('"off" if not _on_pp else', "switch gates the bell only"),
                  ("+ _kr_note(_sig_pp))", "kronos line")):
    if need not in blk:
        fails.append(f"wiring missing: {lab}")
if blk.index("store.record_signal(_tier_pp, _sig_pp)") > blk.index('if _bell_pp == "due":'):
    fails.append("the record must happen before the bell decision")
for need in ('"star_prime": "⭐🥇 STAR × PRIME', '"conv_prime": "💎🥇 ELITE × PRIME', '"trigkr_prime": "💥🔮🥇 TRIG × KR × PRIME',
             '"leg2_prime": "🔥🥇 SECOND LEG × PRIME', 'def _pair_band_split(tier: str) -> str:', 'st.caption(_pair_band_split(rec.get("tier")))',
             '_PAIR_SPLIT_TIERS = ("star_prime", "conv_prime", "trigkr_prime", "leg2_prime")'):
    if need not in A:
        fails.append(f"app name missing: {need}")
for need in ('    "star_prime": "star_prime",\n', '    "conv_prime": "conv_prime",\n', '    "trigkr_prime": "trigkr_prime",\n', '    "leg2_prime": "leg2_prime",\n'):
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
