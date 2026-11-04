"""Guard test — 📡 CHANNEL DESK (2026-11-05). Parser on the real channel formats, the book on a
fake candle path (TP1 ladder, stop at entry, liquidation before the stop, plain stop), claims tied
to signals, the truth table, the light, the bells, the worker/page hooks. No network, no Telegram.
Run: .venv\\Scripts\\python.exe .channel_desk_test.py
"""
import json
import os
import sys
import tempfile
import time

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import channel_desk as cd  # noqa: E402

TMP = tempfile.mkdtemp(prefix="cdtest_")
cd.STATE_FILE = os.path.join(TMP, "state.json")
cd.INBOX_FILE = os.path.join(TMP, "inbox.jsonl")
cd._ensure_reader = lambda: None
cd._our_fires = lambda sym, side, ts: ["apex", "one_trade"] if sym == "OGN" else []


class FakeTG:
    enabled = staticmethod(lambda: False)
    sent = []

    @staticmethod
    def send_thread(text, reply_to=None, silent=False):
        FakeTG.sent.append(text); return True, "ok", {"1": 1}


cd.tg = FakeTG


class FakeBC:
    px = {}
    bars = {}
    btc = None

    @staticmethod
    def get_ticker_price(sym):
        return FakeBC.px.get(sym)

    @staticmethod
    def get_klines(sym, interval, limit):
        if sym == "BTCUSDT" and interval == "1h":
            return FakeBC.btc
        b = FakeBC.bars.get(sym)
        if b is None:
            return pd.DataFrame()
        return b.tail(limit).copy()


cd.bc = FakeBC
fails = []


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


ANDREW = "╭━━━ ✦ OGN/USDT ✦ ━━━╮\n\n LONG 0.028\n\nLEVERAGE: 25x\n\nTARGETS\n\n➊ 0.0285\n➋ 0.0290\n➌ 0.0296\n\n STOP LOSS: 0.0258\n\n╰━━━━━━━━━━━━━━━━━━╯"
FREE = "#FREE_SIGNAL 🏆 Trade: #DOGE/USDT\nSHORT\nEntry: 0.1620 - 0.1640\nTP1: 0.1580\nTP2: 0.1550\nTP3: 0.1500\nSL: 0.1700\nLeverage: Cross 20x"
CYCLE_GUESS = "🚀 #ARB/USDT LONG\nEntry: 0.163\nTargets: 0.166 - 0.170 - 0.175\nStop loss: 0.152\nLeverage 10x"

print("── parser ──")
s = cd.parse_signal(ANDREW)
check(s and s["sym"] == "OGN" and s["side"] == 1 and s["entry"] == 0.028 and s["tps"] == [0.0285, 0.029, 0.0296] and s["sl"] == 0.0258 and s["lev"] == 25, "Andrew card: coin/side/entry/3 circled targets/stop/leverage")
s = cd.parse_signal(FREE)
check(s and s["sym"] == "DOGE" and s["side"] == -1 and abs(s["entry"] - 0.163) < 1e-9 and s["tps"] == [0.158, 0.155, 0.15] and s["sl"] == 0.17 and s["lev"] == 20, "free-channel card: entry zone midpoint, TP1..3, SL, lev")
s = cd.parse_signal(CYCLE_GUESS)
check(s and s["sym"] == "ARB" and s["tps"] == [0.166, 0.17, 0.175] and s["sl"] == 0.152 and s["lev"] == 10, "generic card: targets list, stop, lev")
check(cd.parse_signal("Use 1% to 2% maximum funds in trade") is None and cd.parse_signal("Tp1 ✅") is None, "rules text / result post are not signals")
check(cd.classify_result("Tp1 ✅") == "tp1" and cd.classify_result("All Hit") == "all" and cd.classify_result("SL hit ❌") == "sl" and cd.classify_result("Tp2") == "tp2"
      and cd.classify_result(ANDREW) is None, "result posts classified, cards are not")
check(cd.channel_of_title("Crypto Andrew VIP") == "andrew" and cd.channel_of_title("Crypto Cycle VIP 🔥") == "cycle" and cd.channel_of_title("Hammad_signals_bot") is None, "channel matched by title")

print("── book: TP1 ladder then stop at entry ──")
now = time.time()
FakeBC.px = {"OGNUSDT": 0.02801}
FakeBC.btc = pd.DataFrame({"close": [100.0] * 24 + [100.4, 100.4]})
with open(cd.INBOX_FILE, "w", encoding="utf-8") as f:
    f.write(json.dumps({"channel": "andrew", "id": 778, "ts": now - 3 * 3600, "text": ANDREW}) + "\n")
r = cd.tick()
st = cd.load()
sig = st["signals"][0]; book = st["books"]["v2"]
check(r["ingested"] == 1 and len(st["signals"]) == 1 and len(book["open"]) == 1, "signal ingested → one seat in demo v2")
seat = book["open"][0]
check(abs(seat["margin"] - 20.0) < 1e-6 and seat["lev"] == 25 and abs(seat["notional"] - 500.0) < 1e-6, "seat = 2% of $1000 margin × 25x = $500 notional")
check(abs(seat["liq"] - 0.02801 * (1 - 0.95 / 25)) < 1e-9 and seat["stop0"] is not None and seat["liq"] > seat["stop0"], "liquidation level sits ABOVE their stop (25x)")
check(sig["light"]["code"] == "UNRATED" and sig["stamp"]["win"] in ("05–09", "09–13", "13–17", "17–21", "21–01", "01–05") and sig["stamp"]["ours"] == ["apex", "one_trade"] and abs(sig["stamp"]["btc24"] - 0.4) < 1e-6, "stamp: light UNRATED, PKT window, our co-fire, BTC day")
bell = cd._fmt_signal_bell(sig, seat, sig["light"], cd.truth(st, "andrew"))
check("CHANNEL SIGNAL" in bell and "OGN LONG" in bell and "liquidated at −3.8%" in bell and "UNRATED" in bell and "apex/one_trade" in bell, "signal bell text")
# backdate the seat 3h and feed a candle path: TP1 prints in bar 2, price returns to entry in bar 5
seat["opened_at"] = now - 3 * 3600
cd.save(st)
base = int((now - 3 * 3600) // 900 * 900)
ots = [base + 900 * k for k in range(1, 9)]
e = seat["entry"]
path = [(e, e * 1.004, e * 0.998, e * 1.003), (e * 1.003, e * 1.02, e * 1.002, e * 1.018), (e * 1.018, e * 1.019, e * 1.01, e * 1.012),
        (e * 1.012, e * 1.013, e * 1.005, e * 1.006), (e * 1.006, e * 1.007, e * 0.999, e * 1.0), (e, e * 1.001, e * 0.999, e * 1.0),
        (e, e * 1.001, e * 0.999, e * 1.0), (e, e * 1.001, e * 0.999, e * 1.0)]
FakeBC.bars = {"OGNUSDT": pd.DataFrame([{"open": o, "high": h, "low": l, "close": c} for o, h, l, c in path],
                                        index=pd.to_datetime(ots, unit="s", utc=True))}
r = cd.tick()
st = cd.load(); book = st["books"]["v2"]; sig = st["signals"][0]
check(r["events"] == 2 and not book["open"] and [c["reason"] for c in book["closed"]] == ["TP1 · 50% banked", "stop at entry"], "TP1 banked 50% then the rest stopped at entry")
check(sig["result"]["first"] == "tp1" and sig["result"]["r_their"] > 0 and sig["result"]["r_liq"] > 0 and sig["status"] == "closed", "truth table: TP1 printed first, R positive at both stops")
tp1_pnl = book["closed"][0]["pnl_usd"]
check(abs(tp1_pnl - (0.5 * 500 / e * (seat["tps"][0] - e) - 0.5 * 500 / e * seat["tps"][0] * cd.FEE)) < 1e-3 and book["equity"] > 1000 - 1 and book["equity"] < 1000 + 6, "pnl math: half position × TP1 move − fee; equity moved by cents, not dollars")

print("── book: liquidation before their stop (25x) ──")
FakeBC.px = {"HOTUSDT": 0.00042}
HOT = "╭━━━ ✦ HOT/USDT ✦ ━━━╮\n SHORT 0.00042\nLEVERAGE: 25x\nTARGETS\n➊ 0.000412\n➋ 0.000408\n➌ 0.000396\n STOP LOSS: 0.00045\n╰━━━╯"
with open(cd.INBOX_FILE, "w", encoding="utf-8") as f:
    f.write(json.dumps({"channel": "andrew", "id": 794, "ts": now - 2 * 3600, "text": HOT}) + "\n")
cd.tick(); st = cd.load(); seat = st["books"]["v2"]["open"][0]; seat["opened_at"] = now - 2 * 3600; cd.save(st)
base = int((now - 2 * 3600) // 900 * 900); e = seat["entry"]
path = [(e, e * 1.01, e * 0.999, e * 1.008), (e * 1.008, e * 1.045, e * 1.005, e * 1.04)]      # +4.5% adverse: past liquidation (3.8%), before their stop (7.1%)
FakeBC.bars = {"HOTUSDT": pd.DataFrame([{"open": o, "high": h, "low": l, "close": c} for o, h, l, c in path], index=pd.to_datetime([base + 900, base + 1800], unit="s", utc=True))}
r = cd.tick(); st = cd.load(); book = st["books"]["v2"]; sig = st["signals"][1]
check(r["events"] == 1 and book["closed"][-1]["reason"] == "liquidated" and sig["result"]["first"] == "liq", "liquidated on the candle path, their stop never printed")
check(abs(book["closed"][-1]["pnl_margin_pct"] + 95) < 3 and sig["result"]["r_liq"] < -1 and sig["result"]["r_their"] < 0 and sig["result"]["r_their"] > -1, "loss ≈ the whole margin; −1R at the liquidation stop, a partial R at their (unreached) stop")
ev = cd._fmt_event_reply("liq", seat, book["closed"][-1], sig)
check("LIQUIDATED" in ev and "HOT SHORT" in ev, "liquidation reply text")

print("── claims tied to signals ──")
with open(cd.INBOX_FILE, "w", encoding="utf-8") as f:
    f.write(json.dumps({"channel": "andrew", "id": 795, "ts": now - 1.5 * 3600, "text": "Tp2 ✅", "reply_text": HOT.replace("\n", " ")}) + "\n")
    f.write(json.dumps({"channel": "andrew", "id": 796, "ts": now - 1.4 * 3600, "text": "All Hit", "reply_text": "Tp1 Crypto Andrew VIP"}) + "\n")
cd.tick(); st = cd.load(); tr = cd.truth(st, "andrew")
check(st["signals"][1]["claims"] and st["signals"][1]["claims"][0]["kind"] == "tp2" and len(st.get("orphan_claims", [])) == 1, "result post quoting the HOT card → claim on HOT; unquotable one → orphan")
check(tr["n"] == 2 and tr["tp1"] == 1 and tr["liq"] == 1 and tr["claimed_but_lost"] == 1 and tr["lost_unposted"] == 0, "truth table counts the claimed win that was liquidated")

print("── plain stop at 10x (stop inside liquidation) ──")
FakeBC.px = {"ARBUSDT": 0.163}
with open(cd.INBOX_FILE, "w", encoding="utf-8") as f:
    f.write(json.dumps({"channel": "cycle", "id": 5, "ts": now - 2 * 3600, "text": CYCLE_GUESS}) + "\n")
cd.tick(); st = cd.load(); seat = st["books"]["v3"]["open"][0]; seat["opened_at"] = now - 2 * 3600; cd.save(st)
base = int((now - 2 * 3600) // 900 * 900); e = seat["entry"]
path = [(e, e * 1.005, e * 0.98, e * 0.985), (e * 0.985, e * 0.99, e * 0.93, e * 0.935)]        # −7% adverse: their stop (−6.7%) before liquidation (−9.5%)
FakeBC.bars = {"ARBUSDT": pd.DataFrame([{"open": o, "high": h, "low": l, "close": c} for o, h, l, c in path], index=pd.to_datetime([base + 900, base + 1800], unit="s", utc=True))}
r = cd.tick(); st = cd.load(); book = st["books"]["v3"]; sig = [s for s in st["signals"] if s["channel"] == "cycle"][0]
check(book["closed"][-1]["reason"] == "stop" and sig["result"]["first"] == "stop" and abs(sig["result"]["r_their"] + 1) < 0.05 and sig["result"]["r_liq"] < 0, "demo v3: their stop printed first at 10x (−1R at their stop)")
check(st["books"]["v2"]["equity"] != st["books"]["v3"]["equity"], "v2 and v3 are separate books")

print("── light after 60 resolved ──")
st = cd.load()
for k in range(60):
    st["signals"].append({"id": f"cycle:x{k}", "channel": "cycle", "msg_id": f"x{k}", "ts": now - (100 - k) * 3600, "sym": "ZZZ", "side": 1 if k % 2 else -1, "entry": 1.0, "tps": [1.02], "sl": 0.93, "lev": 10,
                          "claims": [], "status": "closed", "stamp": {"btc_band": "flat" if k % 3 else ">+1.5", "win": "13–17", "weekend": 0, "ours": []}, "tp1_pct": 2.0, "stop_pct": 7.0,
                          "result": {"first": "tp1" if k % 3 else "stop", "r_liq": 0.4 if k % 3 else -1.0, "r_their": 0.3 if k % 3 else -1.0}})
cd.save(st)
lt = cd.light_for(st, "cycle", {"side": 1, "stamp": {"btc_band": ">+1.5", "win": "13–17", "weekend": 0, "ours": []}, "tp1_pct": 2.0, "stop_pct": 7.0})
check(lt["code"] == "SKIP" and ">+1.5" in lt["text"], "light: a held losing cell (BTC >+1.5) turns the signal 🔴 SKIP even though the channel's own forward R is positive")
lt2 = cd.light_for(st, "cycle", {"side": 1, "stamp": {"btc_band": "flat", "win": "13–17", "weekend": 0, "ours": []}, "tp1_pct": 2.0, "stop_pct": 7.0})
check(lt2["code"] == "TAKE" and "flat" in lt2["text"], "light: the held winning cell reads 🟢 TAKE")

print("── state round-trip + hooks ──")
st2 = cd.load()
check(st2["books"]["v2"]["closed"] and st2["signals"] and st2["seen"]["andrew"] == ["778", "794", "795", "796"], "state survives save/load; message ids de-duplicated")
w = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read(); a = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
check("import channel_desk" in w and "_cd = channel_desk.tick()" in w and w.index("_cd = channel_desk.tick()") > w.index("def cycle() -> None:"), "worker: tick() at the top of cycle()")
check("import channel_desk" in a and "channel_desk.render(st)" in a and a.index("channel_desk.render(st)") > a.index("_render_t1_board(pb_state, live_prices)"), "page: desk rendered after the T1 board")
check("telethon" in open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8").read(), "requirements: telethon")
check(cd.TG_CHANNEL_DESK is True, "bell switch ON")

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + '; '.join(fails)}")
sys.exit(1 if fails else 0)
