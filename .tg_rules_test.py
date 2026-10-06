"""🧵📵 TG RULES 2026-10-05 — the mute list + the rung-thread phone.

1. telegram_notify.send_thread returns per-chat message ids and posts replies
   (requests stubbed); send() keeps its 2-tuple contract.
2. rung_stats on a synthetic desk DB: the class joins (LIVE/DEAD, DEAD->GO,
   frozen night/day, ignited), the stamps, every message's action word and
   markdown balance, the scoreboard.
3. agent_worker wiring: the switch, the mutes (roster, APEX V2, reports, live
   receipts) with the three real-money safety alerts still live, the thread
   sends with reply_to, the arrival stamps, the scoreboard schedule, and a
   ghost scan of the three touched modules.
"""
import ast
import builtins
import io
import os
import sqlite3
import sys
import tempfile
import time
import types

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"F:\Trading Indicator"
sys.path.insert(0, ROOT)
fails = []

# ── 1. telegram threading with a stubbed requests ─────────────────────────
calls = []


class _R:
    def __init__(self, mid):
        self.ok, self.status_code, self.text, self._m = True, 200, "", mid

    def json(self):
        return {"ok": True, "result": {"message_id": self._m}}


fake = types.ModuleType("requests")
fake.post = lambda url, json=None, timeout=10: (calls.append(json), _R(100 + len(calls)))[1]
sys.modules["requests"] = fake
import telegram_notify as tg  # noqa: E402

tg._TOKEN, tg._CHATS = "t", ["1", "2"]
ok, msg, ids = tg.send_thread("hi")
if not ok or ids != {"1": 101, "2": 102}:
    fails.append(f"send_thread ids wrong: {ok} {msg} {ids}")
ok2, _, ids2 = tg.send_thread("re", reply_to=ids)
if not ok2 or calls[2].get("reply_to_message_id") != 101 or calls[3].get("reply_to_message_id") != 102:
    fails.append(f"reply ids not passed: {calls[2:4]}")
if not calls[2].get("allow_sending_without_reply"):
    fails.append("reply must allow sending without the parent")
r = tg.send("plain")
if not (isinstance(r, tuple) and len(r) == 2 and r[0] is True) or "reply_to_message_id" in calls[4]:
    fails.append(f"send() contract broken: {r} {calls[4]}")
ok3, _, ids3 = tg.send_thread("x", reply_to={"9": 5})
if ids3 != {"1": 107, "2": 108} or "reply_to_message_id" in calls[6]:
    fails.append("unknown chat in reply_to must not attach a reply")

# ── 2. rung_stats on a synthetic desk ─────────────────────────────────────
import rung_stats as rs  # noqa: E402
import worker_store  # noqa: E402

tmp = tempfile.mkdtemp()
DB = os.path.join(tmp, "w.db")
con = sqlite3.connect(DB)
con.executescript(worker_store._SCHEMA)
import calendar
NOW = float(calendar.timegm((2026, 10, 3, 8, 40, 0)))   # 2026-10-03 08:40 UTC = 13:40 PKT (a Saturday)
H = 3600


def fire(sym, side, hour_pkt, days_ago, pnl, verdict=None, go_h=None, close_h=8.0, tier="elite_star"):
    """one desk trade + its stamps; hour_pkt = fire hour in PKT."""
    day0 = ((NOW + rs.PK) // 86400) * 86400 - rs.PK - days_ago * 86400
    o = day0 + hour_pkt * H
    c = o + close_h * H
    con.execute("INSERT INTO shadow_trades (tier,symbol,side,entry,stop,stop0,tp1,tp2,opened_at,status,closed_at,pnl_r) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (tier, sym, side, 1.0, 0.95, 0.95, 1.08, 1.15, o, "CLOSED", c, pnl))
    con.execute("INSERT INTO signals (ts,stream,symbol,base,side,tier,score) VALUES (?,?,?,?,?,?,?)",
                (o, tier, sym, sym.replace("USDT", ""), side, "HIGH", 80))
    if verdict:
        con.execute("INSERT INTO signals (ts,stream,symbol,base,side,tier,score) VALUES (?,?,?,?,?,?,?)",
                    (o + 62 * 60, "elite_1h", sym, sym.replace("USDT", ""), side, verdict, 12.0))
    if go_h is not None:
        con.execute("INSERT INTO signals (ts,stream,symbol,base,side,tier,score) VALUES (?,?,?,?,?,?,?)",
                    (o + go_h * H, "star_go", sym, sym.replace("USDT", ""), side, "FAST" if go_h <= 4 else "LATE", go_h * 60))
    return o


# day fires (15 PKT): 12 LIVE + GO winners, 6 DEAD->GO (4 win 2 lose), 8 DEAD silent losers (closed at 6h)
for i in range(12):
    fire(f"L{i}USDT", "LONG", 15, 3 + i % 5, 1.0, "LIVE", go_h=1.5)
for i in range(10):
    fire(f"D{i}USDT", "LONG", 15, 3 + i % 5, 0.8 if i < 7 else -1.0, "DEAD", go_h=2.0)
for i in range(11):
    fire(f"S{i}USDT", "LONG", 15, 3 + i % 5, -1.0, "DEAD", go_h=None, close_h=6.0)
# night fires (23 PKT): 4 ignited winners, 6 silent losers (alive at 4h)
for i in range(4):
    fire(f"N{i}USDT", "LONG", 23, 3 + i % 5, 1.0, "LIVE", go_h=2.5)
for i in range(10):
    fire(f"F{i}USDT", "SHORT", 23, 3 + i % 5, -1.0, "DEAD", go_h=None, close_h=5.0)
# GO-entry control ledger (12 closes) + a young T1 ledger (3 closes)
for i in range(12):
    con.execute("INSERT INTO shadow_trades (tier,symbol,side,entry,stop,stop0,tp1,opened_at,status,closed_at,pnl_r) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("star_go_chase", f"C{i}USDT", "LONG", 1, 0.95, 0.95, 1.08, NOW - 5 * 86400, "CLOSED", NOW - 4 * 86400, 0.3 if i < 7 else -1.0))
for i in range(3):
    con.execute("INSERT INTO shadow_trades (tier,symbol,side,entry,stop,stop0,tp1,opened_at,status,closed_at,pnl_r) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("trig_hot", f"T{i}USDT", "LONG", 1, 0.95, 0.95, 1.08, NOW - 5 * 86400, "CLOSED", NOW - 4 * 86400, 1.0))
# yesterday's rung-1 fires for the scoreboard: 3 star (2 GO, 1 silent old enough to freeze), 1 T1, 2 arr_hot (one = the T1)
y0 = ((NOW + rs.PK) // 86400) * 86400 - rs.PK - 86400
for k, (sym, go) in enumerate((("Y1USDT", 1.0), ("Y2USDT", 3.0), ("Y3USDT", None))):
    o = y0 + (10 + k) * H
    con.execute("INSERT INTO signals (ts,stream,symbol,base,side,tier) VALUES (?,?,?,?,?,?)", (o, "elite_star", sym, sym[:2], "LONG", "HIGH"))
    con.execute("INSERT INTO shadow_trades (tier,symbol,side,entry,stop,stop0,tp1,opened_at,status,closed_at,pnl_r) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("elite_star", sym, "LONG", 1, 0.95, 0.95, 1.08, o, "CLOSED" if k < 2 else "OPEN", o + 6 * H if k < 2 else None, (1.2, -1.0, None)[k]))
    if go:
        con.execute("INSERT INTO signals (ts,stream,symbol,base,side,tier,score) VALUES (?,?,?,?,?,?,?)", (o + go * H, "star_go", sym, sym[:2], "LONG", "FAST", go * 60))
oT = y0 + 14 * H
for st in ("trig_hot", "arr_hot"):
    con.execute("INSERT INTO signals (ts,stream,symbol,base,side,tier) VALUES (?,?,?,?,?,?)", (oT, st, "XLMUSDT", "XLM", "LONG", "HOT"))
    con.execute("INSERT INTO shadow_trades (tier,symbol,side,entry,stop,stop0,tp1,opened_at,status,closed_at,pnl_r) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (st, "XLMUSDT", "LONG", 1, 0.95, 0.95, 1.08, oT, "CLOSED", oT + 3 * H, 0.9))
con.execute("INSERT INTO signals (ts,stream,symbol,base,side,tier) VALUES (?,?,?,?,?,?)", (oT + H, "arr_hot", "ADAUSDT", "ADA", "LONG", "HOT"))
con.execute("INSERT INTO shadow_trades (tier,symbol,side,entry,stop,stop0,tp1,opened_at,status,closed_at,pnl_r) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("arr_hot", "ADAUSDT", "LONG", 1, 0.95, 0.95, 1.08, oT + H, "CLOSED", oT + 4 * H, -1.0))
con.commit()
con.close()

st = rs.classes("elite_star", NOW, DB)
C = st["cls"]
# L 12 + D 10 + S 11 + Y 2 closed = 35 day fires · N 4 + F 10 = 14 night fires
want = {"all": 49, "night": 14, "day": 35, "live": 16, "dead": 31, "dead_go": 10, "dead_nogo": 21,
        "go4h": 28, "frozen": 21, "frozen_night": 10, "frozen_day": 11, "ignited_night": 4, "ignited_day": 24}
for k, n in want.items():
    if C[k][0] != n:
        fails.append(f"class {k}: n={C[k][0]} wanted {n}")
if abs(C["dead_go"][1] - 70.0) > 0.1 or abs(C["frozen_night"][2] + 1.0) > 1e-9:
    fails.append(f"class values wrong: dead_go {C['dead_go']} frozen_night {C['frozen_night']}")
if st["chase"] != (12, 7 / 12 * 100, (7 * 0.3 - 5) / 12):
    fails.append(f"chase cell wrong {st['chase']}")
if [rs.light(c) for c in ((14, 100.0, 1.0), (42, 60.0, 0.16), (20, 48.0, 0.3), (20, 55.0, 0.05), (20, 30.0, -0.4))] != ["🟡", "🟢", "🟡", "🟡", "🔴"]:
    fails.append("light() thresholds wrong")
if rs.rec((3, 100.0, 1.0)) != "young (3 closes)" or rs.rec((0, 0, 0)) != "no closes yet" or rs.rec((48, 77.1, 0.49)) != "77% / +0.49R (48)":
    fails.append("rec() formatting wrong")
if rs.rec(rs.tier_rec("trig_hot", None, NOW, DB)) != "young (4 closes)":   # 3 old + yesterday's XLM
    fails.append(f"tier_rec young wrong: {rs.tier_rec('trig_hot', None, NOW, DB)}")
if not rs.stamp(st).startswith("measured on the desk ") or "refreshed 13:40 PKT" not in rs.stamp(st):
    fails.append(f"stamp wrong: {rs.stamp(st)}")
if rs.stamp({"n": 0}) != "record unavailable":
    fails.append("empty stamp must say unavailable")

p = {"symbol": "GLMRUSDT", "base": "GLMR", "side": "LONG", "entry": 0.012078, "stop": 0.010827, "tp1": 0.01343,
     "tp2": 0.014512, "tier": "HIGH", "score": 81, "appr": True}
day_msg = rs.star_fire(p, 77, NOW, ["🎯 conf 77/100", "🌡 heat 23"], "\n🔮 ✅ Kronos agrees · UP +2.1%/24h", DB)
for need in ("⭐ *ELITE STAR — GLMR LONG · TAKE (full size: 13–17 PKT window) · 13:40 PKT*",
             "entry `0.012078` · SL `0.010827` · TP1 `0.01343` · TP2 `0.014512` · HIGH 81 · 🚀 approved",
             "🎯 conf 77/100 · 🌡 heat 23", "rule: enter at the buzz, no conf filter",
             "window record: 🟢 13–17 PKT longs 58% / +0.11R (33)", "day fires 57% / +0.11R (35)", "night fires 29% / −0.43R (14)",
             "measured on the desk", "refreshed 13:40 PKT",
             "next: ⏱ verdict 14:40 · ⭐⚡ GO window till 17:40 · ❄️ freeze after", "🔮 ✅ Kronos agrees"):
    if need not in day_msg:
        fails.append(f"day star fire missing {need!r}")
NIGHT = NOW + 10 * H      # 23:40 PKT
night_msg = rs.star_fire(dict(p, side="SHORT"), 40, NIGHT, [], "", DB)
for need in ("TAKE HALF, or wait for GO (night fire) · 23:40 PKT*", "window record: 🟡 21–01 PKT shorts 0% / −1.00R (10)",
             "frozen night fires 0% / −1.00R (10)", "ignited night fires young (4 closes)", "🎯 conf 40"):
    if need not in night_msg:
        fails.append(f"night star fire missing {need!r}")
ew = {"symbol": "GLMRUSDT", "base": "GLMR", "side": "LONG", "stop": 0.010827, "tp1": 0.01343, "star": True,
      "oneh": "LIVE", "entry0": 0.0121, "fired_at": NOW - 2.5 * H}
v_live = rs.verdict_text(ew, 0.16, NOW, DB)
if "⏱ *GLMR LONG · 1H LIVE at 13:40 PKT · HOLD FULL*" not in v_live or "+16% of the path at 60 min · LIVE class (⭐ stars) 100% / +1.00R (16)" not in v_live:
    fails.append(f"LIVE verdict wrong:\n{v_live}")
v_dead = rs.verdict_text(dict(ew, oneh="DEAD"), 0.03, NOW, DB)
if "1H DEAD at 13:40 PKT · HOLD — no add, no cut*" not in v_dead or "DEAD then ignited (⭐ stars): 70% / +0.26R (10)" not in v_dead or "DEAD never ignited: 0% / −1.00R (21)" not in v_dead:
    fails.append(f"DEAD verdict wrong:\n{v_dead}")
v_plain = rs.verdict_text(dict(ew, star=False, oneh="DEAD"), 0.03, NOW, DB)
if "DEAD then ignited (elite fires):" not in v_plain:
    fails.append("non-star verdict must carry the elite ignition split")
ge = rs.go_text(dict(ew, star=False, oneh="DEAD", entry0=0.0121, stop=0.0119), 0.26, 2.0 * H, 0.01215, NOW, DB)
if not ge.startswith("💎⚡ *GO — GLMR LONG · REVIVED · PROTECT · 13:40 PKT (2.0h after the fire)*") or "DEAD then ignited (elite fires)" not in ge:
    fails.append(f"elite GO revived text wrong:\n{ge}")
g = rs.go_text(ew, 0.34, 2.5 * H, 0.01254, NOW, DB)
for need in ("⭐⚡ *GO — GLMR LONG · PROTECT · 13:40 PKT (2.5h after the fire)*", "ignited: +34% of the path · live `0.01254`",
             "holding it: hold to TP1 / TP2, do not bank early · ignited within 4h (⭐ stars) 86% / +0.67R (28)",
             "not in it: 0.7R left to TP1 from here — PASS"):
    if need not in g:
        fails.append(f"GO text missing {need!r}")
g2 = rs.go_text(dict(ew, oneh="DEAD", entry0=0.0121, stop=0.0119), 0.26, 5 * H, 0.01215, NOW, DB)
if "⭐⚡ *GO — GLMR LONG · REVIVED · PROTECT · 13:40 PKT (5.0h after the fire, late)*" not in g2 or "REVIVED" in g or "DEAD then ignited (⭐ stars) 70% / +0.26R (10)" not in g2 or "entry at GO measured 58% / −0.24R (12) — small, your call" not in g2:
    fails.append(f"late GO text wrong:\n{g2}")
fz_n = rs.freeze_text(dict(ew, fired_at=NOW + 10 * H - 86400), NOW, DB)   # fired 23:40 PKT yesterday
if "❄️ *GLMR LONG · silent at 4h · 13:40 PKT · FREEZE — free the seat*" not in fz_n or "night frozen fires: 0% / −1.00R (10) · day frozen fires: 0% / −1.00R (11)" not in fz_n or "release it the moment" not in fz_n:
    fails.append(f"night freeze wrong:\n{fz_n}")
fz_d = rs.freeze_text(dict(ew, fired_at=NOW - 4 * H), NOW, DB)
if "FREEZE — hold, no adds*" not in fz_d or "day frozen fires: 0% / −1.00R (11) · night frozen fires" not in fz_d or "lowest priority if a ⭐ / T1 / A-GRADE bell needs the capital" not in fz_d:
    fails.append(f"day freeze wrong:\n{fz_d}")
if "💎🏆 *ELITE A-GRADE — ONE LONG · TAKE · 13:40 PKT*" != rs.agrade_head({"base": "ONE"}, NOW):
    fails.append("agrade head wrong")
ar = rs.arrival_record(1, NOW, DB)
if ar != "T1 record: replay 86% / +0.21R (154), 15 Aug → 28 Sep · forward desk young (4 closes) · refreshed 13:40 PKT":
    fails.append(f"arrival record wrong: {ar}")
sb = rs.scoreboard(NOW, DB)
for need in ("📊 *RUNG-1 SCOREBOARD — Fri 02 Oct, 00:00 → 23:59 PKT* · built 13:40 PKT",
             "⭐ star 3 fires: 1 won of 2 closed, +0.2R · 1 still open · GO on 2, froze 1",
             "⚡🔥 T1 1 fire: 1 won of 1 closed, +0.9R · ⚡🔥 T2 1 fire: 0 won of 1 closed, -1.0R",
             "💎🏆 A-GRADE: no fires (no Top Conviction seat paired with an elite card)",
             "30-day desk: star ", "T1 young (4 closes)", "A-grade no closes yet", "refreshed 13:40 PKT"):
    if need not in sb:
        fails.append(f"scoreboard missing {need!r}")
for m in (day_msg, night_msg, v_live, v_dead, v_plain, g, g2, ge, fz_n, fz_d, ar, sb):
    if m.count("*") % 2 or m.count("`") % 2 or "\ufffd" in m:
        fails.append(f"markdown/encoding unbalanced in: {m[:60]!r}")
    if "_" in m.replace("`", ""):
        fails.append(f"stray underscore (Markdown v1 italics risk) in: {m[:60]!r}")
T0 = NOW + 48 * H
_a = rs.classes("elite_star", T0, DB)
if rs.classes("elite_star", T0 + 60, DB) is not _a or rs.classes("elite_star", T0 + rs.TTL + 1, DB) is _a:
    fails.append("30-min cache not honoured")

# ── 3. agent_worker wiring ────────────────────────────────────────────────
W = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
ast.parse(W)
for need, lab in (("TG_RULES = True\n", "switch on"),
                  ("_MUTE_RULES = _MUTE_R9 if TG_RULES else tg.send\n", "mute lambda"),
                  ("import rung_stats\n", "import"),
                  ('if key_prefix not in (("moon",) if TG_RULES else\n', "roster moon-only"),
                  ("tg.send(_fmt_apex_v2(_sig2, _px2, _rv2)", "apex v2 bell live again (user 2026-10-06)"),
                  ('ok, _m9, _ids9 = tg.send_thread(_msg9)', "star/A-grade send as thread anchor"),
                  ("ok, _m9 = _MUTE_RULES(_msg9)", "plain conviction muted"),
                  ('_ewb["tg_ids"] = _ids9', "ids stored on the watch entry"),
                  ('and _ewb.get("fam", "elite")\n                                        == "elite"):', "buzzed marking elite-only"),
                  ('_TG_THREADS[(_pmx.get("symbol"),', "thread memory written"),
                  ('_th = _TG_THREADS.get((sym, side))', "ego_add adopts the thread"),
                  ("rung_stats.verdict_text(\n                                            _ew, _prg, _ew_now),\n                                        reply_to=_ew.get(\"tg_ids\"))", "verdict reply"),
                  ("_go9 = rung_stats.go_text(\n                                        _ew, _prg, _age, _ew_px,\n                                        _ew_now)", "GO text built"),
                  ('if _ew.get("oneh") == "DEAD":\n                                        # GO REVIVED is its own bell', "revived branch"),
                  ("int(1.0 * 3600)):   # 1h (user 2026-10-06", "elite re-buzz key 1h"),
                  ('if _ew.get("star") or _ew.get("appr"):\n                                            _ok9, _m9x = tg.send(_go9)', "revived: stars + approved elite only"),
                  ('_bell9 = ("not-approved (unapproved "', "unapproved elite stays records-only"),
                  ("_ok9, _m9x = tg.send(_go9)", "GO REVIVED standalone"),
                  ('_bell9 = "not-buzzed (LIVE fire not on the phone)"', "GO bell status default"),
                  ('if (_ew.get("fam", "elite") == "elite"\n                            and _ew.get("go") is None', "GO for the whole elite family"),
                  ('"star_go" if _ew.get("star") else "elite_go", {', "elite_go stamp"),
                  ('if _ew["go"] == "FAST" and _ew.get("star"):', "chase tier star-only"),
                  ('elif (_ew.get("buzzed") and _ew.get("star")\n                                and _ew.get("oneh") == "DEAD"):', "old path stays star-only"),
                  ('"star": bool(_ew.get("star")),\n                            "bell": _bell9})', "GO stamp carries the bell status"),
                  ("def _ego_save() -> None:", "watch persisted"),
                  ("def _ego_load() -> int:", "watch restored"),
                  ("        _ego_save()\n", "save each cycle"),
                  ("_EGO_RESTORED = _ego_load()\n", "watch restored at module import (launch.py path)"),
                  ("[thread] verdict", "verdict send logged"),
                  ("[thread] freeze", "freeze send logged"),
                  ("TG_FREEZE = False\n", "freeze reply muted (user 2026-10-06)"),
                  ('if (TG_RULES and TG_FREEZE and _ew.get("buzzed")', "freeze gated by its switch"),
                  ('ok, _ = _MUTE_R9(\n                    f"🔴 *{_rg_b3} {_rg_side} — INVERSE RISK', "inverse risk muted (user 2026-10-06)"),
                  ("tg.send_thread(\n                                            _go9,\n                                            reply_to=_ew.get(\"tg_ids\"))", "GO thread reply"),
                  ("rung_stats.freeze_text(_ew, _ew_now),\n                                    reply_to=_ew.get(\"tg_ids\"))", "freeze reply"),
                  ("now=(time.time() if TG_RULES else None))\n                                    + _kr_note(a))", "arrival stamps"),
                  ('store.should_alert("rung_scoreboard", 20 * 3600)', "scoreboard scheduled"),
                  ("_sb9 = rung_stats.scoreboard(time.time())", "scoreboard built"),
                  ("head=(rung_stats.agrade_head(", "A-grade action head"),
                  ('def _agrade_banner(seat, conf, rr, head=None, nxt=""):', "banner signature")):
    if need not in W:
        fails.append(f"wiring missing: {lab}")
if W.count('ok, _dmsg = _MUTE_RULES("\\n".join(lines))') != 2 or 'ok, _dmsg = tg.send("\\n".join(lines))' in W:
    fails.append("both reports must be muted")
# live executor: receipts muted, the three safety alerts live
for gone in ('tg.send(\n                f"💸 *LIVE OPENED*', 'tg.send(\n                f"💸 *LIVE CLOSED*',
             'tg.send(f"👀 *LIVE* — {_note}")', 'tg.send(\n                    f"💸 *GEN10 LIVE OPENED*',
             'tg.send(\n                        f"🤖💸 *LIVE EXECUTOR'):
    if gone in W:
        fails.append(f"live receipt still live: {gone[:40]!r}")
for keep in ('ok, _ = tg.send(\n                "🛑 *KILL SWITCH FIRED*', 'ok, _ = tg.send(\n                    "⛔ *LIVE DAILY HALT*',
             'ok, _ = tg.send(\n                    "⚠️ *LIVE EXECUTOR CAN\'T REACH BYBIT*'):
    if keep not in W:
        fails.append(f"real-money safety alert must stay live: {keep[-40:]!r}")
# the thread sends sit inside the TG_RULES branch and the old sends inside elif
i_v = W.find("rung_stats.verdict_text(")
if not (0 < W.rfind("if TG_RULES:", 0, i_v) and W.find('elif _ew.get("buzzed") or _ew.get("appr"):', i_v) > 0):
    fails.append("verdict: old send must be the elif of the TG_RULES branch")
i_g = W.find("rung_stats.go_text(")
if W.find('elif (_ew.get("buzzed") and _ew.get("star")\n                                and _ew.get("oneh") == "DEAD"):', i_g) < 0:
    fails.append("GO: old revival send must be the elif of the TG_RULES branch")
if "WHERE stream IN ('star_go', 'elite_go')" not in open(os.path.join(ROOT, "rung_stats.py"), encoding="utf-8").read():
    fails.append("rung_stats must join both GO streams")
if "int(1.5 * 3600)):   # 1.5h (user 2026-09-19)" in W:
    fails.append("elite re-buzz key still 1.5h")
# star bell keeps its own record path (star gate test anchors) and is never time-gated
blk = W.split("def _push_elite")[1].split("\n    tn_hot =")[0]
for need in ('_ego_add(dict(_st_sig', 'store.record_signal("elite_star"', 'if not (_star9 or _ag9):'):
    if need not in blk:
        fails.append(f"star path piece missing: {need}")
if "is_night" in blk or "pkt_hour" in blk:
    fails.append("the send site must not gate on the clock")

# the GO stamp must come AFTER the send (it records what the phone got)
if not (0 < W.find("_bell9 = \"not-buzzed") < W.find('"bell": _bell9})') < W.find('if _ew["go"] == "FAST" and _ew.get("star"):')):
    fails.append("GO stamp must follow the send and precede the chase tier")
_i_d = W.find('if _ew.get("oneh") == "DEAD":\n                                        # GO REVIVED is its own bell')
_i_s = W.find("_ok9, _m9x = tg.send(_go9)")
if not (0 < _i_d < _i_s) or "buzzed" in W[_i_d:_i_s]:
    fails.append("the revived bell must ring whether or not the fire was on the phone")
# persistence round-trip (the two helpers run standalone)
import ast as _ast
_ns = {"time": time, "_EGO_WATCH": [], "_TG_THREADS": {}, "_EGO_FILE": os.path.join(tmp, "ego.json"), "print": print}
for _n in _ast.parse(W).body:
    if isinstance(_n, _ast.FunctionDef) and _n.name in ("_ego_save", "_ego_load"):
        exec(compile(_ast.Module(body=[_n], type_ignores=[]), _n.name, "exec"), _ns)
_ns["_EGO_WATCH"].extend([{"symbol": "ZECUSDT", "base": "ZEC", "side": "SHORT", "stop": 1371.34, "tp1": 1249.37, "tp2": None, "tier": "HIGH", "star": True, "appr": True,
                          "entry0": 1299.5, "go": None, "oneh": "DEAD", "froze": False, "buzzed": True, "fam": "elite", "fired_at": time.time() - 3 * 3600, "tg_ids": {"1": 555}},
                         {"symbol": "OLDUSDT", "base": "OLD", "side": "LONG", "stop": 1, "tp1": 2, "fired_at": time.time() - 30 * 3600, "fam": "elite"}])
_ns["_TG_THREADS"][("ZECUSDT", "SHORT")] = {"ts": time.time() - 3 * 3600, "ids": {"1": 555}}
_ns["_TG_THREADS"][("NEWUSDT", "LONG")] = {"ts": time.time() - 600, "ids": {"1": 777}}
_ns["_ego_save"]()
_ns["_EGO_WATCH"].clear(); _ns["_TG_THREADS"].clear()
_nr = _ns["_ego_load"]()
_w = _ns["_EGO_WATCH"]
if _nr != 1 or len(_w) != 1 or _w[0]["symbol"] != "ZECUSDT" or _w[0]["tg_ids"] != {"1": 555} or _w[0]["oneh"] != "DEAD" or not _w[0]["buzzed"]:
    fails.append(f"watch round-trip wrong: {_nr} {_w}")
if _ns["_TG_THREADS"] != {("NEWUSDT", "LONG"): {"ts": _ns["_TG_THREADS"].get(("NEWUSDT", "LONG"), {}).get("ts"), "ids": {"1": 777}}}:
    fails.append(f"thread memory round-trip wrong (old entries must drop): {_ns['_TG_THREADS']}")
A_ = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
for need in ("SELECT ts, symbol, side, tier, extra FROM signals WHERE ", '(" (bell ✓)" if _gb.startswith("sent")'):
    if need not in A_:
        fails.append(f"board chip missing: {need[:40]}")
# ghost scan of the touched modules
def ghosts(src):
    tree = ast.parse(src)
    assigned, loads = set(), set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            (assigned if isinstance(n.ctx, ast.Store) else loads).add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assigned.add(n.name)
            if not isinstance(n, ast.ClassDef):
                for a in n.args.args + n.args.kwonlyargs + n.args.posonlyargs + ([n.args.vararg] if n.args.vararg else []) + ([n.args.kwarg] if n.args.kwarg else []):
                    assigned.add(a.arg)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names:
                assigned.add((al.asname or al.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            assigned.add(n.name)
        elif isinstance(n, ast.Lambda):
            for a in n.args.args:
                assigned.add(a.arg)
        elif isinstance(n, ast.comprehension):
            for t in ast.walk(n.target):
                if isinstance(t, ast.Name):
                    assigned.add(t.id)
        elif isinstance(n, (ast.With, ast.AsyncWith)):
            for it in n.items:
                if it.optional_vars:
                    for t in ast.walk(it.optional_vars):
                        if isinstance(t, ast.Name):
                            assigned.add(t.id)
    return sorted(g for g in loads - assigned if not hasattr(builtins, g) and g not in ("Any", "__file__"))


for path in ("agent_worker.py", "rung_stats.py", "telegram_notify.py"):
    gh = ghosts(open(os.path.join(ROOT, path), encoding="utf-8").read())
    if gh:
        fails.append(f"{path} ghosts: {gh}")

print(day_msg, "\n\n" + night_msg, "\n\n" + v_dead, "\n\n" + g, "\n\n" + fz_n, "\n\n" + sb, "\n")
print("TG RULES:", "ALL PASS" if not fails else fails)
