"""🤖💸 AGENTIC LIVE EXECUTOR — real-money Bybit trading from PROVEN tiers.

User go (2026-07-13) after the Decision Desk gate was met on live forward
records (APEX +36.1R/164, EARLY-LANE +26.6R/71, EARLY MOVERS +23.6R/74,
FRESH +17.2R/29 — all after fees). This layer lets the 24/7 worker place
REAL orders through live_broker.py using the exact policy the desk proved:

  entry:   market order at signal time (the desk record already includes
           taker fees both sides — parity with the proof)
  stops:   exchange-side SL + TP set the moment the position opens
  ladder:  FULL DESK PARITY (user 2026-07-13 "ride the trade"): BE at
           +1R -> TP1 LOCK (stop jumps to TP1, win banked) -> trail at
           peak-1.2R -> exit at TP2 / trail / 48h time-stop. The
           exchange TP sits at TP2 so winners RIDE; every stop ratchet
           is mirrored to the exchange.
  picks:   ONLY tiers that are 🟢 GREEN on the desk RIGHT NOW — a tier
           whose live record degrades below the gate auto-pauses
  dedup:   one position per symbol; priority early_lane > apex > fresh >
           early_movers when the same coin fires on several boards
  zone:    entries only while <=25% of entry→TP1 is covered (no chasing)

Hard rails (beyond live_broker's preflight):
  - risk per trade: LIVE_RISK_PCT of balance (default 1%)
  - max concurrent: LIVE_MAX_CONCURRENT (default 3)
  - daily loss halt: LIVE_DAILY_LOSS_PCT (default 3%) — auto-trade stops
  - KILL SWITCH: equity <= starting * (1 - LIVE_KILL_PCT/100, default 15%)
    → close everything, halt permanently, alert. Never auto-resumes.
  - leverage cap 5x (stops always fire far before liquidation)

ARMING — all three must be true, so going live is an explicit human act:
  1. LIVE_EXECUTOR=1 in the environment (Render dashboard)
  2. BYBIT_API_KEY / BYBIT_API_SECRET set (Render dashboard)
  3. the tier is green on the desk at signal time

State: .live_exec.json on STATE_DIR (separate from the UI's .live_bot.json
— the Live Trading tab still sees these positions through its own
exchange sync, because Bybit is the source of truth for both).
"""
from __future__ import annotations

import os
import time

import config
import live_broker as lb
import shadow_trader

ENABLED = (os.environ.get("LIVE_EXECUTOR", "") or "").strip().lower() \
    in ("1", "true", "yes", "on")
RISK_PCT = float(os.environ.get("LIVE_RISK_PCT", "1.0") or 1.0)
MAX_CONCURRENT = int(os.environ.get("LIVE_MAX_CONCURRENT", "3") or 3)
DAILY_LOSS_PCT = float(os.environ.get("LIVE_DAILY_LOSS_PCT", "3") or 3)
KILL_PCT = float(os.environ.get("LIVE_KILL_PCT", "15") or 15)
LEV_CAP = int(os.environ.get("LIVE_LEV_CAP", "5") or 5)
MAX_HOLD_H = float(os.environ.get("LIVE_MAX_HOLD_H", "48") or 48)

STATE_PATH = config.state_path(".live_exec.json")

# Priority when the same coin fires on several proven boards.
TIERS = ("early_lane", "apex", "fresh", "early_movers")

_SETTINGS = {
    "leverage_cap": LEV_CAP,
    "daily_loss_pct": DAILY_LOSS_PCT,
    "notional_cap_pct": 20,
    "max_concurrent": MAX_CONCURRENT,
    "slippage_tol_pct": 0.5,
    "confirm_first_n": 0,          # agentic — explicit user go 2026-07-13
    "auto_threshold": 0,           # the tier's GREEN record IS the gate
    "auto_premium_only": False,
    "premium_risk_multiplier": 1.0,
}


def _load() -> dict:
    s = lb.load_state(STATE_PATH)
    s["settings"].update(_SETTINGS)
    s["risk_per_trade_pct"] = RISK_PCT
    return s


def _set_exchange_stop(symbol: str, sl: float | None = None,
                       tp: float | None = None) -> None:
    """Mirror a ladder stop/target move to the exchange. Fail-soft — the
    local backup close in _ladder still protects if this call fails."""
    try:
        kwargs = {"category": "linear", "symbol": symbol,
                  "tpslMode": "Full", "positionIdx": 0}
        if sl is not None:
            kwargs["stopLoss"] = str(sl)
        if tp is not None:
            kwargs["takeProfit"] = str(tp)
        lb.client().set_trading_stop(**kwargs)
    except Exception:
        pass


def _ladder(s: dict, prices: dict) -> list[dict]:
    """The DESK-PARITY exit policy on every open live position — the
    exact ladder the tiers were proven with (shadow_trader.manage):
    BE at +1R, TP1 lock, 1.2R trail after TP1, TP2 / trail / 48h exit.
    Every stop improvement is mirrored to the exchange."""
    closed: list[dict] = []
    now = time.time()
    for p in list(s.get("open") or []):
        # HANDS OFF adopted positions (manual trades the user opened on
        # Bybit, or crash-orphans): their exchange-side SL/TP governs.
        # Managing them here could close the user's own manual trade at
        # our 48h rule — never. They still occupy slots (conservative).
        if p.get("imported_from_exchange"):
            continue
        px = prices.get(p["symbol"])
        expired = (now - float(p.get("opened_at") or now)
                   >= MAX_HOLD_H * 3600)
        if not px:
            if expired:
                try:
                    cl = lb.close_position_at(
                        s, p["symbol"], float(p["entry"]), reason="TIME")
                    if cl:
                        closed.append(cl)
                except Exception:
                    pass
            continue
        px = float(px)
        long = p["side"] == "LONG"
        entry = float(p["entry"])
        orig = float(p.get("original_stop") or p["stop"])
        p.setdefault("original_stop", orig)
        risk = abs(entry - orig)
        if risk <= 0:
            # unmanageable (no usable stop) — we never HOLD what we
            # cannot manage; close at market.
            try:
                cl = lb.close_position_at(s, p["symbol"], px,
                                          reason="UNMANAGED")
                if cl:
                    closed.append(cl)
            except Exception:
                pass
            continue
        tp1 = float(p.get("tp1") or p.get("target") or 0)
        tp2 = float(p.get("tp2") or 0)
        gain = (px - entry) if long else (entry - px)
        peak = float(p.get("peak") or entry)
        peak = max(peak, px) if long else min(peak, px)
        p["peak"] = peak
        new_stop = float(p["stop"])
        if not p.get("break_even_set") and gain >= risk:
            new_stop = entry
            p["break_even_set"] = True
        hit_tp1 = tp1 > 0 and ((px >= tp1) if long else (px <= tp1))
        if hit_tp1 and not p.get("tp1_locked"):
            new_stop = tp1
            p["tp1_locked"] = True
        if p.get("tp1_locked"):
            trail = (peak - 1.2 * risk) if long else (peak + 1.2 * risk)
            new_stop = max(new_stop, trail) if long else min(new_stop, trail)
        if ((long and new_stop > float(p["stop"]))
                or (not long and new_stop < float(p["stop"]))):
            p["stop"] = float(new_stop)
            _set_exchange_stop(p["symbol"], sl=new_stop)
        # exits — backup to the exchange-side SL/TP (sync ran first)
        stopped = (px <= float(p["stop"])) if long \
            else (px >= float(p["stop"]))
        hit_tp2 = tp2 > 0 and ((px >= tp2) if long else (px <= tp2))
        if stopped or hit_tp2 or expired:
            if hit_tp2:
                xp, reason = tp2, "TP2"
            elif stopped:
                xp = float(p["stop"])
                reason = "TP1_LOCK" if p.get("tp1_locked") else \
                    ("BE" if p.get("break_even_set") else "stop")
            else:
                xp, reason = px, "TIME"
            try:
                cl = lb.close_position_at(s, p["symbol"], xp, reason=reason)
                if cl:
                    closed.append(cl)
            except Exception:
                pass
    return closed


def status() -> dict:
    """For reports/UI: {enabled, ready, mode, halted, balance, open, ...}."""
    ok, mode = lb.is_ready()
    s = _load()
    return {
        "enabled": ENABLED, "ready": ok, "mode": mode,
        "halted": bool(s.get("halted")),
        "balance": float(s.get("balance") or 0),
        "starting": float(s.get("starting_balance") or 0),
        "open": len(s.get("open") or []),
        "closed": len(s.get("closed") or []),
    }


def run_cycle(tier_signals: dict, live_px_fn) -> dict:
    """One executor pass per worker cycle. tier_signals maps tier name ->
    signal list (same dicts the desk consumes). live_px_fn(sym) -> price.
    Returns {opened: [...], closed: [...], notes: [...], armed: bool}."""
    out: dict = {"opened": [], "closed": [], "notes": [], "armed": False}
    if not ENABLED:
        return out
    ok, _mode = lb.is_ready()
    if not ok:
        out["notes"].append("keys/pybit missing — dry")
        return out
    out["armed"] = True
    now = time.time()
    s = _load()

    # --- equity from the exchange (source of truth) ----------------------
    eq = None
    try:
        eq = (lb.account_balance() or {}).get("equity")
    except Exception:
        eq = None
    if not s.get("started_at"):
        if not eq or eq <= 0:
            out["notes"].append("cannot read Bybit equity — not arming")
            return out
        s["balance"] = float(eq)
        s["starting_balance"] = float(eq)
        s["started_at"] = now
        lb.save_state(STATE_PATH, s)
        out["notes"].append(f"ARMED — starting equity ${eq:,.2f}")
    elif eq and eq > 0:
        s["balance"] = float(eq)

    # --- permanent halt / kill switch ------------------------------------
    if s.get("halted"):
        lb.save_state(STATE_PATH, s)
        out["notes"].append("HALTED (kill switch) — no trading")
        return out
    start = float(s.get("starting_balance") or 0)
    if eq and start > 0 and eq <= start * (1 - KILL_PCT / 100.0):
        try:
            lb.emergency_stop_all(s)
        except Exception:
            pass
        s["halted"] = True
        lb.save_state(STATE_PATH, s)
        out["notes"].append(
            f"KILL SWITCH — equity ${eq:,.2f} <= "
            f"{100 - KILL_PCT:.0f}% of ${start:,.2f}. All closed, halted.")
        out["killed"] = True
        return out

    # --- reconcile with the exchange (SL/TP may have fired) --------------
    # closes the sync detects (stop/target fired while we weren't looking)
    # are surfaced in out["closed"] so the user gets the Telegram receipt;
    # adopted external positions are announced but NEVER managed.
    _n_closed_before = len(s.get("closed") or [])
    _syms_before = {p.get("symbol") for p in s.get("open") or []}
    try:
        lb.sync_positions(s)
    except Exception:
        pass
    out["closed"] += list(s.get("closed") or [])[_n_closed_before:]
    for p in s.get("open") or []:
        if (p.get("imported_from_exchange")
                and p.get("symbol") not in _syms_before):
            out["notes"].append(
                f"adopted external position {p.get('symbol')} "
                f"{p.get('side')} — leaving it to its exchange SL/TP "
                f"(occupies a slot, never auto-managed)")

    # --- manage opens: FULL desk-parity ladder (BE -> TP1 lock -> trail
    # -> TP2/trail/48h). lb.evaluate is deliberately NOT used here — its
    # partial-take policy differs from the proven desk ladder.
    prices = {}
    for p in list(s.get("open") or []):
        try:
            px = live_px_fn(p["symbol"])
            if px:
                prices[p["symbol"]] = float(px)
        except Exception:
            pass
    out["closed"] += _ladder(s, prices)

    # --- entries: proven tiers only, deduped, in-zone --------------------
    greens = set()
    try:
        greens = {r["tier"] for r in shadow_trader.tier_records()
                  if r.get("green")}
    except Exception:
        pass
    seen: set = set()
    for tier in TIERS:
        if tier not in greens:
            continue                     # tier lost its proof — auto-pause
        for p in tier_signals.get(tier) or []:
            sym = p.get("symbol")
            side = (p.get("side") or "").upper()
            if not sym or side not in ("LONG", "SHORT"):
                continue
            if (sym, side) in seen:
                continue
            seen.add((sym, side))
            if len(s.get("open") or []) >= MAX_CONCURRENT:
                break
            if any(o["symbol"] == sym for o in s.get("open") or []):
                continue
            if not lb.is_tradeable_on_bybit(sym):
                continue
            try:
                live = float(live_px_fn(sym) or 0)
            except Exception:
                live = 0.0
            if live <= 0:
                continue
            entry = float(p.get("entry") or 0)
            stop = float(p.get("stop") or 0)
            tp1 = float(p.get("tp1") or 0)
            if entry <= 0 or stop <= 0 or tp1 <= 0 or tp1 == entry:
                continue
            # 🟢 in-zone + alive at THIS moment — no chasing, ever
            f = ((live - entry) / (tp1 - entry) if side == "LONG"
                 else (entry - live) / (entry - tp1))
            dead = live <= stop if side == "LONG" else live >= stop
            if dead or f > 0.25:
                continue
            conf = int(float(p.get("score") or p.get("conviction") or 0))
            tp2 = float(p.get("tp2") or 0)
            # RIDE policy (user 2026-07-13): the exchange TP sits at TP2
            # so winners can run; the ladder locks TP1 and trails — the
            # exact policy the desk record was earned with.
            alert = {
                "symbol": sym,
                "base": p.get("base") or sym.replace("USDT", ""),
                "side": side, "entry_low": entry, "stop": stop,
                "target": tp2 if tp2 > 0 else tp1,
                "target_2": tp2 or None,
                # preflight needs conf>=70 for the leverage ladder; the
                # tier's green record is the real gate, so floor at 75.
                "confidence": max(75, conf),
                "rr": 0.0,
            }
            ok2, why = lb.auto_trade_gate(s, alert)
            if not ok2:
                out["notes"].append(f"{sym}: {why}")
                if "loss limit" in why.lower():
                    lb.save_state(STATE_PATH, s)
                    return out           # daily halt — stop trying
                continue
            try:
                pos = lb.open_position(s, alert, live, confirmed=True)
            except Exception as exc:
                out["notes"].append(f"{sym}: {exc}")
                continue
            if pos:
                # ladder bookkeeping — pos is the same object stored in
                # state["open"], so these fields persist with the state.
                pos["tier"] = tier
                pos["tp1"] = tp1
                pos["tp2"] = tp2
                pos["original_stop"] = stop
                pos["peak"] = float(pos.get("entry") or entry)
                out["opened"].append(dict(pos))
                # save IMMEDIATELY — a crash between open and end-of-cycle
                # must never orphan a live position from local state.
                lb.save_state(STATE_PATH, s)

    lb.save_state(STATE_PATH, s)
    return out
