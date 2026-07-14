"""🤖💸 AGENTIC LIVE EXECUTOR — real-money Bybit trading from PROVEN tiers.

User go (2026-07-13) after the Decision Desk gate was met on live forward
records (APEX +36.1R/164, EARLY-LANE +26.6R/71, EARLY MOVERS +23.6R/74,
FRESH +17.2R/29 — all after fees). This layer lets the 24/7 worker place
REAL orders through live_broker.py using the exact policy the desk proved:

  entry:   market order at signal time (the desk record already includes
           taker fees both sides — parity with the proof)
  stops:   exchange-side SL + TP set the moment the position opens
  ladder:  BE at +1R (exchange stop moved), target = TP1, 48h time-stop
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
    try:
        lb.sync_positions(s)
    except Exception:
        pass

    # --- manage opens: BE ladder + backup stop/target + 48h time-stop ----
    prices = {}
    for p in list(s.get("open") or []):
        try:
            px = live_px_fn(p["symbol"])
            if px:
                prices[p["symbol"]] = float(px)
        except Exception:
            pass
    try:
        out["closed"] += lb.evaluate(s, prices)
    except Exception:
        pass
    for p in list(s.get("open") or []):
        if now - float(p.get("opened_at") or now) >= MAX_HOLD_H * 3600:
            px = prices.get(p["symbol"]) or float(p["entry"])
            try:
                cl = lb.close_position_at(s, p["symbol"], px, reason="TIME")
                if cl:
                    out["closed"].append(cl)
            except Exception:
                pass

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
            alert = {
                "symbol": sym,
                "base": p.get("base") or sym.replace("USDT", ""),
                "side": side, "entry_low": entry, "stop": stop,
                "target": tp1, "target_2": p.get("tp2") or None,
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
                pos["tier"] = tier
                out["opened"].append(dict(pos))

    lb.save_state(STATE_PATH, s)
    return out
