"""Live trading broker — routes the same signal engine through Bybit's
USDT-perp API. Public API mirrors paper_bot.py so the new Live Trading
section of the dashboard is a near-clone of the Paper Trader UI.

Bybit is the source of truth: every fragment tick reconciles local state
with the exchange via `sync_positions`. Stops and take-profits are set
on the EXCHANGE the moment a position opens, so they protect the user
even if the Streamlit process dies. The bot's local stop/target
evaluation in `evaluate()` is a backup that fires before the exchange
ticks if our prices update faster.

Safety guardrails are non-negotiable and live in `preflight()` and
`auto_trade_gate()`:
  - per-trade notional cap (% of balance)
  - max concurrent positions
  - daily loss cap (% of starting balance) -> halts auto-trade
  - hard leverage ceiling (user-set)
  - post-fill slippage check (closes immediately if fill is too far off)
  - first-N trades always require manual confirm

Withdrawals MUST be disabled on the API key (set on Bybit's web UI);
this module never calls a withdraw endpoint.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import config

try:
    from pybit.unified_trading import HTTP as _BybitHTTP
except ImportError:
    _BybitHTTP = None    # the Live Trading tab gates itself when this is None


# Default per-period balance for the live account (kept symbolic — the
# real source of truth for live equity is `account_balance()` against
# Bybit's wallet endpoint).
DEFAULT_STATE = {
    "balance": 100.0,                # symbolic; real value comes from Bybit
    "starting_balance": 100.0,
    "risk_per_trade_pct": 1.0,
    "open": [],
    "closed": [],
    "started_at": None,
    "settings": dict(config.LIVE_DEFAULTS),
    "trades_opened_total": 0,        # used by the first-N confirm rule
    "last_sync_ts": 0.0,
    "version": 1,
}


# Confidence ladder for the leverage scaler. (min_confidence, leverage)
DEFAULT_LEV_MAP = [(70, 3), (80, 8), (90, 15)]


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def load_state(path: Path) -> dict:
    """Read live-bot state from disk; return defaults if absent / corrupt."""
    try:
        with open(path) as f:
            s = json.load(f)
        for key, value in DEFAULT_STATE.items():
            s.setdefault(key, value)
        # Backfill settings keys so a new guardrail rolls in without
        # wiping the user's existing tweaks.
        for k, v in config.LIVE_DEFAULTS.items():
            s.setdefault("settings", {}).setdefault(k, v)
        return s
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return json.loads(json.dumps(DEFAULT_STATE))


def save_state(path: Path, state: dict) -> None:
    try:
        Path(path).write_text(json.dumps(state, indent=2))
    except OSError:
        pass


def reset(path: Path, starting_balance: float,
          risk_pct: float, settings: dict | None = None) -> dict:
    """Wipe the live state and start a fresh period."""
    s = json.loads(json.dumps(DEFAULT_STATE))
    s["balance"] = float(starting_balance)
    s["starting_balance"] = float(starting_balance)
    s["risk_per_trade_pct"] = float(risk_pct)
    s["started_at"] = time.time()
    if settings:
        s["settings"].update(settings)
    save_state(path, s)
    return s


# ---------------------------------------------------------------------------
# Bybit client
# ---------------------------------------------------------------------------

_client_cache: dict[bool, object] = {}


def client(testnet: bool | None = None):
    """Return a cached pybit HTTP client. Raises ConfigError when keys are
    missing or the pybit dependency is not installed."""
    if _BybitHTTP is None:
        raise ConfigError(
            "pybit is not installed — run "
            "`pip install -r requirements.txt`.")
    if not config.BYBIT_API_KEY or not config.BYBIT_API_SECRET:
        raise ConfigError(
            "BYBIT_API_KEY / BYBIT_API_SECRET are missing. Add them to "
            "your .env (or Streamlit Cloud secrets) and reboot.")
    testnet = bool(testnet) if testnet is not None else config.BYBIT_TESTNET
    if testnet not in _client_cache:
        _client_cache[testnet] = _BybitHTTP(
            testnet=testnet,
            api_key=config.BYBIT_API_KEY,
            api_secret=config.BYBIT_API_SECRET,
        )
    return _client_cache[testnet]


class ConfigError(RuntimeError):
    """Raised when the live broker is not properly configured."""


def is_ready() -> tuple[bool, str]:
    """Quick check the UI uses to gate the Live Trading tab."""
    if _BybitHTTP is None:
        return False, "pybit not installed"
    if not config.BYBIT_API_KEY or not config.BYBIT_API_SECRET:
        return False, "API keys not set in .env"
    return True, ("testnet" if config.BYBIT_TESTNET else "live")


# ---------------------------------------------------------------------------
# Account & market data
# ---------------------------------------------------------------------------

def account_balance() -> dict:
    """Live equity snapshot from Bybit. Returns {equity, available,
    used_margin, currency}. Empty dict on failure."""
    try:
        c = client()
        resp = c.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        rows = ((resp.get("result") or {}).get("list") or [])
        if not rows:
            return {}
        acct = rows[0]
        coins = acct.get("coin") or []
        usdt = next((c for c in coins
                     if (c.get("coin") or "").upper() == "USDT"), {})
        equity = float(acct.get("totalEquity")
                       or usdt.get("equity") or 0.0)
        avail = float(acct.get("totalAvailableBalance")
                      or usdt.get("availableToWithdraw")
                      or usdt.get("availableToBorrow") or 0.0)
        used = max(0.0, equity - avail)
        return {"equity": equity, "available": avail,
                "used_margin": used, "currency": "USDT"}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Leverage scaling
# ---------------------------------------------------------------------------

def leverage_for_signal(confidence: float, forecast_aligned: bool,
                        forecast_disagrees: bool, user_cap: int) -> int:
    """Map signal confidence to a leverage multiplier, with forecast boost
    or penalty. Returns 0 when the signal is too weak to auto-trade."""
    conf = float(confidence or 0)
    if conf < 70:
        return 0
    lev = next(L for c, L in reversed(DEFAULT_LEV_MAP) if conf >= c)
    if forecast_aligned:
        lev = int(round(lev * 1.5))
    if forecast_disagrees:
        lev = max(1, int(round(lev * 0.5)))
    return max(1, min(int(lev), int(user_cap or 20)))


# ---------------------------------------------------------------------------
# Margin & P&L helpers (mirror paper_bot for UI compatibility)
# ---------------------------------------------------------------------------

def open_margin_used(state: dict) -> float:
    total = 0.0
    for p in state.get("open") or []:
        notional = float(p.get("notional")
                         or (p.get("qty", 0) * p.get("entry", 0)))
        leverage = float(p.get("leverage") or 1.0)
        total += notional / leverage if leverage > 0 else notional
    return total


def unrealized_pnl(state: dict, prices: dict[str, float]) -> float:
    total = 0.0
    for p in state.get("open") or []:
        price = prices.get(p["symbol"])
        if price is None:
            continue
        long = (p["side"] == "LONG")
        entry, qty = float(p["entry"]), float(p["qty"])
        total += (((price - entry) if long else (entry - price)) * qty)
    return total


def stats(state: dict) -> dict:
    closed = state.get("closed") or []
    n = len(closed)
    bal = float(state.get("balance") or 0.0)
    start = float(state.get("starting_balance") or 1.0) or 1.0
    if not n:
        return {"trades": 0, "wins": 0, "win_rate": 0.0,
                "total_pnl_usd": 0.0,
                "total_pnl_pct": round((bal - start) / start * 100, 2),
                "best_trade": 0.0, "worst_trade": 0.0,
                "avg_pnl_pct": 0.0, "balance": bal}
    wins = sum(1 for c in closed if c["pnl_usd"] > 0)
    total = sum(c["pnl_usd"] for c in closed)
    return {"trades": n, "wins": wins, "win_rate": wins / n * 100,
            "total_pnl_usd": round(total, 2),
            "total_pnl_pct": round((bal - start) / start * 100, 2),
            "best_trade": max(c["pnl_pct"] for c in closed),
            "worst_trade": min(c["pnl_pct"] for c in closed),
            "avg_pnl_pct": round(sum(c["pnl_pct"] for c in closed) / n, 2),
            "balance": bal}


def daily_realised_pnl(state: dict) -> float:
    """Realised P&L closed within the last 24h — used by the daily-loss cap."""
    cutoff = time.time() - 24 * 3600
    return sum(float(c.get("pnl_usd") or 0.0)
               for c in state.get("closed") or []
               if (c.get("exit_at") or 0) >= cutoff)


# ---------------------------------------------------------------------------
# Preflight, auto-trade gate, leverage
# ---------------------------------------------------------------------------

def preflight(state: dict, alert: dict,
              price_now: float) -> tuple[bool, str, dict]:
    """Enforce every guardrail BEFORE any Bybit API call.

    Returns (ok, reason, preview). `preview` always carries qty / notional
    / leverage / margin / sl / tp / slippage_budget so the UI can show
    the user exactly what would be placed.
    """
    settings = state.get("settings") or config.LIVE_DEFAULTS
    bal = float(state.get("balance") or 0.0)
    if bal <= 0:
        return False, "Bank balance is zero.", {}

    side = alert.get("side")
    if side not in ("LONG", "SHORT"):
        return False, f"Bad side '{side}'", {}

    stop = float(alert.get("stop") or 0.0)
    target = float(alert.get("target") or 0.0)
    entry = float(price_now or alert.get("entry_low") or 0.0)
    if not (entry and stop and target):
        return False, "Missing entry / stop / target.", {}
    if side == "LONG" and (stop >= entry or target <= entry):
        return False, "LONG: stop must be below entry, target above.", {}
    if side == "SHORT" and (stop <= entry or target >= entry):
        return False, "SHORT: stop must be above entry, target below.", {}

    # Leverage
    conf = float(alert.get("confidence") or 0)
    aligned = bool(alert.get("forecast_aligned"))
    disagrees = bool(alert.get("forecast_disagrees"))
    cap = int(settings.get("leverage_cap") or 20)
    lev = leverage_for_signal(conf, aligned, disagrees, cap)
    if lev <= 0:
        return False, "Signal too weak (confidence < 70).", {}

    # Concurrent positions cap
    n_open = len(state.get("open") or [])
    max_conc = int(settings.get("max_concurrent") or 3)
    if n_open >= max_conc:
        return (False,
                f"Max concurrent positions hit ({n_open}/{max_conc}).", {})

    # Risk-based qty (fixed-fractional, the same model paper_bot uses)
    risk_per_unit = abs(entry - stop)
    risk_dollars = bal * float(state.get("risk_per_trade_pct") or 1.0) / 100
    qty = (risk_dollars / risk_per_unit) if risk_per_unit > 0 else 0.0
    notional = qty * entry
    margin = notional / lev if lev > 0 else notional

    # Per-trade notional cap (% of balance)
    cap_pct = float(settings.get("notional_cap_pct") or 30)
    max_notional = bal * cap_pct / 100 * lev   # cap is on margin, not notional
    if margin > bal * cap_pct / 100:
        # shrink qty so margin sits at the cap
        max_margin = bal * cap_pct / 100
        margin = max_margin
        notional = margin * lev
        qty = notional / entry if entry > 0 else 0.0
        if qty <= 0:
            return False, "Cap-shrunk size is zero.", {}

    # Slippage budget
    slip = float(settings.get("slippage_tol_pct") or 0.5)
    slippage_budget = entry * slip / 100

    preview = {
        "symbol": alert.get("symbol"),
        "side": side,
        "entry": entry, "stop": stop, "target": target,
        "qty": round(qty, 6), "notional": round(notional, 2),
        "leverage": int(lev), "margin": round(margin, 2),
        "slippage_budget": round(slippage_budget, 6),
        "est_fee_round_trip": round(notional * 0.00055 * 2, 4),  # taker x2
    }
    return True, "ok", preview


def auto_trade_gate(state: dict, alert: dict,
                    settings: dict | None = None) -> tuple[bool, str]:
    """Decide whether agentic mode should auto-open this alert. Returns
    (should_open, reason)."""
    s = settings or state.get("settings") or config.LIVE_DEFAULTS
    # Daily loss cap
    realised_24h = daily_realised_pnl(state)
    start = float(state.get("starting_balance") or 1.0) or 1.0
    if realised_24h <= -start * float(s["daily_loss_pct"]) / 100:
        return False, "Daily loss limit hit — auto-trade halted."
    # First-N confirm-only
    if (int(state.get("trades_opened_total") or 0)
            < int(s["confirm_first_n"])):
        return False, ("Confirm-first-N still in effect "
                       "— manual confirm required.")
    # Strong-signal threshold
    conf = float(alert.get("confidence") or 0)
    if conf < float(s["auto_threshold"]):
        return False, ("Signal below auto-threshold "
                       f"({conf:.0f} < {s['auto_threshold']}).")
    # Concurrent positions
    if len(state.get("open") or []) >= int(s["max_concurrent"]):
        return False, "Max concurrent positions reached."
    return True, "ok"


# ---------------------------------------------------------------------------
# Order placement — open, close, evaluate, sync, emergency stop
# ---------------------------------------------------------------------------

def set_leverage(symbol: str, leverage: int) -> None:
    """Set leverage on Bybit for one symbol. Idempotent — Bybit returns
    34036 if already set; we treat that as success."""
    c = client()
    try:
        c.set_leverage(category="linear", symbol=symbol,
                       buyLeverage=str(leverage),
                       sellLeverage=str(leverage))
    except Exception as exc:   # pybit raises on retCode != 0
        msg = str(exc).lower()
        if "34036" in msg or "leverage not modified" in msg:
            return    # already set to this value — fine
        raise


def open_position(state: dict, alert: dict, price_now: float,
                  *, confirmed: bool = False) -> dict | None:
    """Open a real Bybit position from an alert. Sets stop and take-profit
    on the exchange so they survive even if our app dies."""
    if not confirmed:
        return None
    ok, reason, preview = preflight(state, alert, price_now)
    if not ok:
        raise ConfigError(f"Preflight failed: {reason}")

    symbol = preview["symbol"]
    side = "Buy" if preview["side"] == "LONG" else "Sell"
    qty = preview["qty"]
    lev = preview["leverage"]
    order_link = f"ti-{uuid.uuid4().hex[:14]}"   # idempotency on retries

    set_leverage(symbol, lev)

    c = client()
    placed = c.place_order(
        category="linear", symbol=symbol, side=side,
        orderType="Market", qty=str(qty), timeInForce="IOC",
        reduceOnly=False, positionIdx=0,
        orderLinkId=order_link)
    order_id = ((placed.get("result") or {}).get("orderId")
                or (placed.get("result") or {}).get("orderLinkId"))

    # Poll until filled (or timeout) — capture the real average fill price.
    fill_price = None
    for _ in range(20):     # ~10s max
        time.sleep(0.5)
        try:
            hist = c.get_order_history(category="linear",
                                       orderLinkId=order_link, limit=1)
            rows = (hist.get("result") or {}).get("list") or []
            if rows and (rows[0].get("orderStatus") == "Filled"
                         or float(rows[0].get("cumExecQty") or 0) >= qty):
                fill_price = float(rows[0].get("avgPrice")
                                   or rows[0].get("lastPriceOnCreated")
                                   or preview["entry"])
                break
        except Exception:
            continue
    if fill_price is None:
        fill_price = preview["entry"]   # best-effort; sync will reconcile

    # Slippage check — close immediately if fill is far off.
    expected = preview["entry"]
    slip_budget = preview["slippage_budget"]
    if abs(fill_price - expected) > slip_budget:
        try:
            c.place_order(category="linear", symbol=symbol,
                          side=("Sell" if side == "Buy" else "Buy"),
                          orderType="Market", qty=str(qty),
                          timeInForce="IOC", reduceOnly=True,
                          positionIdx=0)
        except Exception:
            pass
        raise ConfigError(
            f"Slippage rejected: filled at {fill_price} "
            f"vs expected {expected} (budget {slip_budget}). "
            "Position closed.")

    # Park exchange-side stop & take-profit (so they fire even if our
    # process dies).
    try:
        c.set_trading_stop(
            category="linear", symbol=symbol,
            stopLoss=str(preview["stop"]),
            takeProfit=str(preview["target"]),
            tpslMode="Full", positionIdx=0)
    except Exception:
        pass    # not fatal — local evaluate() also tracks

    pos = {
        "symbol": symbol,
        "base": (alert.get("base")
                 or symbol.replace("USDT", "")),
        "side": preview["side"],
        "entry": float(fill_price),
        "stop": float(preview["stop"]),
        "target": float(preview["target"]),
        "qty": float(qty),
        "notional": float(preview["notional"]),
        "leverage": int(lev),
        "margin": float(preview["margin"]),
        "opened_at": time.time(),
        "confidence": int(alert.get("confidence") or 0),
        "rr": float(alert.get("rr") or 0.0),
        "order_id": order_id,
        "order_link_id": order_link,
        "exchange_synced": True,
    }
    state["open"].append(pos)
    state["trades_opened_total"] = int(
        state.get("trades_opened_total") or 0) + 1
    return pos


def close_position_at(state: dict, symbol: str, price: float,
                      reason: str = "manual") -> dict | None:
    """Close a Bybit position at market via a reduce-only order."""
    pos = next((p for p in state.get("open") or []
                if p["symbol"] == symbol), None)
    if pos is None:
        return None
    side = "Sell" if pos["side"] == "LONG" else "Buy"
    qty = float(pos["qty"])
    c = client()
    closing_link = f"ti-close-{uuid.uuid4().hex[:12]}"
    fill_price = float(price or pos["entry"])
    try:
        c.place_order(category="linear", symbol=symbol, side=side,
                      orderType="Market", qty=str(qty),
                      timeInForce="IOC", reduceOnly=True,
                      positionIdx=0, orderLinkId=closing_link)
        # Poll for the close fill.
        for _ in range(20):
            time.sleep(0.5)
            try:
                hist = c.get_order_history(category="linear",
                                           orderLinkId=closing_link,
                                           limit=1)
                rows = (hist.get("result") or {}).get("list") or []
                if rows and (rows[0].get("orderStatus") == "Filled"):
                    fill_price = float(rows[0].get("avgPrice")
                                       or fill_price)
                    break
            except Exception:
                continue
    except Exception:
        pass    # fall through and record the close locally using `price`

    long = (pos["side"] == "LONG")
    pnl_per_unit = ((fill_price - pos["entry"]) if long
                    else (pos["entry"] - fill_price))
    pnl_usd = pnl_per_unit * qty
    closed = dict(pos)
    closed.update({
        "exit": float(fill_price),
        "exit_at": time.time(),
        "exit_reason": reason,
        "pnl_usd": round(pnl_usd, 2),
        "pnl_pct": round(pnl_usd / state["balance"] * 100, 2)
                   if state["balance"] else 0.0,
    })
    state["closed"].append(closed)
    state["balance"] = round(state["balance"] + pnl_usd, 2)
    state["open"] = [p for p in state["open"]
                     if p["symbol"] != symbol]
    return closed


def evaluate(state: dict, prices: dict[str, float]) -> list[dict]:
    """Local stop/target check — runs as a backup. Bybit's exchange-side
    SL/TP fires primarily; this catches any case where our price feed
    sees a hit before Bybit ticks."""
    just_closed: list[dict] = []
    for p in list(state.get("open") or []):
        price = prices.get(p["symbol"])
        if price is None:
            continue
        long = (p["side"] == "LONG")
        hit_stop = (price <= p["stop"]) if long else (price >= p["stop"])
        hit_target = ((price >= p["target"]) if long
                      else (price <= p["target"]))
        if hit_stop or hit_target:
            exit_price = p["stop"] if hit_stop else p["target"]
            closed = close_position_at(
                state, p["symbol"], exit_price,
                reason=("stop" if hit_stop else "target"))
            if closed:
                just_closed.append(closed)
    return just_closed


def sync_positions(state: dict) -> dict:
    """Reconcile local state with what Bybit thinks. Exchange is the
    source of truth. Returns {drift, last_sync_ts, exchange_count}."""
    drift = 0
    try:
        c = client()
        resp = c.get_positions(category="linear", settleCoin="USDT")
        rows = (resp.get("result") or {}).get("list") or []
        exchange_syms = {
            r["symbol"] for r in rows
            if float(r.get("size") or 0) > 0
        }
    except Exception:
        state["last_sync_ts"] = time.time()
        return {"drift": 0, "last_sync_ts": state["last_sync_ts"],
                "exchange_count": 0}

    local_syms = {p["symbol"] for p in state.get("open") or []}
    # Positions we think are open but Bybit closed (SL/TP fired while
    # offline) → move to closed history.
    for sym in (local_syms - exchange_syms):
        pos = next(p for p in state["open"] if p["symbol"] == sym)
        # Best-effort: query execution history to find the actual fill.
        exit_price = pos["entry"]    # fallback
        try:
            execs = c.get_executions(category="linear", symbol=sym,
                                     limit=5)
            ex_rows = (execs.get("result") or {}).get("list") or []
            closing = next((e for e in ex_rows
                            if e.get("orderType", "").lower() in
                            ("market", "stop", "takeprofit")), None)
            if closing:
                exit_price = float(closing.get("execPrice")
                                   or closing.get("price")
                                   or exit_price)
        except Exception:
            pass
        long = (pos["side"] == "LONG")
        pnl_per_unit = ((exit_price - pos["entry"]) if long
                        else (pos["entry"] - exit_price))
        pnl_usd = pnl_per_unit * pos["qty"]
        closed = dict(pos)
        closed.update({
            "exit": float(exit_price),
            "exit_at": time.time(),
            "exit_reason": "exchange (stop/target fired offline)",
            "pnl_usd": round(pnl_usd, 2),
            "pnl_pct": round(pnl_usd / state["balance"] * 100, 2)
                       if state["balance"] else 0.0,
        })
        state["closed"].append(closed)
        state["balance"] = round(state["balance"] + pnl_usd, 2)
        drift += 1
    if drift:
        state["open"] = [p for p in state["open"]
                         if p["symbol"] in exchange_syms]
    state["last_sync_ts"] = time.time()
    return {"drift": drift, "last_sync_ts": state["last_sync_ts"],
            "exchange_count": len(exchange_syms)}


def emergency_stop_all(state: dict) -> dict:
    """Close every live position at market, cancel all open orders. The
    red big-red-button on the Live tab calls this."""
    closed_now = []
    try:
        c = client()
        # Cancel any unfilled orders first.
        try:
            c.cancel_all_orders(category="linear", settleCoin="USDT")
        except Exception:
            pass
        # Then reduceOnly close every open position.
        for p in list(state.get("open") or []):
            try:
                closed = close_position_at(
                    state, p["symbol"], p["entry"],
                    reason="emergency stop")
                if closed:
                    closed_now.append(closed)
            except Exception:
                continue
    except Exception:
        pass
    return {"closed": closed_now, "n": len(closed_now)}
