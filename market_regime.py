"""Market regime detection — BULL / BEAR / TRANSITION / CHOP.

Critical insight motivating this module: signal edges are regime-dependent.
"Buy the dip" works in bull markets, fails brutally in bear markets.
"Fade the rally" works in bear markets, fails in bull markets. A signal
that scored 38% LONG win in the last 6 weeks of bearish chop may score
60%+ LONG win in the next 6 weeks of bullish trend — same signal, same
math, opposite outcome.

So we DETECT the regime and let it tilt signal scoring, instead of
freezing one period's conclusion into the code.

This module is PURE — takes Binance klines + optional BTC.D regime input,
returns a regime classification. No state, no API calls beyond the
existing binance_client. Designed to be called every few minutes (cached).

Inputs used (all free, all already wired into the system):
  - BTC daily klines (250d) → 50d/200d EMA, distance from each
  - BTC weekly klines (52w) → 50w SMA position, weekly momentum
  - BTC.D from btc_dominance module → rising/falling (alt regime)
  - Market breadth (% of top 50 above 50d MA) → broad participation
  - Volatility regime (recent ATR vs longer ATR) → calm vs frantic

Output is a regime dict with:
  - regime: "BULL" | "BEAR" | "TRANSITION" | "CHOP"
  - confidence: 0-100 — how sure we are
  - long_bias: 0-100 — recommended LONG-side weighting
  - short_bias: 0-100 — recommended SHORT-side weighting
  - components: breakdown of each input score
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

import binance_client


# Cache for the universe-level breadth calc (expensive — top 50 klines fetch)
_BREADTH_CACHE: dict = {"ts": 0.0, "value": None}
_BREADTH_TTL = 1800  # 30 min — breadth changes slowly


# ---------------------------------------------------------------------------
# BTC trend components
# ---------------------------------------------------------------------------

def _btc_daily_trend(btc_daily: pd.DataFrame) -> dict:
    """Score BTC's position vs daily 50/200 EMAs.

    Classic golden-cross / death-cross + distance metrics:
      - close > both = strong bull
      - close > 50 but < 200 = mid-cycle (transition up)
      - close < both, 50 < 200 = strong bear
      - close < 50, > 200 = pullback in bull
      - close < 200, > 50 = bear-market rally
    """
    if len(btc_daily) < 200:
        return {"score": 50, "label": "INSUFFICIENT_DATA"}
    close = btc_daily["close"]
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()
    c = float(close.iloc[-1])
    e50 = float(ema50.iloc[-1])
    e200 = float(ema200.iloc[-1])

    # Distances as fractions of price (scale-invariant)
    d50 = (c - e50) / e50 if e50 > 0 else 0.0
    d200 = (c - e200) / e200 if e200 > 0 else 0.0
    # 50 vs 200 cross-state
    golden = e50 > e200
    # 50d EMA slope over 14 days
    slope_50 = (e50 - float(ema50.iloc[-15])) / float(ema50.iloc[-15]) \
        if len(ema50) >= 15 and ema50.iloc[-15] > 0 else 0.0

    if c > e50 and c > e200 and golden:
        score = 75 + min(20, d50 * 200)
        label = "STRONG_BULL"
    elif c > e50 and c > e200:
        score = 65
        label = "BULL"
    elif c > e200 and c < e50:
        score = 55
        label = "BULL_PULLBACK"
    elif c < e200 and c > e50:
        score = 45
        label = "BEAR_RALLY"
    elif c < e50 and c < e200 and not golden:
        score = 20 - min(15, abs(d50) * 200)
        label = "STRONG_BEAR"
    elif c < e50 and c < e200:
        score = 30
        label = "BEAR"
    else:
        score = 50
        label = "TRANSITION"
    score = float(np.clip(score, 0, 100))

    return {"score": round(score, 1), "label": label,
            "btc_close": c, "ema50": e50, "ema200": e200,
            "dist_50_pct": round(d50 * 100, 2),
            "dist_200_pct": round(d200 * 100, 2),
            "ema50_slope_14d_pct": round(slope_50 * 100, 2)}


def _btc_weekly_trend(btc_weekly: pd.DataFrame) -> dict:
    """Weekly higher-timeframe trend. The 50w MA position is one of the
    cleanest long-term cycle indicators for BTC."""
    if len(btc_weekly) < 50:
        return {"score": 50, "label": "INSUFFICIENT_DATA"}
    close = btc_weekly["close"]
    sma50w = close.rolling(50).mean()
    c = float(close.iloc[-1])
    sma = float(sma50w.iloc[-1])
    if sma <= 0:
        return {"score": 50, "label": "UNKNOWN"}
    dist_pct = (c - sma) / sma * 100
    # 8-week slope
    slope_pct = (float(sma50w.iloc[-1]) - float(sma50w.iloc[-9])) / float(sma50w.iloc[-9]) * 100 \
        if len(sma50w) >= 9 and sma50w.iloc[-9] > 0 else 0.0

    if c > sma and slope_pct > 0:
        score = 70 + min(20, dist_pct / 2)
        label = "WEEKLY_BULL"
    elif c > sma and slope_pct <= 0:
        score = 55
        label = "WEEKLY_NEUTRAL_BULL"
    elif c < sma and slope_pct < 0:
        score = 30 - min(15, abs(dist_pct) / 2)
        label = "WEEKLY_BEAR"
    elif c < sma and slope_pct >= 0:
        score = 45
        label = "WEEKLY_NEUTRAL_BEAR"
    else:
        score = 50
        label = "WEEKLY_UNCLEAR"
    return {"score": round(float(np.clip(score, 0, 100)), 1), "label": label,
            "dist_50w_pct": round(dist_pct, 2),
            "slope_50w_8w_pct": round(slope_pct, 2)}


# ---------------------------------------------------------------------------
# Market breadth — % of top coins above their 50d MA
# ---------------------------------------------------------------------------

def _market_breadth(top_symbols: list[str], force_refresh: bool = False) -> dict:
    """% of top-N coins above their 50d MA.

    When >60% of top alts are above their 50d MA, broad participation
    is bullish — even a recent dip is unlikely to mean BEAR regime.
    When <40%, broad bear pressure dominates regardless of where BTC
    sits.

    Cached at 30-min TTL because the full scan is ~20+ API calls.
    """
    now = time.time()
    if (not force_refresh and _BREADTH_CACHE["value"] is not None
            and (now - _BREADTH_CACHE["ts"]) < _BREADTH_TTL):
        return _BREADTH_CACHE["value"]

    if not top_symbols:
        return {"score": 50, "above_count": 0, "total": 0,
                "pct_above": 50.0, "label": "NO_DATA"}

    def _one(sym):
        try:
            df = binance_client.get_klines(sym, "1d", limit=80)
            if len(df) < 50:
                return None
            sma = df["close"].rolling(50).mean().iloc[-1]
            return bool(df["close"].iloc[-1] > sma)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_one, top_symbols))

    valid = [r for r in results if r is not None]
    total = len(valid)
    above = sum(1 for r in valid if r)
    pct = (above / total * 100) if total > 0 else 50.0

    if pct >= 70:
        score, label = 85, "BREADTH_STRONG_BULL"
    elif pct >= 55:
        score, label = 65, "BREADTH_BULL"
    elif pct >= 45:
        score, label = 50, "BREADTH_NEUTRAL"
    elif pct >= 30:
        score, label = 35, "BREADTH_BEAR"
    else:
        score, label = 15, "BREADTH_STRONG_BEAR"

    out = {"score": float(score), "above_count": above, "total": total,
           "pct_above": round(pct, 1), "label": label}
    _BREADTH_CACHE.update(ts=now, value=out)
    return out


# ---------------------------------------------------------------------------
# Volatility regime
# ---------------------------------------------------------------------------

def _volatility_regime(btc_daily: pd.DataFrame) -> dict:
    """Compare recent (14d) volatility to longer (60d) volatility.

    Compressed volatility = chop/coil; expanding = trending or panic.
    The interaction with price direction tells us BULL (expanding up)
    vs BEAR (expanding down) vs CHOP (compressed).
    """
    if len(btc_daily) < 60:
        return {"score": 50, "label": "UNKNOWN", "vol_ratio": 1.0}
    rets = btc_daily["close"].pct_change()
    recent_vol = float(rets.tail(14).std() or 0)
    long_vol = float(rets.tail(60).std() or 0)
    if long_vol <= 0:
        return {"score": 50, "label": "UNKNOWN", "vol_ratio": 1.0}
    ratio = recent_vol / long_vol

    # Recent direction
    p_now = float(btc_daily["close"].iloc[-1])
    p_14 = float(btc_daily["close"].iloc[-15]) if len(btc_daily) >= 15 else p_now
    direction = (p_now / p_14 - 1.0) if p_14 > 0 else 0.0

    if ratio > 1.5 and direction > 0.02:
        label = "EXPANDING_UP"  # bullish breakout
        score = 75
    elif ratio > 1.5 and direction < -0.02:
        label = "EXPANDING_DOWN"  # bearish breakdown
        score = 25
    elif ratio < 0.7:
        label = "COMPRESSED"  # chop / coil
        score = 50
    elif ratio > 1.2:
        label = "ELEVATED"
        score = 55 if direction > 0 else 45
    else:
        label = "NORMAL"
        score = 50 + min(15, max(-15, direction * 200))

    return {"score": round(float(np.clip(score, 0, 100)), 1), "label": label,
            "vol_ratio": round(ratio, 2),
            "btc_14d_change_pct": round(direction * 100, 2)}


# ---------------------------------------------------------------------------
# Composite regime
# ---------------------------------------------------------------------------

# Weights — sum to 1.0. Daily trend dominates because it's the closest
# proxy for "is BTC trending now?". Weekly trend gives long-horizon context.
# Breadth + volatility are confirming layers.
_WEIGHTS = {
    "daily":   0.35,
    "weekly":  0.20,
    "breadth": 0.25,
    "vol":     0.20,
}


def detect_regime(top_symbols: list[str] | None = None,
                  btc_d_pct: float | None = None,
                  force_breadth_refresh: bool = False) -> dict:
    """Detect the current market regime and return bias scores.

    Args:
        top_symbols: list of symbols for the breadth calc. If None,
            uses binance_client.get_top_symbols(50) result.
        btc_d_pct: optional BTC dominance %, used as a sanity check.
        force_breadth_refresh: bypass the breadth cache.

    Returns dict:
        {
          "regime": "BULL" | "BEAR" | "TRANSITION" | "CHOP",
          "confidence": 0-100,
          "long_bias": 0-100,
          "short_bias": 0-100,
          "components": {...},
          "summary": str,
        }
    """
    # Fetch BTC data once
    try:
        btc_daily = binance_client.get_klines("BTCUSDT", "1d", limit=250)
        btc_weekly = binance_client.get_klines("BTCUSDT", "1w", limit=100)
    except Exception as exc:
        return _empty_regime(f"BTC data fetch failed: {exc}")

    daily = _btc_daily_trend(btc_daily)
    weekly = _btc_weekly_trend(btc_weekly)
    vol = _volatility_regime(btc_daily)

    # Resolve top symbols for breadth
    if top_symbols is None:
        try:
            top_df = binance_client.get_top_symbols(50)
            top_symbols = top_df["symbol"].tolist()[:50]
        except Exception:
            top_symbols = []
    breadth = _market_breadth(top_symbols, force_refresh=force_breadth_refresh)

    # Weighted composite — 0 to 100, higher = more bullish regime
    composite = (
        _WEIGHTS["daily"] * daily["score"]
        + _WEIGHTS["weekly"] * weekly["score"]
        + _WEIGHTS["breadth"] * breadth["score"]
        + _WEIGHTS["vol"] * vol["score"]
    )
    composite = float(np.clip(composite, 0, 100))

    # BTC.D sanity (when supplied) — rising BTC.D in a "BULL" reading
    # should temper the call.
    if btc_d_pct is not None and btc_d_pct > 60 and composite > 65:
        # BTC dominance high — likely BTC-only rally, not full alt bull
        composite -= 5

    # Classify
    if composite >= 65:
        regime = "BULL"
        confidence = min(100, (composite - 50) * 2)
        long_bias = composite
        short_bias = max(0, 100 - composite)
    elif composite <= 35:
        regime = "BEAR"
        confidence = min(100, (50 - composite) * 2)
        short_bias = 100 - composite
        long_bias = composite
    elif 45 <= composite <= 55:
        regime = "CHOP"
        confidence = 40
        long_bias = 50
        short_bias = 50
    else:
        regime = "TRANSITION"
        confidence = 30
        long_bias = composite
        short_bias = 100 - composite

    summary_bits = [
        f"BTC daily: {daily['label']} ({daily['score']:.0f})",
        f"weekly: {weekly['label']} ({weekly['score']:.0f})",
        f"breadth: {breadth['pct_above']:.0f}% above 50d ({breadth['score']:.0f})",
        f"vol: {vol['label']} ({vol['score']:.0f})",
    ]

    return {
        "regime": regime,
        "confidence": round(confidence, 1),
        "composite": round(composite, 1),
        "long_bias": round(long_bias, 1),
        "short_bias": round(short_bias, 1),
        "components": {
            "daily": daily,
            "weekly": weekly,
            "breadth": breadth,
            "volatility": vol,
        },
        "summary": " · ".join(summary_bits),
    }


def _empty_regime(reason: str) -> dict:
    return {
        "regime": "UNKNOWN",
        "confidence": 0.0,
        "composite": 50.0,
        "long_bias": 50.0,
        "short_bias": 50.0,
        "components": {},
        "summary": reason,
    }


# ---------------------------------------------------------------------------
# Convenience: regime-aware score adjustment
# ---------------------------------------------------------------------------

def regime_tilt(score: float, side: str, regime_info: dict,
                max_tilt: float = 15.0) -> float:
    """Tilt a 0-100 directional signal score by the current regime.

    Scoring convention used throughout the system:
        score = 0   → strongest SHORT
        score = 50  → neutral
        score = 100 → strongest LONG

    So in a BULL regime we push the score TOWARDS 100 (boosting longs,
    weakening shorts). In a BEAR regime we push TOWARDS 0 (boosting
    shorts, weakening longs). `side` is accepted for API symmetry but
    not used for direction — the regime alone determines which way
    we tilt.

    The motivation: a LONG signal that backtested at 38% win rate in
    a bear sample may be a perfectly reasonable signal — it just needs
    to fire ONLY when the regime is friendly. Same with SHORT signals
    that backtested well in a bear sample needing the regime to stay
    bearish to keep working.

    `max_tilt` is the maximum +/- adjustment. 15 is a reasonable default:
    enough to push a borderline LONG fire (62) into solid (77) during a
    BULL regime, but not enough to single-handedly flip the sign.
    """
    if not regime_info or regime_info.get("regime") == "UNKNOWN":
        return score
    composite = float(regime_info.get("composite") or 50)
    confidence = float(regime_info.get("confidence") or 0) / 100.0

    # Tilt is signed: positive in bull regimes (push toward LONG),
    # negative in bear regimes (push toward SHORT). Magnitude scales
    # with regime confidence so a low-conviction read doesn't move
    # signals much.
    tilt = (composite - 50.0) / 50.0 * max_tilt * confidence
    return float(np.clip(score + tilt, 0, 100))
