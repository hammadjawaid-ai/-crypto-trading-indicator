"""One-shot patch — Paper Trader page speed (user 2026-10-04: "make it load faster,
nothing on the signals or the things we measure should be touched").
1. _worker_scan_file accepts the worker's published scan up to 40 min old (was 12;
   the worker cycle is ~17 min, so most loads fell back to a 150-coin page scan).
2. The six heavy scanner functions keep their bodies/caches, renamed *_raw with a
   _bucket key; thin same-name wrappers serve the board warmer's latest result and
   fall back to the raw call. Call sites are untouched.
3. A daemon thread (one per process) re-runs the same scanners with the page's
   default arguments every WARM_EVERY seconds. Early bursts hoisted the same way.
4. binance_client: kline cache cap 800 -> 3000 and shorter requests served from a
   fresh longer frame of the same symbol/interval (identical data).
Every anchor must match exactly once or nothing is written."""
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = "F:/Trading Indicator/"


def rep(src, old, new, label):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"ANCHOR {label!r} matched {n} times — aborting, nothing written")
    return src.replace(old, new, 1)


A = open(ROOT + "app.py", encoding="utf-8").read()
NAMES = ["compute_unified_best_picks", "compute_convergence_picks", "run_reversal_approach_scan",
         "run_pattern_scout", "forecast_market", "scan_breakouts"]
# pre-check: no attribute use (.clear() etc.) or re-binding of the names
for nm in NAMES:
    bad = re.findall(rf"\b{nm}\s*\.\s*\w+|\b{nm}\s*=(?!=)", A)
    if bad:
        raise SystemExit(f"{nm} has attribute/rebinding uses: {bad[:3]} — patch needs a look")

# 1) worker scan freshness
A = rep(A, "def _worker_scan_file(max_age: float = 720.0, min_n: int = 100):\n",
        "def _worker_scan_file(max_age: float = 2400.0, min_n: int = 100):\n", "worker scan max_age")
A = rep(A,
        '    """⚡ Read the 24/7 worker\'s freshly published unified scan off the\n',
        '    """⚡ Read the 24/7 worker\'s freshly published unified scan off the\n'
        '    shared disk. max_age 720 -> 2400 (user 2026-10-04 page-speed order):\n'
        '    the worker cycle is ~17 min (p95 24), so a 12-min limit sent most\n'
        '    page loads into a 150-coin page scan (~3 min). 40 min keeps the\n'
        '    worker as the single source; the board shows the scan age.\n',
        "worker scan docstring")

# 2) rename the heavy scanners to *_raw with a _bucket key
A = rep(A,
        "def compute_unified_best_picks(interval: str, scan_n: int = 50,\n"
        "                               _cache_version: int = 1) -> list:\n",
        "def _compute_unified_best_picks_raw(interval: str, scan_n: int = 50,\n"
        "                                    _cache_version: int = 1,\n"
        "                                    _bucket: int = 0) -> list:\n", "unified def")
A = rep(A,
        "def compute_convergence_picks(interval: str, scan_n: int = 50,\n"
        "                              _cache_version: int = 2) -> list:\n",
        "def _compute_convergence_picks_raw(interval: str, scan_n: int = 50,\n"
        "                                   _cache_version: int = 2,\n"
        "                                   _bucket: int = 0) -> list:\n", "convergence def")
A = rep(A,
        "def run_reversal_approach_scan(interval: str, scan_n: int = 30,\n"
        "                               _cache_version: int = 2) -> list:\n",
        "def _run_reversal_approach_scan_raw(interval: str, scan_n: int = 30,\n"
        "                                    _cache_version: int = 2,\n"
        "                                    _bucket: int = 0) -> list:\n", "approach def")
A = rep(A,
        "def run_pattern_scout(interval: str, scan_n: int = 50,\n"
        "                      _cache_version: int = 6) -> list:\n",
        "def _run_pattern_scout_raw(interval: str, scan_n: int = 50,\n"
        "                           _cache_version: int = 6,\n"
        "                           _bucket: int = 0) -> list:\n", "scout def")
A = rep(A,
        "def forecast_market(symbols: tuple[str, ...]) -> pd.DataFrame:\n",
        "def _forecast_market_raw(symbols: tuple[str, ...],\n"
        "                         _bucket: int = 0) -> pd.DataFrame:\n", "forecast def")
A = rep(A,
        "def scan_breakouts(symbols: tuple[str, ...],\n"
        "                   horizon: str = \"imminent\") -> tuple[pd.DataFrame, dict]:\n",
        "def _scan_breakouts_raw(symbols: tuple[str, ...],\n"
        "                        horizon: str = \"imminent\",\n"
        "                        _bucket: int = 0) -> tuple[pd.DataFrame, dict]:\n", "breakouts def")

# 3) early bursts: the nested radar body calls the hoisted, warmable function
A = rep(A, "                return _vb_radar.scan_15m_early(_syms, max_results=30)\n",
        "                return early_bursts_now(_syms)   # ⚡ warmable (same scan)\n", "early bursts call")

WARM = '''
# =====================================================================
# ⚡ BOARD WARMER (user 2026-10-04: "make it load faster ... nothing on
# the signals or the things we measure should be touched"). Profile of
# one Paper Trader load (.pt_profile.py: 504s) — 457s were Binance kline
# fetches re-running the scanner boards INSIDE the page request: unified
# picks 95s, elite picks 83s, best trades 65s, early bursts 35s, forecast
# 27s, breakouts 14s. Two causes: (a) the worker's published scan was
# accepted only when <12 min old while the worker cycle is ~17 min, so
# the page re-ran the 150-coin scan itself; (b) the page's own cached
# scans expire (300-600s) between its 270s auto-refreshes, so nearly
# every refresh recomputed them in the request.
# Fix: the SAME scanner functions with the SAME arguments, run by one
# daemon thread every WARM_EVERY seconds; the page reads the latest
# finished result from _WARM_STORE (a deep copy, so no caller can
# mutate it) and computes itself only when nothing warm exists — the
# first minutes after a restart, or a non-default timeframe / coin
# count. Board numbers are the same functions' outputs, at most
# WARM_EVERY old; the worker's own signal cadence is ~17 min.
# APP_BOARD_WARMER=0 disables the thread (tests / profiling).
# =====================================================================
import copy as _copy
import threading as _threading

WARM_EVERY = 240
WARM_MAX_AGE = 3 * WARM_EVERY
_WARM_STORE: dict = {}
_WARM_STATUS: dict = {"last_sweep": None, "sweep_s": None, "jobs": {},
                      "errors": {}, "sweeps": 0}
_WARM_STATUS_FILE = str(config.state_path(".app_warm.json"))


def _warm_get(key):
    hit = _WARM_STORE.get(key)
    if hit is not None and time.time() - hit[0] <= WARM_MAX_AGE:
        try:
            return _copy.deepcopy(hit[1])
        except Exception:
            return hit[1]
    return None


def _warm_put(key, val) -> None:
    _WARM_STORE[key] = (time.time(), val)


def compute_unified_best_picks(interval: str, scan_n: int = 50,
                               _cache_version: int = 1) -> list:
    w = _warm_get(("unified", interval, int(scan_n)))
    if w is not None:
        return w
    return _compute_unified_best_picks_raw(interval, scan_n, _cache_version)


def compute_convergence_picks(interval: str, scan_n: int = 50,
                              _cache_version: int = 2) -> list:
    w = _warm_get(("convergence", interval, int(scan_n)))
    if w is not None:
        return w
    return _compute_convergence_picks_raw(interval, scan_n, _cache_version)


def run_reversal_approach_scan(interval: str, scan_n: int = 30,
                               _cache_version: int = 2) -> list:
    w = _warm_get(("approach", interval, int(scan_n)))
    if w is not None:
        return w
    return _run_reversal_approach_scan_raw(interval, scan_n, _cache_version)


def run_pattern_scout(interval: str, scan_n: int = 50,
                      _cache_version: int = 6) -> list:
    w = _warm_get(("scout", interval, int(scan_n)))
    if w is not None:
        return w
    return _run_pattern_scout_raw(interval, scan_n, _cache_version)


def forecast_market(symbols: tuple[str, ...]) -> pd.DataFrame:
    w = _warm_get(("forecast", tuple(symbols)))
    if w is not None:
        return w
    return _forecast_market_raw(tuple(symbols))


def scan_breakouts(symbols: tuple[str, ...],
                   horizon: str = "imminent") -> tuple[pd.DataFrame, dict]:
    w = _warm_get(("breakouts", tuple(symbols), horizon))
    if w is not None:
        return w
    return _scan_breakouts_raw(tuple(symbols), horizon)


@st.cache_data(ttl=60, show_spinner=False)
def _early_bursts_raw(syms: tuple, _bust: int = 0, _bucket: int = 0) -> list:
    import velocity_burst as _vb_w
    return _vb_w.scan_15m_early(list(syms), max_results=30)


def early_bursts_now(syms) -> list:
    """The 🔥 Early Burst Radar scan (15m, top-100): warm result if the
    warmer has one, else the same scan on the given symbols."""
    w = _warm_get(("early_bursts",))
    if w is not None:
        return w
    return _early_bursts_raw(tuple(syms), int(time.time() // 60))


def _warm_universe():
    """Exactly the symbol tuples the page builds with its defaults:
    top_n slider default 100 -> head(40) for forecast/breakouts; the
    early-burst radar's top-110 -> first 100."""
    tops = load_top_symbols(100)
    syms40 = tuple(tops["symbol"].head(40))
    try:
        syms100 = tuple(binance_client.get_top_symbols(110)["symbol"]
                        .tolist()[:100])
    except Exception:
        syms100 = tuple(tops["symbol"].head(100))
    return syms40, syms100


def _warm_sweep() -> None:
    b = int(time.time() // WARM_EVERY)
    tf = config.DEFAULT_TIMEFRAME
    syms40, syms100 = _warm_universe()
    # dependency order: the unified board calls convergence / scout /
    # approach through the wrappers above, so those are warmed first.
    jobs = [
        (("approach", tf, 30), lambda: _run_reversal_approach_scan_raw(tf, 30, _bucket=b)),
        (("approach", tf, 100), lambda: _run_reversal_approach_scan_raw(tf, 100, _bucket=b)),
        (("scout", tf, 50), lambda: _run_pattern_scout_raw(tf, 50, _bucket=b)),
        (("convergence", tf, 50), lambda: _compute_convergence_picks_raw(tf, 50, _bucket=b)),
        (("convergence", "1h", 50), lambda: _compute_convergence_picks_raw("1h", 50, _bucket=b)),
        (("unified", tf, 50), lambda: _compute_unified_best_picks_raw(tf, 50, _bucket=b)),
        (("forecast", syms40), lambda: _forecast_market_raw(syms40, _bucket=b)),
        (("breakouts", syms40, "imminent"), lambda: _scan_breakouts_raw(syms40, "imminent", _bucket=b)),
        (("early_bursts",), lambda: _early_bursts_raw(syms100, 0, _bucket=b)),
    ]
    t_all = time.time()
    durs, errs = {}, {}
    for key, fn in jobs:
        t0 = time.time()
        try:
            _warm_put(key, fn())
            durs[str(key)] = round(time.time() - t0, 1)
        except Exception as exc:
            errs[str(key)] = str(exc)[:160]
    _WARM_STATUS.update(last_sweep=time.time(),
                        sweep_s=round(time.time() - t_all, 1),
                        jobs=durs, errors=errs,
                        sweeps=int(_WARM_STATUS.get("sweeps") or 0) + 1)
    try:
        with open(_WARM_STATUS_FILE, "w", encoding="utf-8") as _f:
            json.dump(_WARM_STATUS, _f)
    except Exception:
        pass


def _warm_loop() -> None:
    while True:
        t0 = time.time()
        try:
            _warm_sweep()
        except Exception as exc:
            print("board warmer error:", exc, flush=True)
        time.sleep(max(15.0, WARM_EVERY - (time.time() - t0)))


@st.cache_resource(show_spinner=False)
def _start_board_warmer() -> bool:
    _threading.Thread(target=_warm_loop, name="board-warmer",
                      daemon=True).start()
    return True


if os.environ.get("APP_BOARD_WARMER", "1") != "0":
    try:
        _start_board_warmer()
    except Exception as _bw_exc:
        print("board warmer start error:", _bw_exc, flush=True)


def _warm_caption() -> str:
    """One line for the boards: how fresh the pre-computed scans are."""
    ls = _WARM_STATUS.get("last_sweep")
    if not ls:
        return ("⚡ boards computing in the page this time — the background "
                "warmer has not finished its first sweep since the app "
                "restarted.")
    return (f"⚡ scanner boards pre-computed {(time.time() - ls) / 60:.0f} min "
            f"ago in {_WARM_STATUS.get('sweep_s')}s (refreshed every "
            f"{WARM_EVERY // 60} min; worker signal cadence unchanged).")


def _worker_scan_age_min():
    try:
        with open(str(config.state_path(".last_scan.json")),
                  encoding="utf-8") as _f:
            return (time.time() - float(json.load(_f).get("ts") or 0)) / 60
    except Exception:
        return None


'''
A = rep(A, "_qp = st.query_params\n", WARM + "_qp = st.query_params\n", "warm block before query params")

# board captions: worker scan age + warmer freshness on the ELITE CONVICTION board
A = rep(A,
        '                "(85+, ≥2 strong) · 🟢 STRONG (80+). Cached 5 min.")\n',
        '                "(85+, ≥2 strong) · 🟢 STRONG (80+). Cached 5 min.")\n'
        '            _wsa = _worker_scan_age_min()\n'
        '            st.caption((f"🤖 scan published by the 24/7 worker {_wsa:.0f} min "\n'
        '                        f"ago (accepted up to 40 min; the worker cycle is "\n'
        '                        f"~17 min)." if _wsa is not None and _wsa <= 40\n'
        '                        else "⚠️ worker scan older than 40 min — this load "\n'
        '                        "ran the 150-coin scan in the page.")\n'
        '                       + " " + _warm_caption())\n',
        "elite board caption")

# =========================== binance_client.py ===========================
B = open(ROOT + "binance_client.py", encoding="utf-8").read()
B = rep(B, "def _cache_put(cache: dict, key, val, cap: int = 800) -> None:\n",
        "def _cache_put(cache: dict, key, val, cap: int = 3000) -> None:\n", "cache cap")
B = rep(B,
        "    key = (symbol, interval, int(limit))\n"
        "    hit = _cache_get(_KL_CACHE, key, _KL_TTL)\n"
        "    if hit is not None:\n"
        "        return hit.copy()\n"
        "    df = _get_klines_uncached(symbol, interval, limit)\n",
        "    key = (symbol, interval, int(limit))\n"
        "    hit = _cache_get(_KL_CACHE, key, _KL_TTL)\n"
        "    if hit is not None:\n"
        "        return hit.copy()\n"
        "    # ⚡ page-speed (2026-10-04): a shorter request is served from a\n"
        "    # FRESH longer frame of the same symbol/interval — the last N\n"
        "    # candles of a 300-candle fetch are the same candles a 100-candle\n"
        "    # fetch returns, so callers asking for different limits no longer\n"
        "    # pay a second round trip.\n"
        "    _best = None\n"
        "    _now = time.time()\n"
        "    for (_s, _i, _l), (_ts, _df) in list(_KL_CACHE.items()):\n"
        "        if (_s == symbol and _i == interval and _l > int(limit)\n"
        "                and _now - _ts <= _KL_TTL and len(_df) >= int(limit)\n"
        "                and (_best is None or _l < _best[0])):\n"
        "            _best = (_l, _df)\n"
        "    if _best is not None:\n"
        "        return _best[1].tail(int(limit)).copy()\n"
        "    df = _get_klines_uncached(symbol, interval, limit)\n",
        "serve from longer frame")

for path, s in (("app.py", A), ("binance_client.py", B)):
    with open(ROOT + path, "w", encoding="utf-8", newline="") as f:
        f.write(s)
print("patched app.py + binance_client.py")
