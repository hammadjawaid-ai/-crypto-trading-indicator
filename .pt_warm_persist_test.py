"""Paper Trader warm-store persistence (2026-10-11): the disk helpers run
standalone from app.py's AST; the wiring is checked by anchors."""
import ast
import io
import os
import pickle
import sys
import tempfile
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"F:\Trading Indicator"
A = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
fails = []
ns = {"time": time, "os": os}
for n in ast.parse(A).body:
    if isinstance(n, ast.FunctionDef) and n.name in ("_warm_disk_save", "_warm_disk_load"):
        exec(compile(ast.Module(body=[n], type_ignores=[]), n.name, "exec"), ns)
save, load = ns["_warm_disk_save"], ns["_warm_disk_load"]

import shutil
_D = os.path.join(ROOT, '.tmp_warm_test')
shutil.rmtree(_D, ignore_errors=True); os.makedirs(_D)
class _Dir:
    def __enter__(self): return _D
    def __exit__(self, *a): shutil.rmtree(_D, ignore_errors=True)
with _Dir() as d:   # project-local: the sandbox temp folder rejects os.replace
    p = os.path.join(d, ".app_warm_store.pkl")
    now = 1_800_000_000.0
    store = {("unified", "4h", 50): (now - 600, [{"symbol": "AAVEUSDT", "score": 91.5}]),
             ("approach", "4h", 30): (now - 2400, ["stale"]),
             ("forecast", ("BTCUSDT", "ETHUSDT")): (now - 60, {"BTCUSDT": {"dir": "up"}}),
             ("broken",): "not a pair"}
    if not save(store, p, now=now):
        fails.append("save returned False")
    if os.path.exists(p + ".tmp"):
        fails.append("tmp file left behind (write not atomic)")
    got, info = load(p, 1800, now=now)
    if set(got) != {("unified", "4h", 50), ("forecast", ("BTCUSDT", "ETHUSDT"))}:
        fails.append(f"restore kept the wrong keys: {sorted(map(str, got))}")
    if got.get(("unified", "4h", 50)) != (now - 600, [{"symbol": "AAVEUSDT", "score": 91.5}]):
        fails.append("restored value is not the exact (ts, result) pair")
    if info.get("restored") != 2 or info.get("dropped") != 2 or info.get("saved") != now:
        fails.append(f"restore info wrong: {info}")
    # a later process: everything aged past max_age -> nothing restored
    got2, info2 = load(p, 1800, now=now + 1800)
    if got2 or info2.get("restored") != 0:
        fails.append("stale entries must not be restored")
    # future-dated garbage is dropped too
    save({("x",): (now + 999, 1)}, p, now=now)
    if load(p, 1800, now=now)[0]:
        fails.append("future-stamped entry restored")
    # missing file / corrupt file never raise
    g3, i3 = load(os.path.join(d, "nope.pkl"), 1800, now=now)
    if g3 != {} or i3.get("restored") != 0 or "error" in i3:
        fails.append(f"missing file must be a clean empty restore: {i3}")
    with open(p, "wb") as f:
        f.write(b"garbage")
    g4, i4 = load(p, 1800, now=now)
    if g4 != {} or "error" not in i4:
        fails.append(f"corrupt file must be an empty restore with an error note: {i4}")
    # save never raises on an unwritable path
    if save({}, os.path.join(d, "no_dir", "x.pkl")) is not False:
        fails.append("save on a bad path must return False")

# wiring
i_file = A.find('_WARM_DISK_FILE = str(config.state_path(".app_warm_store.pkl"))')
i_save = A.find("def _warm_disk_save(")
i_load = A.find("def _warm_disk_load(")
i_state = A.find("def _warm_state() -> dict:")
i_seed = A.find("_store, _info = _warm_disk_load(_WARM_DISK_FILE, 6 * 3600)")
i_store = A.find('_WARM_STORE: dict = _warm_state()["store"]')
i_sweep_save = A.find("saved=_warm_disk_save(_WARM_STORE, _WARM_DISK_FILE))")
i_cap = A.find("scanner boards restored from the last sweep before the")
if not (0 < i_file < i_save < i_load < i_state < i_seed < i_store < i_sweep_save < i_cap):
    fails.append(f"wiring order wrong: file {i_file} save {i_save} load {i_load} state {i_state} seed {i_seed} store {i_store} sweep {i_sweep_save} caption {i_cap}")
if 'or not _WARM_STATUS.get("last_sweep")):' not in A:
    fails.append("restored boards must stay in service until the first in-process sweep")
if "fall back to the status file the sweep writes" in A:
    fails.append("the misleading status-file caption fallback is still there")
for need in ('"disk": _info}}', 'WARM_MAX_AGE = 3 * WARM_EVERY', "pickle.HIGHEST_PROTOCOL", "os.replace(tmp, path)"):
    if need not in A:
        fails.append(f"missing: {need}")
# scanner bodies untouched: the raw functions and the sweep's job list are byte-identical to HEAD
import subprocess
head = subprocess.run(["git", "show", "HEAD:app.py"], capture_output=True, cwd=ROOT).stdout.decode("utf-8")
def block(src, start, end):
    i = src.find(start); j = src.find(end, i)
    return src[i:j] if i >= 0 and j >= 0 else None
jobs_now, jobs_head = block(A, "    jobs = [\n", "    t_all = time.time()"), block(head, "    jobs = [\n", "    t_all = time.time()")
# 2026-10-22 (speed round 3): the ONE sanctioned addition is the market-scan job at the top of the list
_mkt_line = '        (("market", tf, "futures"), lambda: _warm_market(tf, b)),\n'
if jobs_now:
    jobs_now = jobs_now.replace(_mkt_line, "")
if jobs_head:
    jobs_head = jobs_head.replace(_mkt_line, "")   # HEAD may still carry the 90e9329 job line
if jobs_now != jobs_head or jobs_now is None:
    fails.append("the warmer's job list changed")
for fn in ("_compute_unified_best_picks_raw", "_compute_convergence_picks_raw", "_run_reversal_approach_scan_raw",
           "_run_pattern_scout_raw", "_forecast_market_raw", "_scan_breakouts_raw", "_early_bursts_raw"):
    a, b = block(A, f"def {fn}(", "\n\n\n"), block(head, f"def {fn}(", "\n\n\n")
    if a != b or a is None:
        fails.append(f"scanner body changed: {fn}")
print("WARM PERSIST:", "ALL PASS" if not fails else fails)
