"""Guard test — 🔁 TAKE NOW RESTORE (2026-11-06). The 4 Oct kline-cache reuse silently killed every stream
that needs entry_timing's TAKE_NOW (TAKE NOW HOT, EARLY LANE, EARLY MOVERS, FRESH, EARLY ELITE, TOP CONVICTION):
the plan entry is the scanner frame's last close and the confirm needs the forming candle to close strictly
beyond it — served the same frame they are equal. This checks: get_klines(fresh=True) takes its own snapshot
while the default path still reuses a longer frame; entry_signal asks for fresh=True; with a fresh tick beyond
the plan entry the gate returns TAKE_NOW again; and the 🏆💎 APEX V2 GATED verdict branch is reachable with
TG_RULES on. No network.
Run: .venv\\Scripts\\python.exe .takenow_restore_test.py
"""
import os
import re
import sys
import time

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import binance_client as bc      # noqa: E402
import entry_timing as et        # noqa: E402

PASS, FAIL = 0, []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL.append(name)
        print(f"  ❌ {name} {detail}")


def frame(n, last_close, seed=1):
    rng = np.random.default_rng(seed)
    base = np.linspace(100.0, 110.0, n)
    close = base + rng.normal(0, 0.05, n)
    close[-1] = last_close
    idx = pd.date_range("2026-11-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame({"open": close - 0.1, "high": close + 0.3, "low": close - 0.3, "close": close,
                         "volume": np.full(n, 1000.0), "quote_volume": np.full(n, 1e5)}, index=idx)


print("1. get_klines: the default path reuses a longer frame, fresh=True takes its own snapshot")
calls = {"n": 0}
_orig = bc._get_klines_uncached


def fake_uncached(symbol, interval, limit=300):
    calls["n"] += 1
    return frame(int(limit), 110.0 + 0.01 * calls["n"])     # every real fetch ticks the forming close up


bc._get_klines_uncached = fake_uncached
bc._KL_CACHE.clear()
long = bc.get_klines("TESTUSDT", "1h", 300)                  # the scanner's frame
n_after_long = calls["n"]
served = bc.get_klines("TESTUSDT", "1h", 120)                 # today's default path
check("default 120 request served from the 300 frame (no fetch)", calls["n"] == n_after_long and len(served) == 120)
check("served close equals the scanner's close exactly", float(served["close"].iloc[-1]) == float(long["close"].iloc[-1]))
own = bc.get_klines("TESTUSDT", "1h", 120, fresh=True)
check("fresh=True fetched its own snapshot", calls["n"] == n_after_long + 1 and len(own) == 120)
check("fresh close differs from the scanner's close (the forming candle ticked)",
      float(own["close"].iloc[-1]) != float(long["close"].iloc[-1]))
n_now = calls["n"]
again = bc.get_klines("TESTUSDT", "1h", 120, fresh=True)
check("fresh=True still honours the exact-key 120s cache (as before 4 Oct)", calls["n"] == n_now
      and float(again["close"].iloc[-1]) == float(own["close"].iloc[-1]))
bc._KL_CACHE.clear()
bc.get_klines("TESTUSDT", "1h", 300)
n0 = calls["n"]
bc.get_klines("TESTUSDT", "15m", 100)
check("other interval still fetches (reuse is per symbol+interval)", calls["n"] == n0 + 1)
bc._get_klines_uncached = _orig

print("2. entry_signal asks for its own snapshot and TAKE_NOW is reachable again")
src = open(os.path.join(ROOT, "entry_timing.py"), encoding="utf-8").read()
check("entry_signal passes fresh=True", re.search(r'get_klines\(symbol, "1h", limit=120,\s*fresh=True\)', src) is not None)
plan_entry = 110.0                                            # = the scanner's last close
df = frame(120, 110.0)
df.loc[df.index[-25], "low"] = 100.0                          # a pullback to below the entry inside the 48-bar window
df.loc[df.index[-1], "volume"] = 5000.0                       # the volume kick
df.loc[df.index[-1], "open"] = 109.5
df.loc[df.index[-2], "close"] = 109.6
same = et.entry_signal("TESTUSDT", "LONG", plan_entry, stop=105.0, df=df.copy())
check("same snapshot as the plan: close == entry -> not TAKE_NOW", same["status"] != "TAKE_NOW", same)
df2 = df.copy()
df2.loc[df2.index[-1], "close"] = 110.05                      # the forming candle ticked beyond the plan entry
fresh = et.entry_signal("TESTUSDT", "LONG", plan_entry, stop=105.0, df=df2)
check("fresh snapshot beyond the entry -> TAKE_NOW", fresh["status"] == "TAKE_NOW", fresh)

print("3. the 🏆💎 APEX V2 GATED verdict reply is reachable with TG_RULES on")
w = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
ia = w.index('if _ew.get("buzzed") and _ew.get("fam") == "apexv2":')
ib = w.index("elif TG_RULES:", ia)
ic = w.index('elif _ew.get("buzzed") or _ew.get("appr"):', ib)
check("apexv2 verdict branch is an `if` that comes BEFORE the TG_RULES elif", ia < ib < ic)
check("the apexv2 branch sends the verdict in its thread", "_fmt_apex_v2_verdict(_ew, _prg)" in w[ia:ib])
check("no second standalone verdict path for apexv2 under the rules", w[ib:ic].count("apexv2") == 0)

print(f"\n{PASS} passed, {len(FAIL)} failed" + (f": {FAIL}" if FAIL else " — ALL PASS"))
sys.exit(1 if FAIL else 0)
