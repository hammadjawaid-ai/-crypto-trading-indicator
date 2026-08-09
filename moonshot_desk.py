"""🚀 MOONSHOT DESK — the separate big-move desk (user 2026-08-09).

Mission: catch the BMT-class move BEFORE it goes, on a ~60-coin
universe, 24/7, without touching the existing system. Four analyst
layers vote on every coin every cycle:

  🔥 HEAT   — LunarCrush social velocity: AltRank ripping better and/or
              interactions surging vs the coin's own baseline. The
              crowd arrives before the candle finishes.
  ⛽ FUEL   — Coinalyze positioning: open interest building (+5%/24h,
              the runner archetype from the 2026-08-06 precursor
              study) and/or the crowd leaning the wrong way (squeeze).
  🏗 BASE   — chart structure: NOT already extended, sitting in the
              upper half of its recent range or coiled tight. We buy
              the loaded spring, never the rocket mid-flight.
  ⏱ TRIGGER — the boiling point: a 1h close breaking the prior 12h
              high on >=1.5x volume. Entry ON the break — the only
              entry style that measured positive across our studies
              (thrust-chasing -0.15R, coil-close -0.21R, break +0.10R).

A 🚀 fire needs TRIGGER + at least two of HEAT/FUEL/BASE. Kronos is
recorded as color, never a gate here. Plan: tight stop under the break
bar (-0.25 ATR), bank HALF at +1R, runner rides a 3xATR trail for the
big move.

STATUS: UNPROVEN construct — deployed as its own desk tier proving
forward from day one; every watch snapshot is stored so future BMTs
become measurable precursor data. Live executor NEVER reads this.
"""
from __future__ import annotations

import time

# 60 -> 100 (user 2026-08-09: "should be for all") — full match with
# the worker's hunting universe.
UNIVERSE_N = 100
# 2026-08-09 validation (backtest_moonshot, 298 fires/100 coins): the
# fuel+base+trigger core measured +0.14R/61.5% banking 1R on the
# TOP-30 by volume but ~flat-to-negative on the 31-100 tail, and the
# 3xATR trail gave back money at both scales (-0.11R full universe).
# FIRES therefore restrict to the top-30; the 100-coin boil WATCH
# stays (heat has no backtest — it proves forward on the desk).
FIRE_UNIVERSE_N = 30
EXT_MAX = 12.0          # |24h| beyond this = already flying, too late
HEAT_RANK_JUMP = 150    # alt_rank improvement vs ~6h ago
HEAT_INTER_X = 2.0      # interactions_24h vs ~12h-ago baseline
FUEL_OI_PCT = 5.0       # OI build over 24h
BREAK_VOL_X = 1.5
MAX_DEEP = 12           # deep-chart candidates per cycle (CPU guard)
MAX_FIRES = 3


def map_social(rows: list) -> dict:
    """LunarCrush coin_list rows -> {SYMUSDT: social snapshot}."""
    out = {}
    for r in rows or []:
        s = str(r.get("symbol") or "").upper()
        if not s:
            continue
        out[s + "USDT"] = {
            "alt_rank": r.get("alt_rank"),
            "galaxy": r.get("galaxy_score"),
            "inter": r.get("interactions_24h"),
            "soc_dom": r.get("social_dominance"),
            "sent": r.get("sentiment"),
        }
    return out


def heat_check(sym: str, hist: list) -> tuple[bool, str]:
    """hist = list of (ts, alt_rank, interactions) snapshots, oldest
    first, appended once per worker cycle (~5 min)."""
    if len(hist) < 2:
        return False, "warming up"
    now = hist[-1]
    t_now = now[0]
    # ~6h-ago rank / ~12h-ago interactions baselines (fail-soft to the
    # oldest snapshot while history warms up)
    r6 = next((h for h in hist if t_now - h[0] <= 6.5 * 3600), hist[0])
    i12 = next((h for h in hist if t_now - h[0] <= 12.5 * 3600), hist[0])
    bits = []
    hot = False
    try:
        if (r6[1] or 0) and (now[1] or 0) and r6[1] - now[1] >= \
                HEAT_RANK_JUMP:
            hot = True
            bits.append(f"altrank +{r6[1] - now[1]:.0f} in 6h")
    except TypeError:
        pass
    try:
        if (i12[2] or 0) > 0 and (now[2] or 0) / i12[2] >= HEAT_INTER_X:
            hot = True
            bits.append(f"social x{now[2] / i12[2]:.1f} vs 12h")
    except TypeError:
        pass
    return hot, " · ".join(bits) or "quiet"


def fuel_check(pos: dict | None) -> tuple[bool, str]:
    """pos = {'d_oi': pct 24h, 'd_ls': ratio delta 24h, 'fund': now}."""
    if not pos:
        return False, "no data yet"
    bits = []
    fueled = False
    d_oi = pos.get("d_oi")
    if d_oi is not None and d_oi >= FUEL_OI_PCT:
        fueled = True
        bits.append(f"OI +{d_oi:.1f}%/24h")
    d_ls = pos.get("d_ls")
    if d_ls is not None and d_ls <= -0.05:
        fueled = True
        bits.append(f"crowd leaning short ({d_ls:+.2f}) — squeeze fuel")
    f = pos.get("fund")
    if f is not None and f <= -0.05:
        fueled = True
        bits.append(f"funding {f:+.3f} (shorts paying)")
    return fueled, " · ".join(bits) or "flat"


def analyze_chart(d1) -> dict | None:
    """BASE + TRIGGER from ~200 1h candles. Returns feature dict with
    a ready plan when the trigger just fired, else trigger=False."""
    if d1 is None or len(d1) < 60:
        return None
    h = d1["high"].astype(float).tolist()
    l = d1["low"].astype(float).tolist()
    c = d1["close"].astype(float).tolist()
    v = d1["volume"].astype(float).tolist()
    px = c[-1]
    chg24 = (px / c[-25] - 1) * 100 if len(c) >= 25 else 0.0
    trs = [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
           for i in range(len(c) - 14, len(c))]
    a14 = sum(trs) / len(trs)
    if a14 <= 0 or px <= 0:
        return None
    lo_r = min(l[-192:]) if len(l) >= 192 else min(l)
    hi_r = max(h[-192:]) if len(h) >= 192 else max(h)
    pos_r = (px - lo_r) / (hi_r - lo_r) * 100 if hi_r > lo_r else 50.0
    rng24 = (max(h[-24:]) - min(l[-24:])) / px * 100
    rng72 = (max(h[-72:]) - min(l[-72:])) / px * 100 / 3
    coiled = rng72 > 0 and rng24 / rng72 < 1.2
    base_ok = abs(chg24) < EXT_MAX and (pos_r >= 50 or coiled)
    # TRIGGER: current bar broke the prior 12h high on volume.
    # hi12 doubles as the PRE-ANNOUNCED fire level (user 2026-08-09:
    # "predict early and first" — the board shows WHERE it fires
    # before it happens).
    hi12 = max(h[-13:-1])
    vma = sum(v[-21:-1]) / 20
    vx = v[-1] / vma if vma > 0 else 0.0
    trig = c[-1] > hi12 and vx >= BREAK_VOL_X and abs(chg24) < EXT_MAX
    stop = l[-1] - 0.25 * a14
    risk = px - stop
    if risk <= 0 or risk > 4 * a14:
        stop = px - 1.5 * a14
        risk = px - stop
    return {"px": px, "chg24": round(chg24, 1),
            "pos_r": round(pos_r), "coiled": coiled,
            "base_ok": base_ok, "trigger": trig,
            "vx": round(vx, 1), "trig_px": hi12,
            "extended": abs(chg24) >= EXT_MAX,
            "entry": px, "stop": stop, "tp1": px + risk,
            "tp2": px + 3 * risk, "atr": a14}


def scan(symbols: list, soc_hist: dict, pos_cache: dict,
         get_klines, kr_get=None) -> tuple[list, list]:
    """One desk pass. Returns (fires, watch_rows).

    soc_hist: {sym: [(ts, alt_rank, interactions), ...]} maintained by
    the worker. pos_cache: {sym: positioning dict} on rotation.
    Deep chart work only for coins showing HEAT or FUEL (CPU guard).
    """
    fires, watch = [], []
    fire_ok = set(symbols[:FIRE_UNIVERSE_N])
    deep = 0
    for sym in symbols:
        hot, hot_d = heat_check(sym, soc_hist.get(sym) or [])
        fueled, fuel_d = fuel_check(pos_cache.get(sym))
        if not (hot or fueled):
            continue
        row = {"symbol": sym, "base": sym.replace("USDT", ""),
               "heat": hot, "heat_d": hot_d,
               "fuel": fueled, "fuel_d": fuel_d, "ts": time.time()}
        if deep < MAX_DEEP:
            deep += 1
            try:
                ch = analyze_chart(get_klines(sym, "1h", limit=200))
            except Exception:
                ch = None
            if ch:
                row.update({"px": ch["px"], "chg24": ch["chg24"],
                            "pos_r": ch["pos_r"],
                            "coiled": ch["coiled"],
                            "base_ok": ch["base_ok"],
                            "trigger": ch["trigger"],
                            "vx": ch["vx"],
                            "trig_px": ch["trig_px"],
                            "extended": ch["extended"],
                            "votes": sum((hot, fueled,
                                          ch["base_ok"]))})
                votes = sum((hot, fueled, ch["base_ok"]))
                if ch["trigger"] and votes >= 2 and sym in fire_ok:
                    kr = None
                    if kr_get is not None:
                        try:
                            kr = kr_get(sym, "LONG")
                        except Exception:
                            kr = None
                    fires.append({
                        "symbol": sym,
                        "base": sym.replace("USDT", ""),
                        "side": "LONG", "tier": "MOONSHOT",
                        "score": 60 + 10 * votes,
                        "entry": ch["entry"], "stop": ch["stop"],
                        "tp1": ch["tp1"], "tp2": ch["tp2"],
                        "heat_d": hot_d, "fuel_d": fuel_d,
                        "vx": ch["vx"], "chg24": ch["chg24"],
                        "votes": votes,
                        "kr_dir": (kr or {}).get("direction"),
                        "kr_exp": (kr or {}).get("exp_move_pct")})
        watch.append(row)
        if len(fires) >= MAX_FIRES:
            break
    # early-first ordering (user 2026-08-09): fresh loaded springs at
    # the top, already-ran coins at the bottom labeled as such
    watch.sort(key=lambda r: (bool(r.get("extended")),
                              -int(r.get("votes") or 0)))
    return fires, watch[:12]
