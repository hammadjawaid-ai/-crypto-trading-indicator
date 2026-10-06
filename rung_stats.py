"""🧵 RUNG THREADS — the measured lines on the rung-1 bells and their thread replies.

User 2026-10-05 (the thread design, approved with "rest bring the ones we
discussed"): every ⭐ star fire is one thread on the phone. The fire bell leads
with a one-word ACTION, every measured number carries two stamps (the desk
window it was measured on and when it was last refreshed), and the ⏱ 1H
verdict, ⭐⚡ GO and ❄️ FREEZE arrive as REPLIES inside the fire's thread. The
⚡🔥 ARRIVAL T1/T2 and 💎🏆 A-GRADE bells get the same action word and stamps.
09:00 PKT: the RUNG-1 SCOREBOARD for yesterday.

LAWS
  - action words are LABELS, never gates: every fire rings, day or night
    (user: "I don't want to restrict or limit notifications for the elite
    star notification for the time of the day"). Night (21-05 PKT) changes
    the wording only: TAKE HALF, or wait for GO.
  - numbers come from the desk ledger (shadow_trades joined to the elite_1h
    verdict stamps and the star_go ignition stamps) at send time, cached 30
    min — never a hand-typed study figure. The one exception is the ARRIVAL
    replay line, which says "replay" and names its window.
  - a class under MIN_N closes says "young (n closes)" instead of a number.
  - the measurement window is the first graded trade -> the last close in
    the ledger, never a typed date; "refreshed" is the time the desk was read.
  - fail-soft: a formatting error can never stop a bell — callers catch and
    fall back to the old message.
"""
from __future__ import annotations

import sqlite3
import time
from collections import defaultdict

import buzz_clock
import worker_store as store

PK = 5 * 3600                 # Pakistan time, the user's clock
TTL = 30 * 60                 # desk re-read cadence
MIN_N = 10                    # below this a class is "young"
CLEAN = 0.005                 # |entry-stop0|/entry >= 0.5% (star-board hygiene)
_CACHE: dict = {}

# ⚡🔥 ARRIVAL replay record (Aug 15 - Sep 28, .prefire_study.py) — the only
# typed numbers here, labelled "replay" with their window on the bell.
ARRIVAL_REPLAY = {1: ("86% / +0.21R (154)", "trig_hot"),
                  2: ("83% / +0.23R (197)", "arr_hot"),
                  3: ("76% / +0.11R", "arr_long")}
ARRIVAL_WINDOW = "15 Aug → 28 Sep"


# ───────────────────────── clock helpers ─────────────────────────
def pkt_hm(ts: float) -> str:
    return time.strftime("%H:%M", time.gmtime(float(ts) + PK))


def pkt_hour(ts: float) -> int:
    return int(((float(ts) + PK) // 3600) % 24)


def pkt_day(ts: float) -> str:
    return time.strftime("%d %b", time.gmtime(float(ts) + PK))


def is_night(hour: int) -> bool:
    """21:00 -> 05:00 PKT — the windows where star longs ran weakest."""
    return hour >= 21 or hour < 5


def _r(v: float) -> str:
    return f"{'+' if v >= 0 else '−'}{abs(v):.2f}R"


def cell(pnls) -> tuple:
    """(n, win%, avg R) of a list of pnl_r."""
    pnls = [float(x) for x in pnls if x is not None]
    n = len(pnls)
    if not n:
        return (0, 0.0, 0.0)
    w = sum(1 for x in pnls if x > 0)
    return (n, w / n * 100.0, sum(pnls) / n)


def light(c: tuple) -> str:
    """🟢 / 🟡 / 🔴 — the clock's verdict light (user 2026-10-05: "previously
    we had buttons for the time, can we have them again?"), same thresholds
    as the old 🕐 tagline: a verdict needs buzz_clock.MIN_N closes; 🟢 at
    avg >= GREEN_R with win >= 50%; 🔴 at avg <= RED_R; 🟡 otherwise."""
    n, wp, ar = c
    if n < buzz_clock.MIN_N:
        return "🟡"
    if ar >= buzz_clock.GREEN_R and wp >= 50:
        return "🟢"
    if ar <= buzz_clock.RED_R:
        return "🔴"
    return "🟡"


def rec(c: tuple) -> str:
    """'77% / +0.49R (48)' — or honest 'young (n closes)' under MIN_N."""
    n, wp, ar = c
    if n < MIN_N:
        return f"young ({n} close{'s' if n != 1 else ''})" if n else "no closes yet"
    return f"{wp:.0f}% / {_r(ar)} ({n})"


# ───────────────────────── desk reads ─────────────────────────
def _connect(db_path: str | None = None) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path or store.DB_PATH}?mode=ro",
                           uri=True, timeout=10)


def _load(tier: str, db_path: str | None) -> dict:
    """Join the tier's closed desk trades to their ⏱ verdict (elite_1h) and
    ⭐⚡ GO (star_go) stamps. The frozen / ignited classes are only meaningful
    on the star tier (GO stamps exist for stars only)."""
    con = _connect(db_path)
    try:
        rows = con.execute(
            "SELECT symbol, side, opened_at, closed_at, pnl_r FROM shadow_trades "
            "WHERE tier=? AND status='CLOSED' AND closed_at IS NOT NULL AND "
            "pnl_r IS NOT NULL AND entry>0 AND abs(entry-stop0)/entry>=?",
            (tier, CLEAN)).fetchall()
        vd = con.execute("SELECT symbol, side, ts, tier FROM signals "
                         "WHERE stream='elite_1h'").fetchall()
        go = con.execute("SELECT symbol, side, ts FROM signals "
                         "WHERE stream IN ('star_go', 'elite_go')").fetchall()
        chase = [r[0] for r in con.execute(
            "SELECT pnl_r FROM shadow_trades WHERE tier='star_go_chase' AND "
            "status='CLOSED' AND pnl_r IS NOT NULL")]
    finally:
        con.close()
    vmap, gmap = defaultdict(list), defaultdict(list)
    for s, d, ts, t in vd:
        vmap[(s, (d or "").upper())].append((float(ts), str(t or "").upper()))
    for s, d, ts in go:
        gmap[(s, (d or "").upper())].append(float(ts))
    keys = ("all", "night", "day", "live", "dead", "dead_go", "dead_nogo",
            "go4h", "frozen", "frozen_night", "frozen_day", "ignited_night",
            "ignited_day")
    cls = {k: [] for k in keys}
    first = last = None
    for sym, side, o, c, r in rows:
        side = (side or "").upper()
        o, c, r = float(o), float(c), float(r)
        first = o if first is None else min(first, o)
        last = c if last is None else max(last, c)
        night = is_night(pkt_hour(o))
        cls["all"].append(r)
        cls["night" if night else "day"].append(r)
        v = next((t for ts, t in sorted(vmap.get((sym, side), ()))
                  if o + 45 * 60 <= ts < o + 3 * 3600), None)
        g = next((ts for ts in sorted(gmap.get((sym, side), ()))
                  if o < ts < o + 24 * 3600), None)
        ignited4 = g is not None and (g - o) <= 4 * 3600
        if v == "LIVE":
            cls["live"].append(r)
        elif v == "DEAD":
            cls["dead"].append(r)
            (cls["dead_go"] if g is not None else cls["dead_nogo"]).append(r)
        if ignited4:
            cls["go4h"].append(r)
            cls["ignited_night" if night else "ignited_day"].append(r)
        elif c - o >= 4 * 3600:   # alive and silent at the 4h mark
            cls["frozen"].append(r)
            cls["frozen_night" if night else "frozen_day"].append(r)
    return {"tier": tier, "t": time.time(), "first": first, "last": last,
            "n": len(rows), "cls": {k: cell(v) for k, v in cls.items()},
            "chase": cell(chase)}


def _empty(tier: str, now: float) -> dict:
    """What a bell gets when the desk cannot be read: every class empty, so
    the lines print 'no closes yet' / 'record unavailable' — the bell itself
    still goes out (a stats failure must never silence a bell)."""
    keys = ("all", "night", "day", "live", "dead", "dead_go", "dead_nogo",
            "go4h", "frozen", "frozen_night", "frozen_day", "ignited_night",
            "ignited_day")
    return {"tier": tier, "t": now, "first": None, "last": None, "n": 0,
            "cls": {k: (0, 0.0, 0.0) for k in keys}, "chase": (0, 0.0, 0.0),
            "error": True}


def classes(tier: str, now: float | None = None,
            db_path: str | None = None) -> dict:
    now = time.time() if now is None else now
    hit = _CACHE.get(("cls", tier, db_path))
    if hit and now - hit["t"] < TTL:
        return hit
    try:
        st = _load(tier, db_path)
    except Exception as exc:
        print("  rung_stats desk read failed:", exc, flush=True)
        return _empty(tier, now)          # not cached: retried next call
    st["t"] = now
    _CACHE[("cls", tier, db_path)] = st
    return st


def tier_rec(tier: str, days: int | None = None, now: float | None = None,
             db_path: str | None = None) -> tuple:
    """(n, win%, avg R) of a desk tier's clean closes, optionally the last N
    days by close time. Cached 30 min."""
    now = time.time() if now is None else now
    key = ("rec", tier, days, db_path)
    hit = _CACHE.get(key)
    if hit and now - hit["t"] < TTL:
        return hit["c"]
    try:
        con = _connect(db_path)
        try:
            q = ("SELECT pnl_r FROM shadow_trades WHERE tier=? AND "
                 "status='CLOSED' AND pnl_r IS NOT NULL AND entry>0 AND "
                 "abs(entry-stop0)/entry>=?")
            args = [tier, CLEAN]
            if days:
                q += " AND closed_at>=?"
                args.append(now - days * 86400)
            c = cell([r[0] for r in con.execute(q, args)])
        finally:
            con.close()
    except Exception as exc:
        print("  rung_stats tier read failed:", exc, flush=True)
        return (0, 0.0, 0.0)              # 'no closes yet', bell still rings
    _CACHE[key] = {"t": now, "c": c}
    return c


def stamp(st: dict) -> str:
    if not st.get("n"):
        return "record unavailable"
    return (f"measured on the desk {pkt_day(st['first'])} → {pkt_day(st['last'])}"
            f" · refreshed {pkt_hm(st['t'])} PKT")


def stamp_now(now: float) -> str:
    return f"refreshed {pkt_hm(now)} PKT"


def next_line(now: float) -> str:
    return (f"next: ⏱ verdict {pkt_hm(now + 3600)} · ⭐⚡ GO window till "
            f"{pkt_hm(now + 4 * 3600)} · ❄️ freeze after")


# ───────────────────────── rung 1: the fire bells ─────────────────────────
def star_fire(p: dict, conf, now: float, chips=(), kr_line: str = "",
              db_path: str | None = None) -> str:
    """⭐ ELITE STAR fire bell: action word first, plan, chips, the rule, the
    window record with both stamps, what comes next, the Kronos line."""
    side = (p.get("side") or "").upper()
    base = p.get("base") or str(p.get("symbol") or "").replace("USDT", "")
    hour = pkt_hour(now)
    win = buzz_clock.window_of(hour)
    night = is_night(hour)
    st = classes("elite_star", now, db_path)
    C = st["cls"]
    try:
        bc = buzz_clock.stats("elite_star", now, db_path)
    except Exception:
        bc = {}
    wcell = bc.get((side, win), (0, 0.0, 0.0))
    who = "longs" if side == "LONG" else "shorts"
    action = ("TAKE HALF, or wait for GO (night fire)" if night
              else f"TAKE (full size: {win} PKT window)")
    e, s, t1 = float(p["entry"]), float(p["stop"]), float(p["tp1"])
    t2 = p.get("tp2")
    plan = (f"entry `{e:g}` · SL `{s:g}` · TP1 `{t1:g}`"
            + (f" · TP2 `{float(t2):g}`" if t2 else "")
            + f" · {str(p.get('tier') or 'HIGH')} "
              f"{float(p.get('score') or 0):.0f} · "
            + ("🚀 approved" if p.get("appr") else "⚠️ unapproved"))
    chips_line = " · ".join(str(c) for c in chips if c)
    if not chips_line and conf is not None:
        chips_line = f"🎯 conf {conf}"
    if night:
        wl = (f"window record: {light(wcell)} {win} PKT {who} {rec(wcell)} · "
              f"night fires {rec(C['night'])} · frozen night fires "
              f"{rec(C['frozen_night'])} · ignited night fires "
              f"{rec(C['ignited_night'])}")
    else:
        wl = (f"window record: {light(wcell)} {win} PKT {who} {rec(wcell)} · "
              f"day fires {rec(C['day'])} · night fires {rec(C['night'])}")
    hn, hw, ha = bc.get((side, hour), (0, 0.0, 0.0))
    if hn >= buzz_clock.MIN_H and abs(ha) >= buzz_clock.HOUR_R:
        wl += (f" · {'⚠️' if ha < 0 else '✨'} {hour:02d}:00 itself: "
               f"{hw:.0f}% / {_r(ha)} ({hn})")
    lines = [f"⭐ *ELITE STAR — {base} {side} · {action} · {pkt_hm(now)} PKT*",
             plan]
    if chips_line:
        lines.append(chips_line)
    lines += ["rule: enter at the buzz, no conf filter", wl, stamp(st),
              next_line(now)]
    msg = "\n".join(lines)
    kr = (kr_line or "").strip()
    if kr:
        msg += "\n" + kr
    return msg


def agrade_head(p: dict, now: float) -> str:
    base = p.get("base") or str(p.get("symbol") or "").replace("USDT", "")
    return f"💎🏆 *ELITE A-GRADE — {base} LONG · TAKE · {pkt_hm(now)} PKT*"


def arrival_record(tier: int, now: float, db_path: str | None = None) -> str:
    rp, tname = ARRIVAL_REPLAY[int(tier)]
    fwd = tier_rec(tname, None, now, db_path)
    return (f"T{int(tier)} record: replay {rp}, {ARRIVAL_WINDOW} · forward desk "
            f"{rec(fwd)} · {stamp_now(now)}")


# ───────────────────────── rungs 2-4: thread replies ─────────────────────────
def verdict_text(ew: dict, prg: float, now: float,
                 db_path: str | None = None) -> str:
    star = bool(ew.get("star"))
    st = classes("elite_star" if star else "elite_conv", now, db_path)
    C = st["cls"]
    fam = "⭐ stars" if star else "elite fires"
    base, side, when = ew["base"], ew["side"], pkt_hm(now)
    if ew.get("oneh") == "LIVE":
        return (f"⏱ *{base} {side} · 1H LIVE at {when} PKT · HOLD FULL*\n"
                f"{prg * 100:+.0f}% of the path at 60 min · LIVE class "
                f"({fam}) {rec(C['live'])}\n{stamp(st)}")
    l3 = (f"DEAD then ignited ({fam}): {rec(C['dead_go'])} · DEAD never "
          f"ignited: {rec(C['dead_nogo'])}")
    return (f"⏱ *{base} {side} · 1H DEAD at {when} PKT · HOLD — no add, no cut*\n"
            f"{prg * 100:+.0f}% of the path at 60 min\n{l3}\n{stamp(st)}")


def go_text(ew: dict, prg: float, age_s: float, px: float, now: float,
            db_path: str | None = None) -> str:
    star = bool(ew.get("star"))
    st = classes("elite_star" if star else "elite_conv", now, db_path)
    C = st["cls"]
    fam = "⭐ stars" if star else "elite fires"
    emo = "⭐⚡" if star else "💎⚡"
    base, side = ew["base"], ew["side"]
    late = age_s > 4 * 3600
    # ⭐⚡ REVIVED (user 2026-10-05: "where does our GO revived go?"): a fire
    # the 1H verdict graded DEAD that ignites anyway keeps its name in the
    # header — the old revival bell, now inside the thread.
    rev = ew.get("oneh") == "DEAD"
    head = (f"{emo} *GO — {base} {side} · {'REVIVED · ' if rev else ''}PROTECT · "
            f"{pkt_hm(now)} PKT ({age_s / 3600:.1f}h after the fire"
            f"{', late' if late else ''})*")
    l2 = f"ignited: {prg * 100:+.0f}% of the path · live `{float(px):g}`"
    if ew.get("oneh") == "DEAD":
        lab, c = f"DEAD then ignited ({fam})", C["dead_go"]
    else:
        lab, c = f"ignited within 4h ({fam})", C["go4h"]
    l3 = f"holding it: hold to TP1 / TP2, do not bank early · {lab} {rec(c)}"
    sgn = 1 if side == "LONG" else -1
    e0 = float(ew.get("entry0") or 0)
    risk = abs(e0 - float(ew["stop"])) if e0 else 0.0
    r_left = ((float(ew["tp1"]) - float(px)) * sgn / risk) if risk > 0 else None
    if r_left is None:
        l4 = (f"not in it: entry at GO measured {rec(st['chase'])} — a hold "
              f"bell, not an entry bell")
    elif r_left >= 1.0:
        l4 = (f"not in it: {r_left:.1f}R left to TP1 from here · entry at GO "
              f"measured {rec(st['chase'])} — small, your call")
    else:
        l4 = f"not in it: {r_left:.1f}R left to TP1 from here — PASS"
    return "\n".join([head, l2, l3, l4, stamp(st)])


def freeze_text(ew: dict, now: float, db_path: str | None = None) -> str:
    st = classes("elite_star", now, db_path)
    C = st["cls"]
    base, side = ew["base"], ew["side"]
    night = is_night(pkt_hour(float(ew.get("fired_at") or now)))
    fn, fd = C["frozen_night"], C["frozen_day"]
    if night:
        act = "FREEZE — free the seat"
        l2 = f"night frozen fires: {rec(fn)} · day frozen fires: {rec(fd)}"
        l3 = ("no adds · lowest priority · release it the moment a ⭐ / T1 / "
              "A-GRADE bell needs capital")
    else:
        act = "FREEZE — hold, no adds"
        l2 = f"day frozen fires: {rec(fd)} · night frozen fires: {rec(fn)}"
        l3 = ("no adds · the plan's SL / TP stay in charge"
              + (" · this class still pays a little, so no cut"
                 if fd[0] >= MIN_N and fd[2] > 0 else
                 " · lowest priority if a ⭐ / T1 / A-GRADE bell needs the "
                 "capital"))
    head = f"❄️ *{base} {side} · silent at 4h · {pkt_hm(now)} PKT · {act}*"
    return "\n".join([head, l2, l3, stamp(st)])


# ───────────────────────── 09:00 PKT scoreboard ─────────────────────────
def _outcome(tr) -> tuple:
    closed = [float(r[4]) for r in tr if r[3] == "CLOSED" and r[4] is not None]
    open_n = sum(1 for r in tr if r[3] == "OPEN")
    won = sum(1 for x in closed if x > 0)
    return len(closed), won, sum(closed), open_n


def _line(label: str, n_fires: int, tr, none_txt: str) -> str:
    if not n_fires:
        return f"{label}: {none_txt}"
    nc, won, net, op = _outcome(tr)
    s = f"{label} {n_fires} fire{'s' if n_fires != 1 else ''}: "
    s += (f"{won} won of {nc} closed, {net:+.1f}R" if nc else "none closed yet")
    if op:
        s += f" · {op} still open"
    return s


def scoreboard(now: float, db_path: str | None = None) -> str:
    """📊 RUNG-1 SCOREBOARD — yesterday (00:00 → 23:59 PKT): the ⭐ / ⚡🔥 T1-T2
    / 💎🏆 fires, how many won, their R, GO and freeze counts, the 30-day desk."""
    pk = now + PK
    start = (pk // 86400) * 86400 - 86400 - PK      # yesterday 00:00 PKT, UTC
    end = start + 86400
    con = _connect(db_path)
    try:
        fires = {}
        for stream in ("elite_star", "elite_agrade", "trig_hot", "arr_hot"):
            seen, out = set(), []
            for s, d, ts in con.execute(
                    "SELECT symbol, side, ts FROM signals WHERE stream=? AND "
                    "ts>=? AND ts<? ORDER BY ts", (stream, start, end)):
                k = (s, (d or "").upper())
                if k in seen:
                    continue
                seen.add(k)
                out.append((s, k[1], float(ts)))
            fires[stream] = out
        trades = {}
        for tier in ("elite_star", "elite_agrade", "trig_hot", "arr_hot"):
            trades[tier] = con.execute(
                "SELECT symbol, side, opened_at, status, pnl_r FROM shadow_trades"
                " WHERE tier=? AND opened_at>=? AND opened_at<?",
                (tier, start, end)).fetchall()
        go = con.execute("SELECT symbol, side, ts FROM signals WHERE "
                         "stream='star_go' AND ts>=? AND ts<?",
                         (start, end + 24 * 3600)).fetchall()
    finally:
        con.close()
    t1 = fires["trig_hot"]
    t2 = [f for f in fires["arr_hot"]
          if not any(g[0] == f[0] and g[1] == f[1] and abs(g[2] - f[2]) < 600
                     for g in t1)]
    t2_tr = [r for r in trades["arr_hot"]
             if not any(q[0] == r[0]
                        and (q[1] or "").upper() == (r[1] or "").upper()
                        and abs(float(q[2]) - float(r[2])) < 600
                        for q in trades["trig_hot"])]
    star_f = fires["elite_star"]

    def _go_for(f, within):
        return any(gs == f[0] and (gd or "").upper() == f[1]
                   and f[2] < float(gts) <= f[2] + within for gs, gd, gts in go)
    g_n = sum(1 for f in star_f if _go_for(f, 24 * 3600))
    froze = sum(1 for f in star_f
                if now - f[2] >= 4 * 3600 and not _go_for(f, 4 * 3600))
    star_line = _line("⭐ star", len(star_f), trades["elite_star"], "no fires")
    if star_f:
        star_line += f" · GO on {g_n}, froze {froze}"
    day = time.strftime("%a %d %b", time.gmtime(start + PK))
    lines = [
        f"📊 *RUNG-1 SCOREBOARD — {day}, 00:00 → 23:59 PKT* · built "
        f"{pkt_hm(now)} PKT",
        star_line,
        _line("⚡🔥 T1", len(t1), trades["trig_hot"], "no fires") + " · "
        + _line("⚡🔥 T2", len(t2), t2_tr, "no fires"),
        _line("💎🏆 A-GRADE", len(fires["elite_agrade"]), trades["elite_agrade"],
              "no fires (no Top Conviction seat paired with an elite card)"),
        f"30-day desk: star {rec(tier_rec('elite_star', 30, now, db_path))} · "
        f"T1 {rec(tier_rec('trig_hot', 30, now, db_path))} · "
        f"T2 {rec(tier_rec('arr_hot', 30, now, db_path))} · "
        f"A-grade {rec(tier_rec('elite_agrade', 30, now, db_path))}",
        stamp_now(now)]
    return "\n".join(lines)
