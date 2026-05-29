"""Early-momentum scoring — leading indicators for crypto futures.

The existing multi-timeframe scoring is a *lagging* filter by design: it
waits for 15m + 1h + 4h alignment before "Very Strong" picks appear. That
keeps false positives low but pays a lag tax — by the time three TFs agree,
the move has often run.

This module computes a parallel 0-100 "early momentum" score from four
leading indicators that fire BEFORE confirmed multi-TF breakouts:

1. CVD divergence (30%) — taker-buy volume rising while price is flat/down.
   Accumulation detection from kline-native data (taker_base column).
2. TTM Squeeze fire (25%) — Bollinger Bands inside Keltner Channels (a
   volatility coil), then the first bar BB exits KC. Pre-breakout trigger.
3. ROC-of-ROC (15%) — second derivative of price (acceleration). Catches
   inflection points before velocity peaks. Heavily smoothed/z-scored.
4. SMC liquidity sweep (15%) — stop-hunt wick beyond a recent swing
   high/low that closes back inside. Canonical reversal trigger.

A Hurst-style regime gate (×0.5 / ×1.0 / ×1.0 multiplier) caps the
composite during choppy regimes where breakout signals whipsaw.

Critical: this module is PURE — no state, no API mutations, no side
effects. It is NOT wired into live_broker.py or auto_trade_gate() during
the MVP phase. The score is *displayed* on the picks board and *available*
to the paper trader for A/B testing only. Promotion into the live premium
gate requires explicit user signoff after paper data validates it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Component 1: Cumulative Volume Delta (CVD) divergence
# ---------------------------------------------------------------------------

def _cvd_divergence(df: pd.DataFrame, window: int = 30) -> dict:
    """Detect price/CVD divergence — accumulation or distribution before
    the breakout.

    CVD = cumulative (taker_buy_vol - taker_sell_vol). Since Binance gives
    us taker_base (the BUY side of taker volume), sell-side taker volume
    is (volume - taker_base). Delta per candle is therefore:
        delta = taker_base - (volume - taker_base) = 2 * taker_base - volume

    Bullish divergence: price flat or down over the window, CVD rising
    (aggressive buyers accumulating despite no price movement). Score
    maxes at +100 when price drops while CVD climbs hard.

    Bearish divergence: mirror — price flat or up, CVD dropping.
    """
    if "taker_base" not in df.columns or len(df) < window + 5:
        return {"score": 50, "side": "NEUTRAL", "detail": "CVD — insufficient data"}

    # CVD per bar — uses kline-native taker_base, no extra API calls.
    delta = 2.0 * df["taker_base"] - df["volume"]
    cvd = delta.cumsum()

    # Window-over-window change.
    price_chg = (df["close"].iloc[-1] / df["close"].iloc[-window] - 1.0)
    cvd_chg = cvd.iloc[-1] - cvd.iloc[-window]

    # Normalise CVD change to a 0-1 score using its own recent volatility,
    # so it travels on the same scale across coins.
    cvd_std = float(delta.rolling(window).std().iloc[-1] or 0)
    if cvd_std <= 0:
        return {"score": 50, "side": "NEUTRAL", "detail": "CVD — flat delta"}
    cvd_z = float(cvd_chg / (cvd_std * np.sqrt(window)))

    # Detect divergence by combining signs.
    if price_chg <= -0.005 and cvd_z >= 0.5:
        # Price down, CVD up — bullish accumulation
        strength = min(1.0, abs(cvd_z) / 2.5) * min(1.0, abs(price_chg) / 0.03)
        score = 50 + strength * 50
        return {"score": round(score), "side": "LONG",
                "detail": f"Bullish CVD divergence "
                          f"(price {price_chg * 100:+.1f}% · CVD z+{cvd_z:.1f})"}
    if price_chg >= 0.005 and cvd_z <= -0.5:
        # Price up, CVD down — bearish distribution
        strength = min(1.0, abs(cvd_z) / 2.5) * min(1.0, abs(price_chg) / 0.03)
        score = 50 - strength * 50
        return {"score": round(score), "side": "SHORT",
                "detail": f"Bearish CVD divergence "
                          f"(price {price_chg * 100:+.1f}% · CVD z{cvd_z:.1f})"}
    # No clear divergence — confirmation only (CVD aligns with price)
    if price_chg > 0 and cvd_z > 0.3:
        return {"score": 60, "side": "LONG",
                "detail": f"CVD confirms uptrend (z+{cvd_z:.1f})"}
    if price_chg < 0 and cvd_z < -0.3:
        return {"score": 40, "side": "SHORT",
                "detail": f"CVD confirms downtrend (z{cvd_z:.1f})"}
    return {"score": 50, "side": "NEUTRAL",
            "detail": f"CVD neutral (z{cvd_z:+.1f}, price {price_chg * 100:+.1f}%)"}


# ---------------------------------------------------------------------------
# Component 2: TTM Squeeze fire
# ---------------------------------------------------------------------------

def _ttm_squeeze(df: pd.DataFrame, period: int = 20,
                 bb_std: float = 2.0, kc_mult: float = 1.5) -> dict:
    """TTM Squeeze: detect a volatility coil followed by a breakout fire.

    Squeeze ON = Bollinger Bands sit INSIDE Keltner Channels (volatility
    compressed below the channel's normal range). The longer the squeeze,
    the more energy stored.

    Fire = the first bar where BB exits KC (squeeze releases). Direction
    is taken from the slope of (close - midline).

    Returns max score when squeeze fires THIS bar with strong directional
    bias from price vs midline.
    """
    if len(df) < period + 25:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Squeeze — insufficient data"}

    close = df["close"]
    high = df["high"]
    low = df["low"]

    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    bb_upper = sma + bb_std * std
    bb_lower = sma - bb_std * std

    # Keltner uses EMA + ATR (we recompute ATR locally to keep this module
    # pure — doesn't matter if caller already enriched the DF).
    ema = close.ewm(span=period, adjust=False).mean()
    tr = pd.concat([high - low,
                    (high - close.shift(1)).abs(),
                    (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr_ = tr.ewm(alpha=1 / period, adjust=False).mean()
    kc_upper = ema + kc_mult * atr_
    kc_lower = ema - kc_mult * atr_

    squeeze_on = (bb_lower > kc_lower) & (bb_upper < kc_upper)
    if len(squeeze_on) < 3:
        return {"score": 50, "side": "NEUTRAL", "detail": "Squeeze — too few bars"}

    fire_now = bool(squeeze_on.iloc[-2] and not squeeze_on.iloc[-1])
    in_squeeze = bool(squeeze_on.iloc[-1])
    bars_in_squeeze = int(squeeze_on.iloc[-15:].sum())

    # Direction from linreg slope of (close - midline) over the last 8 bars.
    diff = (close - sma).tail(8).reset_index(drop=True)
    if len(diff) >= 3 and not diff.isna().all():
        x = np.arange(len(diff))
        slope = float(np.polyfit(x, diff.fillna(0), 1)[0])
    else:
        slope = 0.0

    if fire_now:
        # Strong signal — coil released this bar
        side = "LONG" if slope > 0 else ("SHORT" if slope < 0 else "NEUTRAL")
        if side == "NEUTRAL":
            return {"score": 60, "side": "NEUTRAL",
                    "detail": f"Squeeze FIRED ({bars_in_squeeze} bars coiled) — "
                              "direction unclear"}
        strength = min(1.0, bars_in_squeeze / 12)  # longer coil = bigger signal
        score = 60 + strength * 40 if side == "LONG" else 40 - strength * 40
        return {"score": round(score), "side": side,
                "detail": f"Squeeze FIRED {side} ({bars_in_squeeze} bars "
                          f"coiled, slope {slope:+.4f})"}
    if in_squeeze:
        # Building energy but no fire yet — slight bias from slope
        return {"score": 55 if slope > 0 else (45 if slope < 0 else 50),
                "side": "NEUTRAL",
                "detail": f"Squeeze loading ({bars_in_squeeze} bars) — "
                          "no fire yet"}
    return {"score": 50, "side": "NEUTRAL",
            "detail": "No squeeze — normal volatility"}


# ---------------------------------------------------------------------------
# Component 3: ROC-of-ROC (price acceleration)
# ---------------------------------------------------------------------------

def _roc_of_roc(df: pd.DataFrame, roc_n: int = 12,
                accel_n: int = 6, z_window: int = 100) -> dict:
    """Second derivative of price — catches acceleration inflection points
    BEFORE velocity peaks.

    Heavy smoothing + z-score is mandatory: raw 2nd derivative is pure
    noise on crypto candles. The signal we want is:
        accel just crossed zero from below (transition from decel to
        accel) AND the z-score of accel is unusually high.
    """
    if len(df) < max(roc_n + accel_n + z_window, 50):
        return {"score": 50, "side": "NEUTRAL", "detail": "Accel — insufficient data"}

    close = df["close"]
    # Smooth price first so noise doesn't dominate
    smoothed = close.ewm(span=5, adjust=False).mean()
    roc1 = smoothed.pct_change(roc_n)
    # Smooth the inner ROC too — kills 2nd-derivative noise amplification
    roc1_smooth = roc1.ewm(span=accel_n, adjust=False).mean()
    accel = roc1_smooth.diff(accel_n)

    if accel.isna().all() or len(accel.dropna()) < z_window:
        return {"score": 50, "side": "NEUTRAL", "detail": "Accel — too few bars"}

    accel_mean = float(accel.rolling(z_window).mean().iloc[-1] or 0)
    accel_std = float(accel.rolling(z_window).std().iloc[-1] or 0)
    if accel_std <= 0:
        return {"score": 50, "side": "NEUTRAL", "detail": "Accel — no volatility"}
    accel_z = float((accel.iloc[-1] - accel_mean) / accel_std)

    # Detect zero-cross from below (decel → accel) over last 2 bars
    crossed_up = bool(accel.iloc[-2] <= 0 and accel.iloc[-1] > 0)
    crossed_down = bool(accel.iloc[-2] >= 0 and accel.iloc[-1] < 0)

    if crossed_up and accel_z >= 1.0:
        strength = min(1.0, accel_z / 2.5)
        score = 60 + strength * 40
        return {"score": round(score), "side": "LONG",
                "detail": f"Accel inflection UP (z+{accel_z:.1f}, just crossed 0)"}
    if crossed_down and accel_z <= -1.0:
        strength = min(1.0, abs(accel_z) / 2.5)
        score = 40 - strength * 40
        return {"score": round(score), "side": "SHORT",
                "detail": f"Accel inflection DOWN (z{accel_z:.1f}, just crossed 0)"}
    # No inflection — return slight bias from accel sign
    if accel_z >= 0.5:
        return {"score": 55, "side": "LONG",
                "detail": f"Accel positive (z+{accel_z:.1f})"}
    if accel_z <= -0.5:
        return {"score": 45, "side": "SHORT",
                "detail": f"Accel negative (z{accel_z:.1f})"}
    return {"score": 50, "side": "NEUTRAL",
            "detail": f"Accel flat (z{accel_z:+.1f})"}


# ---------------------------------------------------------------------------
# Component 5: Anchored VWAP reclaim
# ---------------------------------------------------------------------------

def _vwap_reclaim(df: pd.DataFrame, anchor_bars: int = 24,
                  vol_mult: float = 1.5) -> dict:
    """First reclaim of the rolling-anchor VWAP with volume confirmation.

    Anchored VWAP is the volume-weighted average price computed from a
    specific anchor point (session open, swing low, etc.). For automated
    use we approximate "session" with a rolling N-bar window (24 bars
    on 1h ≈ daily anchor). The signal we want is the FIRST bar where
    price reclaims the anchor VWAP from below — this is often the first
    objective sign that buyers regained control after a downtrend.

    Bearish mirror: first bar that loses VWAP from above with volume.

    Volume confirmation cuts noise — a reclaim on thin volume is just
    a chop bounce, not a regime change.
    """
    if len(df) < anchor_bars + 3 or "volume" not in df.columns:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "VWAP — insufficient data"}

    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = (typical * df["volume"]).rolling(anchor_bars).sum()
    vol_sum = df["volume"].rolling(anchor_bars).sum().replace(0, np.nan)
    vwap = pv / vol_sum

    if vwap.iloc[-1] != vwap.iloc[-1]:  # NaN check
        return {"score": 50, "side": "NEUTRAL",
                "detail": "VWAP — warmup not complete"}

    close = df["close"]
    last_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    last_vwap = float(vwap.iloc[-1])
    prev_vwap = float(vwap.iloc[-2])

    last_vol = float(df["volume"].iloc[-1])
    avg_vol = float(df["volume"].tail(20).mean() or 1)
    vol_ok = last_vol >= vol_mult * avg_vol

    # Bullish reclaim: prev close was below VWAP, current closes above
    reclaim_up = prev_close <= prev_vwap and last_close > last_vwap
    # Bearish loss: prev close was above VWAP, current closes below
    reclaim_down = prev_close >= prev_vwap and last_close < last_vwap

    if reclaim_up:
        # Strength based on the magnitude of the reclaim above VWAP
        reclaim_pct = (last_close - last_vwap) / last_vwap
        strength = min(1.0, reclaim_pct / 0.02)  # 2% above VWAP = max
        base_score = 65 + strength * 25
        if vol_ok:
            base_score += 10
        return {"score": round(min(100, base_score)), "side": "LONG",
                "detail": f"VWAP reclaim UP "
                          f"({reclaim_pct * 100:+.2f}% above, "
                          f"vol {last_vol / avg_vol:.1f}x"
                          f"{' ✓' if vol_ok else ' light'})"}
    if reclaim_down:
        reclaim_pct = (last_vwap - last_close) / last_vwap
        strength = min(1.0, reclaim_pct / 0.02)
        base_score = 35 - strength * 25
        if vol_ok:
            base_score -= 10
        return {"score": round(max(0, base_score)), "side": "SHORT",
                "detail": f"VWAP loss DOWN "
                          f"({reclaim_pct * 100:+.2f}% below, "
                          f"vol {last_vol / avg_vol:.1f}x"
                          f"{' ✓' if vol_ok else ' light'})"}
    # No reclaim event — slight directional bias from current position vs VWAP
    if last_close > last_vwap * 1.005:
        return {"score": 55, "side": "LONG",
                "detail": f"Above VWAP (+{(last_close / last_vwap - 1) * 100:.2f}%)"}
    if last_close < last_vwap * 0.995:
        return {"score": 45, "side": "SHORT",
                "detail": f"Below VWAP ({(last_close / last_vwap - 1) * 100:.2f}%)"}
    return {"score": 50, "side": "NEUTRAL",
            "detail": "Near VWAP — no reclaim event"}


# ---------------------------------------------------------------------------
# Component 6: N-candle continuation (the user's "3 positive candles" rule)
# ---------------------------------------------------------------------------

def _candle_continuation(df: pd.DataFrame, min_count: int = 3,
                         min_body_ratio: float = 0.50) -> dict:
    """Detect N+ consecutive same-direction candles with strong bodies.

    The classic visual cue traders use: when you see three green candles in
    a row with strong bodies (each one closing well above its open), the
    short-term path of least resistance is up. The mirror also holds —
    three red candles with strong bodies often precede 2–5 more bars in
    the same direction.

    Strong body = body / (high-low) > min_body_ratio. This filters out
    indecisive candles with long wicks that *look* directional but really
    are not.

    Score scaling:
      3 strong candles      → score ~70 (LONG) / ~30 (SHORT)
      4 strong candles      → ~78 / ~22
      5+ strong candles     → ~85 / ~15
    """
    if len(df) < min_count + 1:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Continuation — not enough bars"}

    # Walk backwards finding the run of same-direction candles
    closes = df["close"].to_numpy()
    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()

    bull_run = 0
    bear_run = 0
    body_ratios: list[float] = []
    for i in range(len(closes) - 1, max(-1, len(closes) - 10), -1):
        is_bull = closes[i] > opens[i]
        is_bear = closes[i] < opens[i]
        rng = highs[i] - lows[i]
        body = abs(closes[i] - opens[i])
        ratio = (body / rng) if rng > 0 else 0.0
        if is_bull and ratio >= min_body_ratio:
            if bear_run > 0:
                break
            bull_run += 1
            body_ratios.append(ratio)
        elif is_bear and ratio >= min_body_ratio:
            if bull_run > 0:
                break
            bear_run += 1
            body_ratios.append(ratio)
        else:
            break

    avg_body = float(np.mean(body_ratios)) if body_ratios else 0.0
    if bull_run >= min_count:
        # Score scales with run length + body strength
        run_strength = min(1.0, (bull_run - min_count + 1) / 4)
        body_boost = (avg_body - min_body_ratio) / (1 - min_body_ratio) \
            if avg_body > min_body_ratio else 0
        score = 65 + 20 * run_strength + 10 * body_boost
        return {"score": round(min(100, score)), "side": "LONG",
                "detail": (f"{bull_run} strong bullish candles in a row "
                           f"(avg body {avg_body * 100:.0f}% of range)")}
    if bear_run >= min_count:
        run_strength = min(1.0, (bear_run - min_count + 1) / 4)
        body_boost = (avg_body - min_body_ratio) / (1 - min_body_ratio) \
            if avg_body > min_body_ratio else 0
        score = 35 - 20 * run_strength - 10 * body_boost
        return {"score": round(max(0, score)), "side": "SHORT",
                "detail": (f"{bear_run} strong bearish candles in a row "
                           f"(avg body {avg_body * 100:.0f}% of range)")}
    return {"score": 50, "side": "NEUTRAL",
            "detail": (f"No 3+ same-direction run "
                       f"(bull_run={bull_run}, bear_run={bear_run})")}


# ---------------------------------------------------------------------------
# Component 4: SMC liquidity sweep
# ---------------------------------------------------------------------------

def _smc_liquidity_sweep(df: pd.DataFrame, lookback: int = 30,
                         wick_threshold: float = 0.001) -> dict:
    """Detect a stop-hunt wick that swept liquidity beyond a recent swing
    high/low and closed back inside (reversal trigger).

    Bullish sweep: low of current bar broke below the recent swing low
    but close reclaimed above it — shorts got run, longs stepped in.

    Bearish sweep: high of current bar broke above the recent swing high
    but close fell back below it — longs got run, shorts stepped in.

    `wick_threshold` is the minimum overshoot (% of price) to count — too
    tight and any noise candle counts; too loose and real sweeps miss.
    """
    if len(df) < lookback + 5:
        return {"score": 50, "side": "NEUTRAL", "detail": "SMC — insufficient data"}

    last = df.iloc[-1]
    last_low = float(last["low"])
    last_high = float(last["high"])
    last_close = float(last["close"])

    # Recent swing highs/lows over the lookback (excluding current bar)
    recent = df.iloc[-lookback - 1:-1]
    swing_low = float(recent["low"].min())
    swing_high = float(recent["high"].max())

    overshoot_pct = wick_threshold * last_close

    bull_swept = (last_low < swing_low - overshoot_pct
                  and last_close > swing_low)
    bear_swept = (last_high > swing_high + overshoot_pct
                  and last_close < swing_high)

    if bull_swept:
        # Strength scales with the rejection distance from the sweep
        rej_pct = (last_close - last_low) / last_close
        strength = min(1.0, rej_pct / 0.03)
        score = 65 + strength * 35
        return {"score": round(score), "side": "LONG",
                "detail": f"Bull liquidity sweep ({rej_pct * 100:.1f}% wick "
                          "rejection — stops run, longs stepped in)"}
    if bear_swept:
        rej_pct = (last_high - last_close) / last_close
        strength = min(1.0, rej_pct / 0.03)
        score = 35 - strength * 35
        return {"score": round(score), "side": "SHORT",
                "detail": f"Bear liquidity sweep ({rej_pct * 100:.1f}% wick "
                          "rejection — stops run, shorts stepped in)"}
    return {"score": 50, "side": "NEUTRAL",
            "detail": "No recent liquidity sweep"}


# ---------------------------------------------------------------------------
# Hurst regime gate
# ---------------------------------------------------------------------------

def _hurst_exponent(series: pd.Series, max_lag: int = 30) -> float:
    """Estimate the Hurst exponent via R/S analysis.

    Pure pandas/numpy — no external dependency. H > 0.55 = trending
    regime (momentum signals valid); H < 0.45 = mean-reverting (breakout
    signals tend to whipsaw); 0.5 = random walk.

    Returns 0.5 (neutral) when there isn't enough data.
    """
    s = series.dropna().to_numpy()
    if len(s) < max_lag * 3:
        return 0.5
    lags = range(2, max_lag)
    try:
        tau = [float(np.std(s[lag:] - s[:-lag])) for lag in lags]
        # log-log slope = Hurst exponent (Hurst's R/S method, simplified)
        with np.errstate(divide="ignore", invalid="ignore"):
            log_lags = np.log(list(lags))
            log_tau = np.log(tau)
            mask = np.isfinite(log_tau)
            if mask.sum() < 5:
                return 0.5
            slope = np.polyfit(log_lags[mask], log_tau[mask], 1)[0]
        return float(np.clip(slope, 0.0, 1.0))
    except Exception:
        return 0.5


def _regime_multiplier(df: pd.DataFrame) -> tuple[float, str, float]:
    """Hurst-based regime gate. Returns (multiplier, regime_label, h_value)."""
    if len(df) < 200:
        return 1.0, "unknown", 0.5
    h = _hurst_exponent(df["close"].tail(300))
    if h >= 0.55:
        return 1.0, "trending", h
    if h <= 0.45:
        return 0.5, "choppy", h
    return 0.85, "developing", h


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------

# Component weights — sum to 1.0. Used for the legacy weighted-average
# composite (kept as `weighted_avg` in the result for reference). The
# PRIMARY composite uses max-deviation-plus-agreement instead — see
# the docstring on `score()` for why.
_WEIGHTS = {
    "cvd": 0.30,        # highest edge per research (SHORT 67% win rate)
    "squeeze": 0.20,    # cleanest binary signal (SHORT 57% win rate)
    "accel": 0.15,      # inflection catcher
    "smc": 0.15,        # reversal trigger
    "vwap": 0.20,       # Phase B — first-control-shift (SHORT 62% win rate)
    # NOTE: 3-candle continuation removed 2026-05-29 after backtest showed
    # adding it DEGRADED both LONG and SHORT win rates. Specifically the
    # SHORT +12bar win rate fell from 71.6% to 53.0% — adding a 6th
    # component diluted the CVD divergence's load-bearing edge. Kept
    # the function `_candle_continuation()` available below but it's
    # no longer wired into the composite.
}


def score(df: pd.DataFrame) -> dict:
    """Compute the composite early-momentum score for one timeframe's klines.

    Returns a dict shaped like:
        {
          "score": 0-100,                  # composite, after Hurst gate
          "raw_score": 0-100,              # before Hurst gate
          "side": "LONG" | "SHORT" | "NEUTRAL",
          "side_confidence": 0-1,
          "regime": "trending"|"developing"|"choppy"|"unknown",
          "hurst": 0.0-1.0,
          "regime_multiplier": 0.5-1.0,
          "components": {
              "cvd_divergence":   {"score": .., "side": .., "detail": ..},
              "ttm_squeeze":      {"score": .., "side": .., "detail": ..},
              "roc_acceleration": {"score": .., "side": .., "detail": ..},
              "smc_sweep":        {"score": .., "side": .., "detail": ..},
          },
          "flags": [...],  # binary triggers fired this bar
        }

    Score interpretation:
      >=75  EARLY-MOMENTUM signal — fires on the picks board as 🔥
      60-74 mild lead, watch but don't act on this alone
      40-59 neutral
      26-39 mild bearish lead
      <=25  EARLY-MOMENTUM bearish signal
    """
    if df is None or len(df) < 50:
        return _empty_result("Not enough klines")

    components = {
        "cvd_divergence":   _cvd_divergence(df),
        "ttm_squeeze":      _ttm_squeeze(df),
        "roc_acceleration": _roc_of_roc(df),
        "smc_sweep":        _smc_liquidity_sweep(df),
        "vwap_reclaim":     _vwap_reclaim(df),
        # `continuation` removed from composite — backtest showed it
        # degraded both LONG and SHORT edge. See _WEIGHTS note above.
    }

    # === Composite scoring — "strongest aligned + agreement bonus" =====
    #
    # The weighted-average approach (kept as `weighted_avg` below for
    # reference) compresses everything around 50: even when ONE
    # component fires at 90, the composite only moves ~7-10 points
    # from neutral. Backtesting showed this configuration produced
    # ZERO chip fires over 4750+ bar evaluations on the top 19 coins.
    #
    # The CORRECT design for "catch early-momentum signals" is:
    #   - If any single leading indicator fires strongly → the chip
    #     should fire. We DON'T want all 5 components to agree (that's
    #     what multi-TF alignment is for). We want "any reliable
    #     leading signal".
    #   - Bonus when multiple components ALSO agree on the side.
    #   - Penalty when components disagree on side.
    #
    # Final composite = strongest aligned component + agreement bonus,
    # then gated by the Hurst regime check.
    weighted_avg = sum(
        _WEIGHTS[w_key] * components[c_key]["score"]
        for w_key, c_key in (
            ("cvd", "cvd_divergence"),
            ("squeeze", "ttm_squeeze"),
            ("accel", "roc_acceleration"),
            ("smc", "smc_sweep"),
            ("vwap", "vwap_reclaim"),
        )
    )

    # Strongest LONG deviation and strongest SHORT deviation
    long_strengths = [c["score"] - 50 for c in components.values()
                      if c["side"] == "LONG"]
    short_strengths = [50 - c["score"] for c in components.values()
                       if c["side"] == "SHORT"]
    max_long = max(long_strengths) if long_strengths else 0.0
    max_short = max(short_strengths) if short_strengths else 0.0
    n_long = sum(1 for c in components.values() if c["side"] == "LONG")
    n_short = sum(1 for c in components.values() if c["side"] == "SHORT")

    # Agreement bonus: +4 per extra aligned component beyond the first.
    # Disagreement penalty: -3 per opposing component.
    if max_long > max_short and max_long >= 10:
        agree_bonus = (n_long - 1) * 4
        disagree_penalty = n_short * 3
        raw_score = 50.0 + max_long + agree_bonus - disagree_penalty
        net_side = "LONG"
        side_conf = float(n_long) / 5.0
    elif max_short > max_long and max_short >= 10:
        agree_bonus = (n_short - 1) * 4
        disagree_penalty = n_long * 3
        raw_score = 50.0 - max_short - agree_bonus + disagree_penalty
        net_side = "SHORT"
        side_conf = float(n_short) / 5.0
    else:
        # No component is firing strongly — fall back to weighted_avg
        raw_score = weighted_avg
        if weighted_avg > 55:
            net_side = "LONG"
        elif weighted_avg < 45:
            net_side = "SHORT"
        else:
            net_side = "NEUTRAL"
        side_conf = 0.2

    raw_score = float(np.clip(raw_score, 0, 100))

    # Hurst gate: in choppy markets, halve the signal's deviation from
    # neutral. Trending and developing markets pass through.
    mult, regime, hurst = _regime_multiplier(df)
    gated_score = 50.0 + (raw_score - 50.0) * mult
    final_score = float(np.clip(gated_score, 0, 100))

    # Flags — binary triggers that fired this bar (useful for UI chips).
    flags: list[str] = []
    if "FIRED" in components["ttm_squeeze"]["detail"]:
        flags.append("squeeze_fire")
    if "sweep" in components["smc_sweep"]["detail"].lower() and \
            components["smc_sweep"]["side"] != "NEUTRAL":
        flags.append("liquidity_sweep")
    if "divergence" in components["cvd_divergence"]["detail"].lower():
        flags.append("cvd_divergence")
    if "inflection" in components["roc_acceleration"]["detail"].lower():
        flags.append("accel_inflection")
    if "reclaim" in components["vwap_reclaim"]["detail"].lower() \
            or "loss" in components["vwap_reclaim"]["detail"].lower():
        flags.append("vwap_event")

    return {
        "score": round(final_score, 1),
        "raw_score": round(raw_score, 1),
        "weighted_avg": round(weighted_avg, 1),
        "side": net_side,
        "side_confidence": round(side_conf, 2),
        "regime": regime,
        "hurst": round(hurst, 3),
        "regime_multiplier": mult,
        "components": components,
        "flags": flags,
    }


def _empty_result(reason: str) -> dict:
    """Neutral result used when input data is insufficient."""
    return {
        "score": 50.0,
        "raw_score": 50.0,
        "weighted_avg": 50.0,
        "side": "NEUTRAL",
        "side_confidence": 0.0,
        "regime": "unknown",
        "hurst": 0.5,
        "regime_multiplier": 1.0,
        "components": {
            "cvd_divergence":   {"score": 50, "side": "NEUTRAL", "detail": reason},
            "ttm_squeeze":      {"score": 50, "side": "NEUTRAL", "detail": reason},
            "roc_acceleration": {"score": 50, "side": "NEUTRAL", "detail": reason},
            "smc_sweep":        {"score": 50, "side": "NEUTRAL", "detail": reason},
            "vwap_reclaim":     {"score": 50, "side": "NEUTRAL", "detail": reason},
        },
        "flags": [],
    }


# ---------------------------------------------------------------------------
# 4h-context tilt — multi-TF without gating
# ---------------------------------------------------------------------------

def score_with_4h_context(klines_1h: pd.DataFrame,
                          klines_4h: pd.DataFrame | None = None,
                          tilt_bps: int = 5) -> dict:
    """Score the 1h primary timeframe with 4h as a CONTEXT tilt (not gate).

    Per the user's design intent: 4h confirms or weakens the read but
    NEVER blocks a fire. A strong 1h signal still fires even if 4h is
    neutral or disagrees — but the composite score gets a +/-`tilt_bps`
    bump depending on alignment.

    `klines_4h` is optional; if missing, primary score is returned with
    a `context_4h` field set to "unavailable" so the UI can show that.

    This implements the request: "4h or beyond can be considered but
    shouldn't be the criteria — gateway to predict the signals early".
    """
    primary = score(klines_1h)
    if klines_4h is None or len(klines_4h) < 50:
        primary["context_4h"] = "unavailable"
        primary["context_4h_score"] = None
        primary["context_4h_side"] = None
        return primary

    ctx = score(klines_4h)
    primary["context_4h_score"] = ctx["score"]
    primary["context_4h_side"] = ctx["side"]
    primary["context_4h_regime"] = ctx.get("regime", "unknown")

    p_side = primary["side"]
    c_side = ctx["side"]
    score_val = primary["score"]
    deviation = score_val - 50.0

    # Apply tilt based on agreement
    if p_side != "NEUTRAL" and c_side == p_side:
        # Aligned: amplify the deviation
        deviation += tilt_bps if deviation >= 0 else -tilt_bps
        primary["context_4h"] = "aligned"
    elif p_side != "NEUTRAL" and c_side != "NEUTRAL" and c_side != p_side:
        # Disagreed: reduce but don't kill the signal
        deviation -= tilt_bps if deviation >= 0 else -tilt_bps
        primary["context_4h"] = "diverges"
    else:
        primary["context_4h"] = "neutral"

    primary["score"] = round(float(np.clip(50 + deviation, 0, 100)), 1)
    return primary


# ---------------------------------------------------------------------------
# Convenience: scoring with multi-timeframe aggregation
# ---------------------------------------------------------------------------

def aggregate_scores(per_tf: dict[str, dict]) -> dict:
    """Combine per-timeframe early-momentum scores into one verdict.

    Uses the same TF weights the existing forecast layer uses, so the
    multi-TF early-momentum read lines up with the rest of the system.
    """
    tf_weight = {"15m": 0.20, "1h": 0.30, "4h": 0.30, "1d": 0.20}
    if not per_tf:
        return _empty_result("No timeframes scored")
    total_w = sum(tf_weight.get(tf, 0.25) for tf in per_tf)
    if total_w <= 0:
        return _empty_result("No timeframe weights")
    agg_score = sum(tf_weight.get(tf, 0.25) * r.get("score", 50)
                    for tf, r in per_tf.items()) / total_w
    # Net side = the side with highest weighted-score deviation from 50
    side_score: dict[str, float] = {"LONG": 0.0, "SHORT": 0.0}
    for tf, r in per_tf.items():
        w = tf_weight.get(tf, 0.25)
        if r.get("side") == "LONG":
            side_score["LONG"] += w * (r.get("score", 50) - 50)
        elif r.get("side") == "SHORT":
            side_score["SHORT"] += w * (50 - r.get("score", 50))
    if side_score["LONG"] > side_score["SHORT"] and side_score["LONG"] > 5:
        net_side = "LONG"
    elif side_score["SHORT"] > side_score["LONG"] and side_score["SHORT"] > 5:
        net_side = "SHORT"
    else:
        net_side = "NEUTRAL"
    # Aligned across all TFs in same direction?
    all_long = all(r.get("side") == "LONG" for r in per_tf.values())
    all_short = all(r.get("side") == "SHORT" for r in per_tf.values())
    aligned = all_long or all_short
    return {
        "score": round(agg_score, 1),
        "side": net_side,
        "aligned": aligned,
        "per_tf": per_tf,
    }
