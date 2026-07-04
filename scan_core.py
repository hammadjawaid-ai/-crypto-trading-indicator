"""Headless scan core — the validated signal streams, no Streamlit.

Produces the two streams the 24/7 worker alerts on, mirroring app.py:
  1. SST1 conv>=70          — the proven ~72% tier (BEST TRADES NOW board)
  2. ELITE MAX/HIGH that is  — TAKE_NOW + 🔥 HOT (validated ~71% higher-edge
     entry timing; the ACTIVE MAX/HIGH board)

Importable from a background worker: it calls the same engines the app calls
(experimental_signals.scan_unified, sureshot_agents.run_pipeline,
entry_timing.entry_signal, market_regime.detect_regime) with NO app.py and NO
streamlit. Convergence is intentionally omitted — it is a tag, not a candidate
source, and backtested negative — so this is faithful, slightly more
conservative, and drift-safe.
"""
from __future__ import annotations

import experimental_signals as es
import sureshot_agents as ssa
import entry_timing
import market_regime
import binance_client
import velocity_burst as _vb
import predict_next as _pn
import funding_fade as _ff
import config


def tp2_rides(cands: list, max_checks: int = 10) -> list:
    """🎯 TP2 continuation tracker — for recent best-signals whose TP1 has
    been HIT since the signal, check if momentum is STILL intact (close on
    the right side of EMA20 + ATR still hot — the validated components).
    Returns the setups worth riding to TP2 (stop managed at TP1, per the
    ladder's chase logic). Display/manage info only — a FRESH entry after
    TP1 is breakout-chasing (tested 24%, rejected)."""
    import numpy as np
    import pandas as pd
    out = []
    for cd in cands[:max_checks]:
        sym = cd.get("symbol")
        side = (cd.get("side") or "").upper()
        tp1 = float(cd.get("tp1") or 0)
        tp2 = float(cd.get("tp2") or 0)
        t0 = float(cd.get("ts") or 0)
        if not sym or side not in ("LONG", "SHORT") or tp1 <= 0 or tp2 <= 0:
            continue
        try:
            df = binance_client.get_klines(sym, "1h", limit=120)
        except Exception:
            continue
        if df is None or len(df) < 30:
            continue
        ts_s = df.index.values.astype("datetime64[s]").astype("int64")
        idx = int(np.searchsorted(ts_s, t0, side="right"))
        if idx >= len(df):
            continue
        h = df["high"].to_numpy(); l = df["low"].to_numpy()
        c = df["close"].to_numpy()
        ema20 = df["close"].ewm(span=20, adjust=False).mean().to_numpy()
        cur = float(c[-1])
        if side == "LONG":
            if float(np.max(h[idx:])) < tp1:      # TP1 not reached yet
                continue
            if cur >= tp2 or cur <= tp1 * 0.995:  # done, or fell back
                continue
            trend = cur > ema20[-1]
        else:
            if float(np.min(l[idx:])) > tp1:
                continue
            if cur <= tp2 or cur >= tp1 * 1.005:
                continue
            trend = cur < ema20[-1]
        pc = np.roll(c, 1); pc[0] = c[0]
        tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
        atr = pd.Series(tr).rolling(14).mean().to_numpy()
        ref = atr[-100:]; ref = ref[~np.isnan(ref)]
        hot = (len(ref) > 0 and atr[-1] == atr[-1]
               and float((ref < atr[-1]).mean() * 100) >= 60)
        if trend and hot:
            out.append({
                "symbol": sym,
                "base": cd.get("base") or sym.replace("USDT", ""),
                "side": side,
                "tier": cd.get("tier"),
                "score": cd.get("score"),
                "entry": cd.get("entry"),
                "stop": cd.get("stop"),
                "tp1": tp1, "tp2": tp2,
                "px": cur,
                "src": cd.get("stream", ""),
            })
    return out


def _regime() -> dict:
    try:
        return market_regime.detect_regime()
    except Exception as exc:
        return {"regime": "UNKNOWN", "confidence": 0.0, "composite": 50.0,
                "long_bias": 50.0, "short_bias": 50.0, "components": {},
                "summary": f"regime detection failed: {exc}"}


def _plan(p: dict) -> dict:
    return p.get("trade_plan") or {}


def scan_all(scan_n: int = 60, min_conv: float = 70.0) -> dict:
    """Return {"sst1": [...], "takenow": [...], "regime": {...}}.

    sst1     = SST1 picks with conviction >= min_conv (sorted high->low).
    takenow  = ELITE MAX/HIGH setups that are TAKE_NOW *and* HOT right now.
    Each pick: symbol/base/side/entry/stop/tp1/tp2 + stream-specific fields.
    """
    scan = es.scan_unified(scan_n=scan_n, interval="1h",
                           min_score=70.0, max_picks=40) or []
    elite = {p.get("symbol"): p for p in scan}
    srs = {p.get("symbol") for p in scan
           if float(p.get("score") or 0) >= 88
           and p.get("tier") in ("HIGH", "MAX")}
    regime = _regime()

    # --- Stream 1: SST1 conv>=70 (proven tier) ---------------------------
    sst1: list[dict] = []
    try:
        r = ssa.run_pipeline(scan, regime, set(), srs, elite,
                             news_headlines=[], det_floor=55.0,
                             llm_top_n=0, use_llm=False, max_picks=24)
        for p in (r.get("sure_shots") or []):
            conv = float(p.get("conviction") or 0)
            if conv < min_conv:
                continue
            pl = _plan(p)
            sst1.append({
                "symbol": p.get("symbol"),
                "base": p.get("base") or (p.get("symbol") or "").replace(
                    "USDT", ""),
                "side": (p.get("side") or "").upper(),
                "conviction": conv,
                "entry": float(pl.get("entry") or 0),
                "stop": float(pl.get("stop") or 0),
                "tp1": float(pl.get("tp1") or 0),
                "tp2": float(pl.get("tp2") or 0),
            })
        sst1.sort(key=lambda x: x["conviction"], reverse=True)
    except Exception:
        pass

    # --- Stream 2: ALL TAKE_NOW entries (HOT flagged) ---------------------
    # Merged universe: ELITE MAX/HIGH picks + SST1 conv>=min picks. Stores
    # every TAKE_NOW (hot=True/False) so the app's unified TAKE NOW board is
    # complete; the worker alerts only the HOT subset (validated higher edge).
    takenow: list[dict] = []
    _tn_seen: set = set()
    _tn_cands: list[tuple] = []
    for p in scan:
        if (p.get("tier") or "").upper() in ("MAX", "HIGH"):
            _tn_cands.append((p.get("symbol"), (p.get("side") or "").upper(),
                              _plan(p), (p.get("tier") or "").upper(),
                              float(p.get("score") or 0), p.get("base"),
                              len(p.get("active_lanes") or [])))
    for sp in sst1:
        _tn_cands.append((sp["symbol"], sp["side"],
                          {"entry": sp["entry"], "stop": sp["stop"],
                           "tp1": sp["tp1"], "tp2": sp["tp2"]},
                          "SST1", sp["conviction"], sp.get("base"), 0))
    for sym, side, pl, tier, score, base, lanes in _tn_cands:
        entry = float(pl.get("entry") or 0)
        if side not in ("LONG", "SHORT") or entry <= 0:
            continue
        if (sym, side) in _tn_seen:
            continue
        try:
            et = entry_timing.entry_signal(
                sym, side, entry, stop=float(pl.get("stop") or 0))
        except Exception:
            continue
        if et.get("status") == "TAKE_NOW":
            _tn_seen.add((sym, side))
            takenow.append({
                "symbol": sym,
                "base": base or (sym or "").replace("USDT", ""),
                "side": side,
                "tier": tier,
                "score": score,
                "lanes": int(lanes),
                "entry": entry,
                "stop": float(pl.get("stop") or 0),
                "tp1": float(pl.get("tp1") or 0),
                "tp2": float(pl.get("tp2") or 0),
                "hot": bool(et.get("hot")),
                "atr_pct": et.get("atr_pct"),
            })
    takenow.sort(key=lambda x: (1 if x["hot"] else 0, x["score"]),
                 reverse=True)

    # --- Stream 2b: ⚡ EARLY MOVERS — STRONG tier + TAKE_NOW + HOT --------
    # Validated (backtest_early_strong, 40 coins / 540 entries): 69.3% win,
    # 0.82R median run on n=176 decided — near-premium win rate at ~8x the
    # frequency, shorter runs. BOARD-ONLY stream (user 2026-07-05): stored +
    # displayed in its own section, never alerted. Separate from the takenow
    # stream so the existing boards/alerts are untouched.
    early_strong: list[dict] = []
    for p in scan:
        if (p.get("tier") or "").upper() != "STRONG":
            continue
        side = (p.get("side") or "").upper()
        pl = _plan(p)
        entry = float(pl.get("entry") or 0)
        if side not in ("LONG", "SHORT") or entry <= 0:
            continue
        if float(p.get("score") or 0) < 80:
            continue
        try:
            et = entry_timing.entry_signal(
                p.get("symbol"), side, entry,
                stop=float(pl.get("stop") or 0))
        except Exception:
            continue
        if et.get("status") == "TAKE_NOW" and et.get("hot"):
            # 🚀 early-lane flag — validated (backtest_early_lanes, 40 coins
            # / 518 entries): fires with these lanes active enter with ~35%
            # less of the move gone and hit >=2R ~50% more often (22% vs
            # 15%), at 64.8% vs 75.2% win. Same expectancy — different
            # profile. Descriptive tag only.
            _elanes = sorted(set(p.get("active_lanes") or [])
                             & {"velocity_burst", "early_trend",
                                "early_momentum"})
            early_strong.append({
                "symbol": p.get("symbol"),
                "base": p.get("base") or (p.get("symbol") or "").replace(
                    "USDT", ""),
                "side": side,
                "tier": "STRONG",
                "score": float(p.get("score") or 0),
                "entry": entry,
                "stop": float(pl.get("stop") or 0),
                "tp1": float(pl.get("tp1") or 0),
                "tp2": float(pl.get("tp2") or 0),
                "hot": True,
                "atr_pct": et.get("atr_pct"),
                "early_lanes": _elanes,
            })
    early_strong.sort(key=lambda x: x["score"], reverse=True)
    early_strong = early_strong[:8]

    # --- Stream 3: leaderboard — top-conviction ELITE MAX/HIGH ----------
    # The highest-score MAX/HIGH picks (the leaderboard), as an early
    # heads-up before they reach TAKE_NOW. Ranked by the ELITE composite.
    leaderboard: list[dict] = []
    for p in scan:
        if (p.get("tier") or "").upper() not in ("MAX", "HIGH"):
            continue
        side = (p.get("side") or "").upper()
        if side not in ("LONG", "SHORT"):
            continue
        pl = _plan(p)
        leaderboard.append({
            "symbol": p.get("symbol"),
            "base": p.get("base") or (p.get("symbol") or "").replace(
                "USDT", ""),
            "side": side,
            "tier": (p.get("tier") or "").upper(),
            "score": float(p.get("score") or 0),
            "entry": float(pl.get("entry") or 0),
            "stop": float(pl.get("stop") or 0),
            "tp1": float(pl.get("tp1") or 0),
            "tp2": float(pl.get("tp2") or 0),
        })
    leaderboard.sort(key=lambda x: x["score"], reverse=True)

    # --- Stream 4: APEX — consensus of validated edges (best of the best) --
    # A setup where >= APEX_MIN independent validated edges agree. Candidate
    # universe = ELITE MAX/HIGH picks UNION SST1 conv>=70 picks. Every edge
    # check is fail-soft so one bad fetch never breaks the cycle.
    apex_min = int(getattr(config, "WORKER_APEX_MIN_EDGES", 3))
    sst1_by = {p["symbol"]: p for p in sst1}
    cand: dict = {}
    for p in scan:
        if (p.get("tier") or "").upper() in ("MAX", "HIGH"):
            cand[p.get("symbol")] = {"pick": p, "sst1": sst1_by.get(
                p.get("symbol"))}
    for sym, sp in sst1_by.items():
        if sym not in cand:
            cand[sym] = {"pick": elite.get(sym), "sst1": sp}
    apex: list[dict] = []
    for sym, c in list(cand.items())[:16]:
        p, sp = c["pick"], c["sst1"]
        if p:
            side = (p.get("side") or "").upper()
            pl = _plan(p)
            tier = (p.get("tier") or "").upper()
            score = float(p.get("score") or 0)
        elif sp:
            side = sp["side"]
            pl = {"entry": sp["entry"], "stop": sp["stop"],
                  "tp1": sp["tp1"], "tp2": sp["tp2"]}
            tier, score = "", 0.0
        else:
            continue
        entry = float(pl.get("entry") or 0)
        if side not in ("LONG", "SHORT") or entry <= 0:
            continue
        edges = []
        if sp is not None:
            edges.append("SST1")
        if tier in ("MAX", "HIGH"):
            edges.append("ELITE")
        df1 = None
        try:
            df1 = binance_client.get_klines(sym, "1h", limit=120)
        except Exception:
            df1 = None
        try:
            et = entry_timing.entry_signal(
                sym, side, entry, stop=float(pl.get("stop") or 0), df=df1)
            if et.get("status") == "TAKE_NOW":
                edges.append("TAKE_NOW")
            if et.get("hot"):
                edges.append("HOT")
        except Exception:
            pass
        try:
            if df1 is not None:
                bs, bside, _ = _vb.lane_velocity_burst(df1)
                if bs >= 90 and (bside or "").upper() == side:
                    edges.append("BURST")
        except Exception:
            pass
        try:
            pr = _pn.predict(
                sym, klines_by_tf={"1h": df1} if df1 is not None else None)
            ol = (pr.get("outlook") or "")
            if pr.get("aligned") and (
                    (side == "LONG" and ol == "Bullish")
                    or (side == "SHORT" and ol == "Bearish")):
                edges.append("FORECAST")
        except Exception:
            pass
        try:
            if p is not None and int(p.get("_mtf_aligned") or 0) >= 2:
                edges.append("MTF")
        except Exception:
            pass
        try:
            # Validated funding-velocity fade (59% @48h, +2.5%): counts as
            # an edge when the fade direction AGREES with the setup side.
            if _ff.signal(sym).get("fade_side") == side:
                edges.append("FUND")
        except Exception:
            pass
        if len(edges) >= apex_min:
            apex.append({
                "symbol": sym,
                "base": (p or sp).get("base") or (sym or "").replace(
                    "USDT", ""),
                "side": side,
                "tier": tier or "SST1",
                "score": score if score else float(
                    (sp or {}).get("conviction") or 0),
                "entry": entry,
                "stop": float(pl.get("stop") or 0),
                "tp1": float(pl.get("tp1") or 0),
                "tp2": float(pl.get("tp2") or 0),
                "edges": edges,
                "apex": len(edges),
            })
    apex.sort(key=lambda x: (x["apex"], x["score"]), reverse=True)

    # --- Stream 5: ELITE (24/7 watch) — the full ELITE board, continuously.
    # Reuses the scan already computed above (near-zero extra cost). Top picks
    # across MAX/HIGH/STRONG so the ELITE section has live 24/7 data too.
    elite_watch: list[dict] = []
    for p in scan:
        tier = (p.get("tier") or "").upper()
        side = (p.get("side") or "").upper()
        if tier not in ("MAX", "HIGH", "STRONG"):
            continue
        if side not in ("LONG", "SHORT"):
            continue
        pl = _plan(p)
        elite_watch.append({
            "symbol": p.get("symbol"),
            "base": p.get("base") or (p.get("symbol") or "").replace(
                "USDT", ""),
            "side": side,
            "tier": tier,
            "score": float(p.get("score") or 0),
            "entry": float(pl.get("entry") or 0),
            "stop": float(pl.get("stop") or 0),
            "tp1": float(pl.get("tp1") or 0),
            "tp2": float(pl.get("tp2") or 0),
        })
    elite_watch.sort(key=lambda x: (
        {"MAX": 3, "HIGH": 2, "STRONG": 1}.get(x["tier"], 0), x["score"]),
        reverse=True)
    elite_watch = elite_watch[:12]

    return {"sst1": sst1, "takenow": takenow, "leaderboard": leaderboard,
            "apex": apex, "elite": elite_watch,
            "early_strong": early_strong, "regime": regime}
