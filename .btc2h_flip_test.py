"""🧭⚡ BTC FLIP — the between-pulse bell on real BTC history (same generator
as the pulse test): rings only on a confirmed label change vs the last sent
message, never within FLIP_GAP of it, once per 15m close; the pulse clock is
untouched; message format; worker wiring."""
import io
import os
import sys
import tempfile

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
        src = H if interval == "1h" else Q
        x = src[src.index <= pd.Timestamp(now, unit="s", tz="UTC")]
        return x.iloc[-limit:]
    return gk


btc2h.STATE_FILE = os.path.join(tempfile.mkdtemp(), "btc2h.json")
btc2h._LAST["t"] = 0.0
btc2h._FLIP["t"] = 0.0
t0 = pd.Timestamp("2026-09-20 00:00", tz="UTC").timestamp()
# before any pulse the flip watch stays silent
if btc2h.run_flip(fake_klines(t0 + 3000), lambda m: fails.append("flip before any pulse"), now=t0 + 3000):
    fails.append("run_flip must return None before the first pulse")
pulses, flips, sent_t = [], [], []       # sent_t: every sent message time (pulse or flip)
for k in range(3 * 24 * 12):             # 3 days of 5-minute worker cycles
    now = t0 + k * 300
    g = pd.Timestamp(now, unit="s", tz="UTC")
    if g.hour % 2 == 0 and g.minute < 30:
        if btc2h.run(fake_klines(now), lambda m: pulses.append((now, m)), now=now):
            sent_t.append(("pulse", now))
    r = btc2h.run_flip(fake_klines(now), lambda m: flips.append((now, m)), now=now)
    if r:
        sent_t.append(("flip", now))
        # the flip's label must be the confirmed 15m-cadence read, and differ from the previous sent label
        c15 = btc2h.closed_closes(Q[Q.index <= g].iloc[-720:], now, minutes=15)
        c1 = btc2h.closed_closes(H[H.index <= g].iloc[-240:], now)
        f_now, f_prev, _ = btc2h.fine_labels(c15, btc2h.read(c1, c15)["band"])
        if r["now"] != f_now or f_prev != f_now:
            fails.append(f"flip at {g} not a confirmed label change ({r['now']} vs {f_now}/{f_prev})")
if len(pulses) != 36:
    fails.append(f"pulse clock changed: {len(pulses)} pulses in 3 days (want 36)")
if not flips:
    fails.append("no flip rang in 3 days of real BTC — detector dead")
# spacing law: a flip never within FLIP_GAP of the previous sent message
for i in range(1, len(sent_t)):
    kind, t = sent_t[i]
    if kind == "flip" and t - sent_t[i - 1][1] < btc2h.FLIP_GAP:
        fails.append(f"flip {t - sent_t[i - 1][1]:.0f}s after the previous message")
        break
# labels alternate: each flip's 'to' differs from the message before it
st = btc2h._load()
chain = st.get("flips") or []
if len(chain) != len(flips):
    fails.append("state file flips do not match sent flips")
for f in chain:
    if f["from"] == f["to"]:
        fails.append("a flip with no label change")
        break
if len({f["t"] for f in chain}) != len(chain):
    fails.append("two flips on the same 15m close")
if len(flips) > 3 * 20:
    fails.append(f"too chatty: {len(flips)} flips in 3 days")
for _, m in flips:
    if "\ufffd" in m or m.count("*") % 2 or m.count("`") % 2 or m.count("_") % 2:
        fails.append("markdown/encoding problem in a flip message"); break
    l = m.splitlines()
    if not l[0].startswith("🧭⚡ *BTC FLIP — ") or not l[1].startswith("🕐") or "the last pulse said" not in l[2] \
            or "next pulse ~" not in l[2] or not l[3].startswith("📍 now:") or not l[5].startswith("🌡 conditions:"):
        fails.append(f"flip message shape wrong:\n{m}"); break
    if not any(h in l[0] for h in btc2h.FLIP_HEAD.values()):
        fails.append("flip head label missing"); break
# the same 15m close never rings twice even if the worker cycles again
if flips:
    t_last = flips[-1][0] + 60
    n0 = len(flips)
    btc2h.run_flip(fake_klines(t_last), lambda m: flips.append((t_last, m)), now=t_last)
    if len(flips) != n0:
        fails.append("duplicate flip on the same close")
# worker wiring: the flip call sits right after the pulse block, every cycle
W = open("F:/Trading Indicator/agent_worker.py", encoding="utf-8").read()
i_p = W.find("if btc2h.run(binance_client.get_klines, tg.send):")
i_f = W.find("if btc2h.run_flip(binance_client.get_klines, tg.send):")
if not (0 < i_p < i_f) or i_f - i_p > 1500:
    fails.append("worker flip hook missing or misplaced")
print(f"3 days of real BTC: {len(pulses)} pulses, {len(flips)} flips "
      f"({', '.join(f['from'] + '>' + f['to'] for f in chain[:12])}{' …' if len(chain) > 12 else ''})")
if flips:
    print("SAMPLE FLIP:\n" + flips[0][1] + "\n")
print("BTC FLIP:", "ALL PASS" if not fails else fails)
