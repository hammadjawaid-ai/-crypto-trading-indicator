"""SHOCK WATCH tests — synthetic BTC shocks, calm detection, re-ignition scan,
end-to-end run with record/open callbacks, state file, wiring."""
import io
import os
import sys
import tempfile

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, "F:/Trading Indicator")
import shock_watch as sw

fails = []
sw.STATE_FILE = os.path.join(tempfile.mkdtemp(), "sw.json")
T0 = pd.Timestamp("2026-10-02 10:00", tz="UTC")


def frame(closes, highs=None, lows=None, vols=None, start=T0):
    n = len(closes)
    idx = pd.date_range(start, periods=n, freq="15min", tz="UTC")
    c = np.asarray(closes, float)
    return pd.DataFrame({"open": c, "high": np.asarray(highs if highs is not None else c * 1.001, float),
                         "low": np.asarray(lows if lows is not None else c * 0.999, float), "close": c,
                         "volume": np.asarray(vols if vols is not None else np.full(n, 100.0), float)}, index=idx)


def ts(frm, i):   # close time of bar i as epoch seconds
    return frm.index[i].timestamp() + 900


# ---- BTC paths ----
flat = [85000.0] * 120
dump = [85000.0] * 70 + list(np.linspace(85000, 82500, 20)) + [82500.0] * 30          # -2.9% over 5h, then flat
pumpdump = [85000.0] * 60 + list(np.linspace(85000, 86700, 10)) + list(np.linspace(86700, 85000, 12)) + [85000.0] * 38
B_flat, B_dump, B_pd = frame(flat), frame(dump), frame(pumpdump)
# shock detection at the end of the dump leg (bar 79 closed)
now = ts(B_dump, 89)
sh = sw.detect_shock(B_dump, now)
if not sh or sh["kind"] != "dump" or abs(sh["high"] - 85000) > 1 or sh["low"] > 82600:
    fails.append(f"dump not detected: {sh}")
if sw.detect_shock(B_flat, ts(B_flat, 100)) is not None:
    fails.append("flat BTC produced a shock")
sh2 = sw.detect_shock(B_pd, ts(B_pd, 81))
if not sh2 or sh2["kind"] != "pump-then-dump":
    fails.append(f"pump-then-dump not detected: {sh2}")
# calm: after the low, 4 bars with no new low and tight range -> calm_at stamped
st = dict(sh); st["fired"] = {}
st = sw.update_calm(st, B_dump, ts(B_dump, 110))
if not st.get("calm_at") or st["calm_at"] > ts(B_dump, 96):
    fails.append(f"calm not stamped in time: {st.get('calm_at')}")
# a lower low after calm keeps tracking the low
B_dump2 = B_dump.copy(); B_dump2.iloc[105, B_dump2.columns.get_loc("low")] = 82000.0
st2 = sw.update_calm(dict(st), B_dump2, ts(B_dump2, 110))
if st2["low"] > 82000.5:
    fails.append("running low not updated after a new low")
# ---- coin scan: a coin that re-ignites vs one that does not ----
n = 800
base = np.full(n, 1.0)
quiet = frame(base, vols=np.full(n, 100.0), start=T0 - pd.Timedelta(minutes=15 * (n - 120)))
btc_long = frame([85000.0] * (n - 120) + dump, start=T0 - pd.Timedelta(minutes=15 * (n - 120)))
st3 = {"shock_at": ts(btc_long, n - 120 + 89), "calm_at": ts(btc_long, n - 120 + 95), "low": 82500.0, "low_at": ts(btc_long, n - 120 + 89), "high": 85000.0, "high_at": ts(btc_long, n - 120 + 69), "kind": "dump", "fired": {}}
hot = quiet.copy()
hc = hot["close"].to_numpy().copy(); hc[-5:] = [1.0, 1.005, 1.01, 1.016, 1.022]; hot["close"] = hc; hot["high"] = hc * 1.001; hot["open"] = hc
hv = hot["volume"].to_numpy().copy(); hv[-4:] = 400.0; hot["volume"] = hv
r_hot = sw.scan_coin(hot, btc_long, st3, ts(hot, n - 1))
r_quiet = sw.scan_coin(quiet, btc_long, st3, ts(quiet, n - 1))
if not r_hot or not r_hot["fires"]:
    fails.append(f"re-ignition not detected: {r_hot}")
if not r_quiet or r_quiet["fires"]:
    fails.append("quiet coin fired")
if r_hot and not (r_hot["stop"] < r_hot["px"] < r_hot["tp1"] < r_hot["tp2"]):
    fails.append("plan geometry wrong")
# ---- end-to-end run(): fake klines, a window open, one coin re-ignites -> record + open called once ----
recs, opens = [], []
def gk(sym, interval, limit=720):
    if sym == "BTCUSDT":
        return btc_long.iloc[-limit:]
    return (hot if sym == "HOTUSDT" else quiet).iloc[-limit:]
t_window = st3["calm_at"] + 2.5 * 3600
# build the shock state first at the shock moment, then advance into the window
sw.run(gk, ["HOTUSDT", "QUIETUSDT"], record=lambda s, p: recs.append((s, p)), open_trade=lambda s, p, px: opens.append((s, p, px)), now=ts(btc_long, n - 120 + 89))
s1 = sw._load()
if not s1.get("shock") or s1["shock"]["kind"] != "dump":
    fails.append(f"run() did not store the shock: {s1.get('shock')}")
# the fake BTC frame does not extend in time, so clamp 'now' inside its last bars for calm + window logic
sw.run(gk, ["HOTUSDT", "QUIETUSDT"], record=lambda s, p: recs.append((s, p)), open_trade=lambda s, p, px: opens.append((s, p, px)), now=ts(btc_long, n - 1))
s2 = sw._load()
ph = (s2.get("shock") or {}).get("phase")
if ph != "window":
    fails.append(f"the e2e run should land inside the window, got {ph}")
if ph == "window":
    if len(recs) != 1 or recs[0][0] != "shock_reignite" or recs[0][1]["symbol"] != "HOTUSDT":
        fails.append(f"expected one shock_reignite record for HOTUSDT, got {recs}")
    if len(opens) != 1:
        fails.append(f"expected one shadow open, got {len(opens)}")
    sw.run(gk, ["HOTUSDT", "QUIETUSDT"], record=lambda s, p: recs.append((s, p)), open_trade=lambda s, p, px: opens.append((s, p, px)), now=ts(btc_long, n - 1) + 60)
    if len(recs) != 1:
        fails.append("same coin recorded twice in one shock")
    if not any(b["symbol"] == "HOTUSDT" and b["fired"] for b in s2.get("board", [])):
        fails.append("board does not show the fired coin")
print("phase reached in the e2e run:", ph, "| records:", len(recs), "| board rows:", len(s2.get("board", [])))
if "shock" not in sw.describe(s2) and "dump" not in sw.describe(s2):
    fails.append(f"describe() odd: {sw.describe(s2)}")
# fail-soft: klines raising -> run returns state, no exception
sw.run(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")), ["X"], now=ts(btc_long, n - 1))
# ---- wiring ----
W = open("F:/Trading Indicator/agent_worker.py", encoding="utf-8").read()
A = open("F:/Trading Indicator/app.py", encoding="utf-8").read()
U = open("F:/Trading Indicator/auditor.py", encoding="utf-8").read()
for need, where, name in (("import shock_watch", W, "worker import"), ("shock_watch.run(", W, "worker run"), ("open_trade=shadow_trader.open_from_signal", W, "worker desk open"),
                          ("#### 🌊 AFTER THE SHOCK", A, "app board"), ("tier='shock_reignite'", A, "app ledger"), ('"shock_reignite": "🌊 SHOCK RE-IGNITION', A, "app tier name"),
                          ('"shock_reignite": "shock_reignite",', U, "auditor tier")):
    if need not in where:
        fails.append(f"wiring missing: {name}")
if "tg.send" in W[W.find("def _sw_job"):W.find("def _sw_job") + 1500]:
    fails.append("shock watch must not send Telegram")
print("SHOCK WATCH:", "ALL PASS" if not fails else fails)
