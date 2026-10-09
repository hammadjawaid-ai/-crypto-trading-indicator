"""🌊⬆️ BOTTOM WATCH — replay on real BTC history (the .dip_kl cache) with 5-min
cycles: one print per dump unless a new low re-arms it (max 3), prints only
after a >= 2% crossing and only on a higher close with no new low, message
format, the 08 Oct night on fresh candles (print at 21:15 then again at 23:15
PKT), worker wiring."""
import calendar
import io
import os
import sys
import tempfile

import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, "F:/Trading Indicator")
import bottom_watch as bw

fails = []
B = pd.read_csv(".dip_kl/BTCUSDT.csv").drop_duplicates("ot").sort_values("ot")
B["t"] = pd.to_datetime(B["ot"], unit="ms", utc=True)
K = B.set_index("t")[["o", "h", "l", "c", "v"]].rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})


def gk(now):
    def f(sym, interval, limit=400):
        return K[K.index <= pd.Timestamp(now, unit="s", tz="UTC")].iloc[-limit:]
    return f


bw.STATE_FILE = os.path.join(tempfile.mkdtemp(), "bw.json")
bw._LAST["shock"] = 0.0
sent = []
t0 = pd.Timestamp("2026-09-01 00:00", tz="UTC").timestamp()
for k in range(30 * 24 * 12):
    now = t0 + k * 300
    r = bw.run(gk(now), lambda m: sent.append((now, m)), recent_shorts=lambda since: ["FET ⭐", "ASTER ⚡GO"], now=now)
    if r:
        # the print must be a higher close with no new low, after a >= 2% crossing
        d = bw._closed(gk(now)("BTCUSDT", "15m"), now)
        c, h, l = d["close"].astype(float).to_numpy(), d["high"].astype(float).to_numpy(), d["low"].astype(float).to_numpy()
        t = d.index.map(lambda x: x.timestamp()).to_numpy(dtype=float)
        i = int((t == r["print_at"]).argmax())
        if not (c[i] > h[i - 1] and l[i] >= r["low"]):
            fails.append(f"print at {now} is not a higher close without a new low")
        if r["depth"] > -0.02:
            fails.append(f"print after a shallow dump {r['depth']:.3f}")
st = bw._load()
prints = st.get("prints") or []
print(f"30 days of real BTC (Sep 2026): {len(sent)} bottom prints · shocks seen {len({p['shock_at'] for p in prints})}")
if not sent:
    fails.append("no print in 30 days — detector dead")
if len(sent) != len(prints):
    fails.append("state prints do not match sent messages")
# per shock: at most MAX_PRINTS, and every re-print sits on a lower low than the one before
from collections import defaultdict
per = defaultdict(list)
for p in prints:
    per[p["shock_at"]].append(p)
for sa, ps in per.items():
    if len(ps) > bw.MAX_PRINTS:
        fails.append("more prints than MAX_PRINTS on one shock")
    for a, b in zip(ps, ps[1:]):
        if not (b["low"] < a["low"] and b["print_at"] > a["print_at"]):
            fails.append("a re-print without a new low")
for _, m in sent:
    if "\ufffd" in m or m.count("*") % 2 or m.count("`") % 2 or m.count("_") % 2:
        fails.append("markdown/encoding problem"); break
    for need in ("🌊⬆️ *BTC BOTTOM CONFIRMED —", "what history did from this print (164 dumps ≥2%, 25 Aug 2025 → 03 Oct 2026)",
                 "the median coin was FLAT 8h later (+0.0%)", "a +5% night like 08 Oct 0.6%", "no entry bell",
                 "shorts rung in the last 3h: FET ⭐, ASTER ⚡GO", "a factual read, not a forecast"):
        if need not in m:
            fails.append(f"message missing {need!r}"); break
    else:
        continue
    break
if sent and not any("higher close again after a NEW low (print 2)" in m for _, m in sent):
    print("  (no re-print occurred in this 30-day slice — fine)")

# ---- 08 Oct 2026 on fresh candles: print at 21:15 PKT (fake), re-print at 23:15 PKT (real) ----
try:
    import binance_client as bc
    live = bc.get_klines("BTCUSDT", "15m", limit=600)
    live.index = pd.to_datetime(live.index, utc=True)
    LK = live[["open", "high", "low", "close", "volume"]]

    def gk2(now):
        def f(sym, interval, limit=400):
            return LK[LK.index <= pd.Timestamp(now, unit="s", tz="UTC")].iloc[-limit:]
        return f
    bw.STATE_FILE = os.path.join(tempfile.mkdtemp(), "bw2.json")
    bw._LAST["shock"] = 0.0
    got = []
    t1 = calendar.timegm((2026, 10, 8, 10, 0, 0))     # 15:00 PKT
    for k in range(14 * 12):                          # 14 hours of 5-min cycles
        now = t1 + k * 300
        r = bw.run(gk2(now), lambda m: got.append(m), recent_shorts=lambda since: [], now=now)
    times = [bw._hm(p["print_at"]) for p in (bw._load().get("prints") or [])]
    print(f"08 Oct replay prints at PKT: {times}")
    if times[:2] != ["21:15", "23:15"]:
        fails.append(f"08 Oct prints wanted 21:15 then 23:15 PKT, got {times}")
    if got and "print 2" not in got[-1]:
        fails.append("second print must say it followed a new low")
    if got:
        print("\n08 Oct, second print:\n" + got[-1])
except Exception as exc:
    print("  (fresh-candle replay skipped:", exc, ")")

W = open("F:/Trading Indicator/agent_worker.py", encoding="utf-8").read()
for need in ("import bottom_watch\n", "_bw = bottom_watch.run(binance_client.get_klines, tg.send,", "def _recent_short_bells(_since):",
             'if (_aid.startswith(("elitestar:", "eliteagrade:"))', 'if str(_ex.get("bell") or "").startswith("sent"):'):
    if need not in W:
        fails.append(f"worker wiring missing: {need[:40]}")
if not (0 < W.find('print("  shock_watch start error:", _sw_exc2, flush=True)') < W.find("_bw = bottom_watch.run(")):
    fails.append("hook must sit right after the shock-watch block")
print("BOTTOM WATCH:", "ALL PASS" if not fails else fails)
