"""✳️ DECISION DESK shadow trader — the FORWARD PROOF engine.

The user's demand (2026-07-08, right): "have you taken a trade at backend
and validated that your signals are working?" — we never had. This engine
makes the 24/7 brain TAKE every tier's signal itself, at live prices, with
real futures fees modeled, and manage the exit — building a transparent
forward track record per tier. A tier earns 🟢 GREEN LIGHT (tradeable) only
when its OWN live record is profitable after fees. Until then it shows as
🧪 PROVING. No backtest numbers — only trades the system actually took.

Exit policy (uniform, answers "how long to hold"):
  - stop:     the signal's structural SL
  - BE move:  stop -> entry at +1R
  - TP1 lock: stop -> TP1 when TP1 is reached; target extends to TP2
  - trail:    after TP1, stop ratchets to (peak - 1.2*initial risk)
  - time-stop: close at market after MAX_HOLD_H hours if still open

Fees: TAKER_FEE per side (Bybit ~0.055%) charged on entry and exit,
expressed in R (fee_pct * entry/risk) so records are honest after-cost.
State: SQLite via worker_store (shadow_trades table). Pure backend — the
app only READS the record for the ✳️ DECISION DESK section.
"""
from __future__ import annotations

import json
import time

import worker_store as store

TAKER_FEE = 0.00055          # per side (Bybit futures taker)
MAX_HOLD_H = 48.0            # time-stop: the "how long to hold" policy
# 🌊 trend_rider is a DAYS-TO-WEEKS strategy (validated ~7-10d avg hold,
# trail-decided) — the uniform 48h cut was force-closing its rides early
# and mismeasuring the tier (found 2026-07-13: LDO cut at 48h as "TIME").
MAX_HOLD_H_BY_TIER = {"trend_rider": 21 * 24.0}
TRAIL_R = 1.2                # post-TP1 trail distance in initial-risk units
GREEN_MIN_TRADES = 20        # a tier needs this many closed trades...
GREEN_MIN_NET_R = 2.0        # ...and this much net R after fees to go GREEN
# RECENCY leg (2026-07-25, the EARLY-LANE lesson: -19R over 12 days
# while still lifetime-green): green ALSO requires a non-negative last-
# 14-days record once there are enough recent closes to judge.
RECENT_DAYS = 14.0
RECENT_MIN_N = 10


def _fees_r(entry: float, risk: float) -> float:
    """Round-trip taker fees expressed in R units."""
    if risk <= 0 or entry <= 0:
        return 0.0
    return (2 * TAKER_FEE) * entry / risk


def open_from_signal(tier: str, p: dict, live_px: float | None) -> bool:
    """Open a shadow trade from a brain signal. One open per (tier, symbol).
    Entry = live price NOW (forward, not the plan's idealised entry)."""
    sym = p.get("symbol")
    side = (p.get("side") or "").upper()
    stop = float(p.get("stop") or 0)
    tp1 = float(p.get("tp1") or 0)
    tp2 = float(p.get("tp2") or 0)
    entry = float(live_px or p.get("entry") or 0)
    if not sym or side not in ("LONG", "SHORT") or entry <= 0 or stop <= 0 \
            or tp1 <= 0:
        return False
    if side == "LONG" and not (stop < entry < tp1):
        return False
    if side == "SHORT" and not (stop > entry > tp1):
        return False
    if store.shadow_has_open(tier, sym):
        return False
    store.shadow_open(tier, sym, side, entry, stop, tp1, tp2)
    return True


def manage(prices: dict) -> list[dict]:
    """Walk every open shadow trade against live prices. Returns closes."""
    now = time.time()
    closed = []
    for t in store.shadow_open_trades():
        px = prices.get(t["symbol"])
        if px is None or px <= 0:
            continue
        side = t["side"]
        entry = float(t["entry"])
        stop = float(t["stop"])
        tp1 = float(t["tp1"])
        tp2 = float(t["tp2"] or 0)
        risk = abs(entry - float(t["stop0"]))
        if risk <= 0:
            continue
        long = side == "LONG"
        gain = (px - entry) if long else (entry - px)
        peak = max(float(t["peak"] or entry), px) if long \
            else min(float(t["peak"] or entry), px)
        st = dict(t)
        st["peak"] = peak
        # --- ladder ------------------------------------------------------
        if not t["be_set"] and gain >= risk:               # +1R -> BE
            stop = entry
            st["be_set"] = 1
        hit_tp1 = (px >= tp1) if long else (px <= tp1)
        if hit_tp1 and not t["tp1_hit"]:                    # lock TP1
            stop = tp1
            st["tp1_hit"] = 1
        if t["tp1_hit"] or hit_tp1:                         # trail after TP1
            trail = (peak - TRAIL_R * risk) if long else (peak + TRAIL_R * risk)
            stop = max(stop, trail) if long else min(stop, trail)
        st["stop"] = stop
        # --- exits ---------------------------------------------------------
        exit_px = None
        reason = None
        stopped = (px <= stop) if long else (px >= stop)
        hit_tp2 = tp2 > 0 and ((px >= tp2) if long else (px <= tp2))
        _hold_h = MAX_HOLD_H_BY_TIER.get(t["tier"], MAX_HOLD_H)
        expired = (now - float(t["opened_at"])) >= _hold_h * 3600
        if stopped:
            exit_px, reason = stop, ("TP1_LOCK" if st.get("tp1_hit")
                                     else "STOP")
        elif hit_tp2:
            exit_px, reason = tp2, "TP2"
        elif expired:
            exit_px, reason = px, "TIME"
        if exit_px is not None:
            g = (exit_px - entry) if long else (entry - exit_px)
            pnl_r = g / risk - _fees_r(entry, risk)
            store.shadow_close(t["id"], exit_px, reason, pnl_r)
            closed.append({**st, "exit": exit_px, "reason": reason,
                           "pnl_r": pnl_r})
        else:
            store.shadow_update(t["id"], st["stop"], st["peak"],
                                int(st.get("be_set") or 0),
                                int(st.get("tp1_hit") or 0))
    return closed


def tier_records() -> list[dict]:
    """Per-tier forward record: n, win%, net R after fees, green-light.
    Green = lifetime gate (>=20 closed, >=+2R) AND recent gate (last
    14d net > 0, once >=10 recent closes exist to judge by)."""
    out = []
    for rec in store.shadow_summary():
        n = int(rec["n"] or 0)
        wins = int(rec["wins"] or 0)
        net = float(rec["net_r"] or 0.0)
        try:
            recent = store.shadow_recent_net(rec["tier"], RECENT_DAYS)
        except Exception:
            recent = {"n": 0, "net_r": 0.0}
        recent_ok = (recent["n"] < RECENT_MIN_N
                     or recent["net_r"] > 0)
        green = (n >= GREEN_MIN_TRADES and net >= GREEN_MIN_NET_R
                 and recent_ok)
        out.append({
            "tier": rec["tier"], "n": n,
            "win_pct": (wins / n * 100.0) if n else 0.0,
            "net_r": net,
            "open": int(rec["open_n"] or 0),
            "recent_n": recent["n"],
            "recent_net": round(recent["net_r"], 2),
            "green": bool(green),
        })
    return out
