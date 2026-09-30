"""🕐 BUZZ CLOCK — the timing tagline under elite conviction / elite star buzzes.

User 2026-10-01: "with buzzes now we add the times as well — if it's a
long buzz have a tagline below accordingly, if it's short the buzz has
its tagline ... elite conviction and elite star only for now".

WHAT IT SAYS: the hour the buzz fires in PKT, the direction, and what
this stream's OWN live desk record did for that direction in that
4-hour PKT window — win rate, average R, trade count — plus the one
action the data supports. The numbers come straight from the desk
ledger (shadow_trades, closed, clean) and refresh every 30 minutes, so
the tagline keeps learning; nothing is hard-coded from a study.

RULES (from the 2026-09-30 timing studies, project_entry_timing_pkt /
project_elite_star):
  - the verdict is the 4-hour window for THAT stream and direction
    (single hours are too thin to carry a verdict on their own);
  - fewer than MIN_N trades in the cell -> 🟡 "not enough data yet",
    never a fake verdict;
  - an hour note is added only when the fire's own hour has >= MIN_H
    trades and an extreme result (|avg| >= 0.30R) — e.g. star longs
    at 22:00 PKT measured 17% win / -0.61R;
  - it is a LABEL, not a gate: every buzz still goes out.
Fail-soft: any error -> empty string, the buzz goes out without it.
"""
from __future__ import annotations

import sqlite3
import time

PK = 5 * 3600                 # Pakistan time, the user's clock
MIN_N = 15                    # trades needed for a window verdict
MIN_H = 12                    # trades needed for an hour note
GREEN_R, RED_R = 0.10, -0.10  # avg-R lines for 🟢 / 🔴
HOUR_R = 0.30                 # |avg R| that earns an hour note
TTL = 1800                    # stats refresh
MIN_STOP = 0.005              # tiny-stop rows are accounting noise
MAX_ABS_R = 5.0
WINDOWS = ("05–09", "09–13", "13–17", "17–21", "21–01", "01–05")
LABEL = {"elite_star": "star", "elite_conv": "conviction"}
_CACHE: dict = {}


def window_of(hour: int) -> str:
    if 5 <= hour < 9:
        return "05–09"
    if 9 <= hour < 13:
        return "09–13"
    if 13 <= hour < 17:
        return "13–17"
    if 17 <= hour < 21:
        return "17–21"
    if hour >= 21 or hour < 1:
        return "21–01"
    return "01–05"


def _db_path() -> str:
    import worker_store
    return worker_store.DB_PATH


def _load(tier: str, db_path: str | None = None) -> dict:
    """{('LONG'|'SHORT', window|hour:int): (n, win_pct, avg_r)} from the
    desk's closed, clean trades for one tier."""
    path = db_path or _db_path()
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    try:
        rows = c.execute(
            "SELECT side, entry, stop0, pnl_r, opened_at FROM shadow_trades "
            "WHERE tier=? AND status='CLOSED' AND pnl_r IS NOT NULL",
            (tier,)).fetchall()
    finally:
        c.close()
    cells: dict = {}
    for side, entry, stop0, r, opened in rows:
        try:
            entry, stop0, r, opened = (float(entry), float(stop0),
                                       float(r), float(opened))
        except (TypeError, ValueError):
            continue
        if entry <= 0 or abs(entry - stop0) / entry < MIN_STOP \
                or abs(r) > MAX_ABS_R:
            continue
        side = (side or "").upper()
        hour = int(((opened + PK) // 3600) % 24)
        for key in ((side, window_of(hour)), (side, hour)):
            cells.setdefault(key, []).append(r)
    out = {}
    for key, rs in cells.items():
        n = len(rs)
        out[key] = (n, sum(1 for v in rs if v > 0) / n * 100.0,
                    sum(rs) / n)
    return out


def stats(tier: str, now: float | None = None,
          db_path: str | None = None) -> dict:
    now = time.time() if now is None else now
    hit = _CACHE.get(tier)
    if hit and now - hit["t"] < TTL:
        return hit["s"]
    s = _load(tier, db_path)
    _CACHE[tier] = {"t": now, "s": s}
    return s


def _fmt_r(v: float) -> str:
    return f"{'+' if v >= 0 else '−'}{abs(v):.2f}R"


def tagline(tier: str, side: str, now: float | None = None,
            db_path: str | None = None) -> str:
    """The 🕐 line, or "" when nothing honest can be said."""
    try:
        now = time.time() if now is None else now
        side = (side or "").upper()
        if side not in ("LONG", "SHORT") or tier not in LABEL:
            return ""
        s = stats(tier, now, db_path)
        pk = now + PK
        hour = int((pk // 3600) % 24)
        minute = int((pk // 60) % 60)
        win = window_of(hour)
        who = f"{LABEL[tier]} {'longs' if side == 'LONG' else 'shorts'}"
        head = f"🕐 {hour:02d}:{minute:02d} PKT · {side}"
        n, wp, ar = s.get((side, win), (0, 0.0, 0.0))
        if n < MIN_N:
            body = (f"🟡 not enough data for {who} in the {win} PKT "
                    f"window yet ({n} trades) — no verdict")
        elif ar >= GREEN_R and wp >= 50:
            body = (f"🟢 {win} window: {wp:.0f}% win · {_fmt_r(ar)} avg "
                    f"({n} {who}) — enter at the buzz")
        elif ar <= RED_R:
            body = (f"🔴 {win} window: {wp:.0f}% win · {_fmt_r(ar)} avg "
                    f"({n} {who}) — skip or half size")
        else:
            body = (f"🟡 {win} window: {wp:.0f}% win · {_fmt_r(ar)} avg "
                    f"({n} {who}) — flat here; normal size, tighter "
                    f"expectations")
        hn, hw, ha = s.get((side, hour), (0, 0.0, 0.0))
        if hn >= MIN_H and abs(ha) >= HOUR_R:
            body += (f" · {'⚠️' if ha < 0 else '✨'} {hour:02d}:00 itself: "
                     f"{hw:.0f}% win · {_fmt_r(ha)} ({hn})")
        return f"{head} · {body}"
    except Exception:
        return ""
