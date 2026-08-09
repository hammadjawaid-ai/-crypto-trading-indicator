"""🎮 DEMO ZONE — the $1,200 one-week live-fire test (user 2026-08-09).

A simulated REAL account run by the 24/7 worker: starts at $1,200,
2% risk per trade, MAX 3 slots, one position per coin, Bybit taker
fees both sides, 48h time-stop — every constraint a real account has.
Each cycle it auto-picks the HIGHEST-QUALITY signals on the desk
(💯 > 🥇 > 🎯 > 🔮✅ > 🚀 > elite streams, boosted by each tier's live
14d form and the signal's own score) and manages them like the desk:
bank HALF at TP1, stop to breakeven, rest to TP2 or the time-stop.

The week's question: where does $1,200 honestly land? Target voiced:
$1,500-1,800. Every open/close buzzes Telegram; the page shows the
equity curve and every position. Simulated only — no real orders.
"""
from __future__ import annotations

import json
import os
import time

STATE_FILE = os.environ.get("DEMO_STATE", ".demo_account.json")
START_BAL = 1200.0
RISK_PCT = 2.0
MAX_SLOTS = 3
LEV_CAP = 3.0                  # notional <= balance * 3
FEE = 0.00055                  # Bybit taker, per side
TIME_STOP_H = 48
ZONE_MAX = 0.25                # skip if >25% of entry->TP1 gone
STOP_MAX_PCT = 0.25            # skip stops wider than 25%
# construct-class weights — the quality ladder the user asked for
CLASS_W = {"conviction": 100, "prime": 92, "true_signal": 86,
           "kr_approved": 72, "moonshot": 66, "elite_early": 58,
           "apex": 52, "fresh": 46, "takenow_hot": 40}


def load() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            s = json.load(f)
        if isinstance(s, dict) and "balance" in s:
            return s
    except Exception:
        pass
    return {"balance": START_BAL, "start": START_BAL,
            "started_at": time.time(), "open": [], "closed": [],
            "equity_hist": []}


def save(state: dict) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass


def rank_candidates(pools: dict, tier_form: dict) -> list:
    """pools: {stream: [signal dicts]} -> ranked candidate list."""
    out, seen = [], set()
    for name, sigs in pools.items():
        w = CLASS_W.get(name, 30)
        form = float(tier_form.get(name, 0.0) or 0.0)
        for p in sigs or []:
            sym = p.get("symbol")
            side = (p.get("side") or "").upper()
            k = (sym, side)
            if not sym or side not in ("LONG", "SHORT") or k in seen:
                continue
            try:
                e = float(p.get("entry") or 0)
                st = float(p.get("stop") or 0)
                t1 = float(p.get("tp1") or 0)
            except (TypeError, ValueError):
                continue
            if min(e, st, t1) <= 0 or e == st or t1 == e:
                continue
            seen.add(k)
            sc = float(p.get("score") or 60)
            t2 = p.get("tp2")
            out.append({"symbol": sym,
                        "base": p.get("base") or sym.replace("USDT", ""),
                        "side": side, "entry": e, "stop": st,
                        "tp1": t1,
                        "tp2": float(t2) if t2 else None,
                        "src": name, "score": sc,
                        "rank": w + sc / 2 + max(-10.0, min(form, 10.0))})
    out.sort(key=lambda x: -x["rank"])
    return out


def try_open(state: dict, cands: list, live_fn) -> list:
    """Fill free slots with the best in-zone candidates. Real-account
    rules: slot cap, one per coin, notional risk-sized off the CURRENT
    balance, entry fee paid immediately."""
    opened = []
    held = {p["symbol"] for p in state["open"]}
    for c in cands:
        if len(state["open"]) >= MAX_SLOTS:
            break
        if c["symbol"] in held:
            continue
        try:
            live = float(live_fn(c["symbol"]) or 0)
        except Exception:
            live = 0.0
        if live <= 0:
            continue
        lng = c["side"] == "LONG"
        prog = ((live - c["entry"]) / (c["tp1"] - c["entry"]) if lng
                else (c["entry"] - live) / (c["entry"] - c["tp1"]))
        dead = live <= c["stop"] if lng else live >= c["stop"]
        if dead or prog > ZONE_MAX:
            continue
        stop_pct = abs(live - c["stop"]) / live
        if stop_pct <= 0.001 or stop_pct > STOP_MAX_PCT:
            continue
        risk_usd = state["balance"] * RISK_PCT / 100.0
        notional = min(risk_usd / stop_pct,
                       state["balance"] * LEV_CAP)
        fee_in = notional * FEE
        pos = {"symbol": c["symbol"], "base": c["base"],
               "side": c["side"], "entry": live, "stop": c["stop"],
               "tp1": c["tp1"], "tp2": c["tp2"],
               "qty": notional / live, "notional": notional,
               "src": c["src"], "score": c["score"],
               "opened_at": time.time(), "fees": fee_in,
               "tp1_banked": 0.0, "be_set": False}
        state["balance"] -= fee_in
        state["open"].append(pos)
        held.add(c["symbol"])
        opened.append(pos)
    return opened


def _close_qty(state, p, qty, px, reason) -> dict:
    lng = p["side"] == "LONG"
    pnl = qty * (px - p["entry"]) * (1 if lng else -1)
    fee = qty * px * FEE
    state["balance"] += pnl - fee
    p["fees"] = p.get("fees", 0.0) + fee
    rec = {"symbol": p["symbol"], "base": p["base"], "side": p["side"],
           "entry": p["entry"], "exit": px, "qty": qty,
           "pnl": round(pnl - fee, 2), "reason": reason,
           "src": p["src"], "opened_at": p["opened_at"],
           "closed_at": time.time()}
    return rec


def manage(state: dict, live_fn) -> list:
    """TP1 half-bank + BE, TP2/stop/time-stop closes. Returns events."""
    events = []
    keep = []
    for p in state["open"]:
        try:
            live = float(live_fn(p["symbol"]) or 0)
        except Exception:
            live = 0.0
        if live <= 0:
            keep.append(p)
            continue
        lng = p["side"] == "LONG"
        hit_stop = live <= p["stop"] if lng else live >= p["stop"]
        hit_tp1 = live >= p["tp1"] if lng else live <= p["tp1"]
        t2 = p.get("tp2")
        hit_tp2 = (t2 is not None
                   and (live >= t2 if lng else live <= t2))
        expired = time.time() - p["opened_at"] > TIME_STOP_H * 3600
        if hit_stop:
            px = p["stop"]
            rec = _close_qty(state, p, p["qty"], px,
                             "BE stop" if p["be_set"] else "stop")
            state["closed"].append(rec)
            events.append(("close", rec))
            continue
        if hit_tp1 and not p["be_set"]:
            half = p["qty"] / 2
            rec = _close_qty(state, p, half, p["tp1"], "TP1 bank half")
            p["qty"] -= half
            p["tp1_banked"] = rec["pnl"]
            p["stop"] = p["entry"]          # breakeven
            p["be_set"] = True
            events.append(("tp1", rec))
        if p["qty"] > 0 and (hit_tp2 or expired):
            px = t2 if hit_tp2 and t2 else live
            rec = _close_qty(state, p, p["qty"], px,
                             "TP2" if hit_tp2 else "48h time-stop")
            state["closed"].append(rec)
            events.append(("close", rec))
            continue
        keep.append(p)
    state["open"] = keep
    # equity snapshot (balance + unrealized)
    unreal = 0.0
    for p in state["open"]:
        try:
            live = float(live_fn(p["symbol"]) or 0)
            if live > 0:
                unreal += p["qty"] * (live - p["entry"]) * \
                    (1 if p["side"] == "LONG" else -1)
        except Exception:
            pass
    state["equity_hist"].append(
        [time.time(), round(state["balance"] + unreal, 2)])
    if len(state["equity_hist"]) > 4200:      # ~2 weeks of 5-min points
        state["equity_hist"] = state["equity_hist"][-4200:]
    return events
