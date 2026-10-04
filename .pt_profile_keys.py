"""Which klines does one Paper Trader load actually fetch? Wraps binance_client's
kline functions during an AppTest run and prints distinct (symbol, interval, limit)
keys, duplicates, cache misses and the per-interval universe sizes."""
import collections
import io
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
S = r"C:\Users\HAMMAD~1.JAW\AppData\Local\Temp\claude\F--Trading-Indicator\761b8a7a-ac27-4b70-b7c6-e365893054c0\scratchpad"
os.environ["STATE_DIR"] = os.path.join(S, "state0928")
os.chdir(r"F:\Trading Indicator")
import binance_client as bc

calls, misses, px_calls, px_misses = [], [], [], []
_gk, _gku, _px = bc.get_klines, bc._get_klines_uncached, bc.get_ticker_price


def gk(symbol, interval, limit=bc.config.KLINE_LIMIT):
    calls.append((symbol, interval, int(limit), time.perf_counter()))
    return _gk(symbol, interval, limit)


def gku(symbol, interval, limit=bc.config.KLINE_LIMIT):
    misses.append((symbol, interval, int(limit), time.perf_counter()))
    return _gku(symbol, interval, limit)


def px(symbol):
    px_calls.append(symbol)
    return _px(symbol)


bc.get_klines, bc._get_klines_uncached, bc.get_ticker_price = gk, gku, px
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("app.py", default_timeout=2400)
at.query_params["section"] = "\U0001F9EA Paper Trader"
t0 = time.perf_counter()
at.run()
print(f"run {time.perf_counter() - t0:.0f}s · get_klines calls {len(calls)} · uncached fetches {len(misses)} · ticker calls {len(px_calls)} (distinct {len(set(px_calls))})")
keys = collections.Counter((s, i, l) for s, i, l, _ in calls)
pairs = collections.Counter((s, i) for s, i, l, _ in calls)
mkeys = collections.Counter((s, i, l) for s, i, l, _ in misses)
mpairs = collections.Counter((s, i) for s, i, l, _ in misses)
print(f"distinct (symbol, interval, limit): {len(keys)} · distinct (symbol, interval): {len(pairs)}")
print(f"uncached: distinct keys {len(mkeys)} · distinct pairs {len(mpairs)} -> re-fetched pairs {sum(1 for v in mpairs.values() if v > 1)} (extra fetches {sum(v - 1 for v in mpairs.values() if v > 1)})")
by_iv = collections.defaultdict(set)
lim_iv = collections.defaultdict(collections.Counter)
for s, i, l in mkeys:
    by_iv[i].add(s)
    lim_iv[i][l] += 1
print("\nper interval: symbols fetched · limits used (uncached)")
for i in sorted(by_iv, key=lambda k: -len(by_iv[k])):
    print(f"  {i:>4}: {len(by_iv[i]):>4} symbols · limits {dict(lim_iv[i])}")
print("\nmost re-fetched pairs:", mpairs.most_common(8))
# when do the misses happen (time since start, per minute) -> TTL expiry pattern
mins = collections.Counter(int((t - t0) // 60) for _, _, _, t in misses)
print("uncached fetches per minute of the run:", dict(sorted(mins.items())))
syms = set(s for s, _ in pairs)
print(f"\nuniverse touched: {len(syms)} symbols; sample: {sorted(syms)[:12]}")
