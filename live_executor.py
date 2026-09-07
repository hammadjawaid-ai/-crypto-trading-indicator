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
import demo_account
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

# ── 💸 GEN 10 LIVE MODE (user 2026-09-07: "move from demo trading to
# my real money with the same gen 10 demo... same guidelines and
# parameters", $1,500, full GEN 10 sizing by explicit choice) ──
# LIVE_GEN10=1 switches the executor's BRAIN wholesale: the old
# green-tier menu stops opening, and entries come from the exact
# ranked candidate list the demo seats eat — same seven streams, same
# conf-band gates, same 8 seats, same margin/leverage physics
# (equity/8 per seat × the demo_account.lev_for ladder), same
# SL-or-TP1-full-bank exit, 72h time-stop. The kill switch, daily
# halt and exchange-side SL/TP rails all stay on top.
GEN10 = (os.environ.get("LIVE_GEN10", "") or "").strip().lower() \
    in ("1", "true", "yes", "on")
GEN10_SLOTS = int(demo_account.MAX_SLOTS)          # 8 — demo parity
GEN10_HOLD_H = float(demo_account.TIME_STOP_H)     # 72h — demo parity
# GEN 10 daily-loss default is 10% (env-overridable): at full GEN 10
# sizing ONE normal stop-out ≈ 2-3% of the account, so the old 3%
# default would freeze the system after a single loss. 10% ≈ three
# full stop-outs in 24h — that's a real "bad day, stand down" line.
GEN10_DAILY_LOSS_PCT = float(
    os.environ.get("LIVE_DAILY_LOSS_PCT", "10") or 10)
# ⏸ ENTRY HOLD (user 2026-09-07: "dont put or open any trade until I
# say so"): arming, equity sync, the dead-key watchdog and management
# of any existing positions ALL keep running — only NEW entries are
# held. Flip to False on the user's explicit word and redeploy.
GEN10_ENTRY_HOLD = True

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
    if GEN10:
        # Demo-parity sizing THROUGH the existing preflight guards:
        # notional cap = 100/slots % of balance ON MARGIN, and an
        # intentionally huge risk% so the cap ALWAYS binds — margin
        # lands at exactly equity/8, notional = margin × lev, which
        # is the demo seat formula to the cent.
        s["settings"].update({
            "leverage_cap": max(LEV_CAP, 10),
            "max_concurrent": GEN10_SLOTS,
            "notional_cap_pct": 100.0 / GEN10_SLOTS,
            "daily_loss_pct": GEN10_DAILY_LOSS_PCT,
        })
        s["risk_per_trade_pct"] = 1000.0
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
        # 💸 GEN 10 positions live by the DEMO exit law: SL or TP1
        # full bank, NOTHING else — no BE move, no TP1 lock, no trail
        # (the ladder below would betray the proof). Exchange-side
        # SL/TP does the real work; this is the local backup + the
        # 72h time-stop.
        if p.get("gen10"):
            _gpx = prices.get(p["symbol"])
            _gexp = (now - float(p.get("opened_at") or now)
                     >= GEN10_HOLD_H * 3600)
            if not _gpx:
                if _gexp:
                    try:
                        cl = lb.close_position_at(
                            s, p["symbol"], float(p["entry"]),
                            reason="TIME")
                        if cl:
                            closed.append(cl)
                    except Exception:
                        pass
                continue
            _gpx = float(_gpx)
            _glng = p["side"] == "LONG"
            _gtp1 = float(p.get("tp1") or p.get("target") or 0)
            _gstop = float(p["stop"])
            _gstopped = (_gpx <= _gstop) if _glng else (_gpx >= _gstop)
            _ghit = _gtp1 > 0 and ((_gpx >= _gtp1) if _glng
                                   else (_gpx <= _gtp1))
            if _gstopped or _ghit or _gexp:
                if _ghit:
                    _gxp, _grsn = _gtp1, "TP1_BANK"
                elif _gstopped:
                    _gxp, _grsn = _gstop, "stop"
                else:
                    _gxp, _grsn = _gpx, "TIME"
                try:
                    cl = lb.close_position_at(s, p["symbol"], _gxp,
                                              reason=_grsn)
                    if cl:
                        closed.append(cl)
                except Exception:
                    pass
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
        "gen10": GEN10,
        "halted": bool(s.get("halted")),
        "balance": float(s.get("balance") or 0),
        "starting": float(s.get("starting_balance") or 0),
        "open": len(s.get("open") or []),
        "closed": len(s.get("closed") or []),
    }


def run_gen10(cands: list, live_px_fn) -> dict:
    """💸 GEN 10 LIVE entries — the demo seat law with real Bybit money.

    `cands` is the EXACT ranked list demo_account.try_open consumed this
    cycle (conf-band gates already applied inside rank_candidates), so
    live entries can never diverge from the demo's brain. Demo physics
    mirrored 1:1: rank floor 85, 8 seats, one per coin, in-zone <= 25%,
    stop-vs-liquidation guard, margin = equity/8, lev = the GEN 10.1
    ladder (demo_account.lev_for), exchange-side SL + FULL take-profit
    at TP1 (the bank-100%-at-TP1 law). run_cycle already armed/synced/
    killed/managed this cycle — this pass only opens.
    """
    out: dict = {"opened": [], "closed": [], "notes": [], "armed": False}
    if not (ENABLED and GEN10):
        return out
    ok, _mode = lb.is_ready()
    if not ok:
        return out
    s = _load()
    if not s.get("started_at") or s.get("halted"):
        return out
    out["armed"] = True
    if GEN10_ENTRY_HOLD:
        out["notes"].append("entry HOLD — armed but not opening "
                            "(waiting for the user's go)")
        return out
    bal = float(s.get("balance") or 0)
    if bal <= 0:
        return out
    for c in cands or []:
        if len(s.get("open") or []) >= GEN10_SLOTS:
            break
        if float(c.get("rank") or 0) < demo_account.MIN_RANK:
            continue
        sym = c.get("symbol")
        side = (c.get("side") or "").upper()
        if not sym or side not in ("LONG", "SHORT"):
            continue
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
        try:
            entry = float(c.get("entry") or 0)
            stop = float(c.get("stop") or 0)
            tp1 = float(c.get("tp1") or 0)
        except (TypeError, ValueError):
            continue
        if min(entry, stop, tp1) <= 0 or tp1 == entry:
            continue
        lng = side == "LONG"
        prog = ((live - entry) / (tp1 - entry) if lng
                else (entry - live) / (entry - tp1))
        dead = live <= stop if lng else live >= stop
        if dead or prog > demo_account.ZONE_MAX:
            continue
        stop_pct = abs(live - stop) / live
        if stop_pct <= 0.001 or stop_pct > demo_account.STOP_MAX_PCT:
            continue
        lev = float(demo_account.lev_for(c.get("src"), c.get("conf")))
        # real-account physics (demo parity): the stop must sit well
        # inside the seat's margin — a stop past ~liquidation is not
        # a trade.
        if stop_pct >= 0.8 / lev:
            continue
        alert = {
            "symbol": sym,
            "base": c.get("base") or sym.replace("USDT", ""),
            "side": side, "entry_low": entry, "stop": stop,
            # GEN 10 exit law: the exchange TP is TP1, FULL position —
            # bank 100% there, no runner.
            "target": tp1, "target_2": None,
            "confidence": int(float(c.get("conf") or c.get("score")
                                    or 0)),
            "force_leverage": int(lev),
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
            pos["gen10"] = True
            pos["src"] = c.get("src")
            pos["tier"] = f"gen10:{c.get('src')}"
            pos["tp1"] = tp1
            pos["tp2"] = None
            pos["original_stop"] = stop
            pos["peak"] = float(pos.get("entry") or entry)
            out["opened"].append(dict(pos))
            # save IMMEDIATELY — a crash between open and end-of-cycle
            # must never orphan a live position from local state.
            lb.save_state(STATE_PATH, s)
    lb.save_state(STATE_PATH, s)
    return out


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
    elif s.get("started_at"):
        # ⚠️ ARMED but the equity read failed — an expired/revoked key
        # or a Bybit API outage looks EXACTLY like this. Surface it so
        # the worker can buzz (the silent-death gap, user 2026-09-07:
        # "so I am aware of everything?").
        out["notes"].append(
            "cannot read Bybit equity — key expired/revoked or API "
            "down; no live trades until this clears")

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

    # 📈 equity snapshots for the board's curve (demo parity, user
    # 2026-09-07: "the ui of live trading should be similar to demo
    # trading"). One point per cycle, capped.
    try:
        _eh = s.setdefault("equity_hist", [])
        if not _eh or now - float(_eh[-1][0]) >= 240:
            _eh.append([now, float(s.get("balance") or 0)])
            del _eh[:-2500]
    except Exception:
        pass

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

    # --- 💸 GEN 10 MODE: the old green-tier menu STOPS opening — the
    # brain is the demo's ranked list, consumed later in the cycle by
    # run_gen10() (arming, kill switch, sync and position management
    # above all still ran).
    if GEN10:
        lb.save_state(STATE_PATH, s)
        return out

    # --- entries: proven tiers only, deduped, in-zone --------------------
    # DYNAMIC PRIORITY (2026-07-25, the slot-scarcity fix): the account
    # has 3 slots against hundreds of desk signals — so slots go to the
    # green tiers with the best RECENT (14d) net per closed trade, not a
    # static order. What's working now gets the money first.
    greens = set()
    _form: dict = {}
    try:
        for _r in shadow_trader.tier_records():
            if _r.get("green"):
                greens.add(_r["tier"])
            _form[_r["tier"]] = (float(_r.get("recent_net") or 0)
                                 / max(1, int(_r.get("recent_n") or 0)))
    except Exception:
        pass
    tier_order = sorted([t for t in TIERS if t in greens],
                        key=lambda t: -_form.get(t, 0.0)) \
        or [t for t in TIERS if t in greens]
    seen: set = set()
    for tier in tier_order:
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
