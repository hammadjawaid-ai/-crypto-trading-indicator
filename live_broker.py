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


# --- Clock-skew immunity ---------------------------------------------------
# Pybit signs each request with the laptop's local time. Bybit only tolerates
# requests up to 1 SECOND ahead of their server (recv_window doesn't help in
# that direction). On a machine whose clock drifts forward (1.5+ sec ahead),
# every authenticated call fails with ErrCode 10002 "invalid request, please
# check your server timestamp."
#
# Rather than depend on the user being able to sync Windows time (often
# blocked on corporate networks), we monkey-patch the `time` module used
# inside pybit so all its timestamps are SHIFTED to match Bybit's server
# clock. We re-sync the offset every 60 seconds against /v5/market/time.
if _BybitHTTP is not None:
    import pybit._helpers as _phelpers   # noqa: E402
    import time as _real_time            # noqa: E402

    class _ClockSync:
        offset_sec = 0.0
        last_sync_at = 0.0

        @classmethod
        def refresh(cls):
            """Re-query Bybit's server time every 60s. offset_sec is
            (local - server). 300ms safety buffer keeps signed requests
            slightly behind the server clock (safe direction)."""
            now = _real_time.time()
            if now - cls.last_sync_at < 60:
                return
            try:
                import requests
                r = requests.get(
                    "https://api.bybit.com/v5/market/time", timeout=5)
                server_s = int(r.json()["result"]["timeNano"]) / 1e9
                cls.offset_sec = now - server_s + 0.3
                cls.last_sync_at = now
            except Exception:
                pass

    def _server_synced_timestamp() -> int:
        """Replacement for pybit._helpers.generate_timestamp() that returns
        a millisecond timestamp synchronised to Bybit's server clock.
        Eliminates the clock-skew rejection (ErrCode 10002) when the local
        machine drifts ahead of Bybit's server clock."""
        _ClockSync.refresh()
        return int((_real_time.time() - _ClockSync.offset_sec) * 1000)

    # Patch pybit's timestamp generator. Every authenticated Bybit call
    # now signs with a server-synced timestamp instead of local time.
    _phelpers.generate_timestamp = _server_synced_timestamp
    # Initial sync on module load.
    _ClockSync.refresh()


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

# Trade-management thresholds (multiples of original risk, "R"). Same
# semantics as paper_bot.py — at +1R move the exchange stop to entry
# (free option); at +1.5R close a 50% chunk on the exchange and let the
# rest ride to the full target.
BREAK_EVEN_R = 1.0
PARTIAL_TAKE_R = 1.5
PARTIAL_FRACTION = 0.5


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

def client(testnet: bool | None = None):
    """Return a FRESH pybit HTTP client per call (not cached).

    Originally this was module-level cached for performance, but pybit's
    HTTP client carries per-request internal state — request signing
    timestamp, retry counter, response handler — that gets corrupted
    when Streamlit fragments and main-script reruns hit the same client
    instance concurrently. Symptom: random `FailedRequestError: Bad
    request. retries exceeded maximum (ErrCode: 400)` on otherwise-fine
    calls. Creating a fresh client per call eliminates the race; the
    overhead is negligible (just attribute assignment — actual TCP
    connection pooling lives in `requests` underneath).

    Raises ConfigError when keys are missing or pybit is not installed.
    """
    if _BybitHTTP is None:
        raise ConfigError(
            "pybit is not installed — run "
            "`pip install -r requirements.txt`.")
    if not config.BYBIT_API_KEY or not config.BYBIT_API_SECRET:
        raise ConfigError(
            "BYBIT_API_KEY / BYBIT_API_SECRET are missing. Add them to "
            "your .env (or Streamlit Cloud secrets) and reboot.")
    testnet = bool(testnet) if testnet is not None else config.BYBIT_TESTNET
    return _BybitHTTP(
        testnet=testnet,
        api_key=config.BYBIT_API_KEY,
        api_secret=config.BYBIT_API_SECRET,
        recv_window=20000,  # 20s tolerance for clock skew (default 5s
                            # rejects requests when laptop time drifts).
    )


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


# Cache of per-symbol lot-size filters so we don't re-fetch on every order.
_lot_filter_cache: dict[str, dict] = {}

# Cache of Bybit's currently-tradeable USDT-perp symbols, with timestamp.
# Refreshes every hour. Lets the live picks board filter out delisted /
# suspended contracts (LUNA-style errors) before user clicks 📥.
_tradeable_cache: dict = {"symbols": set(), "fetched_at": 0.0}


def tradeable_symbols(force_refresh: bool = False) -> set[str]:
    """Return the set of Bybit USDT-perp symbols currently in 'Trading'
    status. Cached for 1 hour. Empty set on failure (caller decides
    whether to be permissive or strict)."""
    now = time.time()
    if not force_refresh and (now - _tradeable_cache["fetched_at"]) < 3600:
        if _tradeable_cache["symbols"]:
            return _tradeable_cache["symbols"]
    try:
        c = client()
        # paginated — fetch all pages
        syms: set[str] = set()
        cursor = ""
        for _ in range(20):   # safety cap on pagination
            kwargs = {"category": "linear", "limit": 1000}
            if cursor:
                kwargs["cursor"] = cursor
            resp = c.get_instruments_info(**kwargs)
            result = resp.get("result") or {}
            for inst in result.get("list") or []:
                if (inst.get("status") == "Trading"
                        and inst.get("quoteCoin") == "USDT"
                        and inst.get("contractType") in (
                            "LinearPerpetual", "LinearFutures")):
                    syms.add(inst["symbol"])
            cursor = result.get("nextPageCursor", "")
            if not cursor:
                break
        if syms:
            _tradeable_cache["symbols"] = syms
            _tradeable_cache["fetched_at"] = now
    except Exception:
        pass
    return _tradeable_cache["symbols"]


def is_tradeable_on_bybit(symbol: str) -> bool:
    """Quick check used by the picks-board filter. Returns False on
    delisted / not-on-Bybit symbols so they never reach the order
    placement path."""
    syms = tradeable_symbols()
    if not syms:
        # If the lookup failed, be permissive — let preflight catch it.
        return True
    return symbol in syms


def _get_lot_filter(symbol: str) -> dict:
    """Return Bybit's lotSizeFilter for a symbol — `qtyStep`, `minOrderQty`,
    `maxOrderQty`. Cached after first call. Different coins have very
    different step sizes (BTC=0.001, ETH=0.01, ALT=1, etc.), and Bybit
    rejects orders with `ErrCode 10001 Qty invalid` if qty isn't a clean
    multiple of qtyStep."""
    if symbol in _lot_filter_cache:
        return _lot_filter_cache[symbol]
    try:
        c = client()
        resp = c.get_instruments_info(category="linear", symbol=symbol)
        rows = (resp.get("result") or {}).get("list") or []
        if rows:
            lot = rows[0].get("lotSizeFilter") or {}
            f = {
                "qtyStep": float(lot.get("qtyStep") or 0),
                "minOrderQty": float(lot.get("minOrderQty") or 0),
                "maxOrderQty": float(lot.get("maxOrderQty") or 0),
            }
            _lot_filter_cache[symbol] = f
            return f
    except Exception:
        pass
    return {"qtyStep": 0, "minOrderQty": 0, "maxOrderQty": 0}


def _round_qty(symbol: str, qty: float) -> float:
    """Round qty DOWN to the symbol's qtyStep — Bybit rejects fractional
    qty that isn't a clean multiple of the step. Floor (not round) so we
    never exceed the original notional cap by accident."""
    import math
    lot = _get_lot_filter(symbol)
    step = lot.get("qtyStep", 0)
    if step and step > 0:
        # Floor to step. Use round-then-floor for float-precision safety.
        qty = math.floor(qty / step + 1e-9) * step
        # Re-precision: avoid 9.999999... artifacts from float math.
        # Determine decimal places from step.
        decimals = max(0, -int(round(math.log10(step))) if step < 1 else 0)
        qty = round(qty, decimals)
    return qty


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

    # Round qty to the symbol's lot-size step. Bybit rejects fractional
    # qty that isn't a clean multiple of qtyStep — different per coin.
    qty = _round_qty(symbol, qty)
    if qty <= 0:
        raise ConfigError(
            f"After rounding to lot step, qty is 0 for {symbol}. "
            f"Try a larger risk_per_trade_pct or notional_cap_pct.")
    lot = _get_lot_filter(symbol)
    if lot["minOrderQty"] > 0 and qty < lot["minOrderQty"]:
        raise ConfigError(
            f"Computed qty {qty} below {symbol} minimum "
            f"{lot['minOrderQty']}. Increase risk or notional cap.")

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

    # Slippage check — close immediately if fill is ADVERSELY off.
    # For LONG: adverse = paid MORE than expected (fill_price > expected).
    # For SHORT: adverse = sold for LESS than expected (fill_price < expected).
    # Favorable slippage (better fill than expected) is GOOD — keep the
    # position. The earlier `abs()` check was closing on favorable
    # slippage which is the opposite of what we want.
    expected = preview["entry"]
    slip_budget = preview["slippage_budget"]
    is_long = (side == "Buy")
    adverse_slip = ((fill_price - expected) if is_long
                    else (expected - fill_price))
    if adverse_slip > slip_budget:
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
            f"vs expected {expected} (adverse {adverse_slip:.6g} > "
            f"budget {slip_budget:.6g}). Position closed.")

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
        "original_qty": float(qty),          # for partial-close math
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
    qty = _round_qty(symbol, float(pos["qty"]))
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


def _manage_position(state: dict, pos: dict, price: float) -> dict | None:
    """Run trade-management triggers (break-even, partial profit-take) on
    an open Bybit position. Returns a closed-trade dict if a partial fill
    fired (so the UI can toast it), None otherwise. Stop/target full
    closes are NOT handled here — `evaluate()` handles those."""
    long = (pos["side"] == "LONG")
    risk_per_unit = abs(pos["entry"] - pos["original_stop"]) \
        if pos.get("original_stop") is not None else abs(
            pos["entry"] - pos["stop"])
    if risk_per_unit <= 0:
        return None
    gain_per_unit = ((price - pos["entry"]) if long
                     else (pos["entry"] - price))

    # +1R → move exchange-side stop to entry (free option).
    if (not pos.get("break_even_set")
            and gain_per_unit >= BREAK_EVEN_R * risk_per_unit):
        try:
            c = client()
            c.set_trading_stop(
                category="linear", symbol=pos["symbol"],
                stopLoss=str(pos["entry"]),
                takeProfit=str(pos["target"]),
                tpslMode="Full", positionIdx=0)
        except Exception:
            pass    # local stop still tracked below
        pos.setdefault("original_stop", pos["stop"])
        pos["stop"] = float(pos["entry"])
        pos["break_even_set"] = True

    # +1.5R → close PARTIAL_FRACTION on the exchange (reduceOnly market),
    # let the remainder ride to the full target. Fires ONCE.
    if (not pos.get("partial_taken")
            and gain_per_unit >= PARTIAL_TAKE_R * risk_per_unit):
        close_qty = _round_qty(pos["symbol"],
                               pos["qty"] * PARTIAL_FRACTION)
        if close_qty <= 0:
            return None  # would round to zero — skip partial
        side = "Sell" if long else "Buy"
        partial_link = f"ti-part-{uuid.uuid4().hex[:12]}"
        fill_price = float(price)
        try:
            c = client()
            c.place_order(category="linear", symbol=pos["symbol"],
                          side=side, orderType="Market",
                          qty=str(close_qty), timeInForce="IOC",
                          reduceOnly=True, positionIdx=0,
                          orderLinkId=partial_link)
            # Poll briefly for the fill price.
            for _ in range(10):
                time.sleep(0.5)
                try:
                    hist = c.get_order_history(
                        category="linear",
                        orderLinkId=partial_link, limit=1)
                    rows = (hist.get("result") or {}).get("list") or []
                    if rows and (rows[0].get("orderStatus") == "Filled"):
                        fill_price = float(rows[0].get("avgPrice")
                                           or fill_price)
                        break
                except Exception:
                    continue
        except Exception:
            return None    # partial failed — leave position untouched

        pnl_per_unit = ((fill_price - pos["entry"]) if long
                        else (pos["entry"] - fill_price))
        partial_pnl = pnl_per_unit * close_qty
        partial = dict(pos)
        partial.update({
            "qty": float(close_qty),
            "exit": float(fill_price),
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
        pos["partial_at"] = float(fill_price)
        return partial
    return None


def evaluate(state: dict, prices: dict[str, float]) -> list[dict]:
    """Local stop/target check — runs as a backup. Bybit's exchange-side
    SL/TP fires primarily; this catches any case where our price feed
    sees a hit before Bybit ticks. Also runs trade-management triggers
    (break-even at +1R, partial-take at +1.5R) on every tick."""
    just_closed: list[dict] = []
    for p in list(state.get("open") or []):
        price = prices.get(p["symbol"])
        if price is None:
            continue
        # Trade management — fires break-even / partial-take when due.
        partial = _manage_position(state, p, price)
        if partial:
            just_closed.append(partial)
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
