"""🚨 IGNITION — the EARLIEST stream (user 2026-07-25).

User's explicit trade-off: "make it fast and early EVEN IF IT FAILS —
I need that anyhow." This is the at-fire entry we always measured but
never shipped because it costs win rate; the user has now knowingly
accepted that cost for this ONE stream.

What it is: ELITE MAX/HIGH the moment the composite fires (BEFORE the
pullback + confirmation candle that the proven tiers wait for — that
wait is where the 1-2 hours go), gated by the VALIDATED 🚀 approval
check (8-month deep window: approved fires 65.5% vs unapproved 48.5%,
n=423): velocity burst >=78 on the same side OR 6-bar ROC in the top
40% of the last 100 bars.

HONEST EXPECTATIONS (measured, backtest_atfire_verified 2026-07-07):
at-fire + verified won 48.9%/+0.078R on never-tested coins vs
confirmation 70.0%/+0.115R on the same fires. Earlier = weaker, by
construction. Size smaller. The Decision Desk shadow tier builds its
live forward record; the LIVE EXECUTOR does NOT trade this stream
unless it ever earns 🟢 GREEN LIGHT and the user says go.
"""
from __future__ import annotations

import numpy as np

import binance_client
import velocity_burst as _vb


def scan(elite_watch: list) -> list[dict]:
    """At-fire ELITE MAX/HIGH picks that pass the 🚀 approval gate.
    Input: scan_core's elite watch list (plans already structural-
    stopped). Fail-soft per symbol."""
    out: list[dict] = []
    for p in elite_watch or []:
        if (p.get("tier") or "").upper() not in ("MAX", "HIGH"):
            continue
        side = (p.get("side") or "").upper()
        sym = p.get("symbol")
        if not sym or side not in ("LONG", "SHORT"):
            continue
        if not (p.get("entry") and p.get("stop") and p.get("tp1")):
            continue
        try:
            df = binance_client.get_klines(sym, "1h", limit=120)
            c = df["close"].to_numpy()
            roc6 = np.abs(c / np.roll(c, 6) - 1.0)
            roc6[:6] = 0.0
            ref = roc6[-100:-1]
            roc_hot = (len(ref) > 0
                       and float((ref < roc6[-1]).mean() * 100) >= 60)
            bs, bside, _ = _vb.lane_velocity_burst(df)
            vb_ok = bs >= 78 and (bside or "").upper() == side
            if not (roc_hot or vb_ok):
                continue                      # unapproved = the 48% junk
        except Exception:
            continue
        q = dict(p)
        q["ignition"] = True
        out.append(q)
    return out[:6]


def scan_strong(strong_watch: list) -> list[dict]:
    """⚡🚨 STRONG IGNITION — the PIXEL-shape catcher (2026-08-14).

    STRONG-tier fires taken AT FIRE, gated by a HARD velocity burst:
    >=85 on the SAME side. The 40-coin at-fire radius study
    (backtest_atfire_strong, 2,761 fires): plain STRONG at-fire is
    noise (43.2%/+0.058R) and even the 🚀 approval gate barely helps
    (+0.052R) — but STRONG + burst>=85 ran 55.2% win / +0.236R, GREEN
    in both history halves (older +0.400 / recent +0.093, n=62). The
    burst IS the signal: it separates "coin that already moved" from
    "coin that is igniting". Rare by construction (~a few fires/week
    on the top-100). Buzz + desk proving tier only — NO demo money
    until the live record is green.
    """
    out: list[dict] = []
    for p in strong_watch or []:
        if (p.get("tier") or "").upper() != "STRONG":
            continue
        side = (p.get("side") or "").upper()
        sym = p.get("symbol")
        if not sym or side not in ("LONG", "SHORT"):
            continue
        if not (p.get("entry") and p.get("stop") and p.get("tp1")):
            continue
        try:
            df = binance_client.get_klines(sym, "1h", limit=120)
            bs, bside, _ = _vb.lane_velocity_burst(df)
        except Exception:
            continue
        if not (bs >= 85 and (bside or "").upper() == side):
            continue                  # no hard burst = the 43% noise
        q = dict(p)
        q["ignition"] = True
        q["burst"] = round(float(bs))
        out.append(q)
    return out[:4]
