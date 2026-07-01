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

    # --- Stream 2: ELITE MAX/HIGH that is TAKE_NOW + HOT -----------------
    takenow: list[dict] = []
    for p in scan:
        if (p.get("tier") or "").upper() not in ("MAX", "HIGH"):
            continue
        side = (p.get("side") or "").upper()
        pl = _plan(p)
        entry = float(pl.get("entry") or 0)
        if side not in ("LONG", "SHORT") or entry <= 0:
            continue
        try:
            et = entry_timing.entry_signal(
                p.get("symbol"), side, entry, stop=float(pl.get("stop") or 0))
        except Exception:
            continue
        if et.get("status") == "TAKE_NOW" and et.get("hot"):
            takenow.append({
                "symbol": p.get("symbol"),
                "base": p.get("base") or (p.get("symbol") or "").replace(
                    "USDT", ""),
                "side": side,
                "tier": (p.get("tier") or "").upper(),
                "score": float(p.get("score") or 0),
                "entry": entry,
                "stop": float(pl.get("stop") or 0),
                "tp1": float(pl.get("tp1") or 0),
                "tp2": float(pl.get("tp2") or 0),
                "hot": True,
                "atr_pct": et.get("atr_pct"),
            })
    return {"sst1": sst1, "takenow": takenow, "regime": regime}
