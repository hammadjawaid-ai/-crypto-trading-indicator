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

# 2026-07-28 user call: TAKE NOW HOT removed as a source — "it sends
# in very late". EARLY ELITE (its best subset, earlier) + IGNITION
# (at-fire, earliest) remain. Reversible with evidence: the funnel
# audit keeps recording, so if data shows TNH-only winners we missed,
# it comes back with proof. TNH keeps its desk tier + Telegram stream.
# 2026-07-29 confirmation head-to-head (20 coins, 130 arm-entries,
# fees in): at-fire -0.324R (worst by far); 15m/30m/1h confirms all
# ~breakeven within noise, but 30m enters at 48m avg (vs 125m for 1h)
# with the best balance (40% win). fast30 = exactly that construct,
# and its live desk record is GREEN (+6.2R/298). It earns a seat.
SOURCES = (("elite_early", "🌟 EARLY ELITE"),
           ("ignition", "🚨 IGNITION"),
           ("fast30", "⏱ FAST CONFIRM 30m"))
# 2026-08-05 (CRCLB gold-card case): tokenized equities are excluded
# from gold — no validated edges there, session gaps, thin books, and
# Kronos reads them unreliably (out-of-distribution).
# swept top-110 on 2026-08-06 when the scan widened to 100 coins —
# the tail is full of these (GOOGLB/NVDAB/SPYB...). Re-sweep with
# .tail_check.py whenever breadth changes; BNB/SHIB are real crypto.
TOKENIZED = {"CRCLBUSDT", "SPCXBUSDT", "SOXLBUSDT", "SNDKBUSDT",
             "SNXXBUSDT", "EWYBUSDT", "MUBUSDT", "SOXSUSDT",
             "SOXLUSDT", "GIGGLEUSDT", "SKHYBUSDT", "KORUBUSDT",
             "SPYBUSDT", "AXTIBUSDT", "AAOIBUSDT", "NBISBUSDT",
             "GOOGLBUSDT", "NVDABUSDT", "FLNCBUSDT"}
ZONE_MAX = 0.10
EXT_24H = 25.0
EXT_6H = 18.0
RR_MIN = 1.5
MAX_CARDS = 3
KR_HORIZON = 24


# 🔬 FUNNEL AUDIT — every candidate considered in the last compose(),
# with each gate's verdict, so the page can show a living board even
# when nothing fully qualifies ("died at kronos" beats an empty page).
# Module global by the best_board.LAST_VOTES precedent; the worker
# stores these rows as stream "ts_audit" for the app.
LAST_AUDIT: list = []
MAX_AUDIT = 10


def compose(sources: dict, tier_form: dict, regime: str,
            live_fn, ext_fn, kronos_fn) -> list[dict]:
    """sources: {tier_name: [signal dicts]} for the three source tiers.
    tier_form: {tier_name: recent-14d net R} (desk truth).
    live_fn(sym)->px · ext_fn(sym)->(pct24h, pct6h) or None ·
    kronos_fn(sym, side)->{"direction","exp_move_pct",...} or None.
    Every gate fails CLOSED. Returns at most MAX_CARDS augmented rows;
    fills LAST_AUDIT with every candidate's per-gate verdict.
    """
    global LAST_AUDIT
    regime = (regime or "").upper()
    seen: set = set()
    out = []
    audit: list = []

    def _note(p, tier_label, gates, detail=""):
        if len(audit) >= MAX_AUDIT:
            return
        audit.append({"symbol": p.get("symbol"), "base": p.get("base"),
                      "side": (p.get("side") or "").upper(),
                      "tier_label": tier_label, "gates": gates,
                      "detail": detail, "ts": time.time()})

    for tier, label in SOURCES:
        form_ok = float(tier_form.get(tier, 0.0) or 0.0) > 0
        for p in sources.get(tier) or []:
            sym = p.get("symbol")
            side = (p.get("side") or "").upper()
            k = (sym, side)
            if not sym or side not in ("LONG", "SHORT") or k in seen:
                continue
            seen.add(k)
            if sym in TOKENIZED:
                _note(p, label, {"source": True, "early": None,
                                 "geometry": None, "kronos": None,
                                 "regime": None},
                      "tokenized equity — excluded instrument class")
                continue
            g = {"source": form_ok, "early": None, "geometry": None,
                 "kronos": None, "regime": None}
            if not form_ok:                # gate 1: source form not hot
                _note(p, label, g, "source tier cold (14d form ≤ 0)")
                continue
            g["regime"] = not ((regime == "BEAR" and side == "LONG") or
                               (regime == "BULL" and side == "SHORT"))
            if not g["regime"]:            # gate 5
                _note(p, label, g, f"{side} against {regime}")
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
                g["early"] = False         # gate 2a: not early anymore
                _note(p, label, g,
                      "stopped" if dead else
                      f"{prog * 100:.0f}% of move gone (>10%)")
                continue
            try:
                ext = ext_fn(sym)
            except Exception:
                ext = None
            if ext is None:
                continue
            c24, c6 = ext
            if abs(c24) >= EXT_24H or abs(c6) >= EXT_6H:
                g["early"] = False         # gate 2b: anti-chase
                _note(p, label, g,
                      f"extended {c24:+.0f}%/24h {c6:+.0f}%/6h")
                continue
            g["early"] = True
            risk = abs(live - st) / live * 100
            if risk <= 0:
                continue
            rr = (abs(t1 - live) / live * 100) / risk
            g["geometry"] = rr >= RR_MIN
            if not g["geometry"]:          # gate 3
                _note(p, label, g, f"R:R {rr:.2f} < {RR_MIN}")
                continue
            try:
                kr = kronos_fn(sym, side)
            except Exception:
                kr = None
            if not kr:                     # gate 4: no verdict, no card
                g["kronos"] = False
                _note(p, label, g, "kronos: no fresh forecast")
                continue
            agree = ((kr.get("direction") == "UP" and is_long) or
                     (kr.get("direction") == "DOWN" and not is_long))
            g["kronos"] = agree
            if not agree:                  # gate 4: the top layer's veto
                _note(p, label, g,
                      f"kronos says {kr.get('direction')} "
                      f"{float(kr.get('exp_move_pct') or 0):+.1f}%")
                continue
            _note(p, label, g, f"✓ QUALIFIED · R:R {rr:.2f}")
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
    LAST_AUDIT = audit
    out.sort(key=lambda r: -float(r.get("ts_rr") or 0))
    return out[:MAX_CARDS]
