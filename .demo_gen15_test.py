"""GEN 15 validation — ghost scan, ten-stream gates, risk-based
sizing, heat cap, margin cap, pct loss rail / no gain cap, 14 seats,
priority order (premium above trigger), star near-TP bank, 💎🔮 ride."""
import ast
import io
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"F:\Trading Indicator")

for fn in (r"F:\Trading Indicator\agent_worker.py",
           r"F:\Trading Indicator\demo_account.py",
           r"F:\Trading Indicator\app.py"):
    src = open(fn, encoding="utf-8").read()
    assert "\ufffd" not in src, f"replacement char in {fn}"
    tree = ast.parse(src)
    assigned = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            assigned.add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assigned.add(n.name)
            for a in (n.args.args + n.args.kwonlyargs
                      + ([n.args.vararg] if n.args.vararg else [])
                      + ([n.args.kwarg] if n.args.kwarg else [])):
                assigned.add(a.arg)
        elif isinstance(n, ast.ClassDef):
            assigned.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names:
                assigned.add((al.asname or al.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            assigned.add(n.name)
        elif isinstance(n, ast.comprehension):
            for t in ast.walk(n.target):
                if isinstance(t, ast.Name):
                    assigned.add(t.id)
        elif isinstance(n, ast.Lambda):
            for a in n.args.args:
                assigned.add(a.arg)
        elif isinstance(n, (ast.With, ast.AsyncWith)):
            for it in n.items:
                if it.optional_vars:
                    for t in ast.walk(it.optional_vars):
                        if isinstance(t, ast.Name):
                            assigned.add(t.id)
    import builtins
    loads = {n.id for n in ast.walk(tree)
             if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    ghosts = sorted(g for g in loads - assigned
                    if not hasattr(builtins, g)
                    and g not in ("Any", "__file__"))
    print(fn.split("\\")[-1], "ghosts:", ghosts or "NONE")

import demo_account as da

FOUR = {"strong_trigger", "elite_star", "kr_premium", "strig_kr"}
assert da.GEN == 15
assert set(da.CLASS_W) == FOUR, set(da.CLASS_W)
assert da.SMART_EXIT_SKIP == FOUR
assert da.RIDE_SRC == set()
assert da.CONF_GATE == {"strong_trigger": ((65.0, 1000.0),)}
assert set(da.MAX_PER_SRC) == FOUR
assert da.START_BAL == 1500.0
assert da.HEAT_CAP == 0.35 and da.DAY_MAX_LOSS_PCT == 0.15
assert da.DAY_MAX_GAIN == float("inf")
# user's ladder order
assert (da.CLASS_W["strong_trigger"] > da.CLASS_W["elite_star"]
        > da.CLASS_W["kr_premium"] > da.CLASS_W["strig_kr"])
assert not hasattr(da, "RISK_PCT"), "GEN 15 sizes by leverage"
assert da.MAX_SLOTS == 10
import time
fails = []


def cand(src, conf, chain=0, score=80, sym=None, stop=97.0):
    p = {"symbol": sym or f"{src[:4].upper()}{int(conf or 0)}USDT",
         "base": "X", "side": "LONG", "entry": 100.0, "stop": stop,
         "tp1": 106.0, "tp2": None, "score": score, "conf": conf}
    if chain:
        p["chain"] = chain
    return p


# ---- seat gates: trigger >=65 only, the other three every band ----
for src, conf, want in (
        ("strong_trigger", 65, True), ("strong_trigger", 85, True),
        ("strong_trigger", 64, False), ("strong_trigger", 45, False),
        ("strong_trigger", None, False),
        ("elite_star", None, True), ("elite_star", 25, True),
        ("elite_star", 90, True),
        ("kr_premium", None, True), ("kr_premium", 30, True),
        ("strig_kr", None, True), ("strig_kr", 45, True)):
    ranked = da.rank_candidates({src: [cand(src, conf)]}, {})
    if bool(ranked) != want:
        fails.append(f"{src} conf={conf}: seat {bool(ranked)} != {want}")
        continue
    if not want:
        continue
    st = {"balance": 1500.0, "open": [], "closed": []}
    op, _ = da.try_open(st, ranked, lambda s: 100.0)
    if not op:
        fails.append(f"{src} conf={conf}: try_open refused")
        continue
    wm = 1500.0 / da.MAX_SLOTS
    if abs(op[0]["margin"] - wm) > 0.05:
        fails.append(f"{src}: margin ${op[0]['margin']} != ${wm}")
    if abs(op[0]["notional"] - wm * da.lev_for(src, conf)) > 0.5:
        fails.append(f"{src}: notional != margin x lev")
    wl = da.lev_for(src, conf)
    if abs(op[0]["lev"] - wl) > 0.01:
        fails.append(f"{src} conf={conf}: lev {op[0]['lev']} != {wl}")

# ---- dropped streams take NO seat ----
for gone in ("pw_confirm", "pw_waking", "moonshot", "kr_strong",
             "elite_kr", "sniper2", "rerun"):
    if da.rank_candidates({gone: [cand(gone, 60)]}, {}):
        fails.append(f"{gone} still seats in GEN 15")

# ---- user ladder: trigger outranks premium on equal merit ----
rk = da.rank_candidates(
    {"kr_premium": [cand("kr_premium", 70, sym="AUSDT")],
     "strong_trigger": [cand("strong_trigger", 70, sym="BUSDT")]}, {})
if not (rk and rk[0]["src"] == "strong_trigger"):
    fails.append("user ladder broken (trigger should lead)")

# ---- conf 85 trigger outranks conf 65 trigger ----
rk = da.rank_candidates({"strong_trigger": [
    cand("strong_trigger", 65, sym="L65USDT"),
    cand("strong_trigger", 90, sym="H90USDT")]}, {})
if not (rk and rk[0]["symbol"] == "H90USDT"):
    fails.append("conf-85 priority inside the trigger lane broken")

# ---- per-stream seat cap: trigger stops at 6 ----
st = {"balance": 1500.0, "open": [], "closed": []}
pool = {"strong_trigger": [cand("strong_trigger", 70, sym=f"T{i}USDT")
                           for i in range(12)]}
op, _ = da.try_open(st, da.rank_candidates(pool, {}), lambda s: 100.0)
if len(op) != 6:
    fails.append(f"trigger seat cap opened {len(op)} != 6")

# ---- heat cap: premium 8% on a 3% stop -> $600 margin each, 2 fit ----
st = {"balance": 1500.0, "open": [], "closed": []}
pool = {"kr_premium": [cand("kr_premium", 70, sym=f"P{i}USDT")
                       for i in range(6)]}
op, _ = da.try_open(st, da.rank_candidates(pool, {}), lambda s: 100.0)
heat = sum(p["qty"] * 3.0 for p in op) / 1500.0
marg = sum(p["margin"] for p in op)
if not (op and heat <= 0.35 + 1e-6 and marg <= 1500.0 + 1e-6):
    fails.append(f"premium heat/collateral: n={len(op)} heat {heat:.2%} "
                 f"margin ${marg:.0f}")

# ---- rails: -15% blocks, gain cap off ----
now = time.time()
st = {"balance": 1275.0, "open": [],
      "closed": [{"pnl": -225.0, "closed_at": now - 3600}]}
if da.try_open(st, da.rank_candidates(
        {"kr_premium": [cand("kr_premium", 70)]}, {}),
        lambda s: 100.0)[0]:
    fails.append("15% loss rail broken")
st = {"balance": 2600.0, "open": [],
      "closed": [{"pnl": 1100.0, "closed_at": now - 3600}]}
if not da.try_open(st, da.rank_candidates(
        {"kr_premium": [cand("kr_premium", 70)]}, {}),
        lambda s: 100.0)[0]:
    fails.append("gain cap should be OFF")

# ---- exits: star near-TP bank kept, premium banks 100% at TP1 ----
st = {"balance": 1500.0, "closed": [], "equity_hist": [],
      "open": [{"symbol": "STARUSDT", "base": "STAR", "side": "LONG",
                "entry": 100.0, "stop": 97.0, "tp1": 106.0,
                "tp2": None, "qty": 1.0, "notional": 100.0,
                "lev": 10.0, "margin": 10.0, "risk0": 3.0,
                "src": "elite_star", "score": 82,
                "opened_at": now - 3600, "fees": 0.0,
                "tp1_banked": 0.0, "be_set": False, "peak": 105.4}]}
ev = da.manage(st, lambda s: 103.0)
if not any("near-TP bank" in str(e[1].get("reason")) for e in ev):
    fails.append("star near-TP bank broken")

for src in ("kr_premium", "strong_trigger", "strig_kr"):
    st = {"balance": 1500.0, "closed": [], "equity_hist": [],
          "open": [{"symbol": "XUSDT", "base": "X", "side": "LONG",
                    "entry": 100.0, "stop": 97.0, "tp1": 104.0,
                    "tp2": 108.0, "qty": 10.0, "notional": 1000.0,
                    "lev": 10.0, "margin": 100.0, "risk0": 3.0,
                    "src": src, "score": 82, "opened_at": now - 3600,
                    "fees": 0.0, "tp1_banked": 0.0, "be_set": False,
                    "peak": 100.0}]}
    ev = da.manage(st, lambda s: 104.2)
    if st["open"] or not any("TP1" in str(e[1].get("reason"))
                             for e in ev):
        fails.append(f"{src} TP1 bank-100% broken (no ride seats)")


# ---- GEN 15 leverage ladder (user 2026-09-13) ----
for src, conf, want in (("strong_trigger", 70, 10.0),
                        ("strong_trigger", 90, 10.0),
                        ("kr_premium", None, 10.0),
                        ("kr_premium", 30, 10.0),
                        ("strig_kr", 45, 8.0),
                        ("strig_kr", None, 8.0),
                        ("elite_star", 70, 8.0),
                        ("elite_star", 85, 8.0),
                        ("elite_star", 40, 6.0),
                        ("elite_star", None, 6.0)):
    got = da.lev_for(src, conf)
    if abs(got - want) > 1e-9:
        fails.append(f"lev_for({src},{conf}) {got} != {want}")

# leverage must NOT change dollar risk, only collateral + stop width
st = {"balance": 1500.0, "open": [], "closed": []}
op6, _ = da.try_open(st, da.rank_candidates(
    {"elite_star": [cand("elite_star", 40, sym="S6USDT")]}, {}),
    lambda s: 100.0)
st = {"balance": 1500.0, "open": [], "closed": []}
op8, _ = da.try_open(st, da.rank_candidates(
    {"elite_star": [cand("elite_star", 70, sym="S8USDT")]}, {}),
    lambda s: 100.0)
if op6 and op8:
    # GEN 15: leverage DRIVES size — same margin, bigger notional,
    # proportionally bigger dollar risk at 8x than at 6x.
    if abs(op6[0]["margin"] - op8[0]["margin"]) > 0.05:
        fails.append("margin should be identical across leverages")
    if not (op8[0]["notional"] > op6[0]["notional"] * 1.3):
        fails.append(f"8x notional {op8[0]['notional']:.0f} should be "
                     f"~1.33x the 6x one {op6[0]['notional']:.0f}")
    r6 = op6[0]["qty"] * 3.0
    r8 = op8[0]["qty"] * 3.0
    if not (r8 > r6 * 1.3):
        fails.append(f"8x risk ${r8:.2f} should exceed 6x ${r6:.2f}")
    if abs(op6[0]["risk_usd"] - r6) > 0.5:
        fails.append("risk_usd not recorded correctly")
else:
    fails.append("star lev test could not open")

# the heat cap must still bind: many wide-stopped star seats
st = {"balance": 1500.0, "open": [], "closed": []}
pool = {"elite_star": [cand("elite_star", 70, sym=f"H{i}USDT",
                            stop=93.0) for i in range(9)]}
op, _ = da.try_open(st, da.rank_candidates(pool, {}), lambda s: 100.0)
heat = sum(p["risk_usd"] for p in op) / 1500.0
if heat > 0.35 + 1e-6:
    fails.append(f"heat cap breached: {heat:.2%}")
marg = sum(p["margin"] for p in op)
if marg > 1500.0 + 1e-6:
    fails.append(f"collateral breached: ${marg:.0f}")

# wider stop admitted at 6x, refused at 10x (0.8/lev liquidation rule)
st = {"balance": 1500.0, "open": [], "closed": []}
wide = cand("elite_star", 40, sym="WIDEUSDT", stop=90.0)   # 10% stop
if not da.try_open(st, da.rank_candidates({"elite_star": [wide]}, {}),
                   lambda s: 100.0)[0]:
    fails.append("6x should admit a 10% stop")
st = {"balance": 1500.0, "open": [], "closed": []}
wide2 = cand("kr_premium", 70, sym="WIDE2USDT", stop=90.0)  # 10% @10x
if da.try_open(st, da.rank_candidates({"kr_premium": [wide2]}, {}),
               lambda s: 100.0)[0]:
    fails.append("10x should REFUSE a 10% stop (0.8/10 = 8%)")

print("GEN 15 sim:", "ALL PASS" if not fails else "FAILS:")
for f in fails:
    print("  x", f)
