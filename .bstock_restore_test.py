"""Guard — 🏦 B-STOCKS BACK (2026-11-10, user: "bring B stocks and stock back to the system on elite conviction and
rest of the streams should also pick them up"). Checks: the switches (phone ON, universe ON, money gate still
CLOSED), the universe shape on a synthetic ticker feed (top-n crypto + liquid tokenized names appended, illiquid
ones left out, the crypto-only shape when the switch is off), the set's new tickers and no real crypto in it,
the worker's quiet rule reads the phone switch, the demo money gate still refuses a tokenized seat. No network.
Run: .venv\\Scripts\\python.exe .bstock_restore_test.py
"""
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.environ["WORKER_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="bstock_"), "worker.db")
import config              # noqa: E402
import binance_client as bc  # noqa: E402
import demo_account as da  # noqa: E402

PASS, FAIL = 0, []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL.append(name)
        print(f"  ❌ {name} {detail}")


print("1. switches")
check("phone ON (BSTOCK_BUZZ)", config.BSTOCK_BUZZ is True)
check("universe ON (BSTOCK_IN_UNIVERSE) with a volume floor", config.BSTOCK_IN_UNIVERSE is True and config.BSTOCK_MIN_QV >= 1_000_000)
check("money gate OPEN on his word (BSTOCK_VALIDATED) — demo / GEN 19 seats", config.BSTOCK_VALIDATED is True)
print("2. the set")
for s in ("TQQQBUSDT", "MRVLBUSDT", "CRWVBUSDT", "TSMBUSDT", "SNDKBUSDT", "NVDABUSDT"):
    check(f"{s} tagged tokenized", s in config.TOKENIZED_STOCKS)
for s in ("ARBUSDT", "BNBUSDT", "SHIBUSDT", "TRBUSDT", "CKBUSDT", "DGBUSDT"):
    check(f"{s} is crypto, not in the set", s not in config.TOKENIZED_STOCKS)
print("3. the universe on a synthetic feed")
feed = [
    {"symbol": "BTCUSDT", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": "900", "highPrice": "1", "lowPrice": "1"},
    {"symbol": "ETHUSDT", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": "800", "highPrice": "1", "lowPrice": "1"},
    {"symbol": "SNDKBUSDT", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": str(5_000_000.0), "highPrice": "1", "lowPrice": "1"},
    {"symbol": "SOLUSDT", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": "700", "highPrice": "1", "lowPrice": "1"},
    {"symbol": "ARBUSDT", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": "600", "highPrice": "1", "lowPrice": "1"},
    {"symbol": "COINBUSDT", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": str(500_000.0), "highPrice": "1", "lowPrice": "1"},
    {"symbol": "TQQQBUSDT", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": str(3_000_000.0), "highPrice": "1", "lowPrice": "1"},
    {"symbol": "USDCUSDT", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": "99999", "highPrice": "1", "lowPrice": "1"},
    {"symbol": "BTCUPUSDT", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": "99999", "highPrice": "1", "lowPrice": "1"},
    {"symbol": "ETHBTC", "lastPrice": "1", "priceChangePercent": "0", "quoteVolume": "99999", "highPrice": "1", "lowPrice": "1"},
]
bc._get = lambda path, **kw: feed   # no network
u = bc.get_top_symbols(3)["symbol"].tolist()
check("top-3 crypto by volume first, in order", u[:3] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"], u)
check("liquid tokenized names appended alongside (≥ floor)", set(u[3:]) == {"SNDKBUSDT", "TQQQBUSDT"}, u)
check("the illiquid tokenized name is left out; ARB (crypto, rank 5) is not pulled in", "COINBUSDT" not in u and "ARBUSDT" not in u, u)
check("stables / leveraged / non-USDT dropped as before", not ({"USDCUSDT", "BTCUPUSDT", "ETHBTC"} & set(u)))
u4 = bc.get_top_symbols(4)["symbol"].tolist()
check("n=4 → ARB joins the crypto block, tokenized still appended", u4[:4] == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ARBUSDT"] and len(u4) == 6, u4)
config.BSTOCK_IN_UNIVERSE = False
u0 = bc.get_top_symbols(5)["symbol"].tolist()
check("switch OFF → the crypto-only universe again", u0 == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ARBUSDT"], u0)
config.BSTOCK_IN_UNIVERSE = True
print("4. the worker's quiet rule and the demo money gate")
W = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
i = W.index("def _bstock_quiet(")
body = W[i:i + 900]
check("worker: _bstock_quiet() returns False when BSTOCK_BUZZ is on (every stream rings)",
      'if getattr(config, "BSTOCK_BUZZ", False)' in body and "return False" in body)
cand = {"symbol": "SNDKBUSDT", "base": "SNDKB", "side": "LONG", "entry": 100.0, "stop": 96.0, "tp1": 106.0, "tp2": 110.0,
        "score": 90.0, "conf": 80.0, "burst": 0.0, "src": "elite_star", "heat": 50, "btc_day": -1.0}
check("demo: a tokenized star ranks like a coin now (BSTOCK_VALIDATED True)",
      len(da.rank_candidates({"elite_star": [cand]}, {})) == 1)
config.BSTOCK_VALIDATED = False
check("demo: with the gate closed again it would take no seat (the revert works)",
      da.rank_candidates({"elite_star": [cand]}, {}) == [])
config.BSTOCK_VALIDATED = True
check("demo: a crypto star still ranks", len(da.rank_candidates({"elite_star": [dict(cand, symbol="SOLUSDT", base="SOL")]}, {})) == 1)
print(f"\n{PASS} passed, {len(FAIL)} failed" + (f": {FAIL}" if FAIL else " — ALL PASS"))
sys.exit(1 if FAIL else 0)
