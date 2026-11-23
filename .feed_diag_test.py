"""🩺 FEED DIAGNOSTIC — the counters tell perp from spot from Bybit, record the
last futures error, never send a request of their own and never change a
reading: a blocked futures host and an open one on a fake session, the same
frames and prices with the counters switched off, worker + admin wiring."""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import binance_client as bc

fails = []
bc.time.sleep = lambda s: None            # the client's own back-off sleeps, not needed here
SPOT_K = [[1790000000000 + i * 3600000, "100.01", "101.02", "99.03", "100.55", "10", 0, "1000", 5, "4", "400", "0"] for i in range(3)]
PERP_K = [[1790000000000 + i * 3600000, "100.1", "101.1", "99.1", "100.6", "90", 0, "9000", 50, "40", "4000", "0"] for i in range(3)]
EXINFO = {"symbols": [{"symbol": "BTCUSDT", "contractType": "PERPETUAL", "status": "TRADING", "quoteAsset": "USDT"}]}
calls = []


class R:
    def __init__(self, code, body):
        self.status_code, self._b = code, body

    def json(self):
        return self._b


def session(futures_open):
    def get(url, params=None, timeout=None):
        calls.append(url)
        fut = "fapi.binance.com" in url
        if fut and not futures_open:
            return R(451, {})
        if url.endswith("/fapi/v1/exchangeInfo"):
            return R(200, EXINFO)
        if url.endswith("/klines"):
            return R(200, PERP_K if fut else SPOT_K)
        if url.endswith("/ticker/price"):
            if params:
                return R(200, {"symbol": params["symbol"], "price": "100.6" if fut else "100.55"})
            return R(200, [{"symbol": "BTCUSDT", "price": "100.6" if fut else "100.55"}])
        return R(404, {})
    return get


def reset():
    bc._FUT_SET, bc._FUT_TS, bc._PX_PRIME_TS, bc._FUT_RETRY_TS = set(), 0.0, 0.0, 0.0
    bc._KL_CACHE.clear(); bc._PX_CACHE.clear(); calls.clear()
    for k in bc._FEED:
        bc._FEED[k] = "" if k == "fut_last_err" else 0


# 1) futures host refuses (what a blocked server sees): spot answers, the counters say so
reset(); bc._session.get = session(False)
df_b = bc._get_klines_uncached("BTCUSDT", "1h", 3)
px_b = bc.get_ticker_price("BTCUSDT")
bc._PX_CACHE.clear(); bc.prime_prices()
st = bc.feed_status()
if float(df_b["close"].iloc[-1]) != 100.55 or px_b != 100.55:
    fails.append("blocked: the reading must be the spot one")
if (st["kl_perp"], st["kl_spot"], st["px_perp"], st["px_spot"]) != (0, 1, 0, 1):
    fails.append(f"blocked: counters {st}")
if st["fut_ok"] != 0 or st["fut_fail"] != 1 or "451" not in st["fut_last_err"] or st["perp_symbols"] != 0:
    fails.append(f"blocked: one futures failure must be recorded, then the back-off {st}")
if st["prime_perp_last"] != 0:
    fails.append("blocked: bulk refresh must report 0 perp prices")
line_b = bc.feed_line(st)
# 1b) ⏳ the back-off (2026-11-23): a refused futures host is asked ONCE, then left alone for 5 minutes, however
# many candles and prices are fetched; after the 5 minutes it is asked once more. Before, every fetch asked.
n_fut = sum("fapi.binance.com" in u for u in calls)
for _s in ["BTCUSDT", "ETHUSDT", "SOLUSDT"] * 100:
    bc.has_perp(_s)
bc._KL_CACHE.clear(); bc._PX_CACHE.clear(); bc._PX_PRIME_TS = 0.0
bc._get_klines_uncached("ETHUSDT", "1h", 3); bc.get_ticker_price("ETHUSDT"); bc.prime_prices()
if n_fut != 1 or sum("fapi.binance.com" in u for u in calls) != 1:
    fails.append(f"back-off: {sum('fapi.binance.com' in u for u in calls)} futures requests while the host refuses (want 1)")
bc._FUT_RETRY_TS = bc.time.time() - 1.0                 # the 5 minutes are over
bc.has_perp("BTCUSDT"); bc.has_perp("ETHUSDT")
if sum("fapi.binance.com" in u for u in calls) != 2:
    fails.append("back-off: the futures host must be asked again once after the wait, and only once")

# 2) futures host answers: perp readings, counted as perp
reset(); bc._session.get = session(True)
df_o = bc._get_klines_uncached("BTCUSDT", "1h", 3)
px_o = bc.get_ticker_price("BTCUSDT")
bc._PX_CACHE.clear(); bc.prime_prices()
st = bc.feed_status()
if float(df_o["close"].iloc[-1]) != 100.6 or px_o != 100.6:
    fails.append("open: the reading must be the perp one")
if (st["kl_perp"], st["kl_spot"], st["px_perp"], st["px_spot"]) != (1, 0, 1, 0):
    fails.append(f"open: counters {st}")
if st["fut_fail"] != 0 or st["fut_ok"] < 3 or st["perp_symbols"] != 1 or st["prime_perp_last"] != 1:
    fails.append(f"open: futures success not recorded {st}")
line_o = bc.feed_line(st)

# 3) reading the status sends nothing
n0 = len(calls)
bc.feed_status(); bc.feed_line()
if len(calls) != n0:
    fails.append("feed_status / feed_line must not send a request")

# 4) no behaviour change: the same frames and prices with the counters switched off
_note = bc._feed_note
bc._feed_note = lambda *a, **k: None
for opened, df_ref, px_ref in ((False, df_b, px_b), (True, df_o, px_o)):
    reset(); bc._session.get = session(opened)
    if not bc._get_klines_uncached("BTCUSDT", "1h", 3).equals(df_ref) or bc.get_ticker_price("BTCUSDT") != px_ref:
        fails.append(f"readings differ with the counters off (futures_open={opened})")
bc._feed_note = _note

# 5) a counter that breaks can never break a reading
reset(); bc._session.get = session(True)
_lock = bc._FEED_LOCK
bc._FEED_LOCK = None                       # `with None` raises inside _feed_note
try:
    if float(bc._get_klines_uncached("BTCUSDT", "1h", 3)["close"].iloc[-1]) != 100.6:
        fails.append("reading changed when the counter failed")
except Exception as exc:
    fails.append(f"a failing counter reached the caller: {exc}")
bc._FEED_LOCK = _lock

# 6) wiring: the worker logs after the scan, the admin panel shows both processes
W = open(os.path.join(HERE, "agent_worker.py"), encoding="utf-8").read()
i_s, i_d = W.find("r = scan_core.scan_all("), W.find('print("🩺 feed: " + binance_client.feed_line(_fd), flush=True)')
if not (0 < i_s < i_d) or i_d - i_s > 1200 or '.feed_status.json' not in W[i_s:i_d + 1200]:
    fails.append("worker feed hook missing or misplaced")
# 6b) the hook must not read a name that is a LOCAL of cycle() bound somewhere else in it. The first build
# called _os.replace(): cycle() has `for _os in …` far below, so _os was an unbound local at the hook and the status
# file stayed as .feed_status.json.tmp (seen in the 23 Nov backup). Names the hook binds itself are fine.
import ast
import textwrap


def hook_ghosts(src):
    a, b = src.find("    if time.time() - _FEED_DIAG[\"t\"] >= 3600:"), src.find("    sst1, takenow = r[\"sst1\"], r[\"takenow\"]")
    blk = ast.parse(textwrap.dedent(src[a:b]))
    loads, stores = set(), set()
    for n in ast.walk(blk):
        if isinstance(n, ast.Name):
            (stores if isinstance(n.ctx, ast.Store) else loads).add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            stores.update((x.asname or x.name).split(".")[0] for x in n.names)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            stores.add(n.name)
        elif isinstance(n, ast.withitem) and n.optional_vars is not None:
            stores.update(t.id for t in ast.walk(n.optional_vars) if isinstance(t, ast.Name))
    cyc = [c for c in compile(src, "agent_worker.py", "exec").co_consts if getattr(c, "co_name", "") == "cycle"][0]
    return sorted((loads - stores) & set(cyc.co_varnames))


if hook_ghosts(W):
    fails.append(f"the worker hook reads cycle() locals it does not bind itself: {hook_ghosts(W)}")
if hook_ghosts(W.replace("_fd_os.replace(", "_os.replace(")) != ["_os"]:
    fails.append("the local-name check no longer catches the _os mistake")
A = open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
i_m, i_f = A.find('if _mig_token and _qp.get("admin") == _mig_token:'), A.find('st.text("this page: " + binance_client.feed_line())')
if not (0 < i_m < i_f) or A[i_m:i_f].count("\nst.") or A[i_m:i_f].count("\nif "):
    fails.append("admin feed lines missing or outside the admin-only block")

print("BLOCKED:", line_b)
print("OPEN:   ", line_o)
print("FEED DIAGNOSTIC:", "ALL PASS" if not fails else fails)
