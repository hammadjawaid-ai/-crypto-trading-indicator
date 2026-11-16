"""Guard — 📱 the phone roster by asset class (2026-11-17). The class rule, the stock cards (stock numbers only, read
live from the tok:<tier> seats), the three new cards, the rang-bell log, the switches, and the worker's wiring.
No network, no Telegram. Run: .venv\\Scripts\\python.exe .tg_roster_test.py
"""
import calendar
import io
import os
import re
import sys
import tempfile
import types

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="tgroster_")
os.environ["WORKER_DB_PATH"] = os.path.join(TMP, "worker.db")
import config               # noqa: E402
import tg_cells as tc       # noqa: E402
import tg_roster as tr      # noqa: E402
import tg_switches as ts    # noqa: E402
import worker_store as ws   # noqa: E402

PASS, FAIL = 0, []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL.append(name)
        print(f"  ❌ {name} {detail}")


def at(y, mo, d, h, mi=0):
    """epoch of a PKT wall time"""
    return calendar.timegm((y, mo, d, h, mi, 0)) - 5 * 3600


STOCK = next(s for s in sorted(config.BSTOCK_PERP) if s.startswith("NVDA"))
COIN = "SOLUSDT"
W = io.open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()

print("1. the class rule")
check("a tokenized stock is a stock, a coin is not", tr.is_stock(STOCK) and not tr.is_stock(COIN) and not tr.is_stock(None))
check("coin-only bells never ring on a stock", all(not tr.class_ok(k, STOCK) and tr.class_ok(k, COIN) for k in
      ("leg2_prime", "star_takenow", "prime_trig", "confirm_star", "apex_v2_short", "elite_agrade")))
check("stock-only bells never ring on a coin", all(tr.class_ok(k, STOCK) and not tr.class_ok(k, COIN) for k in ("elite_confirm", "conv_revival")))
check("a bell in neither set rings on both (its own switch decides)", all(tr.class_ok(k, STOCK) and tr.class_ok(k, COIN) for k in
      ("elite_star", "star_prime", "conv_prime", "star_trig", "star_apexv2", "anything")))

print("2. the stock line: stock seats only, by PKT window, side and all")
T0 = at(2026, 11, 12, 10)                      # a Thursday, 10:00 PKT -> the 09–13 window
check("no seats yet -> says so, no numbers", tr.stock_line("elite_confirm", "LONG", T0) == "🏦 💎✅ confirmed entries on stocks: no closes yet")
con = ws._open()
rows = [("tok:elite_confirm", STOCK, "LONG", at(2026, 11, 10, 9, 30), 1.0), ("tok:elite_confirm", STOCK, "LONG", at(2026, 11, 11, 10), 0.5),
        ("tok:elite_confirm", STOCK, "SHORT", at(2026, 11, 11, 12), -1.0), ("tok:elite_confirm", STOCK, "LONG", at(2026, 11, 11, 22), -1.0),
        ("elite_confirm", COIN, "LONG", at(2026, 11, 11, 10), 9.0), ("tok:elite_confirm", STOCK, "LONG", at(2026, 11, 11, 10), 7.0)]
for i, (tier, sym, side, o, r) in enumerate(rows):
    con.execute("INSERT INTO shadow_trades (tier, symbol, side, entry, stop, opened_at, status, closed_at, pnl_r) VALUES (?,?,?,?,?,?,?,?,?)",
                (tier, sym, side, 100.0, 96.0, o, "VOID" if i == 5 else "CLOSED", o + 3600, r))
con.execute("INSERT INTO shadow_trades (tier, symbol, side, entry, stop, opened_at, status) VALUES ('tok:elite_confirm', ?, 'LONG', 100, 96, ?, 'OPEN')", (STOCK, T0))
con.commit()
con.close()
tr._STOCK_CACHE.clear()
ln = tr.stock_line("elite_confirm", "LONG", T0)
check("window cell = this PKT window, both sides (2 of 3 won): 67% 🟡", "🏦 🕐 🟡 09–13 PKT 67% / +0.17R (3, thin)" in ln, ln)
check("side cell = this side, every hour (2 of 3 longs won)", "longs 67% / +0.17R (3, thin)" in ln, ln)
check("all cell = every clean stock close (coin seats, VOID and OPEN rows left out)", "all 50% / -0.12R (4, thin)" in ln.replace("−", "-"), ln)
check("the label says stocks and where the record starts", ln.endswith("💎✅ confirmed entries on stocks, desk since 10 Nov"), ln)
check("a window with no closes says so and shows 🟡", "🏦 🕐 🟡 13–17 PKT no closes yet" in tr.stock_line("elite_confirm", "LONG", at(2026, 11, 12, 14)))
check("no crypto wording on a stock line", not re.search(r"crypto|BTC|coin", ln))

print("3. the US session tag")
check("Thursday 21:00 PKT = 11:00 New York -> open", tr.us_session(at(2026, 11, 12, 21)) == "🏛 US market OPEN (regular hours)", tr.us_session(at(2026, 11, 12, 21)))
check("Thursday 10:00 PKT = midnight New York -> closed, overnight", tr.us_session(T0) == "🏛 US market CLOSED · overnight", tr.us_session(T0))
check("pre-market and after-hours are named", tr.us_session(at(2026, 11, 12, 18)) == "🏛 US market CLOSED · pre-market"
      and tr.us_session(at(2026, 11, 13, 3)) == "🏛 US market CLOSED · after-hours", (tr.us_session(at(2026, 11, 12, 18)), tr.us_session(at(2026, 11, 13, 3))))
check("Saturday -> weekend; Thanksgiving -> holiday", tr.us_session(at(2026, 11, 14, 21)) == "🏛 US market CLOSED · weekend"
      and tr.us_session(at(2026, 11, 26, 21)) == "🏛 US market CLOSED · holiday")

print("4. the market tag (BTC against its 50-day)")
tc._MKT.update(t=0.0, below=None, gap=None)
check("no read -> no tag", tr.market_tag("SHORT", T0) == "")
tc._MKT.update(t=T0, below=True, gap=-9.8)
check("BTC below: a short is with the market, a long against it", tr.market_tag("SHORT", T0) == " · 🟢 WITH THE MARKET" and tr.market_tag("LONG", T0) == " · ⚠️ AGAINST THE MARKET")
tc._MKT.update(t=T0, below=False, gap=4.0)
check("BTC above: a long is with it; a short is only noted", tr.market_tag("LONG", T0) == " · 🟢 WITH THE MARKET" and tr.market_tag("SHORT", T0) == " · 🟡 BTC ABOVE ITS 50-DAY")
check("a stale read prints nothing", tr.market_tag("LONG", T0 + 37 * 3600) == "")

print("5. the stock cards carry stock numbers only")
star = {"symbol": STOCK, "base": STOCK.replace("USDT", ""), "side": "LONG", "entry": 100.0, "stop": 96.0, "tp1": 104.0, "tp2": 110.0,
        "tier": "HIGH", "score": 78, "appr": True, "heat": 44}
c1 = tr.stock_star_card(star, 71, T0, partners=("trig_strong",), marks="🔥 *SECOND LEG already on the stock* (09:40 PKT)")
L1 = c1.split("\n")
check("star: header names the stock, TAKE, the PKT time", L1[0] == f"⭐ *ELITE STAR · STOCK — {star['base']} LONG · TAKE · 10:00 PKT*", L1[0])
check("star: plan with R to each target", "entry `100` · SL `96` · TP1 `104` (+1.0R) · TP2 `110` (+2.5R) · HIGH 78 · 🚀 approved" in L1[1], L1[1])
check("star: the mark, the partner, the stock line, the session, what replies", "SECOND LEG already on the stock" in c1 and "with: 💥 STRONG TRIGGER" in c1
      and "🏦 ⭐ stars, every fire on stocks: no closes yet" in c1 and "🏛 US market CLOSED · overnight" in c1 and L1[-1] == "next: ⏱ verdict 11:00 · GO till 14:00 · both reply here", c1)
w = {"symbol": STOCK, "base": star["base"], "side": "LONG", "stop": 96.0, "tp1": 104.0, "tp2": None, "tier": "HIGH", "score": 81, "appr": True}
c2 = tr.stock_confirm_card(w, 99.0, T0, conf=66)
check("confirmed entry: header, the confirm close as the entry, the stock line", c2.split("\n")[0] == f"💎✅ *ELITE CONFIRMED ENTRY · STOCK — {star['base']} LONG · TAKE · 10:00 PKT*"
      and "enter `99` · SL `96` · TP1 `104` (+1.7R) · elite HIGH 81 · 🚀 approved · conf 66" in c2 and "🏦 🕐 🟡 09–13 PKT 67%" in c2, c2)
ew = {"symbol": STOCK, "base": star["base"], "side": "LONG", "stop": 96.0, "tp1": 104.0, "tp2": 110.0, "entry0": 100.0, "oneh": "DEAD", "star": True,
      "fired_at": T0 - 5400, "appr": True}
c3 = tr.stock_go_card(ew, 0.3, 5400, 101.2, T0)
check("GO reply: fast, revived, the plan, R left", c3.split("\n")[0] == f"⭐⚡ *{star['base']} LONG · GO FAST · REVIVED · STOCK · 10:00 PKT*"
      and "fire `100` · SL `96` · TP1 `104` · TP2 `110` · ignited +30% of the path · live `101.2` · 0.7R left to TP1" in c3
      and "90 min after the fire · graded DEAD at the hour, then ignited" in c3 and "⭐⚡ fast star GOs entered at the GO on stocks" in c3, c3)
c3b = tr.stock_go_card(dict(ew, oneh="LIVE"), 0.3, 5 * 3600, 101.2, T0)
check("a late GO shows the star's own stock record", "GO LATE · STOCK" in c3b and "REVIVED" not in c3b and "⭐ stars, every fire on stocks" in c3b, c3b)
c4 = tr.stock_verdict(dict(ew, oneh="LIVE"), 0.4, T0)
check("verdict reply", c4.split("\n")[0] == f"⏱ *{star['base']} LONG · 1H LIVE · STOCK · 10:00 PKT*" and "+40% of the path to TP1 at the hour" in c4, c4)
c5 = tr.stock_revival_card(dict(ew, star=False, appr=False), 0.26, 2 * 3600, 101.0, T0)
check("conviction revival on a stock", c5.split("\n")[0] == f"💎⚡ *CONVICTION REVIVAL · STOCK — {star['base']} LONG · GO FAST · 10:00 PKT*"
      and "unapproved fire" in c5 and "💎⚡ revivals entered at the GO on stocks" in c5, c5)
for nm, c in (("star", c1), ("confirm", c2), ("go", c3), ("verdict", c4), ("revival", c5)):
    check(f"{nm}: nothing coin-measured on a stock card", not re.search(r"crypto|BTC|9 Sep|gated ⭐|🚦", c), c)

print("6. the two new coin cards")
tc._MKT.update(t=T0, below=True, gap=-9.8)
sig = {"symbol": COIN, "base": "SOL", "side": "SHORT", "entry": 100.0, "stop": 103.0, "tp1": 96.0, "tp2": 92.0, "score": 92, "heat": 48}
read = "read: ✅ BTC +0.40% today · ✅ stop 3.0% · ⚠️ 18 PKT (17–21 is the weak window) — gated 61% / +0.33R (129)"
a1 = tr.apex_v2_short_card(sig, 99.5, read, False, at(2026, 11, 12, 18))
A1 = a1.split("\n")
check("APEX V2 short: header with the market side", A1[0] == "🏆🔻 *APEX V2 SHORT — SOL · TAKE · 18:00 PKT · 🟢 WITH THE MARKET*", A1[0])
check("the gate's read is ONE line, with the verdict first", A1[1] == "gate: ⚠️ NOT PASSED · ✅ BTC +0.40% today · ✅ stop 3.0% · ⚠️ 18 PKT (17–21 is the weak window)", A1[1])
check("a passed gate says so", tr.apex_v2_short_card(sig, 99.5, read, True, T0).split("\n")[1].startswith("gate: ✅ PASSED · ✅ BTC"))
check("plan at the live price with R", A1[2] == "entry `100` · live `99.5` · SL `103` · TP1 `96` (+1.0R) · TP2 `92` (+2.1R) · score 92 · heat 48", A1[2])
check("its own window cell and period", A1[3] == "🕐 🟢 17–21 shorts 74% / +0.58R (27) · 🏆🔻 APEX V2 shorts, every fire · 23 Sep → 16 Nov", A1[3])
check("the record says longs do not ring; the verdict replies; the gatekeeper line closes it", "longs 41% / −0.04R (123) do not ring" in A1[4]
      and "⏱ 1h verdict replies here" in A1[4] and A1[5].startswith("🚦 *GATE → ") and "✅ APEX V2 shorts 62% / +0.30R (84)" in A1[5], A1[4:])
check("21–01 is the red window", "🕐 🔴 21–01 shorts 36% / -0.40R (14)" in tr.apex_v2_short_card(sig, 99.5, read, True, at(2026, 11, 12, 22)).replace("−", "-"))
wc = {"symbol": COIN, "base": "SOL", "side": "LONG", "stop": 96.0, "tp1": 104.0, "tp2": None}
a2 = tr.confirm_star_card(wc, 99.0, at(2026, 11, 12, 18), at(2026, 11, 12, 16, 30), conf=70)
check("confirmed after a gated star: no TAKE word, the star's time, the honest record", "TAKE" not in a2.split("\n")[0]
      and a2.split("\n")[0] == "💎✅⭐ *CONFIRMED ENTRY after a GATED STAR — SOL LONG · 18:00 PKT · ⚠️ AGAINST THE MARKET*"
      and "⭐ gated star fired 16:30 PKT (90 min ago)" in a2 and "🕐 🔴 17–21 both sides 41% / -0.33R (17)" in a2.replace("−", "-")
      and "all hours 48% / −0.21R (33)" in a2 and "🔴 confirmed after a gated star 48% / −0.21R (33)" in a2, a2)
check("old tables keep their period; a table with its own period prints it", tc.stamp("elite_star", "LONG", T0).endswith("· 9 Sep → 4 Nov")
      and tc.stamp("confirm_star", None, T0).endswith("· 14 Oct → 13 Nov"))
check("every table has three fields; the two new ones name their own period", all(len(v) == 3 for v in tc.TABLES.values())
      and tc.PERIOD == {"apex_v2_short": "23 Sep → 16 Nov", "confirm_star": "14 Oct → 13 Nov"})


class FakeStore:
    def __init__(self, rows):
        self.rows = rows

    def recent_by_stream(self, stream, n):
        return [r for r in self.rows if r["stream"] == stream][:n]


now = at(2026, 11, 12, 18)
fs = FakeStore([{"stream": "elite_star", "symbol": COIN, "side": "LONG", "ts": now - 3600, "extra": '{"gate": "muted"}'},
                {"stream": "elite_star", "symbol": COIN, "side": "LONG", "ts": now - 2 * 3600, "extra": '{"gate": "pass"}'},
                {"stream": "elite_star", "symbol": COIN, "side": "LONG", "ts": now - 8 * 3600, "extra": '{"gate": "1317-pass"}'},
                {"stream": "elite_star", "symbol": COIN, "side": "SHORT", "ts": now - 600, "extra": '{"gate": "pass"}'},
                {"stream": "elite_star", "symbol": "XRPUSDT", "side": "LONG", "ts": now - 600, "extra": "not json"}])
check("gated star look-back: the latest PASSED star on this coin + side inside 6h", tr.gated_star_ts(fs, COIN, "LONG", now) == now - 2 * 3600
      and tr.gated_star_ts(fs, COIN, "SHORT", now) == now - 600 and tr.gated_star_ts(fs, "XRPUSDT", "LONG", now) is None
      and tr.gated_star_ts(FakeStore([fs.rows[0], fs.rows[2]]), COIN, "LONG", now) is None)

print("7. the rang-bell log, the burst read and the TP1 ping")
check("the row carries the bell's key in tier and the plan", tr.bell_row("elite_star", dict(star, junk=1)) == {"symbol": STOCK, "base": star["base"], "side": "LONG",
      "tier": "elite_star", "entry": 100.0, "stop": 96.0, "tp1": 104.0, "tp2": 110.0})
nowg = __import__("time").time()
for sy in ("B1USDT", "B2USDT"):
    ws.record_signal(tr.BELL, tr.bell_row("leg2_prime", {"symbol": sy, "side": "SHORT"}), ts=nowg - 600)
ws.record_signal("star_prime", {"symbol": "B9USDT", "side": "SHORT"}, ts=nowg - 600)      # a record of a bell that is off: not a bell
check("the gatekeeper counts rung bells only", tc.BELL_STREAMS == (tr.BELL,) and ws.bell_burst("SHORT", nowg - 7200, tc.BELL_STREAMS, "ZZZUSDT") == 2
      and ws.bell_burst("SHORT", nowg - 7200, tc.BELL_STREAMS, "B1USDT") == 1 and ws.bell_burst("LONG", nowg - 7200, tc.BELL_STREAMS, "ZZZUSDT") == 0)
got = [r for r in ws.recent_by_stream(tr.BELL, 10)]
check("the log reads back with the key in tier", len(got) == 2 and {r["tier"] for r in got} == {"leg2_prime"})
check("TP1 ping set: every bell on the roster (user 2026-11-17: 'add tp1 ones to the ones that rings')",
      tr.TP1_PING == {"elite_star", "elite_agrade", "elite_confirm", "leg2_prime", "prime_trig", "confirm_star", "kr_premium",
                      "apex_v2_short", "conv_revival", "star_takenow"}
      and tr.ping_stamp("apex_v2_short", COIN, "SHORT", T0).startswith("\n🕐 ") and tr.ping_stamp("star_takenow", COIN, "LONG", T0).startswith("\n🕐 ")
      and tr.ping_stamp("conv_revival", STOCK, "LONG", T0).startswith("\n🏦 "))
check("ping stamp: a coin prints the old coin cell, a stock its stock line", tr.ping_stamp("elite_star", COIN, "LONG", T0) == tc.stamp_src("elite_star", "LONG", T0)
      and tr.ping_stamp("elite_confirm", STOCK, "LONG", T0).startswith("\n🏦 🕐 ") and tr.ping_stamp("elite_agrade", COIN, "LONG", T0) == "")

print("8. the switches")
d = ts.code_defaults()
check("every switch is a module-level True / False in the worker", set(d) == set(ts.FLAGS) and len(ts.FLAGS) == len(set(ts.FLAGS)), sorted(set(ts.FLAGS) - set(d)))
want = {"TG_CONFIRM_STOCK": True, "TG_STAR_STOCK": True, "TG_CONV_REVIVAL": True, "TG_AGRADE": True, "TG_LEG2_PRIME": True, "TG_PRIME_TRIG": True,
        "TG_STAR_TAKENOW": True, "TG_APEX_V2_SHORT": True, "TG_KR_PREMIUM": False, "TG_CONFIRM_STAR": False, "TG_STAR_PRIME": False, "TG_STAR_TRIG": False,
        "TG_STAR_APEXV2": False, "TG_CONV_PRIME": False, "TG_APEX_V2_GATED": False, "TG_GO_LIVE": False, "TG_TRIGKR_PRIME": False, "TG_ARRIVAL_T1": False,
        "TG_NEAR90": False, "TG_FREEZE": False}
check("the roster's defaults", d == want, {k: (d.get(k), v) for k, v in want.items() if d.get(k) != v})
check("the star's gate and the 13–17 window", re.search(r"^TG_GATES = True$", W, re.M) and re.search(r"^STAR_UNGATED_1317 = True\b", W, re.M))
tmp = tempfile.mkdtemp(prefix="tgsw_")
ts._state_dir = lambda: tmp
io.open(os.path.join(tmp, ts.FILE), "w", encoding="utf-8").write('{"TG_STAR_PRIME": true}')
check("a switches file from before this roster is ignored", ts.overrides() == {})
check("a flip made now is kept and tagged", ts.set_switch("TG_CONFIRM_STAR", True) and ts.overrides() == {"TG_CONFIRM_STAR": True}
      and '"_roster": "2026-11-17"' in io.open(os.path.join(tmp, ts.FILE), encoding="utf-8").read())
mod = types.SimpleNamespace(TG_CONFIRM_STAR=False, TG_AGRADE=True)
check("the worker applies it", ts.apply(mod) == {"TG_CONFIRM_STAR": True} and mod.TG_CONFIRM_STAR is True and mod.TG_AGRADE is True)
con = ws._open()
con.execute("INSERT INTO shadow_trades (tier, symbol, side, opened_at, status, closed_at, pnl_r) VALUES ('apex_v2','A','SHORT',?, 'CLOSED', ?, 1.0)", (nowg - 9000, nowg - 3600))
con.execute("INSERT INTO shadow_trades (tier, symbol, side, opened_at, status, closed_at, pnl_r) VALUES ('apex_v2','B','LONG',?, 'CLOSED', ?, -1.0)", (nowg - 9000, nowg - 3600))
rec = ts.records(con, nowg)
con.close()
check("the APEX V2 shorts record is the tier cut to its shorts", rec["apex_v2:short"]["all"]["n"] == 1 and rec["apex_v2:short"]["all"]["win"] == 1.0
      and rec["elite_confirm"]["tok"]["n"] == 4 and rec["elite_confirm"]["all"]["n"] == 1)
check("every listed bell has a record cell or none by design", all((r["tier"] in rec) or r["tier"] is None for r in ts.status()))

print("9. the worker's wiring")
check("imports the roster", "\nimport tg_roster " in W)
check("stock star: its own card, rings past the gate, marks before the read on a coin card",
      "_msg9 = _skc9 + ((\"\\n\" + _krs9) if _krs9 else \"\")" in W and "_free9 = bool(_star9 and _stk9 and TG_STAR_STOCK)" in W
      and "elif _star9 and TG_GATES and not _gate9[0] and not _w1317 and not _free9:" in W and "if not _stk9:   # 🏦 a stock card keeps to stock numbers" in W
      and "_w1317 = (_star9 and not _stk9 and STAR_UNGATED_1317" in W)
check("A-grade: its switch and coins only", 'if not _star9 and not (TG_AGRADE and tg_roster.class_ok(\n                                "elite_agrade", _pmx.get("symbol"))):' in W)
check("confirmed entry: stock bell and the gated-star bell, the old coin bell still muted", "if TG_CONFIRM_STOCK:" in W and "elif TG_CONFIRM_STAR:" in W
      and W.count("ok, _ = _mute_ecf(") == 1 and "💎✅ *ELITE CONFIRMED ENTRY* — {_w9['base']}" in W)
check("pairs and PRIME × trigger follow the class rule", '"class-out" if not tg_roster.class_ok(_tier_pp, _sym_pp) else' in W
      and 'if (TG_PRIME_TRIG and tg_roster.class_ok("prime_trig", _sym_pt)' in W)
check("APEX V2: shorts bell, never two bells for one fire", 'if (TG_APEX_V2_SHORT and _sd2 == "SHORT" and tg_roster.class_ok("apex_v2_short", _sym2)' in W
      and "if TG_APEX_V2_GATED and not _srang2 and not _bstock_quiet(_sym2):" in W)
check("conviction revival: stocks only, the coin bell intact behind it", W.index('"conv_revival", _ew.get("symbol")))):') < W.index("tg_roster.stock_revival_card(")
      < W.index("# 💎 CONVICTION REVIVAL — its own bell (user 2026-11-07") and "_fmt_conv_revival(\n" in W)
check("stock replies: verdict and GO", "tg_roster.stock_verdict(_ew, _prg, _ew_now)" in W and "tg_roster.stock_go_card(" in W
      and W.count("and not _stk_go:") == 2)
i0 = W.index("        _rg_watch = []")
blk = W[i0:i0 + 1700]
check("TP1 ping: the rang-bell log cut to TP1_PING, with the 48h bridge", "store.recent_by_stream(tg_roster.BELL, 150)" in blk and "in tg_roster.TP1_PING]" in blk
      and "for _rg_stream in TP1_STREAMS:" not in W and ">= ROSTER_TS:" in blk and "tg_roster.ping_stamp(_rg_src, _rg_sym, _rg_side, _rg_ts)" in W)
check("every rung entry bell writes the log (star / A-grade, confirm, pairs, PRIME × trigger, APEX V2 short, KR premium, stock revival)", W.count("_tg_rang(") == 8, W.count("_tg_rang("))
check("the gatekeeper line count on the old cards is unchanged", W.count("tg_cells.gate_note(") == 5, W.count("tg_cells.gate_note("))
m = re.search(r"^ROSTER_TS = (\d+)\b", W, re.M)
check("the cut-over stamp is a real epoch on 16–17 Nov 2026 UTC", bool(m) and calendar.timegm((2026, 11, 16, 0, 0, 0)) < int(m.group(1)) < calendar.timegm((2026, 11, 18, 0, 0, 0)))

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("FAIL:", f)
sys.exit(1 if FAIL else 0)
