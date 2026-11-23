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
      ("leg2_prime", "star_takenow", "prime_trig", "confirm_star", "apex_v2_short", "apex_v2_long", "elite_agrade")))
check("no bell is stock-only since 23 Nov: the confirmed entry and the conviction revival ring on both classes (own switches)",
      tr.STOCK_ONLY == frozenset() and all(tr.class_ok(k, STOCK) and tr.class_ok(k, COIN) for k in ("elite_confirm", "conv_revival")))
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

print("4b. the record since the stop rule (2026-11-23): live from the desk, by tier and class")
con = ws._open()
for tier, sym, side, o, r in [
        ("tok:elite_confirm", STOCK, "LONG", at(2026, 11, 18, 22), 1.0), ("tok:elite_confirm", STOCK, "SHORT", at(2026, 11, 19, 22), 0.6),
        ("tok:elite_confirm", STOCK, "LONG", at(2026, 11, 19, 14), 0.4), ("tok:elite_confirm", STOCK, "LONG", at(2026, 11, 20, 6), -1.0),
        ("tok:elite_confirm", STOCK, "LONG", at(2026, 11, 17, 19), 3.0),        # 19:00 PKT on 17 Nov: before the rule went live
        ("elite_confirm", COIN, "SHORT", at(2026, 11, 19, 22), 0.6), ("elite_confirm", COIN, "LONG", at(2026, 11, 20, 10), -1.0),
        ("go_revived", COIN, "SHORT", at(2026, 11, 19, 18), 0.4),
        ("apex_v2", COIN, "SHORT", at(2026, 11, 19, 18), 0.5), ("apex_v2", COIN, "SHORT", at(2026, 11, 20, 18, 30), 0.7),
        ("apex_v2", COIN, "SHORT", at(2026, 11, 20, 23), -1.0), ("apex_v2", COIN, "LONG", at(2026, 11, 21, 18), -1.0)]:
    con.execute("INSERT INTO shadow_trades (tier, symbol, side, entry, stop, opened_at, status, closed_at, pnl_r) VALUES (?,?,?,?,?,?,?,?,?)",
                (tier, sym, side, 100.0, 96.0, o, "CLOSED", o + 3600, r))
con.commit()
con.close()
tr._SINCE_CACHE.clear()
T1 = at(2026, 11, 21, 22)                      # 22:00 PKT -> the 21–01 window
check("the rule went live 17 Nov 20:08 PKT", tr.RULE_SINCE_TS == at(2026, 11, 17, 20, 8))
# ⏪⏩ the before / after block: the bell's own tier, class and side; lights; a thin record keeps its colour and says
# (n, thin); never green on a loss; white only when there is no closed trade
con = ws._open()
for i in range(12):                            # PRIME × trigger shorts before the rule: 9 of 12 won
    con.execute("INSERT INTO shadow_trades (tier, symbol, side, entry, stop, opened_at, status, closed_at, pnl_r) VALUES ('prime_trig',?, 'SHORT',100,104,?, 'CLOSED',?,?)",
                (COIN, at(2026, 11, 5, 9) + i * 600, at(2026, 11, 5, 12), 1.0 if i < 9 else -1.0))
for i in range(10):                            # … and after it: 8 of 10 won, small wins, the record lost money
    con.execute("INSERT INTO shadow_trades (tier, symbol, side, entry, stop, opened_at, status, closed_at, pnl_r) VALUES ('prime_trig',?, 'SHORT',100,104,?, 'CLOSED',?,?)",
                (COIN, at(2026, 11, 19, 22) + i * 60, at(2026, 11, 19, 23), 0.1 if i < 8 else -1.0))
for j, g in enumerate(("pass", "muted")):      # two coin star longs before the rule: one gated, one not
    t_ = at(2026, 11, 6, 10) + j * 7200
    con.execute("INSERT INTO shadow_trades (tier, symbol, side, entry, stop, opened_at, status, closed_at, pnl_r) VALUES ('elite_star',?, 'LONG',100,96,?, 'CLOSED',?,1.0)",
                (COIN, t_, t_ + 3600))
    con.execute("INSERT INTO signals (ts, stream, symbol, base, side, extra) VALUES (?, 'elite_star', ?, 'SOL', 'LONG', ?)", (t_ - 5, COIN, '{"gate": "%s"}' % g))
con.commit()
con.close()
tr._BELL_CACHE.clear()
BA = tr.before_after("prime_trig", COIN, "SHORT", T1)
check("before / after: this bell's side, each line with its light; a winning rate on a losing record is yellow, never green",
      BA == "⏪ before the stop change: 🟢 shorts 75% / +0.50R (12)\n⏩ after the stop change (17 Nov): 🟡 shorts 80% / -0.12R (10) · 21–01 PKT 🟡 80% (10)", BA)
check("the window cell is left off when this window has no trade since the rule; a side with no trade says so in white",
      tr.before_after("prime_trig", COIN, "SHORT", T0).endswith("⏩ after the stop change (17 Nov): 🟡 shorts 80% / -0.12R (10)")
      and tr.before_after("prime_trig", COIN, "LONG", T1) == "⏪ before the stop change: ⚪ longs no closes yet\n⏩ after the stop change (17 Nov): ⚪ longs no closes yet")
check("under ten trades the light keeps its colour and the text says thin (user: 'mark this green instead of grey just write (thin)'); coin and stock seats never mix",
      tr.before_after("elite_confirm", COIN, "SHORT", T1) == "⏪ before the stop change: ⚪ shorts no closes yet\n"
      "⏩ after the stop change (17 Nov): 🟢 shorts 100% / +0.60R (1, thin) · 21–01 PKT 🟢 100% (1, thin)"
      and tr.before_after("elite_confirm", STOCK, "LONG", T1) == "⏪ before the stop change: 🟢 longs 75% / +0.88R (4, thin)\n"      # incl. the 17 Nov 19:00 seat
      "⏩ after the stop change (17 Nov): 🟡 longs 67% / +0.13R (3, thin) · 21–01 PKT 🟢 100% (1, thin)",
      (tr.before_after("elite_confirm", COIN, "SHORT", T1), tr.before_after("elite_confirm", STOCK, "LONG", T1)))
check("APEX V2: the short bell reads the shorts, the long bell the longs, both from the one tier",
      tr.before_after("apex_v2_short", COIN, "SHORT", T1).endswith("🟡 shorts 67% / +0.07R (3, thin) · 21–01 PKT 🔴 0% (1, thin)")
      and tr.before_after("apex_v2_long", COIN, "LONG", T1).endswith("🔴 longs 0% / -1.00R (1, thin)"), tr.before_after("apex_v2_short", COIN, "SHORT", T1))
check("the coin star is cut to its gated fires; a bell with no desk tier gets no block",
      tr.before_after("elite_star", COIN, "LONG", T1).startswith("⏪ before the stop change: 🟢 longs 100% / +1.00R (1, thin)")
      and tr.before_after("kr_premium", COIN, "LONG", T1) == "" and tr.before_after(None, COIN, "LONG", T1) == "")
_c0 = "💥🥇 *PRIME × STRONG TRIGGER — SOL SHORT*\nentry `100` · SL `104` · TP1 `96`"
_c1 = tr.with_record(_c0, {"symbol": COIN, "side": "SHORT"}, "prime_trig", T1)
check("with_record: the block goes at the foot, once, and the card above it is untouched",
      _c1 == _c0 + "\n" + BA and tr.with_record(_c1, {"symbol": COIN, "side": "SHORT"}, "prime_trig", T1) == _c1
      and tr.with_record(_c0, {"symbol": COIN, "side": "SHORT"}, None, T1) == _c0)
WIN_S = "🕐 by window since 17 Nov: 21–01 100% (2) · 13–17 100% (1) · 05–09 0% (1)"
check("the windows list: every window with a trade since the rule, best first", tr.since_rule_windows("elite_confirm", STOCK, T1) == WIN_S
      and tr.since_rule_windows("elite_star", STOCK, T1) == "", tr.since_rule_windows("elite_confirm", STOCK, T1))

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
      and "enter `99` · SL `96` · TP1 `104` (+1.7R) · elite HIGH 81 · 🚀 approved · conf 66" in c2
      and c2.split("\n")[3] == WIN_S and "desk since 10 Nov" not in c2 and "📊" not in c2 and len(c2.split("\n")) == 5, c2)
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
check("no fixed 23 Sep → 16 Nov lines on the card (its record is the ⏪ / ⏩ block the worker adds)", "23 Sep" not in a1 and "do not ring" not in a1 and "📊" not in a1)
check("the verdict replies; the gatekeeper line closes it", A1[3] == "⏱ 1h verdict replies here" and A1[4].startswith("🚦 *GATE → ")
      and "✅ APEX V2 shorts paid before the stop change" in A1[4] and len(A1) == 5, A1[3:])
sigL = dict(sig, side="LONG", stop=97.0, tp1=104.0, tp2=108.0)
aL = tr.apex_v2_card(sigL, 100.5, read, True, at(2026, 11, 12, 18)).split("\n")
check("APEX V2 LONG rings too: its own header, its own side's record, the gatekeeper's long read", aL[0] == "🏆🔺 *APEX V2 LONG — SOL · TAKE · 18:00 PKT · ⚠️ AGAINST THE MARKET*"
      and aL[3] == "⏱ 1h verdict replies here" and aL[4].startswith("🚦 *GATE → SMALL*") and "🔴 APEX V2 longs lost before the stop change" in aL[4]
      and len(aL) == 5, aL)
check("the old card name is the same card", tr.apex_v2_short_card(sig, 99.5, read, False, at(2026, 11, 12, 18)) == tr.apex_v2_card(sig, 99.5, read, False, at(2026, 11, 12, 18)))
wk = {"symbol": COIN, "base": "SOL", "side": "SHORT", "stop": 103.0, "tp1": 96.0, "tp2": None, "tier": "HIGH", "score": 84, "appr": True}
k1 = tr.coin_confirm_card(wk, 100.0, at(2026, 11, 12, 22), conf=68).split("\n")
check("coin confirmed entry: header with the market side, the plan, the gatekeeper (the record block is added by the worker)",
      k1[0] == "💎✅ *ELITE CONFIRMED ENTRY — SOL SHORT · TAKE · 22:00 PKT · 🟢 WITH THE MARKET*"
      and k1[1] == "enter `100` · SL `103` · TP1 `96` (+1.3R) · elite HIGH 84 · 🚀 approved · conf 68"
      and k1[3].startswith("🚦 *GATE → ") and "🟡 a break-even stream before the stop change" in k1[3] and len(k1) == 4, k1)
ewk = {"symbol": COIN, "base": "SOL", "side": "SHORT", "stop": 103.0, "tp1": 96.0, "tp2": 92.0, "entry0": 100.0, "oneh": "DEAD", "star": False, "appr": True}
k2 = tr.coin_revival_card(ewk, 0.27, 2 * 3600, 98.9, at(2026, 11, 12, 18)).split("\n")
check("coin conviction revival: header, the fire plan with R left, the gatekeeper's hold read (the record block is added by the worker)",
      k2[0] == "💎⚡ *CONVICTION REVIVAL — SOL SHORT · GO FAST · 18:00 PKT · 🟢 WITH THE MARKET*"
      and k2[1] == "fire `100` · SL `103` · TP1 `96` · TP2 `92` · ignited +27% of the path · live `98.9` · 1.0R left to TP1"
      and k2[2] == "graded DEAD at the hour, then ignited · 120 min after the fire"
      and k2[3].startswith("🚦 *GATE → HALF*") and "🔴 entered at the GO ≈ 0R: a hold read" in k2[3] and len(k2) == 4, k2)
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
                      "apex_v2_short", "apex_v2_long", "conv_revival", "star_takenow"}
      and tr.ping_stamp("apex_v2_short", COIN, "SHORT", T0).startswith("\n🕐 ") and tr.ping_stamp("star_takenow", COIN, "LONG", T0).startswith("\n🕐 ")
      and tr.ping_stamp("conv_revival", STOCK, "LONG", T0).startswith("\n🏦 "))
check("ping stamp: a coin prints the old coin cell, a stock its stock line", tr.ping_stamp("elite_star", COIN, "LONG", T0) == tc.stamp_src("elite_star", "LONG", T0)
      and tr.ping_stamp("elite_confirm", STOCK, "LONG", T0).startswith("\n🏦 🕐 ") and tr.ping_stamp("elite_agrade", COIN, "LONG", T0) == "")

print("8. the switches")
d = ts.code_defaults()
check("every switch is a module-level True / False in the worker", set(d) == set(ts.FLAGS) and len(ts.FLAGS) == len(set(ts.FLAGS)), sorted(set(ts.FLAGS) - set(d)))
want = {"TG_CONFIRM_STOCK": True, "TG_STAR_STOCK": True, "TG_CONV_REVIVAL": True, "TG_AGRADE": False, "TG_LEG2_PRIME": True, "TG_PRIME_TRIG": True,      # A-grade muted 2026-11-23
        "TG_STAR_TAKENOW": True, "TG_APEX_V2_SHORT": True, "TG_KR_PREMIUM": False, "TG_CONFIRM_STAR": False, "TG_STAR_PRIME": False, "TG_STAR_TRIG": False,
        "TG_STAR_APEXV2": False, "TG_CONV_PRIME": False, "TG_APEX_V2_GATED": False, "TG_GO_LIVE": False, "TG_TRIGKR_PRIME": False, "TG_ARRIVAL_T1": False,
        "TG_NEAR90": False, "TG_FREEZE": False,
        "TG_APEX_V2_LONG": True, "TG_CONFIRM_COIN": True, "TG_CONV_REVIVAL_COIN": True}      # the three coin bells of 2026-11-23
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
check("the APEX V2 record is the tier cut to one side: shorts and, since 23 Nov, longs (the seats of section 4b are in the same ledger)",
      rec["apex_v2:short"]["all"]["n"] == 4 and rec["apex_v2:short"]["all"]["win"] == 0.75
      and rec["apex_v2:long"]["all"]["n"] == 2 and rec["apex_v2:long"]["all"]["win"] == 0.0
      and rec["elite_confirm"]["tok"]["n"] == 9 and rec["elite_confirm"]["all"]["n"] == 3, {k: rec[k]["all"] for k in ("apex_v2:short", "apex_v2:long", "elite_confirm")})
check("every listed bell has a record cell or none by design", all((r["tier"] in rec) or r["tier"] is None for r in ts.status()))

print("9. the worker's wiring")
check("imports the roster", "\nimport tg_roster " in W)
check("stock star: its own card, rings past the gate, marks before the read on a coin card",
      "_msg9 = _skc9 + ((\"\\n\" + _krs9) if _krs9 else \"\")" in W and "_free9 = bool(_star9 and _stk9 and TG_STAR_STOCK)" in W
      and "elif _star9 and TG_GATES and not _gate9[0] and not _w1317 and not _free9:" in W and "if not _stk9:   # 🏦 a stock card keeps to stock numbers" in W
      and "_w1317 = (_star9 and not _stk9 and STAR_UNGATED_1317" in W)
check("A-grade: its switch and coins only", 'if not _star9 and not (TG_AGRADE and tg_roster.class_ok(\n                                "elite_agrade", _pmx.get("symbol"))):' in W)
check("confirmed entry: stock bell, the coin bell of 23 Nov ahead of the gated-star bell, the old coin text still muted", "if TG_CONFIRM_STOCK:" in W
      and W.index("elif TG_CONFIRM_COIN:") < W.index("elif TG_CONFIRM_STAR:") and "tg_roster.coin_confirm_card(" in W
      and W.count("ok, _ = _mute_ecf(") == 1 and "💎✅ *ELITE CONFIRMED ENTRY* — {_w9['base']}" in W)
check("pairs and PRIME × trigger follow the class rule", '"class-out" if not tg_roster.class_ok(_tier_pp, _sym_pp) else' in W
      and 'if (TG_PRIME_TRIG and tg_roster.class_ok("prime_trig", _sym_pt)' in W)
check("APEX V2: shorts and longs each on its own switch and key, never two bells for one fire",
      '_v2key = "apex_v2_short" if _sd2 == "SHORT" else "apex_v2_long"' in W
      and 'if ((TG_APEX_V2_SHORT if _sd2 == "SHORT" else (TG_APEX_V2_LONG and _sd2 == "LONG"))' in W
      and "and tg_roster.class_ok(_v2key, _sym2) and not _bstock_quiet(_sym2)):" in W and "_tg_rang(_v2key, _sig2)" in W
      and "if TG_APEX_V2_GATED and not _srang2 and not _bstock_quiet(_sym2):" in W)
check("conviction revival: each class on its own switch; the coin card, then the stock card; the old gated coin bell kept behind them",
      W.index("TG_CONV_REVIVAL if tg_roster.is_stock(_ew.get(\"symbol\"))") < W.index("tg_roster.coin_revival_card(") < W.index("tg_roster.stock_revival_card(")
      < W.index("# 💎 CONVICTION REVIVAL — its own bell (user 2026-11-07") and "else TG_CONV_REVIVAL_COIN)):" in W and "_fmt_conv_revival(\n" in W
      and W.count('_tg_rang("conv_revival", dict(_ew, entry=_ew_px))') == 2)
check("stock replies: verdict and GO", "tg_roster.stock_verdict(_ew, _prg, _ew_now)" in W and "tg_roster.stock_go_card(" in W
      and W.count("and not _stk_go:") == 2)
i0 = W.index("        _rg_watch = []")
blk = W[i0:i0 + 1700]
check("TP1 ping: the rang-bell log cut to TP1_PING, with the 48h bridge", "store.recent_by_stream(tg_roster.BELL, 150)" in blk and "in tg_roster.TP1_PING]" in blk
      and "for _rg_stream in TP1_STREAMS:" not in W and ">= ROSTER_TS:" in blk and "tg_roster.ping_stamp(_rg_src, _rg_sym, _rg_side, _rg_ts)" in W)
check("every rung entry bell writes the log (star / A-grade, confirm, pairs, PRIME × trigger, APEX V2 both sides, KR premium, coin revival, stock revival)", W.count("_tg_rang(") == 9, W.count("_tg_rang("))
check("the gatekeeper line count on the old cards is unchanged", W.count("tg_cells.gate_note(") == 5, W.count("tg_cells.gate_note("))
m = re.search(r"^ROSTER_TS = (\d+)\b", W, re.M)
check("the cut-over stamp is a real epoch on 16–17 Nov 2026 UTC", bool(m) and calendar.timegm((2026, 11, 16, 0, 0, 0)) < int(m.group(1)) < calendar.timegm((2026, 11, 18, 0, 0, 0)))

# 🛡 THE STOP RULE (2026-11-17): coins the 4h rule, stocks the 15m rule; the bell's SL is swapped and one line added
import stop_rule as sr          # noqa: E402
check("the rule's fetch is off outside the worker; coins read 4h, tokenized stocks 15m", sr.LIVE is False and sr.RULE_ON is True
      and sr.rule_of("SOLUSDT") == "4h" and sr.rule_of(sorted(config.TOKENIZED_STOCKS)[0]) == "15m" and sr.SPEC["coin"][2] == 30 and sr.SPEC["stock"][2] == 96)
flat = [(101.0, 99.0, 100.0)] * 30                                   # candles as (high, low, close); ATR 2 → buffer 0.5
bars = list(flat)
bars[10] = (101.0, 94.0, 100.0)                                      # a swing low at 94, under the plan stop 96
got = sr.rule_stop("LONG", 100.0, 96.0, bars)
atr14 = sum(max(bars[i][0] - bars[i][1], abs(bars[i][0] - bars[i - 1][2]), abs(bars[i][1] - bars[i - 1][2])) for i in range(16, 30)) / 14
check("rule stop, long: a quarter ATR under the nearest swing low at or under the plan stop", bool(got) and abs(got[0] - (94.0 - 0.25 * atr14)) < 1e-9
      and got[1] == 94.0 and got[2] is False, got)
bars2 = list(flat)
bars2[10] = (101.0, 97.5, 100.0)                                     # a swing low ABOVE the plan stop is not the mark
bars2[20] = (101.0, 80.0, 100.0)                                     # a far one: past the 8% limit
got2 = sr.rule_stop("LONG", 100.0, 96.0, bars2)
check("rule stop: never further than 8% from the entry", bool(got2) and abs(got2[0] - 92.0) < 1e-9 and got2[2] is True and got2[1] == 80.0, got2)
got3 = sr.rule_stop("LONG", 100.0, 96.0, flat)
check("rule stop: no swing under the plan stop → a quarter ATR under the plan stop itself", bool(got3) and got3[1] == 96.0 and abs(got3[0] - 95.5) < 1e-9, got3)
sbars = list(flat)
sbars[12] = (106.0, 99.0, 100.0)
got4 = sr.rule_stop("SHORT", 100.0, 104.0, sbars)
check("rule stop, short: a quarter ATR over the nearest swing high at or over the plan stop", bool(got4) and got4[1] == 106.0 and got4[0] > 106.0 and got4[2] is False, got4)
check("rule stop: too few candles, a stop on the wrong side or a zero price give nothing",
      sr.rule_stop("LONG", 100.0, 96.0, flat[:10]) is None and sr.rule_stop("LONG", 100.0, 104.0, flat) is None and sr.rule_stop("LONG", 0, 96.0, flat) is None)
check("for_signal: nothing without candles while the fetch is off; the dict when bars are given",
      sr.for_signal("SOLUSDT", "LONG", 100.0, 96.0) is None and sr.for_signal("SOLUSDT", "LONG", 100.0, 96.0, bars=bars)["rule"] == "4h"
      and abs(sr.for_signal("SOLUSDT", "LONG", 100.0, 96.0, bars=bars)["stop"] - got[0]) < 1e-9)
import pandas as pd          # noqa: E402
NOW_W = 1794900000.0
idx = pd.to_datetime([NOW_W - 4 * 3600 * (30 - i) - 3600 for i in range(31)], unit="s")          # the last candle is still forming
kl = pd.DataFrame({"high": [b[0] for b in bars] + [150.0], "low": [b[1] for b in bars] + [50.0], "close": [b[2] for b in bars] + [100.0]}, index=idx)
check("closed_bars drops the forming candle", len(sr.closed_bars(kl, NOW_W, 14400)) == 30 and sr.closed_bars(kl, NOW_W, 14400)[-1] == bars[-1])
_calls = []
sr.LIVE, sr.FETCH = True, (lambda sym, iv, limit=0: (_calls.append((sym, iv, limit)) or kl))
sr._MEMO.clear()
a1 = sr.for_signal("SOLUSDT", "LONG", 100.0, 96.0, now=NOW_W)
a2 = sr.for_signal("SOLUSDT", "LONG", 100.0, 96.0, now=NOW_W + 60)
check("for_signal fetches the rule's timeframe once and keeps it for ten minutes", bool(a1) and abs(a1["stop"] - got[0]) < 1e-9 and a2 == a1 and _calls == [("SOLUSDT", "4h", 45)], _calls)
sr.LIVE, sr.FETCH = False, None
sr._MEMO.clear()
tr._RULE_LAST.clear()
sig_c = {"symbol": "SOLUSDT", "base": "SOL", "side": "LONG", "entry": 100.0, "stop": 96.0, "tp1": 106.0}
card = "⭐ *ELITE STAR — SOL LONG*\nentry `100` · SL `96` · TP1 `106` (+1.5R)\nrecord line"
out = tr.rule_card(card, sig_c, a1, "elite_star", NOW_W)
REPLAY_C = "🧪 replay on this stop (to 16 Nov, candles): 71% / +0.17R (106)"
check("rule card, coin: the rule's stop is carried in the card's own SL, TP1's R is re-cut on it, and no stop line is added",
      out == "⭐ *ELITE STAR — SOL LONG*\nentry `100` · SL `93.5` · TP1 `106` (+0.9R)\nrecord line\n" + REPLAY_C and "🛡" not in out, out)
check("rule card, coin: exactly one line is added, the candle replay of the bell on this stop", out.count("\n") == card.count("\n") + 1 and out.endswith(REPLAY_C), out)
tr.rule_card(card, sig_c, a1, "elite_star", __import__("time").time())      # the row is read within 15 minutes of the bell
row = tr.bell_row("elite_star", sig_c)
check("the bell's row keeps the plan stop and carries the stop it printed", row["stop"] == 96.0 and abs(row.get("rule_stop", 0) - 93.5) < 1e-9 and row.get("rule") == "4h"
      and "rule_stop" not in tr.bell_row("elite_star", dict(sig_c, symbol="ETHUSDT")), row)
check("a thread reply under that bell prints the bell's stop", tr.rule_reply("fire `100` · SL `96` · TP1 `106`", "SOLUSDT", "LONG") == "fire `100` · SL `93.5` · TP1 `106`"
      and tr.rule_reply("fire `100` · SL `96` · TP1 `106`", "ETHUSDT", "LONG") == "fire `100` · SL `96` · TP1 `106`")
STK = sorted(config.TOKENIZED_STOCKS)[0]
rs_s = sr.for_signal(STK, "LONG", 100.0, 96.0, bars=[(100.4, 99.6, 100.0)] * 96)
T7 = float(calendar.timegm((2026, 11, 18, 2, 30, 0)))                # 07:30 PKT → the 05–09 window
out_s = tr.rule_card("💎✅ *ELITE CONFIRMED ENTRY · STOCK*\nenter `100` · SL `96` · TP1 `106` (+1.5R)", {"symbol": STK, "side": "LONG", "entry": 100.0, "stop": 96.0, "tp1": 106.0},
                     rs_s, "elite_confirm", T7)
check("rule card, stock confirmed entry: the 15m rule's stop in the SL, TP1's R re-cut, and NO fixed replay line since 23 Nov (its card reads the desk live)",
      bool(rs_s) and rs_s["rule"] == "15m" and abs(rs_s["stop"] - 95.8) < 1e-9
      and out_s == "💎✅ *ELITE CONFIRMED ENTRY · STOCK*\nenter `100` · SL `95.8` · TP1 `106` (+1.4R)", out_s)
out_ss = tr.rule_card("⭐ *ELITE STAR · STOCK*\nentry `100` · SL `96` · TP1 `106` (+1.5R)", {"symbol": STK, "side": "LONG", "entry": 100.0, "stop": 96.0, "tp1": 106.0},
                      rs_s, "elite_star", T7)
check("rule card, stock star: the replay line with this PKT window's cell is still there",
      out_ss == "⭐ *ELITE STAR · STOCK*\nentry `100` · SL `95.8` · TP1 `106` (+1.4R)\n"
      "🧪 replay on this stop (to 16 Nov, candles): 65% / +0.10R (26) · 05–09 PKT 100% / +0.66R (5, thin)", out_ss)
check("rule card: no rule result leaves the card untouched; a rule that keeps the plan's stop changes nothing but the replay line",
      tr.rule_card(card, sig_c, None, "elite_star", NOW_W) == card
      and tr.rule_card(card, sig_c, {"stop": 96.0, "plan": 96.0, "rule": "4h", "mark": 96.0, "capped": False}, "elite_star", NOW_W) == card + "\n" + REPLAY_C)
check("rule card: a card with no SL token is left alone (and a bell with no replay cell gets no line)",
      tr.rule_card("a card with no SL token", sig_c, a1, None, NOW_W) == "a card with no SL token"
      and tr.rule_card(card, sig_c, a1, "kr_premium", NOW_W) == card.replace("SL `96`", "SL `93.5`").replace("(+1.5R)", "(+0.9R)"))
check("worker: every entry bell that takes the rule's stop also takes the ⏪ / ⏩ block, in _rule_card, after the swap",
      W.index("text = tg_roster.rule_card(text, sig, _rs_c, key, time.time())") < W.index("text = tg_roster.with_record(text, sig, key, time.time())")
      < W.index("def _tg_rang(key, sig):") and W.count("tg_roster.with_record(") == 1)
check("worker: the rule's fetch is turned on, the six entry bells are swapped, the two reply sites follow", "stop_rule.LIVE = True" in W and W.count("_rule_card(") == 8
      and "def _rule_card(text, sig, key=None):" in W and W.count("tg_roster.rule_reply(") == 2 and "_wick_line" not in W
      and '_rule_card(_msg9, _pmx, "elite_star" if _star9 else "elite_agrade")' in W and "_rule_card(_rc_ec[1], dict(_w9, entry=_cl9), _rc_ec[0])" in W
      and "+ _kr_note(_sig2), _sig2, _v2key))" in W and "+ _kr_note(_sig_pp), _sig_pp, _tier_pp))" in W and '+ _kr_note(_sig_pt), _sig_pt, "prime_trig"))' in W
      and W.count('dict(_ew, entry=_ew_px), "conv_revival"))') == 2, W.count("_rule_card("))
# the desk: a seat opens on the rule's stop; the demo feed and the stop_rule stream keep the plan's
import shadow_trader as sh      # noqa: E402
_opened, _recs = [], []
_keep_store = sh.store
sh.store = types.SimpleNamespace(MIN_RISK_FRAC=0.003, desk_tier=lambda tier, sym: ("tok:" + tier) if sym == STK else tier, base_tier=lambda t: t[4:] if t.startswith("tok:") else t,
                                 shadow_has_open=lambda tier, sym: False, shadow_open=lambda *a, **k: _opened.append(a), record_signal=lambda stream, p, ts=None: _recs.append((stream, p)))
del sh.DEMO_FEED[:]
_tn = __import__("time").time()
kl_live = pd.DataFrame({"high": list(kl["high"]), "low": list(kl["low"]), "close": list(kl["close"])},
                       index=pd.to_datetime([_tn - 4 * 3600 * (30 - i) - 3600 for i in range(31)], unit="s"))
sr.LIVE, sr.FETCH = True, (lambda sym, iv, limit=0: kl_live if iv == "4h" else None)
sr._MEMO.clear()
ok_d = sh.open_from_signal("elite_star", {"symbol": "SOLUSDT", "side": "LONG", "stop": 96.0, "tp1": 106.0, "tp2": 110.0}, 100.0)
check("desk: a coin seat opens on the 4h rule's stop and logs the plan's stop beside it", ok_d and len(_opened) == 1 and abs(_opened[0][4] - got[0]) < 1e-9
      and len(_recs) == 1 and _recs[0][0] == "stop_rule" and _recs[0][1]["plan_stop"] == 96.0 and abs(_recs[0][1]["stop"] - got[0]) < 1e-9 and _recs[0][1]["rule"] == "4h", (_opened, _recs))
ok_m = sh.open_from_signal("conviction_v2_rev", {"symbol": "SOLUSDT", "side": "LONG", "stop": 96.0, "tp1": 106.0, "mirror_of": "conviction_v2"}, 100.0)
check("desk: the mirrored conviction tier keeps its own stop", ok_m and len(_opened) == 2 and _opened[1][4] == 96.0 and len(_recs) == 1, _opened[-1])
sr.FETCH = (lambda sym, iv, limit=0: None)
sr._MEMO.clear()
ok_n = sh.open_from_signal("elite_confirm", {"symbol": STK, "side": "LONG", "stop": 96.0, "tp1": 106.0}, 100.0)
check("desk: with no candles the plan stop stays, and the demo feed always carries the plan stop", ok_n and _opened[2][4] == 96.0 and len(sh.DEMO_FEED) == 1 and sh.DEMO_FEED[0]["stop"] == 96.0, (_opened[-1], sh.DEMO_FEED))
sr.FETCH = (lambda sym, iv, limit=0: pd.DataFrame({"high": [100.4] * 97, "low": [99.6] * 97, "close": [100.0] * 97},
                                                   index=pd.to_datetime([_tn - 900 * (96 - i) - 300 for i in range(97)], unit="s")) if iv == "15m" else None)
sr._MEMO.clear()
del sh.DEMO_FEED[:]
ok_s = sh.open_from_signal("elite_star", {"symbol": STK, "side": "LONG", "stop": 96.0, "tp1": 106.0}, 100.0)
check("desk: a stock seat opens on the 15m rule's stop and the demo is offered that stop too", ok_s and abs(_opened[3][4] - 95.8) < 1e-9 and _opened[3][0] == "tok:elite_star"
      and len(sh.DEMO_FEED) == 1 and abs(sh.DEMO_FEED[0]["stop"] - 95.8) < 1e-9 and sh.DEMO_FEED[0]["plan_stop"] == 96.0 and _recs[-1][1]["rule"] == "15m", (_opened[-1], sh.DEMO_FEED))
del sh.DEMO_FEED[:]
ok_w = sh.open_from_signal("go_revived", {"symbol": STK, "side": "LONG", "stop": 92.3, "tp1": 106.0}, 100.0)      # plan 7.7% away → the rule's is 7.9%
check("desk: a rule stop too wide for the demo's 10x guard leaves the demo on the plan stop", ok_w and sh.DEMO_RULE_MAX == 0.078 and abs(_opened[4][4] - 92.1) < 1e-9
      and len(sh.DEMO_FEED) == 1 and sh.DEMO_FEED[0]["stop"] == 92.3, (_opened[-1], sh.DEMO_FEED))
sr.RULE_ON = False
sr._MEMO.clear()
ok_o = sh.open_from_signal("elite_star", {"symbol": "ETHUSDT", "side": "LONG", "stop": 96.0, "tp1": 106.0}, 100.0)
check("stop_rule.RULE_ON = False puts every seat back on the plan stop", ok_o and _opened[5][4] == 96.0, _opened[-1])
sr.RULE_ON, sr.LIVE, sr.FETCH = True, False, None
sr._MEMO.clear()
sh.store = _keep_store

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("FAIL:", f)
sys.exit(1 if FAIL else 0)
