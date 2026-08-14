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

import config

# 2026-08-10 THE RESET BUG, fixed: this file used to sit on the
# container's EPHEMERAL disk, so every deploy wiped the ledger (user:
# "it should NEVER reset from any source until I hard-reset myself").
# Now on the persistent disk via config.state_path (STATE_DIR=/var/data
# on Render) — the same location that keeps the desk's records alive
# across deploys. The ONLY reset path left is bumping GEN below, which
# happens exclusively on the user's explicit order.
STATE_FILE = os.environ.get("DEMO_STATE") or \
    str(config.state_path(".demo_account.json"))
# generation marker — bump ONLY on the user's explicit hard-reset
# order. GEN 3 = 2026-08-10 ("reset again, Monday to Monday").
# GEN 4 = 2026-08-15 ("reset demo trading lets start fresh again now
# based on the changes") — fresh week on the new ladder: 💎 elite
# conviction (approved-only) wins all, 🔮✅ kronos approved right
# behind, B-stocks out of the universe, and the strength-aware
# smart exit with the TP2 trail below.
GEN = 4
START_BAL = 1200.0
RISK_PCT = 2.0
# 3 -> 5 (user 2026-08-09): a CEILING, not a quota — the MIN_RANK
# floor still gates every slot, so 4-5 only fill on genuinely
# qualified (often confluence) days. Full load = 10% of account at
# risk; the demo's own record decides what the real-money version
# should use.
MAX_SLOTS = 5
LEV_CAP = 3.0                  # notional <= balance * 3
FEE = 0.00055                  # Bybit taker, per side
TIME_STOP_H = 48
# per-source hold limits — 🌊 TREND RIDER is a days-to-weeks construct
# (its +81.6R desk record comes from letting winners RUN); a 48h cut
# would destroy the exact edge we're letting in. 21d matches the desk's
# own trend-rider standard (the 2026-07 48h-cut bug taught this).
TIME_STOP_BY_SRC = {"trend_rider": 504}
# slot discipline: the rider holds for days, so cap it at 2 of 5 slots
# — it can't clog the book and starve the fast constructs.
MAX_PER_SRC = {"trend_rider": 2}
# sources the kronos smart-exit must NOT touch: kronos is a 24h model,
# the rider is a multi-day trend — validated as color-not-gate there
# (the ZBT case: veto wrong, coin ran +51%).
SMART_EXIT_SKIP = {"trend_rider"}
# 🧠 STRENGTH-AWARE SMART EXIT + TRAIL (user 2026-08-15: "smart exit
# should have a trailing method... loosen a bit if the signal
# strength is good... let them ride to tp and trail to tp2 if they
# are good enough — use the brain"). The brain's strength read = the
# signal's own quality at entry: top-class source (💎 elite_conv /
# 🔮✅ kr_approved), multi-system agreement, or a big score.
STRONG_SRC = {"elite_conv", "kr_approved"}
STRONG_SCORE = 85.0            # score >= this counts as strong
STRONG_AGREE = 2               # >= this many agreeing systems counts
TRAIL_LOCK = 0.5               # after TP1: stop locks this share of
                               # the PEAK open gain (ratchet, rides
                               # toward TP2 instead of flat BE)
TRAIL_LOCK_FLIP = 0.75         # kronos flips against a STRONG runner
                               # after TP1: tighten the lock, keep
                               # riding (weak signals still bank)


def _is_strong(p) -> bool:
    """The brain's verdict on this position's signal strength."""
    return (p.get("src") in STRONG_SRC
            or int(p.get("agree") or 1) >= STRONG_AGREE
            or float(p.get("score") or 0) >= STRONG_SCORE)
ZONE_MAX = 0.25                # skip if >25% of entry->TP1 gone
STOP_MAX_PCT = 0.25            # skip stops wider than 25%
# quality floor (my call, user granted latitude 2026-08-09): an empty
# slot is better than a mediocre trade. Rank ~100 needs either a
# top-record system, a strong score, or multi-system agreement.
MIN_RANK = 100.0
# construct-class weights — the user's chosen seven (2026-08-09:
# "early elite, kronos approved, surge, ignition, fresh movers, top
# conviction and moonshot — worth trying"; PRIME/others dropped from
# the demo on his call). Weighted by each tier's live desk record.
# IGNITION dropped 2026-08-10 on user call ("we should skip
# ignition" — at-fire entries, the weakest construct class).
CLASS_W = {"elite_conv": 95,       # 💎 ELITE CONVICTION, MAX/HIGH only
                                   # (user 2026-08-14: "elite
                                   # conviction should now be a part of
                                   # demo trading and on top priority"
                                   # — his ACE/2Z winners came off this
                                   # board, "top notch"). Tied with
                                   # early elite at the top of the
                                   # class ladder; the approval
                                   # agreement bonus below lifts the
                                   # 🔮✅ ones above everything.
           "elite_early": 95,      # +50.8R/215 lifetime
           "top_conviction": 90,   # 55% win · +17.3R/56
           "kr_approved": 85,      # GREEN jury: 59% win · +10.7R/51
           "trend_rider": 80,      # 2026-08-11 user call: the desk's
                                   # biggest earner (+81.6R/244,
                                   # +73.1R last 14d) at 27% win —
                                   # few wins, huge ones. Capped at 2
                                   # slots, long hold, no smart exit.
           "surge": 70,            # 43% win · +5.5R/292
           "fresh": 65}            # 40% win · +17.8R/192
# 2026-08-11 user call: 🚀 MOONSHOT removed from the demo menu (desk
# record 9 closed / −0.65R, and those closes pre-date the top-30
# validation restrictions — it hasn't earned a money seat yet). 🥇
# PRIME was already out (2026-08-09). Both keep proving on the desk;
# they return only when their OWN live record turns green.


def load() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            s = json.load(f)
        if isinstance(s, dict) and "balance" in s \
                and s.get("gen") == GEN:
            return s
    except Exception:
        pass
    return {"gen": GEN, "balance": START_BAL, "start": START_BAL,
            "started_at": time.time(), "open": [], "closed": [],
            "equity_hist": []}


def save(state: dict) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass


def rank_candidates(pools: dict, tier_form: dict) -> list:
    """pools: {stream: [signal dicts]} -> ranked candidates.

    CONFLUENCE RULE (user 2026-08-09: "if most of the system agree and
    the confidence score is highest we take that trade"): the same
    coin+side appearing in MULTIPLE systems gets +25 rank per extra
    agreeing system — agreement dominates the slot race. The plan
    (entry/stop/TPs) comes from the highest-class system that fired it.
    """
    agg: dict = {}
    for name, sigs in pools.items():
        w = CLASS_W.get(name, 30)
        form = max(-10.0, min(float(tier_form.get(name, 0.0) or 0.0),
                              10.0))
        for p in sigs or []:
            sym = p.get("symbol")
            side = (p.get("side") or "").upper()
            if not sym or side not in ("LONG", "SHORT"):
                continue
            try:
                e = float(p.get("entry") or 0)
                st = float(p.get("stop") or 0)
                t1 = float(p.get("tp1") or 0)
            except (TypeError, ValueError):
                continue
            if min(e, st, t1) <= 0 or e == st or t1 == e:
                continue
            sc = float(p.get("score") or 60)
            t2 = p.get("tp2")
            base_rank = w + sc / 2 + form
            k = (sym, side)
            cur = agg.get(k)
            if cur is None:
                agg[k] = {"symbol": sym,
                          "base": p.get("base")
                          or sym.replace("USDT", ""),
                          "side": side, "entry": e, "stop": st,
                          "tp1": t1,
                          "tp2": float(t2) if t2 else None,
                          "src": name, "score": sc, "w": w,
                          "srcs": {name}, "rank": base_rank}
            else:
                cur["srcs"].add(name)
                cur["rank"] = max(cur["rank"], base_rank)
                cur["score"] = max(cur["score"], sc)
                if w > cur["w"]:        # higher-class plan wins
                    cur.update({"entry": e, "stop": st, "tp1": t1,
                                "tp2": float(t2) if t2 else None,
                                "src": name, "w": w})
    out = list(agg.values())
    for c in out:
        c["agree"] = len(c["srcs"])
        bonus = 25 * (c["agree"] - 1)
        # priority ladder (user 2026-08-09): EARLY ELITE + KRONOS
        # APPROVED agreeing = TOP priority; KRONOS APPROVED + any
        # other desk tier = HIGH priority; rest by score/confidence.
        # 2026-08-14 deploy order: 💎 ELITE CONVICTION (already
        # approved-badge-only at the pool gate) WINS ALL — "kronos
        # approved or unapproved ... elite conviction wins all with no
        # cap on 5 slots". Implemented as a hard class sort, not just
        # points: any candidate carrying elite_conv sorts ABOVE every
        # candidate that doesn't, no matter what confluence the rival
        # stacked. Kronos agreement still orders elite-conv cards among
        # THEMSELVES (the +80 pair bonus + confluence +25s), so
        # 💎×🔮✅ stays the best of the best.
        if "elite_conv" in c["srcs"]:
            bonus += 80
        if "kr_approved" in c["srcs"] and (
                "elite_early" in c["srcs"] or "elite_conv" in c["srcs"]):
            bonus += 80
        elif "kr_approved" in c["srcs"] and c["agree"] >= 2:
            bonus += 50
        c["rank"] += bonus
        c["top"] = 1 if "elite_conv" in c["srcs"] else 0
        c["srcs"] = ",".join(sorted(c["srcs"]))
    out.sort(key=lambda x: (-x.get("top", 0), -x["rank"]))
    return out


def try_open(state: dict, cands: list, live_fn) -> list:
    """Fill free slots with the best in-zone candidates. Real-account
    rules: slot cap, one per coin, notional risk-sized off the CURRENT
    balance, entry fee paid immediately."""
    opened = []
    held = {p["symbol"] for p in state["open"]}
    src_n: dict = {}
    for p in state["open"]:
        src_n[p.get("src")] = src_n.get(p.get("src"), 0) + 1
    for c in cands:
        if len(state["open"]) >= MAX_SLOTS:
            break
        if c.get("rank", 0) < MIN_RANK:
            break               # ranked list — nothing below the bar
        if c["symbol"] in held:
            continue
        _cap = MAX_PER_SRC.get(c["src"])
        if _cap is not None and src_n.get(c["src"], 0) >= _cap:
            continue            # per-source slot cap (rider = 2 of 5)
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
               "lev": round(notional / max(1.0, state["balance"]), 1),
               "risk0": abs(live - c["stop"]),
               "src": c["src"], "score": c["score"],
               "agree": c.get("agree", 1),
               "srcs": c.get("srcs", c["src"]),
               "opened_at": time.time(), "fees": fee_in,
               "tp1_banked": 0.0, "be_set": False, "peak": live}
        state["balance"] -= fee_in
        state["open"].append(pos)
        held.add(c["symbol"])
        src_n[c["src"]] = src_n.get(c["src"], 0) + 1
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


def manage(state: dict, live_fn, kr_get=None) -> list:
    """TP1 half-bank + BE, then a TRAIL toward TP2 (stop ratchets to
    lock TRAIL_LOCK of the peak open gain — user 2026-08-15), TP2/
    stop/time-stop closes, plus the STRENGTH-AWARE SMART EXIT: a hard
    kronos flip against a weak signal banks the trade (validated); a
    strong signal (💎/🔮✅ source, 2+ agreeing systems, or score>=85)
    gets room instead — scratch-stop before TP1, tighter trail after.
    Returns events: (close|tp1|guard, rec)."""
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
        # 📈 peak tracking — the best favorable price this position has
        # printed; the trail ratchets off THIS, never off a dip.
        _pk = float(p.get("peak") or p["entry"])
        _pk = max(_pk, live) if lng else min(_pk, live)
        p["peak"] = _pk
        # 🧵 TRAIL TO TP2 (user 2026-08-15): once TP1 banked, the rest
        # doesn't sit at flat breakeven — the stop locks TRAIL_LOCK of
        # the PEAK open gain and only ever moves the safe way, riding
        # toward TP2. Strong signals that get flipped against tighten
        # to TRAIL_LOCK_FLIP instead of closing (below).
        if p.get("be_set") and p["qty"] > 0:
            _lk = float(p.get("trail_lock") or TRAIL_LOCK)
            _cand = p["entry"] + (_pk - p["entry"]) * _lk
            p["stop"] = (max(p["stop"], _cand) if lng
                         else min(p["stop"], _cand))
        hit_stop = live <= p["stop"] if lng else live >= p["stop"]
        hit_tp1 = live >= p["tp1"] if lng else live <= p["tp1"]
        t2 = p.get("tp2")
        hit_tp2 = (t2 is not None
                   and (live >= t2 if lng else live <= t2))
        _tsh = TIME_STOP_BY_SRC.get(p.get("src"), TIME_STOP_H)
        expired = time.time() - p["opened_at"] > _tsh * 3600
        # 🛡 SMART EXIT — in profit + read flipped against us.
        # 2026-08-15 STRENGTH-AWARE (user: "loosen a bit if the signal
        # strength is good to gain more"): the brain checks the
        # signal's own quality —
        #   WEAK signal  → hard close, bank the money (validated)
        #   STRONG, before TP1 → stop to SCRATCH, ride to TP1
        #   STRONG, after TP1  → trail tightens to 75% of the peak
        #     gain, rest keeps riding toward TP2
        if not hit_stop and not hit_tp2 and kr_get is not None \
                and p.get("src") not in SMART_EXIT_SKIP:
            _r0 = float(p.get("risk0") or 0) or \
                abs(p["entry"] - p["stop"]) or p["entry"] * 0.02
            _pr = (live - p["entry"]) * (1 if lng else -1) / _r0
            if _pr >= 0.3:
                try:
                    _kv = kr_get(p["symbol"], p["side"])
                except Exception:
                    _kv = None
                if _kv:
                    _against = ((_kv.get("direction") == "DOWN" and lng)
                                or (_kv.get("direction") == "UP"
                                    and not lng))
                    _ex = abs(float(_kv.get("exp_move_pct") or 0))
                    if _against and _ex >= 2.0 and not _is_strong(p):
                        rec = _close_qty(
                            state, p, p["qty"], live,
                            f"smart exit — read flipped "
                            f"{_kv.get('direction')} "
                            f"{float(_kv.get('exp_move_pct') or 0):+.1f}%"
                            f" at +{_pr:.1f}R")
                        state["closed"].append(rec)
                        events.append(("close", rec))
                        continue
                    if _against and _ex >= 2.0 and _is_strong(p):
                        if p.get("be_set"):
                            _new_lk = TRAIL_LOCK_FLIP
                            _tag = (f"trail tightened to "
                                    f"{int(_new_lk*100)}% of the "
                                    f"peak gain, riding to TP2")
                            p["trail_lock"] = max(
                                float(p.get("trail_lock")
                                      or TRAIL_LOCK), _new_lk)
                            _cand = p["entry"] + \
                                (_pk - p["entry"]) * p["trail_lock"]
                            p["stop"] = (max(p["stop"], _cand) if lng
                                         else min(p["stop"], _cand))
                        else:
                            _cush = p["entry"] * 2 * FEE
                            _cand = p["entry"] + (_cush if lng
                                                  else -_cush)
                            p["stop"] = (max(p["stop"], _cand) if lng
                                         else min(p["stop"], _cand))
                            _tag = ("stop to scratch, riding to TP1 "
                                    "— strong signal earns the room")
                        if not p.get("flip_guard"):
                            p["flip_guard"] = True
                            events.append(("guard", {
                                "base": p["base"], "side": p["side"],
                                "symbol": p["symbol"],
                                "stop": p["stop"],
                                "reason": (
                                    f"read flipped "
                                    f"{_kv.get('direction')} "
                                    f"{float(_kv.get('exp_move_pct') or 0):+.1f}%"
                                    f" at +{_pr:.1f}R — STRONG signal "
                                    f"({p.get('src')}), {_tag}")}))
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
