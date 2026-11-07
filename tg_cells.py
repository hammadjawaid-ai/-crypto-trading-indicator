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
