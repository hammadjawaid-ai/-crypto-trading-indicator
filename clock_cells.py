"""🕐 CLOCK CELLS — the measured side × PKT-window record of the two gated
elite bells, as a one-line TAKE / HALF / DON'T read for the board cards and
the phone (user 2026-10-17: "take trade, or dont because of time").

Cells are the desk ledger from the FIRE price, trades that PASS today's
gates (⭐ star: four-rule read; GO REVIVED: the two card rules), split by
side and the fire's 4h PKT window. Static and dated — re-measure with
.wl_splits_study.py + the side × window split when a new backup lands.
A label, never a gate: the bell rings and the card shows regardless."""
from __future__ import annotations

STAR_MEASURED = "gated ⭐ record 09 Sep → 14 Oct"
REVIVED_MEASURED = "gated GO REVIVED record 13 Sep → 14 Oct"
MIN_N = 10            # fewer trades than this -> no time call

# (win %, avg R, n) — ⭐ ELITE STAR fires that passed the four-rule read
STAR_CELLS = {
    ("LONG", "05–09"): (75, 0.52, 20), ("LONG", "09–13"): (75, 0.50, 16),
    ("LONG", "13–17"): (33, -0.40, 9), ("LONG", "17–21"): (73, 0.43, 22),
    ("LONG", "21–01"): (75, 0.69, 28), ("LONG", "01–05"): None,       # closed by the gate
    ("SHORT", "05–09"): (71, 0.57, 7), ("SHORT", "09–13"): (40, 0.02, 5),
    ("SHORT", "13–17"): (86, 0.43, 7), ("SHORT", "17–21"): (76, 0.54, 25),
    ("SHORT", "21–01"): (57, 0.22, 7), ("SHORT", "01–05"): None,
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
REVIVED_STAR_MEASURED = "gated ⭐ star revived record 13 Sep → 14 Oct"
REVIVED_CONV_MEASURED = "gated 💎 conviction revived record 13 Sep → 14 Oct"
REVIVED_STAR_CELLS = {     # desk, star DEAD at the hour then GO, two card rules passed
    ("LONG", "05–09"): (69, 0.29, 13), ("LONG", "09–13"): (92, 0.75, 12), ("LONG", "13–17"): (43, -0.04, 7),
    ("LONG", "17–21"): (67, 0.42, 9), ("LONG", "21–01"): (67, 0.38, 12), ("LONG", "01–05"): (50, 0.07, 12),
    ("SHORT", "05–09"): (83, 0.67, 6), ("SHORT", "09–13"): (67, 0.37, 3), ("SHORT", "13–17"): (50, -0.08, 4),
    ("SHORT", "17–21"): (79, 0.60, 14), ("SHORT", "01–05"): (67, 0.12, 9),
}
REVIVED_CONV_CELLS = {     # desk, conviction DEAD at the hour then GO, two card rules passed
    ("LONG", "05–09"): (17, -0.44, 6), ("LONG", "09–13"): (0, -0.74, 3), ("LONG", "13–17"): (25, 0.02, 4),
    ("LONG", "17–21"): (40, 0.47, 5), ("LONG", "21–01"): (80, 1.10, 5), ("LONG", "01–05"): (75, 1.52, 4),
    ("SHORT", "05–09"): (67, 0.76, 3), ("SHORT", "09–13"): (33, -0.01, 3), ("SHORT", "13–17"): (33, 0.53, 3),
    ("SHORT", "17–21"): (80, 0.68, 5), ("SHORT", "21–01"): (0, -1.01, 1),
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
