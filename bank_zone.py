"""🎯 BANK ZONE — the number before TP1 (user 2026-10-24: "with the elite star
buzz or go fast buzz we should have a tp, sl and entry, add one more to it like
90% to TP numbers as well, or the closest as per the situation it may land —
closer numbers as per the read of the patterns and charts and candles").

compute() returns 90% of the way to TP1 by default; when a known chart level
(a resistance for a long, a support for a short, from support_resistance's 1h
zones) sits between 80% and 100% of the path, the zone snaps to just inside that
level — the place the move is most likely to stall first. Information on the
bell and the card; the plan's TP1 stays the plan.

Measured 2026-10-24 on 15m candles with wicks (desk 09 Sep → 09 Oct): stars
reversed from 90%+ of the path back to the stop in 8% of fires (5% on the other
streams); a fixed 90% target measured +0.193R vs +0.166R at the full TP1 on 293
star fires, flat on conviction / trigger / PRIME."""
from __future__ import annotations

REC = ("stars reversed from 90%+ back to the stop in 8% of fires; a 90% target "
       "measured +0.19R vs +0.17R at the full TP1 (293 fires, 09 Sep → 09 Oct, "
       "15m candles) — information, the plan's TP1 stays the plan")
PCT = 0.90          # the default zone, share of the entry → TP1 path
BAND = (0.80, 1.00)  # a chart level inside this share of the path snaps the zone
PAD = 0.0015        # sit this far inside the level (0.15%)


def _price_of(level) -> float | None:
    try:
        if isinstance(level, dict):
            return float(level.get("price"))
        return float(level)
    except (TypeError, ValueError):
        return None


def compute(entry, stop, tp1, side, levels=None, pct: float = PCT):
    """-> {"price", "pct", "note", "level"} or None when the plan is unreadable.
    `levels`: chart levels on the TP1 side of the entry (resistances for a
    long, supports for a short); dicts with a "price" key or plain numbers."""
    try:
        e, s, t = float(entry), float(stop), float(tp1)
    except (TypeError, ValueError):
        return None
    sd = (side or "").upper()
    if sd not in ("LONG", "SHORT") or e <= 0:
        return None
    sgn = 1.0 if sd == "LONG" else -1.0
    path = (t - e) * sgn
    if path <= 0:
        return None
    price = e + sgn * pct * path
    note = f"{pct * 100:.0f}% of the way to TP1"
    hit = None
    cands = []
    for lv in levels or []:
        p = _price_of(lv)
        if p is None or p <= 0:
            continue
        frac = (p - e) * sgn / path
        if BAND[0] <= frac <= BAND[1]:
            cands.append((abs(frac - pct), p, frac))
    if cands:
        _, p, frac = min(cands)
        price = p * (1.0 - PAD) if sgn > 0 else p * (1.0 + PAD)
        hit = p
        note = (f"just {'under the 1h resistance' if sgn > 0 else 'over the 1h support'} "
                f"at {p:g} ({frac * 100:.0f}% of the way)")
    return {"price": price, "pct": (price - e) * sgn / path, "note": note, "level": hit}


def line(bz) -> str:
    """The bell line. '' when there is no zone."""
    if not bz:
        return ""
    return f"🎯 bank zone `{bz['price']:g}` — {bz['note']} · {REC}"


def chip(bz) -> str:
    """The short card chip."""
    if not bz:
        return ""
    return f"🎯 bank {bz['price']:g} ({bz['note']})"
