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


def elite_go_line(side: str, fired_at: float) -> str:
    e, c, d = verdict(ELITE_GO_CELLS, side, fired_at)
    return f"🕐 {e} {c} — fired {d} · {ELITE_GO_MEASURED}"


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
    e, c, d = verdict(GOLIVE_CELLS, side, fired_at)
    return f"🕐 {e} {c} — fired {d} · {GOLIVE_MEASURED}"


def star_line(side: str, ts: float) -> str:
    e, c, d = verdict(STAR_CELLS, side, ts)
    return f"🕐 {e} {c} — {d} · {STAR_MEASURED}"


def revived_line(side: str, fired_at: float) -> str:
    e, c, d = verdict(REVIVED_CELLS, side, fired_at)
    return f"🕐 {e} {c} — fired {d} · {REVIVED_MEASURED}"
