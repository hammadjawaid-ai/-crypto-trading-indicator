"""Unified Signal Composite (formerly experimental).

Merged scanner that combines EVERY proven signal lane into ONE
conviction score per coin, with full BEST-TRADES-NOW-style metadata
for rendering. Replaces the separated REBOUND + BREAKOUT + EXPERIMENTAL
hunters with a single unified pick board.

Signal lanes (weights sum to 1.00, calibrated to backtested edge):

  vwap_zfade       0.10  — VWAP z-score fade (counter-trend ≥2σ)
  liq_exhaustion   0.13  — Long-exhaustion liquidation reversal (4%+
                            drop + OI down + vol spike + absorption)
  rebound          0.13  — V-bottom + RSI capitulation + reversal pattern
  breakout_coil    0.10  — BB squeeze + OBV accumulation + OI surge
  pattern_scout    0.18  — Live candle pattern (hammer/star/engulfing)
  reversal_app     0.10  — 7 pre-fire reversal conditions
  early_momentum   0.10  — CVD + TTM + SMC + VWAP-reclaim composite
  recovery         0.08  — recovery_detector V-bottom
  deriv_velocity   0.08  — funding ROC + OI compression

Conviction tier (mirrors Paper Trader's logic):
  MAX      score >= 90 AND (≥3 lanes scoring 70+)
  HIGH     score >= 85 AND (≥2 lanes scoring 70+)
  STRONG   score >= 80
  STANDARD score >= 70  (firing floor)

Cards built by this module carry ALL the chip metadata that BEST
TRADES NOW uses:
  - lanes_fired: dict of {lane_name: lane_score}
  - tier: MAX/HIGH/STRONG/STANDARD
  - reasons: list[str] (top 5)
  - trade_plan: {entry, stop, tp1, tp2, rr, valid}
  - side: LONG / SHORT
  - score: 0-100
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

import binance_client
import indicators

# Optional imports — every lane gracefully degrades to 0 if its module
# can't be reached.
try: import pattern_scout
except Exception: pattern_scout = None
try: import reversal_approach
except Exception: reversal_approach = None
try: import recovery_detector
except Exception: recovery_detector = None
try: import early_momentum
except Exception: early_momentum = None
try: import derivatives_velocity
except Exception: derivatives_velocity = None
try: import rebound_radar
except Exception: rebound_radar = None
try: import breakout_hunter
except Exception: breakout_hunter = None


# ---------------------------------------------------------------------------
# Lane weights (calibrated to backtested edge)
# ---------------------------------------------------------------------------
_LANE_WEIGHTS = {
    "vwap_zfade":     0.10,
    "liq_exhaustion": 0.13,
    "rebound":        0.13,
    "breakout_coil":  0.10,
    "pattern_scout":  0.18,
    "reversal_app":   0.10,
    "early_momentum": 0.10,
    "recovery":       0.08,
    "deriv_velocity": 0.08,
}


# ---------------------------------------------------------------------------
# Individual lane scorers — each returns (score 0-100, side, note)
# ---------------------------------------------------------------------------
def _lane_vwap_zfade(df: pd.DataFrame) -> tuple[float, str, str]:
    """VWAP z-score fade: ≥2σ deviation from session VWAP + RSI extreme."""
    if df is None or len(df) < 50:
        return (0.0, "NEUTRAL", "")
    try:
        typical = (df["high"] + df["low"] + df["close"]) / 3.0
        vwap = (typical * df["volume"]).cumsum() / df["volume"].cumsum().replace(0, np.nan)
        spread = df["close"] - vwap
        roll_std = spread.rolling(20, min_periods=10).std()
        z = (df["close"] - vwap) / roll_std.replace(0, np.nan)
        last_z = float(z.iloc[-1]) if not np.isnan(z.iloc[-1]) else 0.0
        last_rsi = float(df["rsi"].iloc[-1]) if "rsi" in df.columns else 50.0
        if last_z <= -2.0 and last_rsi <= 30:
            mag = min(abs(last_z), 3.5)
            sc = float(np.clip(60 + (mag - 2.0) * 30, 60, 100))
            return (sc, "LONG", f"z={last_z:.2f}σ + RSI {last_rsi:.0f} (oversold)")
        if last_z >= 2.0 and last_rsi >= 70:
            mag = min(abs(last_z), 3.5)
            sc = float(np.clip(60 + (mag - 2.0) * 30, 60, 100))
            return (sc, "SHORT", f"z=+{last_z:.2f}σ + RSI {last_rsi:.0f} (overbought)")
    except Exception:
        pass
    return (0.0, "NEUTRAL", "")


def _lane_liq_exhaustion(df: pd.DataFrame,
                        oi_hist: list | None) -> tuple[float, str, str]:
    """Long-exhaustion: 4%+ 3-bar drop + OI drop + vol spike + absorption."""
    if df is None or len(df) < 25:
        return (0.0, "NEUTRAL", "")
    try:
        last = df.iloc[-1]
        ret_3 = float(last["close"]) / float(df["close"].iloc[-4]) - 1.0
        if ret_3 > -0.04:
            return (0.0, "NEUTRAL", "")
        body = abs(float(last["close"]) - float(last["open"]))
        bar_rng = float(last["high"]) - float(last["low"])
        body_pct = (body / bar_rng) if bar_rng > 0 else 1.0
        close_pos = (
            (float(last["close"]) - float(last["low"])) / bar_rng
            if bar_rng > 0 else 0.5)
        if body_pct > 0.40 or close_pos < 0.60:
            return (0.0, "NEUTRAL", "")
        vol_ratio = (
            float(last["volume"]) / float(df["volume"].tail(20).mean())
            if df["volume"].tail(20).mean() else 0)
        if vol_ratio < 3.0:
            return (0.0, "NEUTRAL", "")
        oi_confirmed = False
        oi_pct = None
        if oi_hist and len(oi_hist) >= 4:
            try:
                oi_vals = [v for _, v in oi_hist[-4:]]
                if oi_vals[0] > 0:
                    oi_pct = (oi_vals[-1] - oi_vals[0]) / oi_vals[0]
                    oi_confirmed = oi_pct <= -0.05
            except Exception:
                pass
        if oi_confirmed:
            return (90.0, "LONG",
                    f"3bar drop {ret_3*100:+.1f}% · vol {vol_ratio:.1f}× "
                    f"· OI {oi_pct*100:+.1f}% · absorption candle")
        return (50.0, "LONG",
                f"3bar drop {ret_3*100:+.1f}% · vol {vol_ratio:.1f}× "
                f"· absorption (OI gate missing — caution)")
    except Exception:
        return (0.0, "NEUTRAL", "")


def _lane_rebound(symbol: str, df: pd.DataFrame,
                 pct_24h: float) -> tuple[float, str, str]:
    """Rebound score from existing rebound_radar (V-bottom composite)."""
    if rebound_radar is None or df is None:
        return (0.0, "NEUTRAL", "")
    try:
        r = rebound_radar.score(symbol, df, pct_24h=pct_24h)
        sc = float(r.get("score", 0))
        if sc < 50:
            return (0.0, "NEUTRAL", "")
        dd = r.get("drawdown_pct", 0)
        exp = r.get("expected_move_pct", 0)
        return (sc, "LONG",
                f"−{dd:.1f}% from high · expected +{exp:.1f}% rebound")
    except Exception:
        return (0.0, "NEUTRAL", "")


def _lane_breakout(symbol: str, df_4h: pd.DataFrame,
                  df_1h: pd.DataFrame | None) -> tuple[float, str, str]:
    """Breakout score from existing breakout_hunter (coil composite)."""
    if breakout_hunter is None or df_4h is None:
        return (0.0, "NEUTRAL", "")
    try:
        r = breakout_hunter.score(symbol, df_4h, df_1h)
        sc = float(r.get("score", 0))
        if sc < 50:
            return (0.0, "NEUTRAL", "")
        d7 = r.get("seven_day_chg_pct", 0)
        return (sc, "LONG", f"coil 7d {d7:+.1f}% (pre-pump compression)")
    except Exception:
        return (0.0, "NEUTRAL", "")


def _lane_pattern_scout(symbol: str, df: pd.DataFrame,
                       pct_24h: float) -> tuple[float, str, str]:
    """Pattern Scout — live candle pattern (hammer/star/engulfing)."""
    if pattern_scout is None or df is None:
        return (0.0, "NEUTRAL", "")
    try:
        r = pattern_scout.scan_one(symbol, df, pct_24h=pct_24h)
        side = r.get("side", "NEUTRAL")
        sc = float(r.get("score", 0))
        if side == "NEUTRAL" or sc < 60:
            return (0.0, "NEUTRAL", "")
        best = r.get("best_signal", "pattern")
        return (sc, side, f"Pattern Scout: {best}")
    except Exception:
        return (0.0, "NEUTRAL", "")


def _lane_reversal_app(df: pd.DataFrame) -> tuple[float, str, str]:
    """7 pre-fire reversal conditions (reversal_approach.scan_both_sides)."""
    if reversal_approach is None or df is None:
        return (0.0, "NEUTRAL", "")
    try:
        r = reversal_approach.scan_both_sides(df)
        side = r.get("side", "NEUTRAL")
        sc = float(r.get("score", 0))
        cm = int(r.get("conditions_met", 0))
        if sc < 65 or side == "NEUTRAL":
            return (0.0, "NEUTRAL", "")
        return (sc, side, f"reversal pre-conditions {cm}/7")
    except Exception:
        return (0.0, "NEUTRAL", "")


def _lane_early_momentum(df: pd.DataFrame) -> tuple[float, str, str]:
    """early_momentum composite (CVD + TTM + ROC² + SMC + VWAP)."""
    if early_momentum is None or df is None:
        return (0.0, "NEUTRAL", "")
    try:
        r = early_momentum.score(df)
        side = r.get("side", "NEUTRAL")
        sc = float(r.get("score", 0))
        if (side == "LONG" and sc >= 70) or (side == "SHORT" and sc <= 30):
            sc_norm = sc if side == "LONG" else (100 - sc)
            return (sc_norm, side, f"early_momentum {side.lower()} composite")
    except Exception:
        pass
    return (0.0, "NEUTRAL", "")


def _lane_recovery(df: pd.DataFrame) -> tuple[float, str, str]:
    """recovery_detector V-bottom (backtested 75% win at 12bar)."""
    if recovery_detector is None or df is None:
        return (0.0, "NEUTRAL", "")
    try:
        from recovery_detector import _v_bottom_bounce
        r = _v_bottom_bounce(df)
        sc = float(r.get("score") or 0)
        if sc < 65:
            return (0.0, "NEUTRAL", "")
        return (sc, "LONG", "V-bottom capitulation pattern")
    except Exception:
        return (0.0, "NEUTRAL", "")


def _lane_deriv_velocity(symbol: str) -> tuple[float, str, str]:
    """derivatives_velocity (funding ROC + OI compression)."""
    if derivatives_velocity is None:
        return (0.0, "NEUTRAL", "")
    try:
        r = derivatives_velocity.score(symbol, interval="1h")
        side = r.get("side", "NEUTRAL")
        sc = float(r.get("score", 0))
        if side == "NEUTRAL" or sc < 65:
            return (0.0, "NEUTRAL", "")
        return (sc, side, f"deriv {side.lower()} (funding+OI)")
    except Exception:
        return (0.0, "NEUTRAL", "")


# ---------------------------------------------------------------------------
# Composite scoring + tier
# ---------------------------------------------------------------------------
def _conviction_tier(score: float, n_strong_lanes: int) -> str:
    """MAX = score >= 90 AND >=3 strong lanes
       HIGH = score >= 85 AND >=2 strong lanes
       STRONG = score >= 80
       STANDARD = score >= 70
       (below 70 we filter out)"""
    if score >= 90 and n_strong_lanes >= 3:
        return "MAX"
    if score >= 85 and n_strong_lanes >= 2:
        return "HIGH"
    if score >= 80:
        return "STRONG"
    if score >= 70:
        return "STANDARD"
    return "LOW"


def score_one(symbol: str, interval: str = "1h",
             pct_24h: float = 0.0) -> dict:
    """Run ALL lanes for one symbol, composite into a single pick."""
    try:
        df = binance_client.get_klines(symbol, interval, limit=200)
        df = indicators.enrich(df)
    except Exception:
        return _empty(symbol)
    df_4h = None
    try:
        df_4h = binance_client.get_klines(symbol, "4h", limit=200)
        df_4h = indicators.enrich(df_4h)
    except Exception:
        pass
    oi_hist = None
    if derivatives_velocity is not None:
        try:
            oi_hist = derivatives_velocity._oi_history(
                symbol, period="1h", limit=12)
        except Exception:
            pass

    # Run each lane
    lanes = {
        "vwap_zfade":     _lane_vwap_zfade(df),
        "liq_exhaustion": _lane_liq_exhaustion(df, oi_hist),
        "rebound":        _lane_rebound(symbol, df, pct_24h),
        "breakout_coil":  _lane_breakout(symbol, df_4h or df, df),
        "pattern_scout":  _lane_pattern_scout(symbol, df, pct_24h),
        "reversal_app":   _lane_reversal_app(df),
        "early_momentum": _lane_early_momentum(df),
        "recovery":       _lane_recovery(df),
        "deriv_velocity": _lane_deriv_velocity(symbol),
    }

    # Vote: count LONG vs SHORT lanes weighted
    long_score = 0.0
    short_score = 0.0
    long_lanes = []
    short_lanes = []
    fired_reasons = []
    for name, (sc, side, note) in lanes.items():
        w = _LANE_WEIGHTS.get(name, 0.0)
        if side == "LONG" and sc >= 60:
            long_score += sc * w
            long_lanes.append((name, sc, note))
            fired_reasons.append(f"{name}: {note}")
        elif side == "SHORT" and sc >= 60:
            short_score += sc * w
            short_lanes.append((name, sc, note))
            fired_reasons.append(f"{name}: {note}")

    # Pick the dominant side. If neither has meaningful score, skip.
    if long_score >= short_score and long_score >= 30:
        side = "LONG"
        score = long_score / sum(_LANE_WEIGHTS.values())
        strong_n = len([1 for n, s, _ in long_lanes if s >= 70])
        active_lanes = long_lanes
    elif short_score > long_score and short_score >= 30:
        side = "SHORT"
        score = short_score / sum(_LANE_WEIGHTS.values())
        strong_n = len([1 for n, s, _ in short_lanes if s >= 70])
        active_lanes = short_lanes
    else:
        return _empty(symbol)

    # Conviction bonus: stack multiple lanes -> +5 per extra strong lane
    if strong_n >= 2:
        score += min(10, (strong_n - 1) * 5)
    score = float(np.clip(score, 0, 100))

    tier = _conviction_tier(score, strong_n)
    if tier == "LOW":
        return _empty(symbol)

    # Trade plan
    plan = _build_plan(df, side)
    # Order reasons by lane score, take top 5
    active_lanes.sort(key=lambda x: x[1], reverse=True)
    top_reasons = [
        f"{lane.replace('_', ' ')}: {note}"
        for lane, sc, note in active_lanes[:5]
        if note
    ]
    # Active lane names for chip rendering (top 6)
    active_lane_names = [lane for lane, _, _ in active_lanes[:6]]

    try:
        price_now = float(df["close"].iloc[-1])
    except Exception:
        price_now = 0.0

    return {
        "symbol": symbol,
        "base": symbol.replace("USDT", ""),
        "side": side,
        "score": round(score, 1),
        "tier": tier,
        "lanes_fired": {name: round(sc, 1)
                        for name, sc, _ in active_lanes},
        "active_lanes": active_lane_names,
        "n_strong_lanes": strong_n,
        "reasons": top_reasons,
        "trade_plan": plan,
        "price_now": price_now,
        "pct_24h": pct_24h,
    }


def scan_unified(scan_n: int = 100,
                interval: str = "1h",
                min_score: float = 70.0,
                max_picks: int = 15,
                max_workers: int = 6) -> list[dict]:
    """Scan top N coins, return high-conviction unified picks."""
    try:
        top = binance_client.get_top_symbols(scan_n)
        syms = top["symbol"].tolist()
        pct_map = dict(zip(top["symbol"], top["priceChangePercent"]))
    except Exception:
        return []

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(score_one, sym, interval,
                        float(pct_map.get(sym, 0))): sym
            for sym in syms
        }
        for fut in as_completed(futures):
            try:
                r = fut.result()
                if r.get("score", 0) >= min_score:
                    results.append(r)
            except Exception:
                continue
    results.sort(key=lambda r: r.get("score", 0), reverse=True)
    return results[:max_picks]


# ---------------------------------------------------------------------------
# Trade plan + helpers
# ---------------------------------------------------------------------------
def _build_plan(df: pd.DataFrame, side: str) -> dict:
    """1.2 ATR stop, 2.0 ATR TP1, 3.5 ATR TP2 (matches existing modules)."""
    if df is None or len(df) < 20:
        return _empty_plan()
    try:
        last = df.iloc[-1]
        entry = float(last["close"])
        atr = float(last.get("atr") or 0)
        if entry <= 0 or atr <= 0:
            return _empty_plan()
        if side == "LONG":
            stop = entry - 1.2 * atr
            tp1 = entry + 2.0 * atr
            tp2 = entry + 3.5 * atr
        else:
            stop = entry + 1.2 * atr
            tp1 = entry - 2.0 * atr
            tp2 = entry - 3.5 * atr
        risk = abs(entry - stop)
        if risk <= 0:
            return _empty_plan()
        rr = abs(tp1 - entry) / risk
        return {
            "side": side,
            "entry": float(entry),
            "stop": float(stop),
            "tp1": float(tp1),
            "tp2": float(tp2),
            "rr": round(float(rr), 2),
            "valid": rr >= 1.5,
        }
    except Exception:
        return _empty_plan()


def _empty(symbol: str) -> dict:
    return {"symbol": symbol, "side": "NEUTRAL", "score": 0.0,
            "tier": "LOW", "lanes_fired": {}, "active_lanes": [],
            "reasons": [], "trade_plan": _empty_plan(),
            "price_now": 0.0, "pct_24h": 0.0}


def _empty_plan() -> dict:
    return {"side": "LONG", "entry": 0.0, "stop": 0.0, "tp1": 0.0,
            "tp2": 0.0, "rr": 0.0, "valid": False}


# Backward-compatible alias (some external code may still call this)
scan_experimental = scan_unified
