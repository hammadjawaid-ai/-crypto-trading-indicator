"""📱 The phone roster by asset class (user 2026-11-17).

His words: "New Stream should be introduced for tokenized stocks … 1. Elite Confirmed Entry 2. Elite Stars (Not Gated)
3. GO Revived Fast and Late on the Elite stars bells … For Crypto 1. Prime x Second Leg 2. Elite Stars Gated and ungated
for only 13-17 pkt … with go and follow up signals … 4. Prime x Strong Trigger 5. Star X Take Hot Now 6. Elite Confirmed
on Gated Star Together" · "measure stocks tokenzied stock seperately and crypto seperatly and their information card on
the buzz should have the information related to it only with timings and emojis" · "Conviction GO revived on stocks Yes
add it!!" · APEX V2 shorts with the gate's read on one line and the market side in the header ("Yes that will be great")
· "also deploy A grade as well to the telegram crypto side" · "for tp1 hit only have on for the streams that are active
on telegram".

What lives here, all new on 17 Nov (no bell that existed before is re-worded in this file):
  · the class rule: which bells ring on stocks only and which on coins only (class_ok);
  · the stock cards: a bell on a tokenized stock prints stock numbers only, read live from the desk's tok:<tier> seats
    (record by PKT window with the 🟢 / 🟡 / 🔴 light, by side, and all), plus the US session tag;
  · the three new cards: 🏆🔻 APEX V2 SHORT, 💎✅⭐ confirmed entry after a gated star, 💎⚡ conviction revival on a stock;
  · the rang-bell log: one row in the signals stream BELL for every entry bell the phone actually heard. The 🏦 TP1 HIT
    ping and the 🚦 gatekeeper's burst read follow that log, so they follow the phone and nothing else.
No Streamlit, no network. Every function is fail-soft: a card helper returns '' rather than raise.
"""
from __future__ import annotations

import json
import time

import tg_cells

ROSTER_TAG = "2026-11-17"
BELL = "tg_bell"                 # signals stream of rung entry bells; the `tier` column carries the bell's key
# class rule. A key in neither set rings on both classes when its own switch is on.
CRYPTO_ONLY = frozenset({"leg2_prime", "star_takenow", "prime_trig", "confirm_star", "apex_v2_short",
                         "elite_agrade"})
STOCK_ONLY = frozenset({"elite_confirm", "conv_revival"})
LABEL = {"elite_star": "⭐ ELITE STAR", "elite_agrade": "💎🏆 A-GRADE", "elite_confirm": "💎✅ CONFIRMED ENTRY",
         "leg2_prime": "🔥🥇 SECOND LEG × PRIME", "prime_trig": "💥🥇 PRIME × STRONG TRIGGER",
         "star_takenow": "⭐✅🔥 STAR × TAKE NOW HOT", "confirm_star": "💎✅⭐ CONFIRMED after a GATED STAR",
         "apex_v2_short": "🏆🔻 APEX V2 SHORT", "conv_revival": "💎⚡ CONVICTION REVIVAL",
         "kr_premium": "⚡🔮 KR-STRONG PREMIUM"}
# 🏦 TP1 HIT ping: only for bells that rang, and for every bell on the roster (user 2026-11-17, after the first
# build left three out: "add tp1 ones to the ones that rings so add it"). The log holds rung bells only, so a muted
# bell can never ping. Remove a key to silence its ping.
TP1_PING = frozenset({"elite_star", "elite_agrade", "elite_confirm", "leg2_prime", "prime_trig", "confirm_star",
                      "kr_premium", "apex_v2_short", "conv_revival", "star_takenow"})
# the desk tier whose stock seats a bell's stock line reads
STOCK_TIER = {"elite_star": "elite_star", "elite_confirm": "elite_confirm", "conv_revival": "go_revived",
              "star_go": "star_go_chase"}
STOCK_LABEL = {"elite_star": "⭐ stars, every fire", "elite_confirm": "💎✅ confirmed entries",
               "go_revived": "💎⚡ revivals entered at the GO", "star_go_chase": "⭐⚡ fast star GOs entered at the GO"}
STOCK_TTL = 1800.0
_STOCK_CACHE: dict = {}
# the two crypto marks' records and the new cards' all-hours lines (16 Nov ledger, desk booking, in-sample)
APEX_V2_SHORT_REC = ("shorts all hours 62% / +0.30R (84) desk · 68% / +0.29R on candles · longs 41% / −0.04R (123) "
                     "do not ring · 23 Sep → 16 Nov")
CONFIRM_STAR_REC = ("all hours 48% / −0.21R (33) · longs 35% / −0.39R (20) · shorts 69% / +0.08R (13) · "
                    "14 Oct → 13 Nov, in-sample")
# NYSE full-day closures (regular session 09:30–16:00 New York); early closes are not tracked
US_HOLIDAYS = frozenset({"2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26",
                         "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24"})


def is_stock(symbol) -> bool:
    return tg_cells.is_tokenized(symbol)


def class_ok(key, symbol) -> bool:
    """False when this bell does not ring on this symbol's class (stock / coin)."""
    k = str(key or "")
    stock = is_stock(symbol)
    if k in CRYPTO_ONLY and stock:
        return False
    if k in STOCK_ONLY and not stock:
        return False
    return True


def _hm(ts: float) -> str:
    return time.strftime("%H:%M", time.gmtime(float(ts) + 5 * 3600))


def _base(d: dict) -> str:
    return str(d.get("base") or str(d.get("symbol") or "").replace("USDT", ""))


# ───────── 🏦 stock records, read live from the desk's tokenized seats ─────────
def _stock_rows(tier: str, now: float) -> list:
    """[(side, opened_at, pnl_r)] of the clean closes under tok:<tier>, cached STOCK_TTL. [] on any error."""
    c = _STOCK_CACHE.get(tier)
    if c is not None and now - c[0] < STOCK_TTL:
        return c[1]
    rows = c[1] if c is not None else []
    try:
        import worker_store as _ws
        con = _ws._open()
        try:
            rows = [(str(s or "").upper(), float(o or 0.0), float(r)) for s, o, r in con.execute(
                "SELECT side, opened_at, pnl_r FROM shadow_trades WHERE status='CLOSED' AND pnl_r IS NOT NULL AND tier=?",
                ("tok:" + str(tier),))]
        finally:
            con.close()
    except Exception:
        pass
    _STOCK_CACHE[tier] = (now, rows)
    return rows


def _cell(v):
    v = list(v)
    n = len(v)
    return None if not n else (sum(1 for x in v if x > 0) / n * 100.0, sum(v) / n, n)


def _rec(c) -> str:
    if not c:
        return "no closes yet"
    w, r, n = c
    return f"{w:.0f}% / {r:+.2f}R ({n}{', thin' if n < tg_cells.THIN_N else ''})"


def stock_line(tier: str, side, now: float | None = None) -> str:
    """'🏦 🕐 🟢 09–13 PKT 88% / +0.45R (8, thin) · longs 68% / +0.25R (31) · all 66% / +0.23R (50) ·
    💎✅ confirmed entries on stocks, desk since 10 Nov'. The window is the 4-hour PKT window of `now`, both sides
    pooled (the seats are few); the side cell is every hour. Desk booking. '' on error."""
    try:
        now = time.time() if now is None else float(now)
        lab = STOCK_LABEL.get(str(tier), str(tier))
        rows = _stock_rows(str(tier), now)
        if not rows:
            return f"🏦 {lab} on stocks: no closes yet"
        win = tg_cells.window_of(now)
        sd = str(side or "").upper()
        wc = _cell(r for _, o, r in rows if tg_cells.window_of(o) == win)
        who = {"LONG": "longs", "SHORT": "shorts"}.get(sd)
        since = time.strftime("%d %b", time.gmtime(min(o for _, o, _ in rows) + 5 * 3600)).lstrip("0")
        return (f"🏦 🕐 {tg_cells.light(wc[0]) if wc else '🟡'} {win} PKT {_rec(wc)} · "
                + (f"{who} {_rec(_cell(r for s, _, r in rows if s == sd))} · " if who else "")
                + f"all {_rec(_cell(r for _, _, r in rows))} · {lab} on stocks, desk since {since}")
    except Exception:
        return ""


def us_session(now: float | None = None) -> str:
    """'🏛 US market OPEN (regular hours)' / '🏛 US market CLOSED · pre-market | after-hours | overnight | weekend |
    holiday'. New York time through zoneinfo; '' when the zone data is missing."""
    try:
        import datetime as _dt
        from zoneinfo import ZoneInfo
        t = _dt.datetime.fromtimestamp(time.time() if now is None else float(now), ZoneInfo("America/New_York"))
    except Exception:
        return ""
    m = t.hour * 60 + t.minute
    if t.weekday() >= 5:
        return "🏛 US market CLOSED · weekend"
    if t.strftime("%Y-%m-%d") in US_HOLIDAYS:
        return "🏛 US market CLOSED · holiday"
    if 570 <= m < 960:
        return "🏛 US market OPEN (regular hours)"
    return "🏛 US market CLOSED · " + ("pre-market" if 240 <= m < 570 else "after-hours" if 960 <= m < 1200 else "overnight")


def market_tag(side, now: float | None = None) -> str:
    """Header tag from BTC's last daily close against its 50-day average (tg_cells.set_btc_regime):
    ' · 🟢 WITH THE MARKET' · ' · ⚠️ AGAINST THE MARKET' (a long under the average) · ' · 🟡 BTC ABOVE ITS 50-DAY'
    (a short over it: not measured as a penalty). '' with no fresh read."""
    try:
        m = tg_cells._MKT
        now = time.time() if now is None else float(now)
        if m.get("below") is None or now - float(m.get("t") or 0.0) > tg_cells.MKT_MAX_AGE:
            return ""
        sd = str(side or "").upper()
        if m["below"]:
            return " · 🟢 WITH THE MARKET" if sd == "SHORT" else " · ⚠️ AGAINST THE MARKET"
        return " · 🟢 WITH THE MARKET" if sd == "LONG" else " · 🟡 BTC ABOVE ITS 50-DAY"
    except Exception:
        return ""


def _join(lines) -> str:
    return "\n".join(str(x) for x in lines if x)


def _plan(entry, stop, tp1, tp2=None, word="entry") -> str:
    e, s, t1 = float(entry), float(stop), float(tp1)
    rk = max(1e-12, abs(e - s))
    out = f"{word} `{e:g}` · SL `{s:g}` · TP1 `{t1:g}` (+{abs(t1 - e) / rk:.1f}R)"
    if tp2:
        out += f" · TP2 `{float(tp2):g}` (+{abs(float(tp2) - e) / rk:.1f}R)"
    return out


# ───────── 🏦 stock cards ─────────
def stock_star_card(p: dict, conf, now: float, partners=(), marks: str = "", bank=None) -> str:
    """⭐ ELITE STAR on a tokenized stock: rings on every fire (no gate on stocks), stock numbers only."""
    side = str(p.get("side") or "").upper()
    plan = (_plan(p["entry"], p["stop"], p["tp1"], p.get("tp2")) + f" · {str(p.get('tier') or 'HIGH')} "
            f"{float(p.get('score') or 0):.0f} · " + ("🚀 approved" if p.get("appr") else "⚠️ unapproved"))
    if bank:
        try:
            import bank_zone as _bz
            plan += " · " + _bz.chip(bank)
        except Exception:
            pass
    bits = []
    try:
        import rung_stats as _rs
        pl = _rs.star_partner_line(partners)
        if pl:
            bits.append("with: " + pl)
    except Exception:
        pass
    if conf is not None:
        bits.append(f"conf {conf}")
    if p.get("heat") is not None:
        try:
            bits.append(f"heat {float(p['heat']):.0f}")
        except (TypeError, ValueError):
            pass
    return _join([f"⭐ *ELITE STAR · STOCK — {_base(p)} {side} · TAKE · {_hm(now)} PKT*", plan, marks,
                  " · ".join(bits), stock_line("elite_star", side, now), us_session(now),
                  f"next: ⏱ verdict {_hm(now + 3600)} · GO till {_hm(now + 4 * 3600)} · both reply here"])


def stock_confirm_card(w: dict, close: float, now: float, conf=None) -> str:
    """💎✅ ELITE CONFIRMED ENTRY on a tokenized stock: the pullback to the plan that confirmed."""
    side = str(w.get("side") or "").upper()
    ap = "🚀 approved" if w.get("appr") else "approval unknown" if w.get("appr") is None else "unapproved"
    plan = (_plan(close, w["stop"], w["tp1"], w.get("tp2"), word="enter")
            + f" · elite {w.get('tier')} {float(w.get('score') or 0):.0f} · {ap}"
            + (f" · conf {conf}" if conf is not None else ""))
    return _join([f"💎✅ *ELITE CONFIRMED ENTRY · STOCK — {_base(w)} {side} · TAKE · {_hm(now)} PKT*", plan,
                  "pulled back to the plan and confirmed on the 15-minute close",
                  stock_line("elite_confirm", side, now), us_session(now)])


def _left(ew: dict, px: float) -> str:
    try:
        e0 = float(ew.get("entry0") or 0)
        risk = abs(e0 - float(ew["stop"]))
        if not e0 or risk <= 0:
            return ""
        sg = 1 if str(ew.get("side") or "").upper() == "LONG" else -1
        return f" · {(float(ew['tp1']) - float(px)) * sg / risk:.1f}R left to TP1"
    except Exception:
        return ""


def _fire_plan(ew: dict, prg: float, px: float) -> str:
    e0 = float(ew.get("entry0") or 0)
    return ((f"fire `{e0:g}`" if e0 else "fire `?`") + f" · SL `{float(ew['stop']):g}` · TP1 `{float(ew['tp1']):g}`"
            + (f" · TP2 `{float(ew['tp2']):g}`" if ew.get("tp2") else "")
            + f" · ignited {float(prg) * 100:+.0f}% of the path · live `{float(px):g}`" + _left(ew, px))


def stock_go_card(ew: dict, prg: float, age_s: float, px: float, now: float) -> str:
    """⭐⚡ GO FAST / GO LATE (and REVIVED) reply under a stock star's bell."""
    late = float(age_s) > 4 * 3600
    rev = ew.get("oneh") == "DEAD"
    side = str(ew.get("side") or "").upper()
    # a fast GO has its own stock record (entered at the GO); a late one has none yet, so it shows the star's
    rec = stock_line("elite_star" if late else "star_go_chase", side, now)
    return _join([f"⭐⚡ *{_base(ew)} {side} · GO {'LATE' if late else 'FAST'}{' · REVIVED' if rev else ''} · STOCK · "
                  f"{_hm(now)} PKT*", _fire_plan(ew, prg, px),
                  f"{float(age_s) / 60:.0f} min after the fire" + (" · graded DEAD at the hour, then ignited" if rev else ""),
                  rec, us_session(now)])


def stock_verdict(ew: dict, prg: float, now: float) -> str:
    """⏱ the 1H verdict reply under a stock star's bell."""
    side = str(ew.get("side") or "").upper()
    live = ew.get("oneh") == "LIVE"
    return _join([f"⏱ *{_base(ew)} {side} · 1H {'LIVE' if live else 'DEAD'} · STOCK · {_hm(now)} PKT*",
                  f"{float(prg) * 100:+.0f}% of the path to TP1 at the hour · the plan's SL / TP stay",
                  stock_line("elite_star", side, float(ew.get("fired_at") or now)), us_session(now)])


def stock_revival_card(ew: dict, prg: float, age_s: float, px: float, now: float) -> str:
    """💎⚡ CONVICTION REVIVAL on a tokenized stock: an elite conviction fire graded DEAD at the hour that then
    ignited to +25% of its path. The stock record is of entering at the GO (desk tier tok:go_revived)."""
    side = str(ew.get("side") or "").upper()
    cls = "LATE" if float(age_s) > 4 * 3600 else "FAST"
    return _join([f"💎⚡ *CONVICTION REVIVAL · STOCK — {_base(ew)} {side} · GO {cls} · {_hm(now)} PKT*",
                  _fire_plan(ew, prg, px),
                  f"graded DEAD at the hour, then ignited · {float(age_s) / 60:.0f} min after the fire"
                  + ("" if ew.get("appr") else " · unapproved fire"),
                  stock_line("go_revived", side, now), us_session(now)])


# ───────── crypto: the two new cards ─────────
def apex_v2_short_card(sig: dict, px, read_line, gate_ok: bool, now: float) -> str:
    """🏆🔻 APEX V2 SHORT: every APEX V2 short fire on a coin, the three-rule gate's read on one line, the market
    side in the header. Longs do not ring. The 1H verdict replies in this thread."""
    e = float(px or sig["entry"])
    ticks = str(read_line or "").split(" — ")[0].replace("read: ", "")
    return _join([f"🏆🔻 *APEX V2 SHORT — {_base(sig)} · TAKE · {_hm(now)} PKT{market_tag('SHORT', now)}*",
                  ("gate: ✅ PASSED · " if gate_ok else "gate: ⚠️ NOT PASSED · ") + ticks,
                  f"entry `{float(sig['entry']):g}` · live `{e:g}` · "
                  + _plan(e, sig["stop"], sig["tp1"], sig.get("tp2")).split(" · ", 1)[1]
                  + f" · score {float(sig.get('score') or 0):.0f} · heat {float(sig.get('heat') or 0):.0f}",
                  tg_cells.stamp("apex_v2_short", "SHORT", now),
                  APEX_V2_SHORT_REC + " · ⏱ 1h verdict replies here"]) \
        + tg_cells.gate_note("apex_v2_short", "SHORT", now, symbol=sig.get("symbol"))


def confirm_star_card(w: dict, close: float, now: float, star_ts: float, conf=None) -> str:
    """💎✅⭐ a confirmed entry on a coin whose GATED star fired in the 6 hours before, same side."""
    side = str(w.get("side") or "").upper()
    return _join([f"💎✅⭐ *CONFIRMED ENTRY after a GATED STAR — {_base(w)} {side} · {_hm(now)} PKT{market_tag(side, now)}*",
                  f"⭐ gated star fired {_hm(star_ts)} PKT ({max(0.0, now - float(star_ts)) / 60:.0f} min ago) · "
                  "pulled back to the plan and confirmed",
                  _plan(close, w["stop"], w["tp1"], w.get("tp2"), word="enter") + (f" · conf {conf}" if conf is not None else ""),
                  tg_cells.stamp("confirm_star", None, now), CONFIRM_STAR_REC]) \
        + tg_cells.gate_note("confirm_star", side, now, symbol=w.get("symbol"))


def gated_star_ts(store, symbol, side, now: float, hours: float = 6.0):
    """ts of the latest ⭐ star fire on this coin + side whose gate passed, from `hours` before to now; else None."""
    try:
        sd = str(side or "").upper()
        best = None
        for r in store.recent_by_stream("elite_star", 150):
            if r.get("symbol") != symbol or str(r.get("side") or "").upper() != sd:
                continue
            ts = float(r.get("ts") or 0)
            if not (now - hours * 3600 <= ts <= now + 60):
                continue
            try:
                g = (json.loads(r.get("extra") or "{}") or {}).get("gate")
            except Exception:
                g = None
            if g in ("pass", "1317-pass") and (best is None or ts > best):
                best = ts
        return best
    except Exception:
        return None


# ───────── the rang-bell log and the TP1 ping's stamp ─────────
# ───────── 🛡 the stop rule on entry bells (stop_rule.py) ─────────
# User 2026-11-17: "we are changing the rule of stops to 4h rule not the ones we have today this goes to all paper
# trading and to our telegram notificaion streams … for stocks on telegram notificaitons … we add the rule of 15m
# rule stops" · "we will have this information of updated win rates for every buzz or signals notificaition on
# telegram so we know what is what" · "stops please dont add line instead carry it within the tp sls and entry we
# have". On an entry bell the SL in the card's own entry · SL · TP line IS the rule's stop (coins the 4h rule,
# stocks the 15m rule), and the (+x.xR) figures that line prints for TP1 / TP2 are re-cut on it. No stop line is
# added. One 🧪 line follows the card: the candle replay of this bell on this stop (by PKT window on stocks).
# Nothing else on the card is re-worded: a level a card derives from the plan's risk (the star's half-off level,
# the bank zone) stays where it was measured. The gate and the signal keep the plan stop (stop_rule: applied
# where a trade is printed, never where it is judged).
# The replay cells: closed desk trades to 16 Nov on 15m candles, wicks counted, fees in, stop or TP1 in full,
# R per 1R risked, in-sample. (key, None) = the bell; (key, window) = the bell in that PKT window (stocks).
RULE_REPLAY_PERIOD = "to 16 Nov"
RULE_REPLAY = {
    ("elite_star", None): (71, 0.17, 106), ("elite_agrade", None): (67, 0.16, 9), ("leg2_prime", None): (82, 0.07, 22),
    ("prime_trig", None): (78, 0.15, 32), ("star_takenow", None): (67, 0.05, 3), ("apex_v2_short", None): (81, 0.23, 84),
}
RULE_REPLAY_STOCK = {
    ("elite_confirm", None): (66, 0.08, 50),
    ("elite_confirm", "01–05"): (86, 0.60, 7), ("elite_confirm", "05–09"): (82, 0.47, 11), ("elite_confirm", "09–13"): (100, 0.42, 4),
    ("elite_confirm", "17–21"): (57, -0.18, 21), ("elite_confirm", "21–01"): (29, -0.49, 7),
    ("elite_star", None): (65, 0.10, 26),
    ("elite_star", "01–05"): (50, -0.08, 6), ("elite_star", "05–09"): (100, 0.66, 5), ("elite_star", "09–13"): (100, 0.67, 3),
    ("elite_star", "17–21"): (43, -0.32, 7), ("elite_star", "21–01"): (60, 0.00, 5),
    ("conv_revival", None): (77, 0.10, 43),
    ("conv_revival", "01–05"): (82, 0.19, 11), ("conv_revival", "05–09"): (100, 0.34, 7), ("conv_revival", "09–13"): (87, 0.23, 15),
    ("conv_revival", "13–17"): (50, -0.32, 2), ("conv_revival", "17–21"): (33, -0.53, 6), ("conv_revival", "21–01"): (50, 0.20, 2),
}
RULE_TTL = 36 * 3600.0
_RULE_LAST: dict = {}     # (symbol, side) -> (plan stop, rule stop, rule name, ts): the swap made on the last bell


def _cellr(c) -> str:
    return f"{c[0]:.0f}% / {c[1]:+.2f}R ({c[2]}" + (", thin)" if c[2] < 20 else ")")


def rule_replay_line(key, symbol, side, now: float) -> str:
    """'🧪 …' the candle replay of this bell on the rule's stop ('' when the bell has no cell)."""
    try:
        if is_stock(symbol):
            c = RULE_REPLAY_STOCK.get((str(key), None))
            if not c:
                return ""
            win = tg_cells.window_of(now)
            w = RULE_REPLAY_STOCK.get((str(key), win))
            return (f"🧪 replay on this stop ({RULE_REPLAY_PERIOD}, candles): {_cellr(c)}"
                    + (f" · {win} PKT {_cellr(w)}" if w else f" · {win} PKT no trades yet"))
        c = RULE_REPLAY.get((str(key), None))
        return f"🧪 replay on this stop ({RULE_REPLAY_PERIOD}, candles): {_cellr(c)}" if c else ""
    except Exception:
        return ""


def rule_card(text: str, sig: dict, rs, key=None, now=None) -> str:
    """The entry bell's text with the rule's stop carried in its own entry · SL · TP line, and the 🧪 replay line.
    rs = the dict of stop_rule.for_signal. None (no candles, rule off) leaves the card exactly as it is."""
    try:
        now = time.time() if now is None else float(now)
        side = str(sig.get("side") or "").upper()
        e, plan = float(sig.get("entry") or 0), float(sig.get("stop") or 0)
        if not rs or e <= 0 or plan <= 0:
            return text
        new = float(rs["stop"])
        d, d0 = abs(e - new), abs(e - plan)
        if d > d0 * 1.001 and f"SL `{plan:g}`" in text:
            text = text.replace(f"SL `{plan:g}`", f"SL `{new:g}`")
            for k in ("tp1", "tp2"):                      # the (+x.xR) a plan line prints beside TP1 / TP2
                try:
                    t = float(sig.get(k) or 0)
                    if t > 0:
                        text = text.replace(f"`{t:g}` (+{abs(t - e) / d0:.1f}R)", f"`{t:g}` (+{abs(t - e) / d:.1f}R)")
                except Exception:
                    pass
            _RULE_LAST[(str(sig.get("symbol")), side)] = (plan, new, str(rs["rule"]), now)
        rp = rule_replay_line(key, sig.get("symbol"), side, now) if key else ""
        return text + (("\n" + rp) if rp else "")
    except Exception:
        return text


def rule_reply(text: str, symbol, side) -> str:
    """A thread reply's text with the plan's SL swapped for the stop the bell printed (within RULE_TTL, in memory)."""
    try:
        hit = _RULE_LAST.get((str(symbol), str(side or "").upper()))
        if not hit or time.time() - float(hit[3]) > RULE_TTL:
            return text
        return text.replace(f"SL `{float(hit[0]):g}`", f"SL `{float(hit[1]):g}`")
    except Exception:
        return text


def bell_row(key: str, sig: dict) -> dict:
    """The row written to the BELL stream when an entry bell rang."""
    row = {"symbol": sig.get("symbol"), "base": _base(sig), "side": str(sig.get("side") or "").upper(),
           "tier": str(key), "entry": sig.get("entry"), "stop": sig.get("stop"), "tp1": sig.get("tp1"),
           "tp2": sig.get("tp2")}
    try:
        w = _RULE_LAST.get((str(sig.get("symbol")), row["side"]))
        if w and time.time() - float(w[3]) < 900:
            row["rule_stop"], row["rule"] = w[1], w[2]      # 🛡 the stop this bell printed, for the forward replay
    except Exception:
        pass
    return row


def ping_stamp(key, symbol, side, ts: float) -> str:
    """'\\n…' under a 🏦 TP1 HIT ping: the stock line for a stock, the bell's 🕐 crypto cell for a coin."""
    try:
        if is_stock(symbol):
            ln = stock_line(STOCK_TIER.get(str(key), str(key)), side, ts)
            return ("\n" + ln) if ln else ""
        return tg_cells.stamp_src(str(key), side, ts)
    except Exception:
        return ""
