"""Experimental intraday signals from GitHub/research pass (2026-06).

Two net-new signals — neither overlaps with what's already in the system.
Both target 15m/1h reversal/fade plays.

  1. VWAP Z-Score Fade — counter-trend mean-reversion when price is
     2+ standard deviations from session VWAP. Backed by NinjaTrader
     z-score research + institutional fair-value microstructure.
     Different from anchored-VWAP-RECLAIM (which is continuation) —
     this is FADE.

  2. Long-Exhaustion Liquidation Reversal — fires after a 4%+ drop in
     3 bars where Open Interest also FELL 5%+ AND volume spiked 3×
     average AND current bar shows absorption (small body + close in
     upper 40% of range). The OI-falling part is critical: it means
     LONGS are being deleveraged, NOT new shorts entering. The bottom
     signature = exhaustion of forced selling. From CryptoCred's
     futures-indicators guide + XT Exchange liquidation-cascade
     microstructure analysis.

Honest scope:
- Both target 15m/1h timeframes.
- VWAP-z hit rate ~55-60% with regime filter (NinjaTrader research).
- Liquidation-reversal hit rate ~60-65% (anecdotal, not net-of-cost
  backtested publicly — be cautious sizing).
- These are EXPERIMENTAL until we have local backtest n>=20 fires
  per signal.

Output shape matches what Paper Trader's openable cards expect:
{symbol, side, score, entry, stop, tp1, tp2, rr, reasons[], lane}
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

import binance_client
import indicators

try:
    import derivatives_velocity  # for OI history fetch
except Exception:
    derivatives_velocity = None


# ---------------------------------------------------------------------------
# SIGNAL 1 — VWAP Z-Score Fade
# ---------------------------------------------------------------------------
def vwap_zscore_fade(df: pd.DataFrame,
                    z_window: int = 20,
                    long_z: float = -2.0,
                    short_z: float = 2.0,
                    rsi_long_max: float = 30,
                    rsi_short_min: float = 70) -> dict:
    """Counter-trend fade when price is ≥2σ from rolling VWAP.

    Required df columns: open, high, low, close, volume, rsi.
    Uses session-anchored VWAP recomputed within df (no carry-over).

    Returns dict with score (0-100), side, z, vwap, distance_pct, reasons.
    """
    if df is None or len(df) < max(z_window, 50):
        return _empty("vwap_zscore")

    try:
        typical = (df["high"] + df["low"] + df["close"]) / 3.0
        vp = typical * df["volume"]
        vwap = vp.cumsum() / df["volume"].cumsum().replace(0, np.nan)
        # Rolling stdev of (close - VWAP) — proxy for fair-value spread
        spread = df["close"] - vwap
        roll_std = spread.rolling(z_window, min_periods=z_window // 2).std()
        z = (df["close"] - vwap) / roll_std.replace(0, np.nan)
        last_z = float(z.iloc[-1]) if not np.isnan(z.iloc[-1]) else 0.0
        last_close = float(df["close"].iloc[-1])
        last_vwap = float(vwap.iloc[-1]) if not np.isnan(vwap.iloc[-1]) else last_close
        last_rsi = float(df["rsi"].iloc[-1]) if "rsi" in df.columns else 50.0
    except Exception:
        return _empty("vwap_zscore")

    score = 0.0
    side = "NEUTRAL"
    reasons: list[str] = []
    if last_z <= long_z and last_rsi <= rsi_long_max:
        # LONG fade: price 2σ below VWAP + oversold
        side = "LONG"
        # Map z-extremity (more negative = stronger) to 60-100 score
        z_mag = min(abs(last_z), 3.5)
        score = 60 + (z_mag - 2.0) * 30  # z=-2 → 60, z=-3.5 → 105 (capped)
        score = float(np.clip(score, 60, 100))
        reasons.append(f"z={last_z:.2f}σ below VWAP {last_vwap:.4g}")
        reasons.append(f"RSI {last_rsi:.0f} (oversold)")
    elif last_z >= short_z and last_rsi >= rsi_short_min:
        side = "SHORT"
        z_mag = min(abs(last_z), 3.5)
        score = 60 + (z_mag - 2.0) * 30
        score = float(np.clip(score, 60, 100))
        reasons.append(f"z=+{last_z:.2f}σ above VWAP {last_vwap:.4g}")
        reasons.append(f"RSI {last_rsi:.0f} (overbought)")

    return {
        "lane": "vwap_zscore",
        "side": side,
        "score": round(score, 1),
        "z": round(last_z, 2),
        "vwap": float(last_vwap),
        "distance_pct": round(
            (last_close - last_vwap) / last_vwap * 100 if last_vwap > 0 else 0, 2),
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# SIGNAL 2 — Long-Exhaustion Liquidation Reversal
# ---------------------------------------------------------------------------
def liquidation_reversal(df: pd.DataFrame,
                        oi_history: list | None = None,
                        ret_3bar_threshold: float = -0.04,
                        oi_delta_threshold: float = -0.05,
                        vol_spike_mult: float = 3.0,
                        body_pct_max: float = 0.40,
                        close_position_min: float = 0.60) -> dict:
    """Long capitulation completion — fires after a sharp drop where OI
    is ALSO falling (longs deleveraging, not shorts entering), volume
    spikes, and the current bar shows absorption (small body + close
    in upper portion of range).

    oi_history: list of (timestamp, open_interest_value) for the same
    symbol. If None or too short, the OI gate is SKIPPED and the
    signal scores conservatively (max 70 instead of 100).
    """
    if df is None or len(df) < 25:
        return _empty("liquidation_reversal")
    try:
        recent = df.tail(20)
        last = df.iloc[-1]
        # Need at least 4 bars to compute ret_3bar
        if len(recent) < 4:
            return _empty("liquidation_reversal")
        ret_3bar = (
            float(last["close"]) / float(df["close"].iloc[-4]) - 1.0)
        body = abs(float(last["close"]) - float(last["open"]))
        bar_range = float(last["high"]) - float(last["low"])
        body_pct = (body / bar_range) if bar_range > 0 else 1.0
        close_position = (
            (float(last["close"]) - float(last["low"])) / bar_range
            if bar_range > 0 else 0.5)
        vol_avg = float(recent["volume"].mean()) or 1.0
        vol_ratio = float(last["volume"]) / vol_avg
    except Exception:
        return _empty("liquidation_reversal")

    # Gate 1: meaningful drop in last 3 bars
    if ret_3bar > ret_3bar_threshold:
        return _empty("liquidation_reversal")

    # Gate 2: absorption candle (small body + close in upper part)
    if body_pct > body_pct_max:
        return _empty("liquidation_reversal")
    if close_position < close_position_min:
        return _empty("liquidation_reversal")

    # Gate 3: volume spike
    if vol_ratio < vol_spike_mult:
        return _empty("liquidation_reversal")

    # Gate 4: OI also falling (longs deleveraging, not shorts entering)
    oi_delta = None
    oi_confirmed = False
    if oi_history and len(oi_history) >= 4:
        try:
            recent_oi = [v for _, v in oi_history[-4:]]
            if recent_oi[0] > 0:
                oi_delta = (recent_oi[-1] - recent_oi[0]) / recent_oi[0]
                oi_confirmed = (oi_delta <= oi_delta_threshold)
        except Exception:
            oi_delta = None

    # Score: base 60 for meeting 3 of 4 gates, +30 if OI confirmed
    score = 60.0
    reasons = [
        f"3-bar drop {ret_3bar * 100:+.1f}% (deep)",
        f"absorption candle (body {body_pct * 100:.0f}% of range, "
        f"close in upper {close_position * 100:.0f}%)",
        f"vol spike {vol_ratio:.1f}× avg",
    ]
    if oi_confirmed:
        score = 90.0
        reasons.append(f"OI {oi_delta * 100:+.1f}% (longs deleveraging)")
    elif oi_delta is not None:
        # OI didn't drop enough — DOWNGRADE because shorts may be
        # entering, weakening the bounce thesis
        score = 50.0
        reasons.append(
            f"OI {oi_delta * 100:+.1f}% (longs not capitulating — caution)")

    return {
        "lane": "liquidation_reversal",
        "side": "LONG",  # this signal is bullish-bias only
        "score": round(score, 1),
        "ret_3bar_pct": round(ret_3bar * 100, 2),
        "vol_ratio": round(vol_ratio, 2),
        "body_pct": round(body_pct * 100, 1),
        "close_position_pct": round(close_position * 100, 1),
        "oi_delta_pct": round(oi_delta * 100, 2) if oi_delta is not None else None,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Combined scan + trade plan builder
# ---------------------------------------------------------------------------
def score_one(symbol: str, interval: str = "1h") -> dict:
    """Run both experimental signals on one symbol/interval.

    Returns the STRONGER of the two if either fires (score >= 60),
    otherwise the NEUTRAL pair so the caller can skip.
    """
    try:
        df = binance_client.get_klines(symbol, interval, limit=200)
        df = indicators.enrich(df)
    except Exception:
        return _empty("none")

    # VWAP z-score fade
    vz = vwap_zscore_fade(df)

    # Liquidation reversal needs OI history
    oi_hist = None
    if derivatives_velocity is not None:
        try:
            oi_hist = derivatives_velocity._oi_history(
                symbol, period="1h", limit=12)
        except Exception:
            oi_hist = None
    liq = liquidation_reversal(df, oi_history=oi_hist)

    # Pick whichever scored higher (and is at least minimal-fire)
    best = max([vz, liq], key=lambda r: r.get("score", 0))
    if best.get("score", 0) < 60:
        return _empty("none")

    # Attach trade plan
    plan = _build_plan(df, best.get("side", "LONG"))
    out = dict(best)
    out["symbol"] = symbol
    out["trade_plan"] = plan
    try:
        out["price_now"] = float(df["close"].iloc[-1])
    except Exception:
        out["price_now"] = 0.0
    return out


def scan_experimental(scan_n: int = 80,
                     interval: str = "1h",
                     min_score: float = 70.0,
                     max_picks: int = 12,
                     max_workers: int = 6) -> list[dict]:
    """Scan top N coins for experimental signal fires.

    Returns list[dict] sorted high-to-low by score, capped at max_picks.
    Only picks at min_score+ are included.
    """
    try:
        top = binance_client.get_top_symbols(scan_n)
        syms = top["symbol"].tolist()
    except Exception:
        return []

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(score_one, sym, interval): sym for sym in syms
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
# Helpers
# ---------------------------------------------------------------------------
def _build_plan(df: pd.DataFrame, side: str) -> dict:
    """Conservative trade plan: 1.2 ATR stop, 2.0 ATR TP1, 3.5 ATR TP2."""
    if df is None or len(df) < 20:
        return _empty_plan()
    try:
        last = df.iloc[-1]
        entry = float(last["close"])
        atr_val = float(last.get("atr") or 0)
        if atr_val <= 0 or entry <= 0:
            return _empty_plan()
        if side == "LONG":
            stop = entry - 1.2 * atr_val
            tp1 = entry + 2.0 * atr_val
            tp2 = entry + 3.5 * atr_val
        else:  # SHORT
            stop = entry + 1.2 * atr_val
            tp1 = entry - 2.0 * atr_val
            tp2 = entry - 3.5 * atr_val
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


def _empty(lane: str) -> dict:
    return {"lane": lane, "side": "NEUTRAL", "score": 0.0, "reasons": []}


def _empty_plan() -> dict:
    return {"side": "LONG", "entry": 0.0, "stop": 0.0, "tp1": 0.0,
            "tp2": 0.0, "rr": 0.0, "valid": False}
