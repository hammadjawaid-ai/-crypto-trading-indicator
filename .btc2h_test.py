"""BTC 2H PULSE validation — the fact-based read on real BTC history."""
import calendar
import io
import os
import sys
import tempfile

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, "F:/Trading Indicator")
import btc2h

fails = []
d = pd.read_csv(".dip_kl/BTCUSDT.csv")
d["t"] = pd.to_datetime(d["ot"], unit="ms", utc=True)
Q = d.set_index("t")[["o", "h", "l", "c"]].rename(
    columns={"o": "open", "h": "high", "l": "low", "c": "close"})
H = Q.resample("1h").agg({"open": "first", "high": "max", "low": "min",
                          "close": "last"}).dropna()


def fake_klines(now):
    def gk(sym, interval, limit=240):
        assert sym == "BTCUSDT"
        src = H if interval == "1h" else Q
        x = src[src.index <= pd.Timestamp(now, unit="s", tz="UTC")]
        return x.iloc[-limit:]
    return gk


btc2h.STATE_FILE = os.path.join(tempfile.mkdtemp(), "btc2h.json")
sent = []
t0 = pd.Timestamp("2026-09-20 00:00", tz="UTC").timestamp()
for k in range(3 * 24 * 6):                      # 3 days of 10-minute worker cycles
    now = t0 + k * 600
    g = pd.Timestamp(now, unit="s", tz="UTC")
    if g.hour % 2 == 0 and g.minute < 30:
        btc2h.run(fake_klines(now), lambda m: sent.append((now, m)), now=now)
if len(sent) != 36:
    fails.append(f"expected 36 pulses in 3 days, got {len(sent)}")
if any(pd.Timestamp(n, unit="s", tz="UTC").hour % 2 for n, _ in sent):
    fails.append("a pulse fired on an odd hour")
for _, m in sent:
    if "\ufffd" in m or m.count("*") % 2 or m.count("`") % 2 or m.count("_") % 2:
        fails.append("markdown/encoding problem in a message"); break
    if not m.splitlines()[1].startswith("🕐") or "📍 now:" not in m or "🌡 conditions:" not in m:
        fails.append("pulse missing a required line"); break
    if "lean" in m.lower() or "score" in m.lower():
        fails.append("forecast wording leaked into the fact-based pulse"); break
# duplicate guard: same hour twice sends nothing new
n0 = len(sent); _tdup = sent[-1][0] + 1200
btc2h.run(fake_klines(_tdup), lambda m: sent.append((0, m)), now=_tdup)
if len(sent) != n0:
    fails.append("duplicate pulse within the same hour")
# classification: NOW follows the 2h move vs the band; 15m flag follows its own z-score
c_all = btc2h.closed_closes(H, H.index[-1].timestamp() + 3600)
q_all = btc2h.closed_closes(Q, Q.index[-1].timestamp() + 900, minutes=15)
r = btc2h.read(c_all, q_all)
want = "UP" if r["past"] > r["band"] else "DOWN" if r["past"] < -r["band"] else "FLAT"
if r["now"] != want:
    fails.append("NOW classification does not match the band rule")
if r["m15"] is None or (r["strong15"] is not None) != (r["z15"] >= btc2h.STRONG_15):
    fails.append("15m strength flag inconsistent")
# find a moment with a strong 15m candle and check the ⚡ line renders
r15 = q_all / q_all.shift(1) - 1
z = (r15.abs() / r15.rolling(672).std()).dropna()
big = z[z >= 2.5].index[-1]
r_big = btc2h.read(c_all[c_all.index <= big.floor("h")], q_all[q_all.index <= big])
if r_big["strong15"] is None or "⚡ strong 15m candle" not in btc2h.now_line(r_big):
    fails.append("strong 15m candle not flagged")
# without 15m data the pulse still renders
r_no = btc2h.read(c_all, None)
if "📍 now:" not in btc2h.message(r_no) or r_no["m15"] is not None:
    fails.append("pulse should render without 15m data")

# ---- 🕐 trading-hours headline: right window for the PKT hour ----
w_fails = []
for utc_h, want_ic in ((8, "🟢"), (15, "🟢"), (0, "🟡"), (7, "🟡"), (16, "🔴"), (22, "🔴"), (2, "🟡"), (20, "🔴")):
    ts = calendar.timegm((2026, 9, 29, utc_h, 0, 0))
    line = btc2h.window(ts); pk = (utc_h + 5) % 24
    if want_ic not in line or f"{pk:02d}:00–{(pk + 2) % 24:02d}:00 PKT" not in line:
        w_fails.append(f"utc {utc_h} -> {line[:60]}")
print("SAMPLE PULSE:\n" + sent[5][1] + "\n")
print("BTC 2H PULSE:", "ALL PASS" if not fails else fails)
print("BTC 2H window headline:", "ALL PASS" if not w_fails else w_fails)
