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
    "open": [],
    "closed": [],
    "suggestion_persistence": {},   # {setup_id: first_seen_ts}
    "started_at": None,             # period start — set on first save
    "version": 3,
}


# How long a paper-trading period runs before balance auto-resets back to
# the starting amount. Anything still open is closed at market first.
WEEKLY_RESET_DAYS = 7


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
             entry: float, stop: float) -> float:
    """Position size so a stop-out costs risk_pct % of the account balance —
    the fixed-fractional risk model real desks use."""
    risk_dollars = balance * risk_pct / 100
    risk_per_unit = abs(entry - stop)
    if risk_per_unit <= 0:
        return 0.0
    return risk_dollars / risk_per_unit


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
    qty = _qty_for(state["balance"], state["risk_per_trade_pct"],
                   entry, float(stop))
    if qty <= 0:
        return None
    pos = {
        "symbol": sym,
        "base": alert.get("base") or sym.replace("USDT", ""),
        "side": side,
        "entry": float(entry),
        "stop": float(stop),
        "target": float(target),
        "qty": float(qty),
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

        # Break-even auto-move: once the position is up by 1R (an amount
        # equal to the original risk), push the stop to entry. From that
        # point on the trade is a "free option" — it can target run with no
        # downside. Move it ONCE and never widen.
        if not pos.get("break_even_set"):
            risk_per_unit = abs(pos["entry"] - pos["original_stop"]) \
                if pos.get("original_stop") is not None else abs(
                    pos["entry"] - pos["stop"])
            gain_per_unit = ((price - pos["entry"]) if long
                             else (pos["entry"] - price))
            if risk_per_unit > 0 and gain_per_unit >= risk_per_unit:
                # remember the original stop for analytics, then move to BE
                pos.setdefault("original_stop", pos["stop"])
                pos["stop"] = pos["entry"]
                pos["break_even_set"] = True

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
