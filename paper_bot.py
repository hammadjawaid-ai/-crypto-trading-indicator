"""Paper trading bot — test the indicator's signals with virtual money,
real prices.

The app opens simulated positions from the live Trade Alerts (each carrying
its own entry/stop/target/R:R from the same trade-plan engine the dashboard
shows), then manages them to stop or target on every refresh. State is
serialised to a JSON file in the project directory so a paper-trading run
PERSISTS across reruns and across full app restarts — close the browser,
come back tomorrow, the trades are still there.

Pure logic, no Streamlit. The app provides the alert stream and the live
price map; this module opens, manages and closes the positions, and keeps
the running stats.

Idealised execution: no slippage, no fees, no partial fills. Use it to gauge
whether the signals tend to win in the current regime; real-money results
will be a little worse.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

DEFAULT_STATE = {
    "balance": 10000.0,
    "starting_balance": 10000.0,
    "risk_per_trade_pct": 1.0,
    # Futures-style sizing controls. The user sets these from the UI.
    "leverage": 3.0,                 # 1x .. 10x, applies as margin = notional / leverage
    "max_notional_per_trade": 5000.0,  # hard cap on $ notional per single trade
    "open": [],
    "closed": [],
    "suggestion_persistence": {},   # {setup_id: first_seen_ts}
    "started_at": None,             # period start — set on first save
    "version": 4,
}


# How long a paper-trading period runs before balance auto-resets back to
# the starting amount. Anything still open is closed at market first.
# Bumped 7 -> 90 (3 months) per user — no more weekly wipe of open
# positions. The variable name is kept as WEEKLY_RESET_DAYS for backward
# compatibility with callers; the period is now quarterly.
WEEKLY_RESET_DAYS = 90

# Trade-management levels (multiples of original risk-per-unit, "R").
#   +1.0R → move stop to entry (break-even)
#   +1.5R → close PARTIAL_FRACTION of the position; let the rest ride
# The combination locks in a guaranteed profit on every trade that touches
# +1.5R while leaving runners free to hit the full target (or, on PREMIUM
# setups, the chase-TP2 trailing target). This was the model the user ran
# successfully on 2026-05-23 — removed at 02:51 on 2026-05-24 and restored
# here after the same-day evidence that pure target/stop gives back too
# much on reversals (a +1.7R then mean-revert trade went from +0.75R
# guaranteed → 0R at BE).
BREAK_EVEN_R = 1.0
PARTIAL_TAKE_R = 1.5
PARTIAL_FRACTION = 0.5


def load_state(path: Path) -> dict:
    """Read paper-bot state from disk; return defaults if absent / corrupt."""
    try:
        with open(path) as f:
            s = json.load(f)
        for key, value in DEFAULT_STATE.items():
            s.setdefault(key, value)
        return s
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        # Deep-copy the default so mutation never leaks back into the default.
        return json.loads(json.dumps(DEFAULT_STATE))


def save_state(path: Path, state: dict) -> None:
    try:
        Path(path).write_text(json.dumps(state, indent=2))
    except OSError:
        pass


def reset(path: Path, starting_balance: float, risk_pct: float) -> dict:
    """Wipe the paper account and start over with new settings."""
    s = json.loads(json.dumps(DEFAULT_STATE))
    s["balance"] = float(starting_balance)
    s["starting_balance"] = float(starting_balance)
    s["risk_per_trade_pct"] = float(risk_pct)
    s["started_at"] = time.time()
    save_state(path, s)
    return s


def open_margin_used(state: dict) -> float:
    """Total margin locked across every open position right now.

    For a spot trade, this is the full notional (notional = qty * entry).
    For a futures trade, it is notional / leverage. The number represents
    capital that is currently TIED UP in positions and therefore not
    available to deploy in a new trade."""
    total = 0.0
    for p in state.get("open") or []:
        qty = float(p.get("qty") or 0.0)
        entry = float(p.get("entry") or 0.0)
        notional = float(p.get("notional") or (qty * entry))
        leverage = float(p.get("leverage") or 1.0)
        margin = (notional / leverage) if leverage > 0 else notional
        total += margin
    return total


def unrealized_pnl(state: dict, prices: dict[str, float]) -> float:
    """Mark-to-market sum of P&L across every open position, using the
    latest price map. Negative numbers mean the open book is currently in
    the red, positive in the green."""
    total = 0.0
    for p in state.get("open") or []:
        price = prices.get(p["symbol"])
        if price is None:
            continue
        long = (p["side"] == "LONG")
        entry = float(p["entry"])
        qty = float(p["qty"])
        total += (((price - entry) if long else (entry - price)) * qty)
    return total


def restore_last_reset(state: dict) -> dict:
    """Recover positions that were force-closed by the last period reset.

    Finds every closed trade whose exit_reason starts with "weekly reset"
    or contains the word "reset", pulls them OUT of state["closed"], and
    re-inserts them into state["open"] as live positions using the
    original entry price (not the reset-time exit). This undoes a
    too-aggressive auto-reset and gives the user back the trades they
    had open.

    Idempotent — calling twice is safe (no duplicates).

    Returns {restored: int, skipped: int, errors: list[str]}.
    """
    closed = list(state.get("closed") or [])
    if not closed:
        return {"restored": 0, "skipped": 0, "errors": []}

    # Find the timestamp of the last reset event (newest first)
    reset_keys = ("weekly reset", "reset")
    reset_closes = [
        c for c in closed
        if any(k in str(c.get("exit_reason", "")).lower()
               for k in reset_keys)
    ]
    if not reset_closes:
        return {"restored": 0, "skipped": 0, "errors": []}

    # Pull out the most recent reset batch — group by exit_at within a
    # 60-second window (the reset closes a batch of positions all at
    # roughly the same instant).
    reset_closes.sort(key=lambda c: float(c.get("exit_at") or 0),
                      reverse=True)
    newest_exit_at = float(reset_closes[0].get("exit_at") or 0)
    batch = [c for c in reset_closes
             if abs(float(c.get("exit_at") or 0) - newest_exit_at) < 60]

    # Dedup against currently-open positions
    open_syms = {p.get("symbol") for p in (state.get("open") or [])}

    restored = 0
    skipped = 0
    errors: list[str] = []
    for c in batch:
        sym = c.get("symbol")
        if not sym:
            continue
        if sym in open_syms:
            skipped += 1
            continue
        # Reconstruct the open-position dict from the closed snapshot.
        # Keep ORIGINAL entry / stop / target — not the exit-reset price.
        try:
            pos = {
                "symbol": sym,
                "base": c.get("base") or sym.replace("USDT", ""),
                "side": c.get("side") or "LONG",
                "entry": float(c.get("entry") or 0),
                "stop": float(c.get("stop") or 0),
                "target": float(c.get("target") or 0),
                "target_2": float(c.get("target_2") or 0),
                "qty": float(c.get("qty") or 0),
                "notional": float(c.get("notional") or 0),
                "leverage": float(c.get("leverage") or 0),
                "opened_at": float(
                    c.get("opened_at") or c.get("entry_at") or time.time()),
                "confidence": int(c.get("confidence") or 0),
                "strength_factor": float(
                    c.get("strength_factor") or 1.0),
                "restored_at": time.time(),
            }
            if pos["entry"] <= 0 or pos["qty"] <= 0:
                errors.append(f"{sym}: invalid entry/qty")
                continue
            state.setdefault("open", []).append(pos)
            # Refund the realised P&L that was deducted on reset close —
            # the position is no longer "closed", so its P&L should be
            # removed from the running balance.
            pnl = float(c.get("pnl_usd") or 0)
            state["balance"] = round(
                float(state.get("balance") or 0) - pnl, 2)
            # Remove this trade from closed history (it's open again)
            state["closed"] = [
                cl for cl in state["closed"]
                if cl is not c
            ]
            restored += 1
            open_syms.add(sym)
        except Exception as exc:
            errors.append(f"{sym}: {exc}")
    return {"restored": restored, "skipped": skipped, "errors": errors}


def check_weekly_reset(state: dict,
                       prices: dict[str, float],
                       period_days: int = WEEKLY_RESET_DAYS) -> dict:
    """If `period_days` have elapsed since the period started, force-close
    every open position at the latest market price, then reset the balance
    back to the starting amount and start a new period.

    Closed-trades history is PRESERVED so the user keeps the audit of
    every paper trade across periods. Returns
    {reset: bool, closed_at_reset: list[dict]}."""
    now = time.time()
    started_at = state.get("started_at")
    if not started_at:
        # First-ever paper run — anchor the period clock here.
        state["started_at"] = now
        return {"reset": False, "closed_at_reset": []}
    elapsed = now - float(started_at)
    if elapsed < period_days * 24 * 3600:
        return {"reset": False, "closed_at_reset": []}
    # Period over — force-close every open position at the latest price.
    just_closed: list[dict] = []
    for p in list(state.get("open") or []):
        price = prices.get(p["symbol"], p["entry"])
        closed = close_position_at(state, p["symbol"], price,
                                   reason="weekly reset")
        if closed:
            just_closed.append(closed)
    # Restart the balance and the period clock.
    start = float(state.get("starting_balance") or 10000.0)
    state["balance"] = start
    state["started_at"] = now
    return {"reset": True, "closed_at_reset": just_closed}


def _qty_for(balance: float, risk_pct: float,
             entry: float, stop: float,
             max_notional: float | None = None) -> float:
    """Position size so a stop-out costs risk_pct % of the account balance
    (the fixed-fractional risk model real desks use), capped by
    `max_notional` if provided. Whichever produces the SMALLER position
    wins — risk-control AND notional-cap both enforced."""
    risk_dollars = balance * risk_pct / 100
    risk_per_unit = abs(entry - stop)
    if risk_per_unit <= 0 or entry <= 0:
        return 0.0
    risk_qty = risk_dollars / risk_per_unit
    if max_notional and max_notional > 0:
        cap_qty = max_notional / entry
        return min(risk_qty, cap_qty)
    return risk_qty


def open_position(state: dict, alert: dict,
                  price_now: float | None) -> dict | None:
    """Open a simulated position from a Trade Alert.

    De-duplicates by symbol so a coin cannot accumulate multiple paper
    positions on top of each other. Returns the new position dict, or None
    if anything about the alert is unusable (no stop, wrong side, zero qty)."""
    sym = alert.get("symbol")
    if not sym:
        return None
    if any(p["symbol"] == sym for p in state["open"]):
        return None
    stop = alert.get("stop")
    target = alert.get("target")
    if stop is None or target is None:
        return None
    side = alert.get("side", "LONG")
    entry = (float(price_now) if price_now is not None
             else float(alert.get("entry_low") or 0))
    if entry <= 0:
        return None
    # Sanity-check the stop is on the correct side of the entry.
    if side == "LONG" and float(stop) >= entry:
        return None
    if side == "SHORT" and float(stop) <= entry:
        return None
    # Effective notional cap: user setting × optional strength factor the
    # caller passes via the alert (e.g. 0.4-1.0 scaled by combined score).
    # If neither is set we fall back to no cap (pure fixed-fractional).
    _base_cap = float(state.get("max_notional_per_trade") or 0)
    _strength = float(alert.get("strength_factor") or 1.0)
    _effective_cap = (_base_cap * _strength) if _base_cap > 0 else 0
    qty = _qty_for(state["balance"], state["risk_per_trade_pct"],
                   entry, float(stop),
                   max_notional=_effective_cap if _effective_cap > 0 else None)
    if qty <= 0:
        return None
    # Chase-TP2 fields — only populated when the alert flags the position
    # as eligible (PREMIUM tier on the dashboard). When set, the trade
    # opens aiming for TP1 (`target`) but if price hits TP1 the
    # `evaluate()` step will move the stop to TP1 (locking in the win)
    # and extend the target to TP2 — riding the remaining momentum
    # without ever giving back the TP1 capture.
    target_2 = alert.get("target_2")
    chase_eligible = bool(alert.get("chase_tp2_eligible"))
    _notional = float(qty * entry)
    _leverage = float(state.get("leverage") or 1.0)
    _margin = _notional / _leverage if _leverage > 0 else _notional
    pos = {
        "symbol": sym,
        "base": alert.get("base") or sym.replace("USDT", ""),
        "side": side,
        "entry": float(entry),
        "stop": float(stop),
        "target": float(target),
        "target_2": float(target_2) if target_2 else 0.0,
        "chase_tp2_eligible": chase_eligible,
        "qty": float(qty),
        "original_qty": float(qty),
        "notional": round(_notional, 2),
        "leverage": _leverage,
        "margin": round(_margin, 2),
        "opened_at": time.time(),
        "confidence": int(alert.get("confidence", 0) or 0),
        "rr": float(alert.get("rr", 0.0) or 0.0),
    }
    state["open"].append(pos)
    return pos


def evaluate(state: dict, prices: dict[str, float]) -> list[dict]:
    """Walk every open position and close any whose stop or target was hit
    by the latest price. Returns the list of trades that just closed.

    `prices` is {symbol: latest_price}. A symbol with no current price is
    left open (we never invent a fill price)."""
    just_closed: list[dict] = []
    keep: list[dict] = []
    for pos in state["open"]:
        price = prices.get(pos["symbol"])
        if price is None:
            keep.append(pos)
            continue
        long = (pos["side"] == "LONG")

        # Original risk-per-unit (in price terms) and current gain. Used by
        # both the BE move and the partial-take check; compute once.
        risk_per_unit = abs(pos["entry"] - pos["original_stop"]) \
            if pos.get("original_stop") is not None else abs(
                pos["entry"] - pos["stop"])
        gain_per_unit = ((price - pos["entry"]) if long
                         else (pos["entry"] - price))

        # Break-even auto-move: once the position is up by 1R (an amount
        # equal to the original risk), push the stop to entry. From that
        # point on the trade is a "free option" — it can target run with no
        # downside. Move it ONCE and never widen.
        if (not pos.get("break_even_set")
                and risk_per_unit > 0
                and gain_per_unit >= BREAK_EVEN_R * risk_per_unit):
            # remember the original stop for analytics, then move to BE
            pos.setdefault("original_stop", pos["stop"])
            pos["stop"] = pos["entry"]
            pos["break_even_set"] = True

        # Partial profit-take at +1.5R — close PARTIAL_FRACTION of the
        # position to lock in a guaranteed win on the closed slice; the
        # rest stays open with the break-even stop (and, if the position
        # is PREMIUM-eligible, the chase-TP2 trailing kicks in for the
        # remainder when price reaches TP1). Worst case after this fires:
        # +0.75R on the closed half, 0R on the remainder = +0.375R on the
        # full original position. Best case: closed half banks +1.5R and
        # the remainder runs to TP2. Fires ONCE per position.
        if (not pos.get("partial_taken")
                and risk_per_unit > 0
                and gain_per_unit >= PARTIAL_TAKE_R * risk_per_unit):
            close_qty = pos["qty"] * PARTIAL_FRACTION
            partial_pnl = gain_per_unit * close_qty
            partial = dict(pos)
            partial.update({
                "qty": float(close_qty),
                "exit": float(price),
                "exit_at": time.time(),
                "exit_reason": f"partial +{PARTIAL_TAKE_R:.1f}R",
                "partial": True,
                "pnl_usd": round(partial_pnl, 2),
                "pnl_pct": round(partial_pnl / state["balance"] * 100, 2)
                           if state["balance"] else 0.0,
            })
            state["closed"].append(partial)
            state["balance"] = round(state["balance"] + partial_pnl, 2)
            pos["qty"] = float(pos["qty"] - close_qty)
            pos["partial_taken"] = True
            pos["partial_at"] = float(price)

        # Chase-TP2 trailing logic — fires once when price reaches TP1 on
        # a PREMIUM-eligible position. Locks in the TP1 win by moving the
        # stop UP to TP1, then extends the target to TP2 so price can
        # keep running. If trend continues, position closes at TP2
        # (+1R extra). If trend dies, price retraces to the new stop and
        # position closes at TP1 (same as the plain TP1 plan). Strictly
        # better than fixed TP1 — zero downside scenario.
        _chase_just_fired = False
        if (pos.get("chase_tp2_eligible")
                and not pos.get("chasing_tp2")
                and pos.get("target_2")):
            tp1_value = pos.get("original_target") or pos["target"]
            hit_tp1 = ((price >= tp1_value) if long
                       else (price <= tp1_value))
            if hit_tp1:
                # Remember the original TP1 for the closed-trade log.
                pos.setdefault("original_target", float(tp1_value))
                # Move stop to TP1 (lock in the +1.5R win) and extend
                # target to TP2. If price retraces from here, we exit
                # at TP1 instead of break-even — strictly better.
                pos["stop"] = float(tp1_value)
                pos["target"] = float(pos["target_2"])
                pos["chasing_tp2"] = True
                _chase_just_fired = True

        # When chase upgrade just fired, the new stop equals current price
        # so the stop check below would immediately close. Skip this
        # tick's close evaluation — the position transitions cleanly
        # into chase mode and the next tick decides the exit.
        if _chase_just_fired:
            keep.append(pos)
            continue

        hit_stop = (price <= pos["stop"]) if long else (price >= pos["stop"])
        hit_target = ((price >= pos["target"]) if long
                      else (price <= pos["target"]))
        if not (hit_stop or hit_target):
            keep.append(pos)
            continue
        # Stop takes priority over target (the conservative assumption when
        # we lack intra-bar data).
        exit_price = pos["stop"] if hit_stop else pos["target"]
        pnl_per_unit = ((exit_price - pos["entry"]) if long
                        else (pos["entry"] - exit_price))
        pnl_usd = pnl_per_unit * pos["qty"]
        closed = dict(pos)
        closed.update({
            "exit": float(exit_price),
            "exit_at": time.time(),
            "exit_reason": "stop" if hit_stop else "target",
            "pnl_usd": round(pnl_usd, 2),
            "pnl_pct": round(pnl_usd / state["balance"] * 100, 2)
                       if state["balance"] else 0.0,
        })
        state["closed"].append(closed)
        state["balance"] = round(state["balance"] + pnl_usd, 2)
        just_closed.append(closed)
    state["open"] = keep
    return just_closed


def close_position_at(state: dict, symbol: str, price: float,
                      reason: str = "manual") -> dict | None:
    """Close one specific open position at the given price (used for the
    'Close' button in the Paper Trader UI). Returns the closed dict, or
    None if the symbol has no matching open position."""
    for i, p in enumerate(state["open"]):
        if p["symbol"] != symbol:
            continue
        long = (p["side"] == "LONG")
        pnl_per_unit = ((price - p["entry"]) if long
                        else (p["entry"] - price))
        pnl_usd = pnl_per_unit * p["qty"]
        closed = dict(p)
        closed.update({
            "exit": float(price),
            "exit_at": time.time(),
            "exit_reason": reason,
            "pnl_usd": round(pnl_usd, 2),
            "pnl_pct": round(pnl_usd / state["balance"] * 100, 2)
                       if state["balance"] else 0.0,
        })
        state["closed"].append(closed)
        state["balance"] = round(state["balance"] + pnl_usd, 2)
        state["open"].pop(i)
        return closed
    return None


def stats(state: dict) -> dict:
    """Headline performance numbers from the closed-trades log."""
    closed = state.get("closed") or []
    n = len(closed)
    bal = float(state.get("balance") or 0.0)
    start = float(state.get("starting_balance") or 1.0) or 1.0
    if not n:
        return {
            "trades": 0, "wins": 0, "win_rate": 0.0,
            "total_pnl_usd": 0.0,
            "total_pnl_pct": round((bal - start) / start * 100, 2),
            "best_trade": 0.0, "worst_trade": 0.0,
            "avg_pnl_pct": 0.0,
            "balance": bal,
        }
    wins = sum(1 for c in closed if c["pnl_usd"] > 0)
    total = sum(c["pnl_usd"] for c in closed)
    return {
        "trades": n, "wins": wins, "win_rate": wins / n * 100,
        "total_pnl_usd": round(total, 2),
        "total_pnl_pct": round((bal - start) / start * 100, 2),
        "best_trade": max(c["pnl_pct"] for c in closed),
        "worst_trade": min(c["pnl_pct"] for c in closed),
        "avg_pnl_pct": round(sum(c["pnl_pct"] for c in closed) / n, 2),
        "balance": bal,
    }
