"""💎 BEST TRADE ZONE — ONE consolidated board (user 2026-07-11).

Every validated lane votes on the same candidate; a setup makes the board
only when the stacked confluence clears the bar. Vote weights come from
the systems' own validated after-fee records (8-month master validation
2026-07-07 + positioning validation 2026-07-11) — not invented numbers:

  ⭐🚀 early-lane            81.3% / +0.066R (n=796)   -> 3.0 (alone = in)
       (= velocity_burst / early_trend / early_momentum lanes — the
        card tag names which ones fired)
  🌊🟢 spot-driven breakout  74.2% / +1.04R  (n=62,
       falling 5d OI, every-era consistent)           -> 3.0 (alone = in)
  🌊 trend breakout          +0.15-0.32R/trade         -> 1.5
  🌊⚠️ crowded breakout      (OI +10%+: worst bucket)  -> 0.75
  🏆 apex                    64.9% / +0.009R           -> 1.5
  🌟 early elite             65.5% approved cell       -> 1.5
  🌱 fresh                   74% short-window cell     -> 1.0
  🛡 elite conviction MAX/HIGH (validated composite)   -> 0.75
  ✅🔥 take-now hot           validated construct       -> 0.5
  🎯 pattern scout           same-side validated-edge
       pattern >= 70 (V-bottom 75%, aligned-longs
       67%, morning star / hammer 60-75%)             -> 0.5 (confirm)

DELIBERATELY OUT: CONVERGENCE — re-backtested NEGATIVE in the worker
era (scan_core), despite the older app-side "+6.8pp" claim. A negative
edge cannot vote on the best board.

QUALIFY: votes >= 3.0 — a single top cell, or 2+ systems agreeing.
Plan (entry/SL/TP) is taken from the EARLIEST-entering source (early-lane
first), which already carries the validated structural stop from
scan_core. The desk ladder then manages BE at +1R / TP1 lock / trail —
"if it goes positive we don't lose money".

OI context per trend candidate comes from Coinalyze (5d daily OI change,
cached 1h, fail-soft to plain-trend weight when unavailable).
"""
from __future__ import annotations

import time

import binance_client
import coinalyze_client as cz
import pattern_scout

W_EARLY_LANE = 3.0
W_TREND_SPOT = 3.0
W_TREND = 1.5
W_TREND_CROWDED = 0.75
W_APEX = 1.5
W_ELITE_EARLY = 1.5
W_FRESH = 1.0
W_ELITE_WATCH = 0.75
W_TN_HOT = 0.5
W_PATTERN = 0.5
MIN_SCORE = 3.0
TOP = 6
PATTERN_MAX_CHECKS = 12

_oi_cache: dict = {}
_OI_TTL = 3600.0


def _oi5(sym: str) -> float | None:
    """5-day % change in daily open interest (cached 1h, fail-soft)."""
    now = time.time()
    hit = _oi_cache.get(sym)
    if hit and now - hit[0] < _OI_TTL:
        return hit[1]
    val = None
    try:
        if cz.is_configured():
            mkt = cz.resolve_perp(sym)
            if mkt:
                h = cz.oi_history(mkt, "daily", days=12)
                if h is not None and len(h) >= 6:
                    prev = float(h["oi_c"].iloc[-6])
                    if prev > 0:
                        val = float(h["oi_c"].iloc[-1]) / prev - 1.0
    except Exception:
        val = None
    _oi_cache[sym] = (now, val)
    return val


def _hold_est(p: dict, from_trend: bool) -> str:
    """⏱ expected hold, derived from the plan itself — TP1's distance in
    hourly ATRs (momentum moves ~0.3-1 ATR/hour net) — not a made-up
    number. Trend rides use their validated 3-10 day historical range."""
    if from_trend:
        return "3-10 days (trail decides)"
    try:
        entry = float(p.get("entry") or 0)
        tp1 = float(p.get("tp1") or 0)
        atr_pct = float(p.get("atr_pct") or 0)
        if entry > 0 and tp1 > 0 and atr_pct > 0:
            n = abs(tp1 - entry) / entry * 100.0 / atr_pct
            lo = max(2, int(round(n)))
            hi = min(48, max(lo + 2, int(round(n * 3))))
            if hi >= 24:
                return f"~{lo}h-{hi / 24:.0f}d (cut at 48h)"
            return f"~{lo}-{hi}h (cut at 48h)"
    except Exception:
        pass
    return "hours-2 days (cut at 48h)"


def compose(trend: list, apex: list, elite_early: list, fresh_m: list,
            tn_hot: list, em_big: list, top: int = TOP,
            elite_watch: list | None = None,
            pattern_votes: bool = True) -> list[dict]:
    """The 💎 list: candidates from every lane, vote-stacked and ranked."""
    cands: dict = {}

    def _add(p: dict, w: float, tag: str, plan_rank: int) -> None:
        sym = p.get("symbol")
        side = (p.get("side") or "").upper()
        if not sym or side not in ("LONG", "SHORT"):
            return
        c = cands.setdefault((sym, side), {
            "votes": 0.0, "tags": [], "plan": None, "plan_rank": 99})
        c["votes"] += w
        if tag not in c["tags"]:
            c["tags"].append(tag)
        if (plan_rank < c["plan_rank"] and p.get("entry")
                and p.get("stop") and p.get("tp1")):
            c["plan_rank"] = plan_rank
            c["plan"] = p

    for p in em_big:
        # name the actual early systems that fired (user 2026-07-13:
        # early_trend / early_momentum must be visible in the stack)
        _lanes = "+".join(p.get("early_lanes") or []) or "early-lane"
        _add(p, W_EARLY_LANE, f"⭐🚀 early-lane 81% ({_lanes})", 0)
    for p in elite_early:
        _add(p, W_ELITE_EARLY, "🌟 early elite", 1)
    for p in apex:
        _add(p, W_APEX, "🏆 apex", 2)
    for p in fresh_m:
        _add(p, W_FRESH, "🌱 fresh", 3)
    for p in tn_hot:
        _add(p, W_TN_HOT, "✅🔥 hot", 4)
    for p in trend:
        oi5 = _oi5(p.get("symbol"))
        if oi5 is not None and oi5 < 0:
            _add(p, W_TREND_SPOT, "🌊🟢 spot-driven breakout 74%", 5)
        elif oi5 is not None and oi5 > 0.10:
            _add(p, W_TREND_CROWDED, "🌊⚠️ crowded breakout", 5)
        else:
            _add(p, W_TREND, "🌊 trend breakout", 5)
    # 🛡 ELITE conviction watch (user 2026-07-13): the full MAX/HIGH
    # conviction board confirms as a vote — plan only as last resort
    # (watch rows can be pre-confirmation/ARMING).
    for p in elite_watch or []:
        if (p.get("tier") or "").upper() in ("MAX", "HIGH"):
            _add(p, W_ELITE_WATCH, "🛡 elite conviction", 7)

    # 🎯 PATTERN SCOUT confirmation (user 2026-07-13): a validated-edge
    # candle pattern firing on the SAME side adds +0.5. Run only for
    # near-qualified candidates (votes >= 1.5), best-first, capped —
    # keeps the worker cycle fast. Fail-soft per symbol.
    if pattern_votes:
        _checked = 0
        for (sym, side), c in sorted(cands.items(),
                                     key=lambda kv: -kv[1]["votes"]):
            if c["votes"] < 1.5:
                continue
            if _checked >= PATTERN_MAX_CHECKS:
                break
            _checked += 1
            try:
                df = binance_client.get_klines(sym, "1h", limit=120)
                ps = pattern_scout.scan_one(sym, df)
                if ((ps.get("side") or "").upper() == side
                        and float(ps.get("score") or 0) >= 70):
                    c["votes"] += W_PATTERN
                    c["tags"].append(f"🎯 pattern: {ps.get('best_signal')}")
            except Exception:
                pass

    out = []
    for (_sym, _side), c in cands.items():
        if c["votes"] < MIN_SCORE or not c["plan"]:
            continue
        p = dict(c["plan"])
        p["best_score"] = round(c["votes"], 2)
        p["tags"] = c["tags"]
        p["hold_est"] = _hold_est(p, c["plan_rank"] == 5)
        out.append(p)
    out.sort(key=lambda q: -q["best_score"])
    return out[:top]
