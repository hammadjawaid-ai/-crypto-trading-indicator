"""Page-speed patch tests: wrappers + raw functions wired, call sites untouched,
warm store semantics (freshness, deep copy), worker-scan freshness window,
binance_client serve-from-longer-frame, ghost scan of app.py names."""
import ast
import io
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"F:\Trading Indicator")
A = open(r"F:\Trading Indicator\app.py", encoding="utf-8").read()
fails = []
tree = ast.parse(A)
defs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
NAMES = ["compute_unified_best_picks", "compute_convergence_picks", "run_reversal_approach_scan",
         "run_pattern_scout", "forecast_market", "scan_breakouts"]
for nm in NAMES:
    raw = f"_{nm}_raw"
    if nm not in defs or raw not in defs:
        fails.append(f"missing wrapper/raw for {nm}")
        continue
    if "_bucket" not in [a.arg for a in defs[raw].args.args]:
        fails.append(f"{raw} has no _bucket key")
    decos = [ast.unparse(d) for d in defs[raw].decorator_list]
    if not any("cache_data" in d for d in decos):
        fails.append(f"{raw} lost its st.cache_data decorator")
    if any("cache_data" in ast.unparse(d) for d in defs[nm].decorator_list):
        fails.append(f"wrapper {nm} must not be cache_data'd (it must see the warm store)")
    # wrapper signature mirrors the original public one
    _pub = lambda fn: [a.arg for a in fn.args.args if not a.arg.startswith("_")]
    if _pub(defs[nm]) != _pub(defs[raw]) or "_bucket" in [a.arg for a in defs[nm].args.args]:
        fails.append(f"{nm} wrapper signature drifted: {_pub(defs[nm])} vs {_pub(defs[raw])}")
for need in ("def _early_bursts_raw(", "def early_bursts_now(", "def _warm_sweep(", "def _warm_loop(",
             "def _start_board_warmer(", "return early_bursts_now(_syms)", "def _worker_scan_file(max_age: float = 2400.0",
             'os.environ.get("APP_BOARD_WARMER", "1") != "0"', "_worker_scan_age_min()", "_warm_caption()"):
    if need not in A:
        fails.append(f"missing: {need}")
if "_vb_radar.scan_15m_early(" in A:
    fails.append("the nested early-burst scan still bypasses the warmer")
# call sites still call the public names (count unchanged vs the pre-patch census)
import re
counts = {nm: len(re.findall(rf"(?<![\w_]){nm}\(", A)) for nm in NAMES}
expect_min = {"compute_unified_best_picks": 2, "compute_convergence_picks": 6, "run_reversal_approach_scan": 6,
              "run_pattern_scout": 4, "forecast_market": 3, "scan_breakouts": 5}
for nm, c in counts.items():
    if c < expect_min[nm]:
        fails.append(f"{nm} call sites look reduced: {c}")
# the warm sweep covers every key the wrappers read
for key in ('("approach", tf, 30)', '("approach", tf, 100)', '("scout", tf, 50)', '("convergence", tf, 50)',
            '("convergence", "1h", 50)', '("unified", tf, 50)', '("forecast", syms40)', '("breakouts", syms40, "imminent")', '("early_bursts",)'):
    if key not in A:
        fails.append(f"warm sweep missing job {key}")

# ---- warm store semantics, extracted ----
want = {"_warm_get", "_warm_put", "WARM_EVERY", "WARM_MAX_AGE", "_WARM_STORE"}
body = []
for n in tree.body:
    if isinstance(n, ast.FunctionDef) and n.name in want:
        body.append(n)
    elif isinstance(n, (ast.Assign, ast.AnnAssign)):
        t = n.targets[0] if isinstance(n, ast.Assign) else n.target
        if isinstance(t, ast.Name) and t.id in want:
            body.append(n)
import copy
ns = {"time": time, "_copy": copy}
exec(compile(ast.Module(body=body, type_ignores=[]), "warm", "exec"), ns)
ns["_warm_put"](("k",), [{"a": 1}])
v = ns["_warm_get"](("k",))
if v != [{"a": 1}]:
    fails.append("warm get/put broken")
v.append("x")
if ns["_warm_get"](("k",)) != [{"a": 1}]:
    fails.append("warm store must hand out copies (caller mutation leaked)")
ns["_WARM_STORE"][("old",)] = (time.time() - ns["WARM_MAX_AGE"] - 1, [1])
if ns["_warm_get"](("old",)) is not None:
    fails.append("stale warm entry served")
if ns["_warm_get"](("none",)) is not None:
    fails.append("missing key must return None")
if not (ns["WARM_MAX_AGE"] >= 2 * ns["WARM_EVERY"]):
    fails.append("WARM_MAX_AGE must outlive at least two sweeps")

# ---- binance_client: shorter request served from a fresh longer frame ----
import pandas as pd
import binance_client as bc
bc._KL_CACHE.clear()
idx = pd.date_range("2026-10-01", periods=300, freq="15min", tz="UTC")
big = pd.DataFrame({"open": range(300), "high": range(300), "low": range(300), "close": range(300), "volume": 1.0}, index=idx)
bc._cache_put(bc._KL_CACHE, ("TESTUSDT", "15m", 300), big)
_orig = bc._get_klines_uncached
bc._get_klines_uncached = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network must not be touched"))
try:
    small = bc.get_klines("TESTUSDT", "15m", 100)
    if len(small) != 100 or int(small["close"].iloc[-1]) != 299 or int(small["close"].iloc[0]) != 200:
        fails.append("served slice is not the last 100 candles")
    try:
        bc.get_klines("TESTUSDT", "15m", 400)   # longer than anything cached -> must fetch
        fails.append("a longer request was served from a shorter frame")
    except RuntimeError:
        pass
    try:
        bc.get_klines("TESTUSDT", "1h", 100)    # other interval -> must fetch
        fails.append("another interval was served from the 15m frame")
    except RuntimeError:
        pass
finally:
    bc._get_klines_uncached = _orig
    bc._KL_CACHE.clear()
src_bc = open(r"F:\Trading Indicator\binance_client.py", encoding="utf-8").read()
# prime_prices fills the price cache from one payload and is TTL-guarded
bc._PX_CACHE.clear(); bc._PX_PRIME_TS = 0.0
_og = bc._get
bc._get = lambda path, params=None, max_attempts=4: [{"symbol": "AAAUSDT", "price": "1.5"}, {"symbol": "BBBUSDT", "price": "2.5"}, {"symbol": "X", "price": "bad"}]
try:
    if bc.prime_prices(["AAAUSDT", "BBBUSDT"]) != 2 or bc.get_ticker_price("BBBUSDT") != 2.5:
        fails.append("prime_prices did not fill the price cache")
    bc._get = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("primed again inside the TTL"))
    if bc.prime_prices() != 0:
        fails.append("prime_prices must be TTL-guarded")
    if bc.get_ticker_price("AAAUSDT") != 1.5:
        fails.append("primed price not served from cache")
except RuntimeError as exc:
    fails.append(str(exc))
finally:
    bc._get = _og; bc._PX_CACHE.clear(); bc._PX_PRIME_TS = 0.0
for need in ("binance_client.prime_prices([_r.get(\"symbol\") for _r in _al_rows])", "binance_client.prime_prices()", "_edge_mine_cached(int(time.time() // 600))", "def _edge_mine_cached("):
    if need not in A:
        fails.append(f"patch-2 wiring missing: {need}")
if "_rep = _em.mine()" in A:
    fails.append("edge miner still mines on every load")
if "cap: int = 1500" not in src_bc:
    fails.append("kline cache cap not raised")

# ---- ghost scan of app.py (names used but never defined) ----
import builtins
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
print("PAGE SPEED:", "ALL PASS" if not fails else fails)
