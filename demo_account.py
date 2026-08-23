"""🎮 DEMO ZONE — GEN 6: the $1,500 WILD run (user 2026-08-23).

A simulated REAL account run by the 24/7 worker. GEN 6 rules, all on
the user's explicit order: $1,500 start, 10 slots, one per coin,
Bybit taker fees both sides, 48h time-stop. The pool is EXACTLY
three streams — 💥⚡ STRONG TRIGGER breaks and 🔄 RE-RUNs (second-leg
breaks + re-qualified elite) own at least 7 of the 10 seats; 💎
elite conviction holds AT MOST 3, and only its cream (approved +
MAX grade / 90+ / 2-lane 85+). Sizing is wild by design: each slot
margins balance/10 and levers 5x-10x by signal grade. TP1 half-bank + BE, trail to TP2, and
the strength-aware smart exit only steps in when a move is fading.

The 10-day question voiced: does $1,500 honestly reach $2,500? Every
open/close buzzes Telegram; the page shows the equity curve and every
position. Simulated only — no real orders.
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
# GEN 5 = 2026-08-15 later the same day (user order 6: "restart demo
# and remove trend rider from it it sucks") — 🌊 TREND RIDER out of
# the money, and the pool trimmed to exactly the named five: 💎 elite
# conviction (approved) · 🏆 top conviction · 🌟 early elite · 🔮✅
# kronos approved · ✅🔥 take now hot. Surge and fresh lose their
# money seats too (not on the user's list).
# GEN 6 = 2026-08-23 ("even in bull it lost me money... this time we
# go wild"): $1,500 start, 5 slots, ONLY the desk's proven-hot
# streams spend — 💥⚡ STRONG TRIGGER breaks + 🔄 RE-RUN (second-leg
# breaks / re-qualified elite) on TOP priority, 💎 elite conviction
# MAX/HIGH (approved) secondary. NOTHING else gets a seat. Sizing is
# the wild part: each slot margins balance/5 and levers 5x-10x by
# signal grade, so a normal 1R swing is ~$50-200 instead of $10-20.
# TP/SL and the smart exit are UNCHANGED — ideally SL/TP resolves;
# the smart exit only steps in when the move is fading.
GEN = 6
START_BAL = 1500.0
# 6 -> 10 (user 2026-08-23 second follow-up: "instead of 6 we have
# 10 slots now and 7 for strong triggers and 3 for elite
# conviction"). A CEILING, not a quota — the MIN_RANK floor still
# gates every slot. Elite's 3-seat cap below guarantees the top
# streams (strong triggers + re-runs) always keep >= 7 seats.
MAX_SLOTS = 10
# The earlier 6->8 good-day overflow is absorbed by the 10-slot
# base; no seats beyond 10.
MAX_SLOTS_HOT = 10
# GEN 6 WILD SIZING (user 2026-08-23: "more leverage 5x to 10x...
# 50-200 dollars per trade... notions as per 1500 in the bank
# accordingly"): per-slot margin = balance / MAX_SLOTS, leverage
# graded by the validated quality tells — never a flat max.
LEV_BASE = 5.0                 # 💎 elite MAX/HIGH (secondary stream)
LEV_MID = 7.0                  # 💥⚡ strong trigger / 🔄 re-run
LEV_MAX = 10.0                 # A-grade: burst >= 85 at the break
                               # (validated 64.7% · +0.288R)
FEE = 0.00055                  # Bybit taker, per side
TIME_STOP_H = 48
# GEN 5 (user order 6): 🌊 TREND RIDER is OUT of the demo — its
# per-source hold/slot/smart-exit carve-outs go with it.
TIME_STOP_BY_SRC: dict = {}
# GEN 6 (user 2026-08-23, updated same day): 💎 elite conviction
# holds AT MOST 3 of the 10 slots — and only its cream (the worker's
# pool gate: approved AND MAX grade / 90+ / 2-lane 85+). Counted by
# plan-winning source, so a coin that a top stream also fired spends
# a TOP seat, not an elite one. NOTE the 2026-08-23 lanes study
# measured every elite AT-FIRE cell negative after fees — these
# seats live or die by the demo's own ledger.
MAX_PER_SRC: dict = {"elite_conv": 3}
SMART_EXIT_SKIP: set = set()
# 🧠 STRENGTH-AWARE SMART EXIT + TRAIL (user 2026-08-15: "smart exit
# should have a trailing method... loosen a bit if the signal
# strength is good... let them ride to tp and trail to tp2 if they
# are good enough — use the brain"). The brain's strength read = the
# signal's own quality at entry: top-class source (💎 elite_conv /
# 🔮✅ kr_approved), multi-system agreement, or a big score.
# GEN 6: every money stream is a proven-hot construct, so all three
# class as STRONG — the smart exit gives them room (scratch-stop /
# tightened trail) instead of banking early. User 2026-08-23:
# "ideally it should stop at sl and tp set... smart exit only if you
# see the movement is fading and it wont push any further."
STRONG_SRC = {"elite_conv", "kr_approved", "strong_trigger", "rerun"}
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
# GEN 5 pool (user order 6, 2026-08-15: "we already told you what we
# want to have — top conviction, early elite, kronos approved and
# take now hot" + elite conviction on top by standing order). 🌊
# TREND RIDER removed ("it sucks" — 3-of-4 losers didn't fit);
# surge and fresh lose their seats too (not on the named list).
# GEN 6 pool (user 2026-08-23: "we only go with Strong triggers and
# Re Run, and Elite conviction max... elite conviction max or high
# can be secondary, top priority is strong triggers and reruns...
# nothing else should be a part of demo trading"): exactly three
# streams, weighted by their LIVE desk records —
CLASS_W = {"strong_trigger": 100,  # 💥⚡ 79% win · +58.7R/241, the
                                   # desk's best win rate at scale
           "rerun": 100,           # 🔄 second-leg breaks + 💎🔄
                                   # re-qualified (68% win · +0.36R)
           "elite_conv": 85}       # 💎 MAX/HIGH approved — SECONDARY
# GEN 6: no conditional seats — the pool is exactly the named three.
CONDITIONAL_SRC: set = set()
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
            # 🏦 B-stock money gate (user 2026-08-17: "give them real
            # size when validated") — tokenized symbols get NO demo
            # money until their cohort validation flips the flag.
            if sym in getattr(config, "TOKENIZED_STOCKS", ()) \
                    and not getattr(config, "BSTOCK_VALIDATED", False):
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
                          "srcs": {name}, "rank": base_rank,
                          "burst": float(p.get("burst") or 0),
                          "kr_ok": bool(p.get("kr_agree"))}
            else:
                cur["srcs"].add(name)
                cur["rank"] = max(cur["rank"], base_rank)
                cur["score"] = max(cur["score"], sc)
                cur["burst"] = max(float(cur.get("burst") or 0),
                                   float(p.get("burst") or 0))
                cur["kr_ok"] = cur.get("kr_ok") \
                    or bool(p.get("kr_agree"))
                if w > cur["w"]:        # higher-class plan wins
                    cur.update({"entry": e, "stop": st, "tp1": t1,
                                "tp2": float(t2) if t2 else None,
                                "src": name, "w": w})
    out = list(agg.values())
    # 🔀 the either/or gate: conditional-only candidates trade ONLY
    # with a kronos agreement or a second agreeing model.
    out = [c for c in out
           if not (c["srcs"] <= CONDITIONAL_SRC
                   and len(c["srcs"]) < 2
                   and not c.get("kr_ok"))]
    for c in out:
        c["agree"] = len(c["srcs"])
        bonus = 25 * (c["agree"] - 1)
        # GEN 6 priority ladder (user 2026-08-23: "top priority is
        # strong triggers and reruns... elite conviction max or high
        # can be secondary"): a hard class sort, not just points —
        # any candidate carrying a top stream sorts ABOVE every
        # elite-only candidate, no matter the rank it stacked. The
        # A-grade burst (>=85, validated) orders top-stream cards
        # among themselves.
        _top6 = c["srcs"] & {"strong_trigger", "rerun"}
        if _top6:
            bonus += 80
        if float(c.get("burst") or 0) >= 85:
            bonus += 40
        c["rank"] += bonus
        c["top"] = 1 if _top6 else 0
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
        if len(state["open"]) >= MAX_SLOTS_HOT:
            break
        if len(state["open"]) >= MAX_SLOTS and not (
                c.get("top")
                and (float(c.get("burst") or 0) >= 85
                     or int(c.get("agree") or 1) >= 2)):
            continue            # 🔥 overflow seats 7-8: hot
                                # top-stream fires only
        if c.get("rank", 0) < MIN_RANK:
            continue            # two-key sort (top, rank) — a low
                                # top-stream rank must not gate the
                                # elite cards sorted after it
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
        # GEN 6 WILD SIZING: slot margin = balance/5, leverage graded
        # by signal quality — 10x needs the validated A-grade burst.
        margin = state["balance"] / MAX_SLOTS
        lev = LEV_BASE
        if c.get("top") or c["src"] in ("strong_trigger", "rerun"):
            lev = LEV_MID
        if float(c.get("burst") or 0) >= 85:
            lev = LEV_MAX
        # real-account physics: the stop must sit well inside the
        # slot's margin — a stop past ~liquidation is not a trade.
        if stop_pct >= 0.8 / lev:
            continue
        notional = margin * lev
        fee_in = notional * FEE
        pos = {"symbol": c["symbol"], "base": c["base"],
               "side": c["side"], "entry": live, "stop": c["stop"],
               "tp1": c["tp1"], "tp2": c["tp2"],
               "qty": notional / live, "notional": notional,
               "lev": round(lev, 1), "margin": round(margin, 2),
               "burst": float(c.get("burst") or 0),
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
