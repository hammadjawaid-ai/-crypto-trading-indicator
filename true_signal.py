"""🎯 TRUE SIGNAL — the one surface that speaks; everything else is backend.

User 2026-07-28 rework ("I don't want noise — few trades, the true ones,
early, max confidence"): a candidate becomes a card ONLY by passing all
five gates, with 🔮 Kronos as the TOP layer holding the last word.

The gates (each one earned its place with data):
  1. SOURCE  — born from EARLY ELITE / IGNITION / TAKE NOW HOT, and only
               while that tier's recent-14d desk form is positive (the
               recency law that silenced APEX at -5.2R/14d).
  2. EARLY   — <=10% of entry->TP1 gone AND not extended (|24h|<25%,
               |6h|<18% — the LA/LPT anti-chase rule, measured -0.087R).
  3. GEOMETRY— R:R to TP1 >= 1.5 at LIVE price (the UNI-2.1R standard;
               rejects the AAVE-0.69 cards).
  4. KRONOS  — the foundation model's 24h forecast must AGREE with the
               side. Validated on OUR entries 2026-07-28: agree bucket
               +0.259R / 81.8% win while baseline lost -0.069R and the
               vetoed bucket bled -0.143R (n=81, fees in). STRICT: no
               agree -> no card. Kronos offline -> no cards + honest
               banner (never silently downgrade the construct).
  5. REGIME  — no fresh LONGs in BEAR, no SHORTs in BULL.

Worker computes this every cycle; desk tier "true_signal" builds the
honest forward record from day one. No Telegram until it earns it
(~20 closed, positive). Live executor NEVER reads this module.
"""
from __future__ import annotations

import time

SOURCES = (("elite_early", "🌟 EARLY ELITE"),
           ("ignition", "🚨 IGNITION"),
           ("takenow_hot", "✅🔥 TAKE NOW HOT"))
ZONE_MAX = 0.10
EXT_24H = 25.0
EXT_6H = 18.0
RR_MIN = 1.5
MAX_CARDS = 3
KR_HORIZON = 24


def compose(sources: dict, tier_form: dict, regime: str,
            live_fn, ext_fn, kronos_fn) -> list[dict]:
    """sources: {tier_name: [signal dicts]} for the three source tiers.
    tier_form: {tier_name: recent-14d net R} (desk truth).
    live_fn(sym)->px · ext_fn(sym)->(pct24h, pct6h) or None ·
    kronos_fn(sym, side)->{"direction","exp_move_pct",...} or None.
    Every gate fails CLOSED. Returns at most MAX_CARDS augmented rows.
    """
    regime = (regime or "").upper()
    seen: set = set()
    out = []
    for tier, label in SOURCES:
        if float(tier_form.get(tier, 0.0) or 0.0) <= 0:
            continue                       # gate 1: source form not hot
        for p in sources.get(tier) or []:
            sym = p.get("symbol")
            side = (p.get("side") or "").upper()
            k = (sym, side)
            if not sym or side not in ("LONG", "SHORT") or k in seen:
                continue
            seen.add(k)
            if regime == "BEAR" and side == "LONG":
                continue                   # gate 5
            if regime == "BULL" and side == "SHORT":
                continue
            try:
                e = float(p.get("entry") or 0)
                st = float(p.get("stop") or 0)
                t1 = float(p.get("tp1") or 0)
            except (TypeError, ValueError):
                continue
            if min(e, st, t1) <= 0 or t1 == e:
                continue
            try:
                live = float(live_fn(sym) or 0)
            except Exception:
                continue
            if live <= 0:
                continue
            is_long = side == "LONG"
            prog = ((live - e) / (t1 - e) if is_long
                    else (e - live) / (e - t1))
            dead = (live <= st if is_long else live >= st)
            if dead or prog > ZONE_MAX:
                continue                   # gate 2a: early zone
            try:
                ext = ext_fn(sym)
            except Exception:
                ext = None
            if ext is None:
                continue
            c24, c6 = ext
            if abs(c24) >= EXT_24H or abs(c6) >= EXT_6H:
                continue                   # gate 2b: anti-chase
            risk = abs(live - st) / live * 100
            if risk <= 0:
                continue
            rr = (abs(t1 - live) / live * 100) / risk
            if rr < RR_MIN:
                continue                   # gate 3: geometry
            try:
                kr = kronos_fn(sym, side)
            except Exception:
                kr = None
            if not kr:
                continue                   # gate 4: no verdict, no card
            agree = ((kr.get("direction") == "UP" and is_long) or
                     (kr.get("direction") == "DOWN" and not is_long))
            if not agree:
                continue                   # gate 4: the top layer's veto
            row = dict(p)
            row["ts_source"] = label
            row["ts_rr"] = round(rr, 2)
            row["ts_prog"] = round(prog, 3)
            row["ts_c24"] = round(c24, 1)
            row["ts_c6"] = round(c6, 1)
            row["ts_live"] = live
            row["kr_dir"] = kr.get("direction")
            row["kr_exp"] = kr.get("exp_move_pct")
            row["ts_born"] = time.time()
            out.append(row)
    out.sort(key=lambda r: -float(r.get("ts_rr") or 0))
    return out[:MAX_CARDS]
