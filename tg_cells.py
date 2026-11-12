"""🕐 TG CELLS — the one window-stamp rule for every Telegram bell (user 2026-11-08: "time stamps on
every signal and buzz on telegram … green for anything 68% and plus, yellow 60–68, red below 60 …
for every stream it should have this inside the information of the signal").

Each bell prints one line: the light, the fire's 4h PKT window and side, and that stream's own
measured record in the window — (win %, avg R, n) — from the clean desk ledger (stops >= 0.3%),
9 Sep → 4 Nov 2026 (.tg_timeframes in the scratch, the 4 Nov backup + research_meta/dataset2.csv).
A label on the card, never a gate: the roster is untouched ("we are not changing it to bold ones
that is for later but keep record"). Re-measure on a new backup and refresh the tables here.

Keys: side-keyed tables take "LONG" / "SHORT"; pooled tables take None; the revival table takes
the GO tier "FAST" / "LATE". Missing cell → "no record". n < 10 → "thin" after the count.
"""
from __future__ import annotations

MEASURED = "9 Sep → 4 Nov"
THIN_N = 10
GREEN_W = 68.0      # 🟢 win >= 68%
YELLOW_W = 60.0     # 🟡 60 <= win < 68 · 🔴 below 60

WINDOWS = ("05–09", "09–13", "13–17", "17–21", "21–01", "01–05")

# ───────── ⭐ gated ELITE STAR, held from the fire, by side × the FIRE's window ─────────
STAR = {
    ("LONG", "05–09"): (69, 0.44, 26), ("LONG", "09–13"): (75, 0.58, 20), ("LONG", "13–17"): (27, -0.51, 11),
    ("LONG", "17–21"): (62, 0.38, 48), ("LONG", "21–01"): (64, 0.38, 39), ("LONG", "01–05"): None,
    ("SHORT", "05–09"): (71, 0.33, 17), ("SHORT", "09–13"): (44, -0.08, 9), ("SHORT", "13–17"): (73, 0.21, 11),
    ("SHORT", "17–21"): (79, 0.60, 33), ("SHORT", "21–01"): (77, 0.51, 13), ("SHORT", "01–05"): None,
}
# ⏱ the hour's verdict on gated stars, held from the fire (the hold read)
STAR_LIVE = {
    ("LONG", "05–09"): (75, 0.59, 8), ("LONG", "09–13"): (75, 0.77, 4), ("LONG", "13–17"): (33, -0.25, 3),
    ("LONG", "17–21"): (79, 1.12, 19), ("LONG", "21–01"): (100, 1.10, 7),
    ("SHORT", "05–09"): (100, 0.77, 7), ("SHORT", "09–13"): (0, -1.02, 1), ("SHORT", "13–17"): (50, -0.14, 4),
    ("SHORT", "17–21"): (100, 1.12, 6), ("SHORT", "21–01"): (80, 0.57, 5),
}
STAR_DEAD = {
    ("LONG", "05–09"): (62, 0.29, 16), ("LONG", "09–13"): (77, 0.52, 13), ("LONG", "13–17"): (20, -0.57, 5),
    ("LONG", "17–21"): (50, -0.15, 24), ("LONG", "21–01"): (56, 0.18, 27),
    ("SHORT", "05–09"): (50, 0.02, 10), ("SHORT", "09–13"): (67, 0.28, 6), ("SHORT", "13–17"): (100, 0.66, 5),
    ("SHORT", "17–21"): (74, 0.45, 19), ("SHORT", "21–01"): (83, 0.64, 6),
}
# ───────── ⭐🤝 pairs, entered at the SECOND fire, by the second fire's window ─────────
STAR_PRIME = {
    ("LONG", "05–09"): (75, 0.47, 12), ("LONG", "09–13"): (90, 0.64, 10), ("LONG", "13–17"): (36, -0.33, 14),
    ("LONG", "17–21"): (45, -0.10, 31), ("LONG", "21–01"): (52, 0.23, 21), ("LONG", "01–05"): (31, -0.33, 13),
    ("SHORT", "05–09"): (80, 0.53, 20), ("SHORT", "09–13"): (50, 0.34, 4), ("SHORT", "13–17"): (25, -0.39, 4),
    ("SHORT", "17–21"): (74, 0.35, 27), ("SHORT", "21–01"): (67, 0.40, 9), ("SHORT", "01–05"): (100, 1.38, 5),
}
STAR_TRIG = {
    ("LONG", "05–09"): (64, 0.20, 14), ("LONG", "09–13"): (83, 0.70, 6), ("LONG", "13–17"): (78, 0.14, 9),
    ("LONG", "17–21"): (75, 0.15, 12), ("LONG", "21–01"): (64, 0.19, 14), ("LONG", "01–05"): (85, 0.40, 13),
    ("SHORT", "05–09"): (75, 0.07, 4), ("SHORT", "09–13"): (57, -0.05, 7), ("SHORT", "13–17"): (67, -0.21, 3),
    ("SHORT", "17–21"): (71, 0.29, 7), ("SHORT", "21–01"): (64, 0.01, 11), ("SHORT", "01–05"): (67, 0.15, 3),
}
STAR_TAKENOW = {   # both sides pooled (52 fires, Sep mostly)
    (None, "05–09"): (60, 0.20, 5), (None, "09–13"): (43, 0.08, 7), (None, "13–17"): (100, 1.02, 6),
    (None, "17–21"): (77, 0.55, 13), (None, "21–01"): (71, 0.71, 17), (None, "01–05"): (0, -0.64, 4),
}
STAR_APEXV2 = {    # both sides pooled (12 fires — thin everywhere)
    (None, "05–09"): (100, 0.69, 1), (None, "09–13"): (100, 1.08, 2), (None, "13–17"): (100, 1.67, 1),
    (None, "17–21"): (100, 0.98, 4), (None, "21–01"): (67, 0.53, 3), (None, "01–05"): (0, -1.04, 1),
}
# ───────── the other bells, their desk tier by the fire's window ─────────
CONV_PRIME = {     # 💎🥇 ELITE × PRIME tier (6 Oct → 4 Nov), by side
    ("LONG", "05–09"): (20, -0.47, 5), ("LONG", "09–13"): (29, -0.44, 7), ("LONG", "13–17"): (0, -0.46, 5),
    ("LONG", "17–21"): (22, -0.35, 9), ("LONG", "21–01"): (50, 0.04, 10), ("LONG", "01–05"): (60, 0.85, 5),
    ("SHORT", "05–09"): (75, 0.70, 4), ("SHORT", "09–13"): (0, -1.03, 2), ("SHORT", "13–17"): (100, 0.68, 2),
    ("SHORT", "17–21"): (86, 1.40, 14), ("SHORT", "21–01"): (67, 0.24, 3), ("SHORT", "01–05"): (50, 0.02, 2),
}
LEG2_PRIME = {     # 🔥🥇 SECOND LEG × PRIME tier (19 closes), pooled
    (None, "05–09"): (80, 0.75, 5), (None, "09–13"): (100, 1.27, 1), (None, "13–17"): None,
    (None, "17–21"): (71, 0.69, 7), (None, "21–01"): (25, -0.56, 4), (None, "01–05"): (50, -0.25, 2),
}
PRIME_TRIG = {     # 💥🥇 PRIME with a strong trigger within 2h (179 fires), pooled
    (None, "05–09"): (69, 0.46, 42), (None, "09–13"): (67, 0.33, 24), (None, "13–17"): (33, -0.33, 15),
    (None, "17–21"): (65, 0.28, 48), (None, "21–01"): (56, 0.03, 34), (None, "01–05"): (62, 0.47, 16),
}
APEX_V2 = {        # 🏆² APEX V2, every fire (22 Sep → 4 Nov), by side
    ("LONG", "05–09"): (47, 0.15, 15), ("LONG", "09–13"): (37, -0.07, 19), ("LONG", "13–17"): (75, 0.50, 16),
    ("LONG", "17–21"): (31, -0.28, 35), ("LONG", "21–01"): (36, -0.07, 25), ("LONG", "01–05"): (43, 0.14, 7),
    ("SHORT", "05–09"): (25, -0.30, 8), ("SHORT", "09–13"): (100, 1.48, 1), ("SHORT", "13–17"): (67, 0.34, 3),
    ("SHORT", "17–21"): (78, 0.54, 18), ("SHORT", "21–01"): (17, -0.77, 6), ("SHORT", "01–05"): (100, 1.16, 5),
}
# ───────── revivals entered AT THE GO (go_revived tier, 6 Oct → 3 Nov), by the GO's window ─────────
CONV_REVIVAL = {   # keyed by the GO tier
    ("FAST", "05–09"): (41, -0.21, 17), ("FAST", "09–13"): (42, -0.18, 12), ("FAST", "13–17"): (62, 0.16, 13),
    ("FAST", "17–21"): (70, 0.26, 20), ("FAST", "21–01"): (40, -0.30, 20), ("FAST", "01–05"): (53, -0.20, 17),
    ("LATE", "05–09"): (71, 0.26, 17), ("LATE", "09–13"): (43, 0.01, 14), ("LATE", "13–17"): (73, 0.14, 11),
    ("LATE", "17–21"): (52, -0.08, 21), ("LATE", "21–01"): (33, -0.40, 6), ("LATE", "01–05"): (55, 0.24, 11),
}
STAR_REVIVAL = {   # ⭐ star revival entered at the GO, pooled
    (None, "05–09"): (90, 0.27, 10), (None, "09–13"): (80, 0.32, 5), (None, "13–17"): (40, -0.42, 10),
    (None, "17–21"): (47, -0.22, 17), (None, "21–01"): (71, -0.01, 14), (None, "01–05"): (43, -0.33, 7),
}

TABLES = {
    "elite_star": (STAR, "⭐ gated stars held from the fire", "side"),
    "star_live": (STAR_LIVE, "⭐ 1H LIVE stars held from the fire", "side"),
    "star_dead": (STAR_DEAD, "⭐ 1H DEAD stars held from the fire", "side"),
    "star_prime": (STAR_PRIME, "⭐🥇 entered at the 2nd fire", "side"),
    "star_trig": (STAR_TRIG, "⭐💥 entered at the 2nd fire", "side"),
    "star_takenow": (STAR_TAKENOW, "⭐✅🔥 entered at the 2nd fire", None),
    "star_apexv2": (STAR_APEXV2, "⭐🏆² entered at the 2nd fire", None),
    "conv_prime": (CONV_PRIME, "💎🥇 ELITE × PRIME tier", "side"),
    "leg2_prime": (LEG2_PRIME, "🔥🥇 SECOND LEG × PRIME tier", None),
    "prime_trig": (PRIME_TRIG, "💥🥇 PRIME + strong trigger ≤2h", None),
    "apex_v2": (APEX_V2, "🏆² APEX V2 every fire", "side"),
    "conv_revival": (CONV_REVIVAL, "💎 revival entered at the GO", "go"),
    "star_revival": (STAR_REVIVAL, "⭐ revival entered at the GO", None),
}
# worker source keys → (table, keyed by side?) for pings that only know the stream name
SRC_TABLE = {"elite_star": "elite_star", "star_prime": "star_prime", "star_trig": "star_trig",
             "star_takenow": "star_takenow", "star_apexv2": "star_apexv2", "conv_prime": "conv_prime",
             "leg2_prime": "leg2_prime", "prime_trig": "prime_trig", "apex_v2": "apex_v2",
             "apex_v2_gated": "apex_v2"}


def window_of(ts: float) -> str:
    h = int(((float(ts) + 5 * 3600) // 3600) % 24)
    for lo, hi, lab in ((5, 9, "05–09"), (9, 13, "09–13"), (13, 17, "13–17"), (17, 21, "17–21")):
        if lo <= h < hi:
            return lab
    return "21–01" if (h >= 21 or h < 1) else "01–05"


def light(win_pct) -> str:
    """🟢 win >= 68 · 🟡 60–68 · 🔴 under 60 (user 2026-11-08). None → 🟡."""
    try:
        w = float(win_pct)
    except (TypeError, ValueError):
        return "🟡"
    return "🟢" if w >= GREEN_W else "🟡" if w >= YELLOW_W else "🔴"


def _key(stream: str, key):
    kind = TABLES[stream][2]
    if kind == "side":
        return (str(key or "").upper() or None)
    if kind == "go":
        return (str(key or "").upper() or None)
    return None


def cell(stream: str, key, ts: float):
    """-> (win, R, n) or None for this stream's cell in the window of `ts`."""
    tab = TABLES.get(stream)
    if tab is None:
        return None
    return tab[0].get((_key(stream, key), window_of(ts)))


def light_of(stream: str, key, ts: float) -> str:
    c = cell(stream, key, ts)
    return light(c[0]) if c else "🟡"


def stamp(stream: str, key, ts: float) -> str:
    """The one line: '🕐 🟢 05–09 longs 75% / +0.47R (12) · ⭐🥇 entered at the 2nd fire · 9 Sep → 4 Nov'."""
    tab = TABLES.get(stream)
    win = window_of(ts)
    if tab is None:
        return f"🕐 🟡 {win} — no record"
    table, label, kind = tab
    k = _key(stream, key)
    who = ({"LONG": "longs", "SHORT": "shorts"}.get(k, "") if kind == "side"
           else (k or "") if kind == "go" else "both sides")
    c = table.get((k, win))
    if c is None:
        return f"🕐 🟡 {win} {who} — no record · {label} · {MEASURED}".replace("  ", " ")
    w, r, n = c
    thin = ", thin" if n < THIN_N else ""
    return f"🕐 {light(w)} {win} {who} {w:.0f}% / {r:+.2f}R ({n}{thin}) · {label} · {MEASURED}".replace("  ", " ")


def stamp_src(src: str, side, ts: float) -> str:
    """'\\n🕐 …' for a worker source key the tables know, else '' (pings)."""
    t = SRC_TABLE.get(str(src or ""))
    if t is None:
        return ""
    key = side if TABLES[t][2] == "side" else None
    return "\n" + stamp(t, key, ts)


# ───────── 🏦 tokenized names: their own desk record, on its own line ─────────
# (user 2026-11-10: "have these for tokenized desk records separately as well"). Every 🕐 cell
# above was measured on crypto; a bell on a tokenized stock adds this line: the same stream's
# record on tokenized names since the restore (config.BSTOCK_RESTORED_TS). Cached 30 min.
TOK_LABEL = {"elite_star": "⭐ stars", "elite_conv": "💎 conviction", "go_revived": "revivals at the GO",
             "star_prime": "⭐🥇 pairs", "star_trig": "⭐💥 pairs", "star_takenow": "⭐✅🔥 pairs",
             "star_apexv2": "⭐🏆² pairs", "conv_prime": "💎🥇 pairs", "leg2_prime": "🔥🥇 pairs",
             "trigkr_prime": "💥🔮🥇 pairs", "prime_trig": "💥🥇 pairs", "apex_v2": "🏆² APEX V2",
             "apex_v2_gated": "🏆💎 APEX V2 GATED"}
TOK_TTL = 1800.0
_TOK_CACHE: dict = {"t": 0.0, "d": None}


def is_tokenized(symbol) -> bool:
    try:
        import config
        return bool(symbol) and str(symbol) in getattr(config, "TOKENIZED_STOCKS", ())
    except Exception:
        return False


def tok_data(now: float | None = None) -> dict:
    """The tokenized desk split (worker_store.shadow_tokenized), cached TOK_TTL."""
    import time as _t
    now = _t.time() if now is None else float(now)
    if _TOK_CACHE["d"] is not None and now - _TOK_CACHE["t"] < TOK_TTL:
        return _TOK_CACHE["d"]
    try:
        import config
        import worker_store as _ws
        d = _ws.shadow_tokenized(sorted(getattr(config, "TOKENIZED_STOCKS", ())),
                                 float(getattr(config, "BSTOCK_RESTORED_TS", 0.0) or 0.0))
    except Exception:
        d = {"since": 0.0, "tiers": {}, "symbols": {}}
    _TOK_CACHE.update(t=now, d=d)
    return d


def tok_rec(n: int, wins: int, net: float) -> str:
    """'no closes yet' · '3 closed, 67% / +0.21R — thin' · '64% / +0.18R (22)'."""
    n = int(n or 0)
    if n <= 0:
        return "no closes yet"
    w, r = wins / n * 100.0, float(net) / n
    return f"{n} closed, {w:.0f}% / {r:+.2f}R — thin" if n < THIN_N else f"{w:.0f}% / {r:+.2f}R ({n})"


def tok_note(symbol, tier: str, now: float | None = None) -> str:
    """'\n🏦 tokenized stock · ⭐ stars on tokenized names since 10 Nov: … · 🕐 cell is crypto-measured'
    for a tokenized symbol, '' for a coin. Never raises."""
    try:
        if not is_tokenized(symbol):
            return ""
        d = tok_data(now)
        t = (d.get("tiers") or {}).get(str(tier)) or {}
        import time as _t
        since = float(d.get("since") or 0.0)
        day = _t.strftime("%d %b", _t.gmtime(since + 5 * 3600)).lstrip("0") if since else "the start"
        return (f"\n🏦 tokenized stock · {TOK_LABEL.get(str(tier), str(tier))} on tokenized names since {day}: "
                f"{tok_rec(t.get('n_since'), t.get('wins_since') or 0, t.get('net_since') or 0.0)}"
                f" · the 🕐 cell is crypto-measured")
    except Exception:
        return ""


# ───────── ⚠️ against the market: a LONG bell while BTC sits under its 50-day average ─────────
# (user 2026-11-13: "yes marked against the market that is better on telegram notifications").
# Measured on the desk: with BTC's last daily close below its 50-day average, longs ran
# 37% / -0.10R (4,047, Jul -> 4 Nov, the audit) and 34% / -0.28R (1,332, 5 -> 12 Nov, fresh
# data), while shorts ran 57% / +0.18R (887) in that second window. The mirror did not hold
# for shorts, so only longs are marked. The worker refreshes the read every cycle
# (set_btc_regime); a read older than MKT_MAX_AGE prints nothing. A mark, never a mute.
MKT_REC = "longs in this state 34% / −0.28R (1,332, 5–12 Nov) · 37% / −0.10R (4,047, Jul–Nov)"
MKT_MAX_AGE = 36 * 3600.0
_MKT: dict = {"t": 0.0, "below": None, "gap": None}


def regime_from_closes(closes):
    """(below, gap %) from COMPLETED daily closes, newest last; (None, None) under 50 closes."""
    xs = []
    for x in closes:
        try:
            xs.append(float(x))
        except (TypeError, ValueError):
            continue
    if len(xs) < 50:
        return None, None
    sma = sum(xs[-50:]) / 50.0
    if sma <= 0:
        return None, None
    return xs[-1] < sma, (xs[-1] / sma - 1.0) * 100.0


def set_btc_regime(closes, now: float | None = None):
    """Store the read (called by the worker each cycle). Returns below / None."""
    import time as _t
    below, gap = regime_from_closes(closes)
    if below is None:
        return None
    _MKT.update(t=float(_t.time() if now is None else now), below=bool(below), gap=float(gap))
    return bool(below)


def market_note(side, now: float | None = None) -> str:
    """'\n⚠️ *AGAINST THE MARKET* — BTC 11.5% under its 50-day average · …' for a LONG while the
    stored read says below; '' otherwise (shorts, BTC above, no read, stale read). Never raises."""
    try:
        import time as _t
        if str(side or "").upper() != "LONG" or _MKT.get("below") is not True:
            return ""
        if float(_t.time() if now is None else now) - float(_MKT.get("t") or 0.0) > MKT_MAX_AGE:
            return ""
        return (f"\n⚠️ *AGAINST THE MARKET* — BTC {abs(float(_MKT['gap'])):.1f}% under its 50-day average · {MKT_REC}")
    except Exception:
        return ""


# ───────── 🚦 the gatekeeper: one line on every fire bell (never a mute) ─────────
# (user 2026-11-13: "build the gatekeeper and make it inside the streams, like not muted but
# just a line so I know things on telegram signals or buzzes"). Four reads, one size:
#   1. MARKET SIDE  BTC's last daily close vs its 50-day average (set_btc_regime). A long while
#      BTC is below = against the market (34% / -0.28R over 1,332, 5-12 Nov; 37% / -0.10R over
#      4,047 before); a short there = with it (57% / +0.18R over 887). The mirror above the
#      average was not measured as a penalty for shorts.
#   2. STREAM TRUST the audit's verdict for the stream (and side where it was measured).
#   3. BURST        other coins that rang a fire bell on this side in the last 2h: three or
#      more is one market move, not that many trades (11 Nov: nine star x PRIME longs, 0 won).
#   4. SIZE         full with no warning, half with one, small with two or more.
# GATEKEEPER = False puts the plain ⚠️ against-the-market line back.
GATEKEEPER = True
GATE_BURST_S = 2 * 3600.0
GATE_BURST_N = 3
BELL_STREAMS = ("elite_star", "star_prime", "star_trig", "star_takenow", "star_apexv2",
                "conv_prime", "leg2_prime", "trigkr_prime", "prime_trig", "apex_v2_gated")
# stream -> (light, text) or {side: (light, text)}; records = clean desk, the audit + the 12 Nov ledger
GATE_TRUST = {
    "elite_star": ("✅", "proven stream"),
    "star_prime": {"SHORT": ("✅", "pair shorts 72% / +0.44R (69)"), "LONG": ("🟡", "pair longs 51% / +0.05R (101)")},
    "star_trig": ("🟡", "pair 71% / +0.19R (103), fading"),
    "star_takenow": ("🟡", "pair thin (52)"),
    "star_apexv2": ("🟡", "pair thin (12)"),
    "conv_prime": {"SHORT": ("✅", "pair shorts 74% / +0.83R (27)"), "LONG": ("🔴", "pair longs 32% / −0.15R (41)")},
    "leg2_prime": ("🟡", "pair thin (19)"),
    "trigkr_prime": ("🔴", "pair did not hold"),
    "prime_trig": ("🟡", "pays only with the APEX card on"),
    "conv_revival": ("🔴", "entered at the GO ≈ 0R: a hold read"),
    "go_revived": ("🔴", "entered at the GO ≈ 0R: a hold read"),
    "apex_v2_gated": {"SHORT": ("✅", "APEX V2 shorts 62% / +0.29R (79)"), "LONG": ("🔴", "APEX V2 longs 41% / −0.03R (124)")},
}
GATE_SIZE = ("full", "half", "small")


def _gate_trust(stream, side):
    t = GATE_TRUST.get(str(stream or ""))
    if isinstance(t, dict):
        t = t.get(str(side or "").upper())
    return t or ("🟡", "unrated stream")


def gate(stream, side, now: float | None = None, symbol=None) -> dict:
    """-> {"size": "full|half|small", "line": "🚦 …", "warn": n}. Never raises."""
    import time as _t
    now = float(_t.time() if now is None else now)
    sd = str(side or "").upper()
    word = "long" if sd == "LONG" else "short"
    warn = 0
    bits = []
    # 1. market side
    fresh = _MKT.get("below") is not None and now - float(_MKT.get("t") or 0.0) <= MKT_MAX_AGE
    if not fresh:
        bits.append("⚪ no market read")
    else:
        gap = abs(float(_MKT.get("gap") or 0.0))
        if _MKT["below"]:
            if sd == "LONG":
                warn += 1
                bits.append(f"🔴 long against the market (BTC {gap:.1f}% under its 50d)")
            else:
                bits.append(f"🟢 short with the market (BTC {gap:.1f}% under its 50d)")
        else:
            bits.append((f"🟢 long with the market (BTC {gap:.1f}% over its 50d)") if sd == "LONG"
                        else f"🟡 short while BTC is {gap:.1f}% over its 50d")
    # 2. stream trust
    lt, tx = _gate_trust(stream, sd)
    if lt == "🔴":
        warn += 1
    bits.append(f"{lt} {tx}")
    # 3. burst
    try:
        import worker_store as _ws
        others = _ws.bell_burst(sd, now - GATE_BURST_S, BELL_STREAMS, symbol)
    except Exception:
        others = None
    if others is not None:
        tot = others + 1
        if tot >= GATE_BURST_N:
            warn += 1
            bits.append(f"🔴 {tot} {word} bells in 2h: one move, not {tot} trades")
        elif tot == 2:
            bits.append(f"🟡 2nd {word} bell in 2h")
        else:
            bits.append(f"🟢 first {word} bell in 2h")
    size = GATE_SIZE[min(warn, 2)]
    return {"size": size, "warn": warn, "line": f"🚦 *GATE → {size.upper()}* · " + " · ".join(bits)}


def gate_note(stream, side, now: float | None = None, symbol=None) -> str:
    """'\n🚦 *GATE → HALF* · …' for a fire bell; the plain ⚠️ line when GATEKEEPER is off."""
    try:
        if not GATEKEEPER:
            return market_note(side, now)
        return "\n" + gate(stream, side, now, symbol)["line"]
    except Exception:
        return ""

