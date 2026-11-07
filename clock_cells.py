"""🕐 CLOCK CELLS — the measured side × PKT-window record of the two gated
elite bells, as a one-line TAKE / HALF / DON'T read for the board cards and
the phone (user 2026-10-17: "take trade, or dont because of time").

Cells are the desk ledger from the FIRE price, trades that PASS today's
gates (⭐ star: four-rule read; GO REVIVED: the two card rules), split by
side and the fire's 4h PKT window. Static and dated — re-measure with
.wl_splits_study.py + the side × window split when a new backup lands.
A label, never a gate: the bell rings and the card shows regardless."""
from __future__ import annotations

STAR_MEASURED = "gated ⭐ record 09 Sep → 04 Nov"   # 2026-11-04 refresh: 226 rung / 282 muted desk closes, gate stamped since 14 Oct, the same four rules reconstructed before
REVIVED_MEASURED = "gated GO REVIVED record 13 Sep → 14 Oct"
MIN_N = 10            # fewer trades than this -> no time call

# (win %, avg R, n) — ⭐ ELITE STAR fires that passed the four-rule read
STAR_CELLS = {   # rung stars (gate pass), desk closes 09 Sep → 04 Nov, by side × FIRE window
    ("LONG", "05–09"): (69, 0.44, 26), ("LONG", "09–13"): (71, 0.50, 21),
    ("LONG", "13–17"): (27, -0.51, 11), ("LONG", "17–21"): (64, 0.41, 47),
    ("LONG", "21–01"): (66, 0.42, 38), ("LONG", "01–05"): None,       # closed by the gate
    ("SHORT", "05–09"): (71, 0.33, 17), ("SHORT", "09–13"): (45, -0.09, 11),
    ("SHORT", "13–17"): (73, 0.21, 11), ("SHORT", "17–21"): (79, 0.60, 33),
    ("SHORT", "21–01"): (82, 0.63, 11), ("SHORT", "01–05"): None,
}
# (win %, avg R, n) — GO REVIVED (DEAD at 1h then ignited) that passed the
# two card rules, by the FIRE's window
REVIVED_CELLS = {
    ("LONG", "05–09"): (53, 0.06, 19), ("LONG", "09–13"): (73, 0.45, 15),
    ("LONG", "13–17"): (36, -0.02, 11), ("LONG", "17–21"): (57, 0.44, 14),
    ("LONG", "21–01"): (71, 0.60, 17), ("LONG", "01–05"): (56, 0.43, 16),
    ("SHORT", "05–09"): (78, 0.70, 9), ("SHORT", "09–13"): (50, 0.18, 6),
    ("SHORT", "13–17"): (43, 0.18, 7), ("SHORT", "17–21"): (79, 0.62, 19),
    ("SHORT", "21–01"): (0, -1.01, 1), ("SHORT", "01–05"): (67, 0.12, 9),
}


def window_of(ts: float) -> str:
    """4h PKT window label (en dash, as buzz_clock prints it)."""
    h = int(((float(ts) + 5 * 3600) // 3600) % 24)
    for lo, hi, lab in ((5, 9, "05–09"), (9, 13, "09–13"), (13, 17, "13–17"), (17, 21, "17–21")):
        if lo <= h < hi:
            return lab
    return "21–01" if (h >= 21 or h < 1) else "01–05"


def verdict(cells: dict, side: str, ts: float, closed_note: str = "closed by the gate") -> tuple[str, str, str]:
    """-> (emoji, call, detail). call in {'TAKE', 'HALF', "DON'T", 'THIN'}.
    TAKE  = win >= 65% and avg >= +0.25R with MIN_N+ trades
    DON'T = win <= 45% or avg <= 0R with MIN_N+ trades (time, not the card)
    HALF  = anything else with MIN_N+ trades
    THIN  = fewer than MIN_N trades -> no time call."""
    side = (side or "").upper()
    win = window_of(ts)
    cell = cells.get((side, win), "missing")
    if cell is None:
        return "🔴", "DON'T", f"{win} PKT {side.lower()}s — {closed_note}"
    if cell == "missing":
        return "🟡", "THIN", f"{win} PKT {side.lower()}s — no record"
    w, r, n = cell
    detail = f"{win} PKT {side.lower()}s {w}% / {r:+.2f}R ({n})"
    if n < MIN_N:
        return "🟡", "THIN", detail + " — thin, no time call"
    if w >= 65 and r >= 0.25:
        return "🟢", "TAKE", detail
    if w <= 45 or r <= 0:
        return "🔴", "DON'T", detail + " — the time, not the card"
    return "🟡", "HALF", detail


# 🕐 13–17 PKT is the one UNGATED window for the ⭐ bell (user 2026-10-17): every
# star fire rings there, with this caution first. Measured 09 Sep → 14 Oct.
STAR_1317_CAUTION = {
    "LONG": ("🕐 ⚠️ 13–17 PKT — UNGATED window (your call): longs that passed the read "
             "ran 33% / -0.40R (9), the ones it would have muted 68% / +0.25R (25) — "
             "thin both ways, size with caution"),
    "SHORT": ("🕐 ⚠️ 13–17 PKT — UNGATED window (your call): shorts that passed the read "
              "ran 86% / +0.43R (7), the ones it would have muted 57% / -0.02R (7) — "
              "thin both ways, size with caution"),
}


def star_1317_caution(side: str) -> str:
    return STAR_1317_CAUTION.get((side or "").upper(), STAR_1317_CAUTION["LONG"])


# (win %, avg R, n) — ⭐⚡ ELITE GO: star LIVE at the hour, then ignited; by the
# FIRE's window. Most cells are thin and say so (user 2026-10-17: "do this for
# elite go as well … same time logic").
ELITE_GO_MEASURED = "⭐⚡ ELITE GO record 13 Sep → 14 Oct"
ELITE_GO_CELLS = {
    ("LONG", "05–09"): (100, 0.93, 7), ("LONG", "09–13"): (80, 0.87, 5),
    ("LONG", "13–17"): (67, 0.26, 9), ("LONG", "17–21"): (82, 0.60, 17),
    ("LONG", "21–01"): (83, 0.83, 12), ("LONG", "01–05"): (67, 0.37, 3),
    ("SHORT", "05–09"): (100, 1.19, 2), ("SHORT", "09–13"): (0, -1.02, 1),
    ("SHORT", "13–17"): (80, 0.26, 5), ("SHORT", "17–21"): (50, -0.02, 6),
    ("SHORT", "21–01"): (67, 0.50, 3), ("SHORT", "01–05"): (100, 0.77, 3),
}


# ── 7-WEEK CANDLE REPLAY cells (.revived_clock_history.py rows, 16 Aug → 10 Oct,
# from the fire price): the FALLBACK when a desk cell is thin (user 2026-10-18:
# "this reading is wrong for 21–01 PKT shorts" — the desk had ONE gated trade
# there, the replay has 29 at 59% / +0.07R). Desk first, replay second, THIN
# only when both are thin.
REPLAY_MEASURED = "7-week candle replay 16 Aug → 10 Oct"
REVIVED_REPLAY_CELLS = {   # DEAD then GO, two card rules passed
    ("LONG", "05–09"): (68, 0.48, 41), ("LONG", "09–13"): (63, 0.31, 27), ("LONG", "13–17"): (56, 0.33, 45),
    ("LONG", "17–21"): (47, -0.02, 78), ("LONG", "21–01"): (52, 0.08, 65), ("LONG", "01–05"): (57, 0.10, 42),
    ("SHORT", "05–09"): (57, 0.05, 23), ("SHORT", "09–13"): (50, -0.06, 22), ("SHORT", "13–17"): (68, 0.22, 25),
    ("SHORT", "17–21"): (70, 0.37, 54), ("SHORT", "21–01"): (59, 0.07, 29), ("SHORT", "01–05"): (50, -0.07, 30),
}
# ── GO REVIVED split by FAMILY (user 2026-10-18: "this reading is for elite star
# not elite conviction, separate them"): the combined cells above were 101
# stars + 42 conviction fires and the clock behaves differently for each.
REVIVED_STAR_MEASURED = "⭐ star revived record 14 Sep → 04 Nov (DEAD at the hour then GO, from the fire price)"
REVIVED_CONV_MEASURED = "💎 conviction revived record 14 Sep → 04 Nov (DEAD at the hour then GO, from the fire price)"
REVIVED_STAR_CELLS = {     # 2026-11-04: star DEAD at the hour then GO (all), FIRE plan from the FIRE price, 14 Sep → 04 Nov, by the FIRE's window
    ("LONG", "05–09"): (60, 0.14, 5), ("LONG", "09–13"): (59, 0.10, 17), ("LONG", "13–17"): (29, -0.38, 7),
    ("LONG", "17–21"): (64, 0.24, 14), ("LONG", "21–01"): (50, -0.19, 10),
    ("SHORT", "05–09"): (50, -0.29, 6), ("SHORT", "09–13"): (87, 0.57, 15), ("SHORT", "13–17"): (100, 0.75, 3),
    ("SHORT", "17–21"): (92, 0.59, 12), ("SHORT", "21–01"): (83, 0.52, 6),
}
REVIVED_CONV_CELLS = {     # 2026-11-04: conviction DEAD at the hour then GO (all), from the FIRE price, 14 Sep → 04 Nov
    ("LONG", "05–09"): (35, -0.40, 17), ("LONG", "09–13"): (58, 0.19, 31), ("LONG", "13–17"): (55, 1.00, 11),
    ("LONG", "17–21"): (65, 0.47, 26), ("LONG", "21–01"): (68, 0.74, 19),
    ("SHORT", "05–09"): (75, 0.27, 8), ("SHORT", "09–13"): (89, 0.91, 27), ("SHORT", "13–17"): (75, 0.73, 8),
    ("SHORT", "17–21"): (77, 0.44, 13), ("SHORT", "21–01"): (56, 0.10, 16),
}
REVIVED_STAR_REPLAY_CELLS = {   # 7-week replay, stars (from 09 Sep), from the fire
    ("LONG", "05–09"): (79, 0.41, 14), ("LONG", "09–13"): (80, 0.48, 10), ("LONG", "13–17"): (62, 0.16, 13),
    ("LONG", "17–21"): (52, -0.06, 21), ("LONG", "21–01"): (67, 0.25, 21), ("LONG", "01–05"): (69, 0.33, 16),
    ("SHORT", "05–09"): (83, 0.43, 6), ("SHORT", "09–13"): (60, 0.14, 5), ("SHORT", "13–17"): (71, 0.26, 7),
    ("SHORT", "17–21"): (94, 0.73, 16), ("SHORT", "21–01"): (71, 0.14, 7), ("SHORT", "01–05"): (82, 0.36, 11),
}
REVIVED_CONV_REPLAY_CELLS = {   # 7-week replay, conviction fires 16 Aug → 10 Oct, from the fire
    ("LONG", "05–09"): (63, 0.51, 27), ("LONG", "09–13"): (53, 0.21, 17), ("LONG", "13–17"): (53, 0.40, 32),
    ("LONG", "17–21"): (46, -0.01, 57), ("LONG", "21–01"): (45, 0.00, 44), ("LONG", "01–05"): (50, -0.04, 26),
    ("SHORT", "05–09"): (47, -0.09, 17), ("SHORT", "09–13"): (47, -0.12, 17), ("SHORT", "13–17"): (67, 0.21, 18),
    ("SHORT", "17–21"): (61, 0.22, 38), ("SHORT", "21–01"): (55, 0.05, 22), ("SHORT", "01–05"): (32, -0.32, 19),
}
ELITE_GO_REPLAY_CELLS = {  # star LIVE at the hour then GO (stars exist from 09 Sep)
    ("LONG", "05–09"): (100, 0.87, 7), ("LONG", "09–13"): (83, 0.52, 6), ("LONG", "13–17"): (86, 0.65, 14),
    ("LONG", "17–21"): (88, 0.64, 16), ("LONG", "21–01"): (100, 1.00, 6), ("LONG", "01–05"): (50, -0.12, 6),
    ("SHORT", "05–09"): (100, 0.98, 3), ("SHORT", "09–13"): (33, -0.43, 3), ("SHORT", "13–17"): (50, 0.06, 2),
    ("SHORT", "17–21"): (73, 0.10, 11), ("SHORT", "21–01"): (50, 0.14, 4), ("SHORT", "01–05"): (75, 0.43, 4),
}
GOLIVE_REPLAY_CELLS = {    # conviction LIVE at the hour then GO, HIGH card, BTC day >= -1.5%
    ("LONG", "05–09"): (75, 1.20, 24), ("LONG", "09–13"): (79, 1.00, 19), ("LONG", "13–17"): (71, 0.42, 34),
    ("LONG", "17–21"): (84, 0.96, 43), ("LONG", "21–01"): (70, 0.70, 20), ("LONG", "01–05"): (83, 1.05, 12),
    ("SHORT", "05–09"): (83, 0.91, 12), ("SHORT", "09–13"): (33, -0.34, 3), ("SHORT", "13–17"): (36, -0.06, 11),
    ("SHORT", "17–21"): (70, 0.62, 23), ("SHORT", "21–01"): (38, -0.17, 8), ("SHORT", "01–05"): (88, 0.58, 8),
}


def verdict2(desk: dict, replay: dict, side: str, ts: float, desk_label: str,
             replay_label: str = REPLAY_MEASURED) -> tuple[str, str, str]:
    """Desk cell when it has MIN_N+ trades; else the replay cell when it has
    MIN_N+; else THIN. The detail names which source (and family) it read."""
    e, c, d = verdict(desk, side, ts)
    if c != "THIN":
        return e, c, f"{d} · {desk_label}"
    dc = desk.get(((side or "").upper(), window_of(ts)))
    n_desk = dc[2] if isinstance(dc, tuple) else 0
    e2, c2, d2 = verdict(replay, side, ts)
    if c2 != "THIN":
        return e2, c2, f"{d2} · {replay_label} (desk thin: {n_desk})"
    return "🟡", "THIN", f"{d.split(' — ')[0]} — thin on the desk ({n_desk}) and in the replay, no time call"


def elite_go_line(side: str, fired_at: float) -> str:
    e, c, d = verdict2(ELITE_GO_CELLS, ELITE_GO_REPLAY_CELLS, side, fired_at, ELITE_GO_MEASURED,
                       f"⭐⚡ ELITE GO, {REPLAY_MEASURED}")
    return f"🕐 {e} {c} — fired {d}"


# (win %, avg R, n) — 💎⚡ GO LIVE: conviction fire LIVE at the hour, then
# ignited; by the FIRE's window (user 2026-10-18: conviction cards too).
GOLIVE_MEASURED = "💎⚡ GO LIVE record 13 Sep → 14 Oct"
GOLIVE_CELLS = {
    ("LONG", "05–09"): (60, 1.48, 5), ("LONG", "09–13"): (33, 0.08, 6),
    ("LONG", "13–17"): (40, 0.45, 5), ("LONG", "17–21"): (50, 0.33, 4),
    ("LONG", "21–01"): (68, 1.13, 19), ("LONG", "01–05"): (50, 0.27, 2),
    ("SHORT", "05–09"): (50, -0.06, 2), ("SHORT", "13–17"): (75, 0.43, 4),
    ("SHORT", "17–21"): (83, 2.02, 6), ("SHORT", "21–01"): (18, -0.28, 11),
    ("SHORT", "01–05"): (0, -0.02, 1),
}


def golive_line(side: str, fired_at: float) -> str:
    e, c, d = verdict2(GOLIVE_CELLS, GOLIVE_REPLAY_CELLS, side, fired_at, GOLIVE_MEASURED,
                       f"💎⚡ GO LIVE, {REPLAY_MEASURED}")
    return f"🕐 {e} {c} — fired {d}"


def star_line(side: str, ts: float) -> str:
    e, c, d = verdict(STAR_CELLS, side, ts)
    return f"🕐 {e} {c} — {d} · {STAR_MEASURED}"


def star_line_short(side: str, ts: float) -> str:
    """The one-line clock cell for the ⭐ bell (2026-11-07, concise cards):
    light + window + the cell, nothing else — the full line stays on the page."""
    e, c, d = verdict(STAR_CELLS, side, ts)
    return f"🕐 {e} {d.split(' — ')[0].replace(' PKT', '')}"


def revived_line(side: str, fired_at: float, star=None) -> str:
    """star=True -> ⭐ star revival cells, False -> 💎 conviction cells, None ->
    the combined cells (family unknown)."""
    if star is True:
        e, c, d = verdict2(REVIVED_STAR_CELLS, REVIVED_STAR_REPLAY_CELLS, side, fired_at, REVIVED_STAR_MEASURED,
                           f"⭐ star revivals, {REPLAY_MEASURED}")
    elif star is False:
        e, c, d = verdict2(REVIVED_CONV_CELLS, REVIVED_CONV_REPLAY_CELLS, side, fired_at, REVIVED_CONV_MEASURED,
                           f"💎 conviction revivals, {REPLAY_MEASURED}")
    else:
        e, c, d = verdict2(REVIVED_CELLS, REVIVED_REPLAY_CELLS, side, fired_at, REVIVED_MEASURED,
                           f"star + conviction revivals, {REPLAY_MEASURED}")
    return f"🕐 {e} {c} — fired {d}"


# ───────────── ⭐ GO FAST / GO LATE by timing (user 2026-11-04: "update these scores") ─────────────
# (held win %, held R, entered win %, entered R, n): HELD = the fire plan from the FIRE price
# (the bell's claim) · ENTERED = buying at the bell, same stop / TP1. Star GOs 14 Sep → 04 Nov,
# 15m candles, 48h, fees. Two keys: the FIRE's window (known at the fire, for the card and the
# ⭐ bell) and the GO's own window (known when the GO lands, for the GO bell). The one entry
# cell that pays is the early-morning GO (01–09 PKT): everything else entered at the bell ≈ 0.
GO_MEASURED = "⭐ GO record 14 Sep → 04 Nov"
GO_FAST_FIRE_CELLS = {
    ("LONG", "05–09"): (91, 0.73, 91, 0.34, 23), ("LONG", "09–13"): (75, 0.33, 72, 0.04, 40), ("LONG", "13–17"): (67, 0.23, 61, -0.04, 24),
    ("LONG", "17–21"): (66, 0.26, 62, -0.06, 50), ("LONG", "21–01"): (77, 0.56, 83, 0.23, 26),
    ("SHORT", "05–09"): (76, 0.31, 76, 0.01, 17), ("SHORT", "09–13"): (86, 0.56, 86, 0.17, 14), ("SHORT", "13–17"): (78, 0.41, 78, 0.08, 9),
    ("SHORT", "17–21"): (78, 0.45, 72, 0.01, 40), ("SHORT", "21–01"): (71, 0.50, 71, 0.11, 7),
}
GO_FAST_GO_CELLS = {
    ("LONG", "05–09"): (92, 0.73, 92, 0.33, 25), ("LONG", "09–13"): (79, 0.46, 78, 0.15, 47), ("LONG", "13–17"): (67, 0.13, 65, -0.08, 21),
    ("LONG", "17–21"): (61, 0.17, 59, -0.11, 41), ("LONG", "21–01"): (72, 0.47, 68, 0.05, 29),
    ("SHORT", "05–09"): (79, 0.40, 79, 0.03, 14), ("SHORT", "09–13"): (82, 0.47, 82, 0.13, 22), ("SHORT", "13–17"): (75, 0.41, 75, 0.06, 8),
    ("SHORT", "17–21"): (79, 0.45, 72, 0.00, 29), ("SHORT", "21–01"): (71, 0.45, 71, 0.05, 14),
}
GO_LATE_FIRE_CELLS = {
    ("LONG", "05–09"): (71, 0.23, 71, -0.02, 7), ("LONG", "09–13"): (83, 0.49, 61, 0.10, 18), ("LONG", "13–17"): (40, -0.17, 40, -0.38, 5),
    ("LONG", "17–21"): (60, 0.73, 60, -0.03, 10), ("LONG", "21–01"): (64, 0.10, 45, -0.17, 11),
    ("SHORT", "05–09"): (60, -0.12, 40, -0.28, 5), ("SHORT", "09–13"): (76, 0.30, 65, -0.06, 17), ("SHORT", "13–17"): (100, 0.77, 100, 0.53, 1),
    ("SHORT", "17–21"): (86, 0.53, 86, 0.15, 7), ("SHORT", "21–01"): (86, 0.46, 86, 0.14, 7),
}
GO_LATE_GO_CELLS = {
    ("LONG", "05–09"): (78, 0.60, 78, 0.18, 9), ("LONG", "09–13"): (78, 0.64, 67, 0.09, 18), ("LONG", "13–17"): (86, 0.29, 57, -0.02, 7),
    ("LONG", "17–21"): (57, 0.13, 43, -0.19, 14), ("LONG", "21–01"): (0, -0.91, 0, -0.93, 3),
    ("SHORT", "05–09"): (85, 0.48, 85, 0.08, 13), ("SHORT", "09–13"): (83, 0.44, 67, 0.05, 6), ("SHORT", "13–17"): (44, -0.30, 33, -0.44, 9),
    ("SHORT", "17–21"): (100, 0.59, 83, 0.30, 6), ("SHORT", "21–01"): (100, 0.80, 100, 0.32, 3),
}
# both sides pooled by the GO's window (the fallback when a side cell is thin)
GO_FAST_GO_POOLED = {"05–09": (87, 0.61, 87, 0.22, 39), "09–13": (80, 0.46, 78, 0.14, 69), "13–17": (69, 0.20, 66, -0.04, 29),
                     "17–21": (69, 0.29, 64, -0.06, 70), "21–01": (72, 0.47, 67, 0.05, 43)}
GO_LATE_GO_POOLED = {"05–09": (82, 0.53, 82, 0.12, 22), "09–13": (79, 0.59, 67, 0.08, 24), "13–17": (59, -0.04, 41, -0.26, 17),
                     "17–21": (70, 0.27, 55, -0.04, 20), "21–01": (50, -0.06, 50, -0.30, 6)}


def go_timing_line(kind: str, side: str, fired_at: float, go_at: float = None) -> str:
    """🕐 the ⭐ GO FAST / LATE timing read. Without go_at: the FIRE's window (for the card and
    the fire bell — what a GO on this fire has done). With go_at: the GO's own window (for the
    GO bell), with the entry call: buy-at-the-bell pays only when the GO lands 01–09 PKT."""
    kind = "LATE" if str(kind).upper() == "LATE" else "FAST"
    side = (side or "").upper()
    if go_at is None:
        cells = GO_FAST_FIRE_CELLS if kind == "FAST" else GO_LATE_FIRE_CELLS
        win = window_of(fired_at)
        c = cells.get((side, win))
        if c is None or c[4] < MIN_N:
            return (f"🕐 ⭐ GO {kind} for {win} PKT {side.lower()}s — thin ({0 if c is None else c[4]}), no record · {GO_MEASURED}")
        hw, hr, ew, er, n = c
        return (f"🕐 ⭐ GO {kind} for {win} PKT {side.lower()}s: held from the fire {hw}% / {hr:+.2f}R · "
                f"entered at the bell {ew}% / {er:+.2f}R ({n}) · {GO_MEASURED}")
    cells = GO_FAST_GO_CELLS if kind == "FAST" else GO_LATE_GO_CELLS
    pooled = GO_FAST_GO_POOLED if kind == "FAST" else GO_LATE_GO_POOLED
    win = window_of(go_at)
    c = cells.get((side, win)); src = f"{side.lower()}s"
    if c is None or c[4] < MIN_N:
        c = pooled.get(win); src = "both sides"
    if c is None or c[4] < MIN_N:
        return f"🕐 GO landing {win} PKT — thin, no entry call · {GO_MEASURED}"
    hw, hr, ew, er, n = c
    call = ("🟢 entry at the bell has paid here" if (er >= 0.10 and ew >= 65)
            else "🟡 hold read only — entry at the bell ≈ flat here" if er > -0.10
            else "🔴 hold read only — entry at the bell LOST here")
    return (f"🕐 GO landing {win} PKT ({src}): held from the fire {hw}% / {hr:+.2f}R · entered at the bell {ew}% / {er:+.2f}R ({n}) — "
            f"{call} · {GO_MEASURED}")

