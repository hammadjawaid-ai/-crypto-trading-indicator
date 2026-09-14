"""GEN 16 validation — ghost scan, ten-stream gates, risk-based
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
import time

FOUR = {"early_lane", "early_movers", "best_zone",
        "strong_trigger", "strig_kr"}
assert da.GEN == 16
assert da.START_BAL == 2000.0
assert set(da.CLASS_W) == FOUR, set(da.CLASS_W)
assert da.SMART_EXIT_SKIP == FOUR
assert da.MAX_SLOTS == 20 and da.MIN_SLOTS == 20
assert da.MAX_PER_SRC == {}
assert da.CONF_GATE == {
    "early_lane": ((85.0, 1000.0),),
    "early_movers": ((55.0, 65.0), (85.0, 1000.0)),
    "strong_trigger": ((65.0, 1000.0),),
    "strig_kr": ((40.0, 1000.0),)}
assert da.RR_OPEN_BOUNDS == {} and da.RIDE_SRC == set()
assert da.HEAT_CAP == 0.35 and da.DAY_MAX_LOSS_PCT == 0.15
assert da.DAY_MAX_GAIN == float("inf")
assert not hasattr(da, "RISK_PCT")
assert (da.CLASS_W["early_lane"] > da.CLASS_W["early_movers"]
        > da.CLASS_W["best_zone"] > da.CLASS_W["strong_trigger"]
        > da.CLASS_W["strig_kr"])
fails = []


def cand(src, conf=70, sym=None, stop=96.75, tp1=106.0, score=80):
    return {"symbol": sym or f"{src[:4].upper()}USDT", "base": "X",
            "side": "LONG", "entry": 100.0, "stop": stop, "tp1": tp1,
            "tp2": None, "score": score, "conf": conf}


# ---- CONF BANDS (user 2026-09-14) ----
BANDS = [
    ("early_lane", 85, True), ("early_lane", 98, True),
    ("early_lane", 84, False), ("early_lane", 55, False),
    ("early_lane", None, False),
    ("early_movers", 55, True), ("early_movers", 64, True),
    ("early_movers", 85, True), ("early_movers", 98, True),
    ("early_movers", 54, False), ("early_movers", 65, False),
    ("early_movers", 84, False), ("early_movers", None, False),
    ("strong_trigger", 65, True), ("strong_trigger", 98, True),
    ("strong_trigger", 64, False), ("strong_trigger", None, False),
    ("strig_kr", 40, True), ("strig_kr", 98, True),
    ("strig_kr", 39, False), ("strig_kr", None, False),
    # best_zone is deliberately ungated
    ("best_zone", None, True), ("best_zone", 25, True),
    ("best_zone", 98, True),
]
for src, conf, want in BANDS:
    got = bool(da.rank_candidates(
        {src: [cand(src, conf, sym=f"{src[:3]}{conf}USDT")]}, {}))
    if got != want:
        fails.append(f"{src} conf={conf}: seat {got} != {want}")

# chain>0 re-entries are exempt from the bands
_c = cand("early_lane", 40, sym="CHAINUSDT")
_c["chain"] = 1
if not da.rank_candidates({"early_lane": [_c]}, {}):
    fails.append("chain re-entry should be exempt from the conf band")

# ---- every roster stream seats, at flat 10x, $100 margin ----
for src in sorted(FOUR):
    for conf in ((98,) if src != "best_zone" else (None, 98)):
        st = {"balance": 2000.0, "open": [], "closed": []}
        r = da.rank_candidates({src: [cand(src, conf)]}, {})
        if not r:
            fails.append(f"{src} conf={conf}: no seat (should be ungated)")
            continue
        op, _ = da.try_open(st, r, lambda s: 100.0)
        if not op:
            fails.append(f"{src} conf={conf}: try_open refused")
            continue
        p = op[0]
        if abs(p["lev"] - 10.0) > 0.01:
            fails.append(f"{src}: lev {p['lev']} != 10")
        if abs(p["margin"] - 100.0) > 0.05:
            fails.append(f"{src}: margin ${p['margin']} != $100")
        if abs(p["notional"] - 1000.0) > 0.5:
            fails.append(f"{src}: notional ${p['notional']} != $1000")
        # 3.25% stop -> ~$32.50 risk = 1.6% of the $2,000 bank
        if abs(p["risk_usd"] - 32.5) > 0.5:
            fails.append(f"{src}: risk ${p['risk_usd']} != $32.50")

# ---- every dropped stream is refused (roster guard) ----
for gone in ("elite_star", "kr_premium", "pw_confirm", "pw_waking",
             "moonshot", "kr_strong", "elite_kr", "sniper2",
             "rerun"):
    if da.rank_candidates({gone: [cand(gone)]}, {}):
        fails.append(f"{gone} still seats in GEN 16")

# ---- user ladder order on equal merit ----
rk = da.rank_candidates(
    {"strig_kr": [cand("strig_kr", 98, sym="AUSDT")],
     "early_lane": [cand("early_lane", 98, sym="BUSDT")]}, {})
if not (rk and rk[0]["src"] == "early_lane"):
    fails.append("ladder broken (early_lane should lead)")

# ---- 20 seats fill, collateral is exactly the bank ----
st = {"balance": 2000.0, "open": [], "closed": []}
pool = {"early_movers": [cand("early_movers", 98, sym=f"M{i}USDT")
                         for i in range(28)]}
op, _ = da.try_open(st, da.rank_candidates(pool, {}), lambda s: 100.0)
# 19, not 20: each open pays a $0.55 entry fee, so the bank (and
# therefore the per-seat margin, recomputed live) shrinks as seats
# fill and the last seat no longer has full collateral. Honest
# behaviour — sizing follows the CURRENT balance, not the start.
if not (19 <= len(op) <= 20):
    fails.append(f"seat cap opened {len(op)}, expected 19-20")
marg = sum(p["margin"] for p in op)
heat = sum(p["risk_usd"] for p in op) / 2000.0
if not (1850.0 <= marg <= 2000.0):
    fails.append(f"full board should use ~the whole bank: ${marg:.0f}")
if heat > 0.35 + 1e-9:
    fails.append(f"heat {heat:.2%} over cap")

# ---- wide stops still bite the heat cap before 20 seats ----
st = {"balance": 2000.0, "open": [], "closed": []}
pool = {"best_zone": [cand("best_zone", 98, sym=f"W{i}USDT",
                           stop=93.0) for i in range(28)]}
op, _ = da.try_open(st, da.rank_candidates(pool, {}), lambda s: 100.0)
heat = sum(p["risk_usd"] for p in op) / 2000.0
if heat > 0.35 + 1e-9:
    fails.append(f"wide-stop heat {heat:.2%} over cap")
if len(op) >= 20:
    fails.append("7% stops should exhaust heat before 20 seats")

# ---- 10x liquidation guard: stops wider than 8% refused ----
st = {"balance": 2000.0, "open": [], "closed": []}
if da.try_open(st, da.rank_candidates(
        {"early_lane": [cand("early_lane", 98, stop=91.0)]}, {}),
        lambda s: 100.0)[0]:
    fails.append("9% stop should be refused at 10x (0.8/10)")

# ---- rails: -15% of day-start equity blocks; gain cap OFF ----
now = time.time()
st = {"balance": 1700.0, "open": [],
      "closed": [{"pnl": -300.0, "closed_at": now - 3600}]}
if da.try_open(st, da.rank_candidates(
        {"best_zone": [cand("best_zone", 98)]}, {}), lambda s: 100.0)[0]:
    fails.append("15% loss rail broken")
st = {"balance": 3500.0, "open": [],
      "closed": [{"pnl": 1500.0, "closed_at": now - 3600}]}
if not da.try_open(st, da.rank_candidates(
        {"best_zone": [cand("best_zone", 98)]}, {}), lambda s: 100.0)[0]:
    fails.append("gain cap should be OFF")

# ---- GEN 15 exit law survives: SL, TP, or the near-TP bank ----
assert da.NEAR_TP_PEAK == 0.85 and da.NEAR_TP_FADE == 0.60


def pos(src, **kw):
    d = {"symbol": "XUSDT", "base": "X", "side": "LONG",
         "entry": 100.0, "stop": 97.0, "tp1": 106.0, "tp2": None,
         "qty": 10.0, "notional": 1000.0, "lev": 10.0,
         "margin": 100.0, "risk0": 3.0, "risk_usd": 30.0,
         "src": src, "score": 80, "opened_at": time.time() - 3600,
         "fees": 0.0, "tp1_banked": 0.0, "be_set": False,
         "peak": 100.0}
    d.update(kw)
    return d


for src in sorted(FOUR):
    st = {"balance": 2000.0, "closed": [], "equity_hist": [],
          "open": [pos(src, peak=105.4)]}
    ev = da.manage(st, lambda s: 103.0)
    if not any("near-TP bank" in str(e[1].get("reason")) for e in ev):
        fails.append(f"{src}: near-TP bank did not fire")
    st = {"balance": 2000.0, "closed": [], "equity_hist": [],
          "open": [pos(src, tp1=104.0)]}
    ev = da.manage(st, lambda s: 104.2)
    if st["open"] or not any("TP1" in str(e[1].get("reason"))
                             for e in ev):
        fails.append(f"{src}: TP1 bank-100% broken")

# no time stop; stops never move
st = {"balance": 2000.0, "closed": [], "equity_hist": [],
      "open": [pos("best_zone", opened_at=time.time() - 200 * 3600)]}
ev = da.manage(st, lambda s: 101.0)
if not st["open"]:
    fails.append("time stop still closes trades")
st = {"balance": 2000.0, "closed": [], "equity_hist": [],
      "open": [pos("early_lane")]}
da.manage(st, lambda s: 105.0)
if st["open"] and abs(st["open"][0]["stop"] - 97.0) > 1e-9:
    fails.append("stop moved off the original SL")

print("GEN 16 sim:", "ALL PASS" if not fails else "FAILS:")
for f in fails:
    print("  x", f)
