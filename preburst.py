"""🌋 PRE-BURST RADAR — quiet coils where Kronos smells a move.

User 2026-08-03 (PORTAL +21% case): "predict trades BEFORE they burst."
Detection = the PORTAL-base signature, the OPPOSITE of chasing:
  - 24h range < 6% of price (tight)
  - |24h change| < 4% (going nowhere yet)
  - ATR14 in the bottom 35% of its trailing 100 (volatility compressed)
Then 🔮 Kronos forecasts the next 24h from the coil; a fire needs
|exp_move| >= EXP_MIN — the model saying "this base is loaded".

Status: UNPROVEN construct deployed by explicit user call (the
IGNITION precedent) — every alert says so; desk tier "preburst" builds
the forward record; backtest_coil_kronos.py is validating in parallel
and recalibrates/retires this per its verdict. Executor never trades it.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

import binance_client

RANGE_MAX = 0.06
MOVE_MAX = 4.0
ATR_PCT_MAX = 35.0
EXP_MIN = float(os.environ.get("PREBURST_EXP_MIN", "2.0"))
MAX_FIRES = 4


def _coil(sym):
    """Return coil context dict if sym is a quiet coil RIGHT NOW."""
    d = binance_client.get_klines(sym, "1h", limit=130)
    if d is None or len(d) < 120:
        return None
    h = d["high"].astype(float).to_numpy()
    l = d["low"].astype(float).to_numpy()
    c = d["close"].astype(float).to_numpy()
    px = c[-1]
    if px <= 0:
        return None
    tr = np.maximum(h[1:] - l[1:],
                    np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    atr = pd.Series(np.concatenate([[tr[0]], tr])).rolling(
        14, min_periods=1).mean().to_numpy()
    rng24 = (h[-24:].max() - l[-24:].min()) / px
    chg24 = abs(px / c[-25] - 1) * 100 if c[-25] else 99
    atr_pct = float((atr[-100:] <= atr[-1]).mean() * 100)
    if rng24 >= RANGE_MAX or chg24 >= MOVE_MAX or atr_pct >= ATR_PCT_MAX:
        return None
    return {"px": px, "atr": float(atr[-1]),
            "swing_lo": float(np.min(l[-10:])),
            "swing_hi": float(np.max(h[-10:])),
            "rng24": round(rng24 * 100, 2), "atr_pct": round(atr_pct)}


def scan(symbols, kronos_fn, max_checks: int = 40) -> list[dict]:
    """kronos_fn(sym) -> {"direction","exp_move_pct",...} or None
    (worker supplies its cached/budgeted forecaster). Returns fires."""
    out = []
    checked = 0
    for sym in symbols:
        if checked >= max_checks or len(out) >= MAX_FIRES:
            break
        checked += 1
        try:
            ctx = _coil(sym)
        except Exception:
            continue
        if not ctx:
            continue
        try:
            kv = kronos_fn(sym)
        except Exception:
            kv = None
        if not kv or kv.get("direction") not in ("UP", "DOWN"):
            continue
        exp = float(kv.get("exp_move_pct") or 0)
        if abs(exp) < EXP_MIN:
            continue
        long = kv["direction"] == "UP"
        px, atr = ctx["px"], ctx["atr"]
        if long:
            stop = ctx["swing_lo"] - 0.25 * atr
            if not (0 < px - stop <= 4 * atr):
                stop = px - 1.5 * atr
            tp1 = px + (px - stop)
            tp2 = px + 2 * (px - stop)
        else:
            stop = ctx["swing_hi"] + 0.25 * atr
            if not (0 < stop - px <= 4 * atr):
                stop = px + 1.5 * atr
            tp1 = px - (stop - px)
            tp2 = px - 2 * (stop - px)
        if min(px, stop, tp1) <= 0:
            continue
        out.append({"symbol": sym,
                    "base": sym.replace("USDT", ""),
                    "side": "LONG" if long else "SHORT",
                    "tier": "COIL", "score": None, "hot": False,
                    "entry": px, "stop": stop, "tp1": tp1, "tp2": tp2,
                    "kr_dir": kv["direction"], "kr_exp": exp,
                    "coil_rng24": ctx["rng24"],
                    "coil_atr_pct": ctx["atr_pct"]})
    out.sort(key=lambda p: -abs(float(p.get("kr_exp") or 0)))
    return out
