"""Long-term spot scoring — Weinstein Stage 2 + Mayer + DD + weekly structure.

The existing signal engine is tuned for short-term (15m–4h) futures
trading. For long-term spot holds — weeks to months — the wrong things
matter: 15m breakouts are noise on a multi-month hold, and ATR-tight
stops are nonsense for an asset you intend to ride through corrections.

This module computes a 0-100 spot conviction score from four classic
long-term-hold signals, all derived from weekly OHLCV bars:

1. Weinstein Stage 2 (35%) — the highest-validated long-entry filter
   outside pure value work. Price above a rising 30-week SMA, broken out
   of a Stage 1 base with confirming volume.
2. Mayer Multiple (20%) — close / 200-week SMA. The closest crypto has
   to a long-term valuation anchor (BTC/ETH only; alts get a neutral).
3. Drawdown from ATH (20%) — discount from peak + capitulated volume.
   Buying liquid majors at 70%+ off ATH near a prior accumulation range
   has the highest base-rate "sure shot" pattern in crypto.
4. Weekly higher-highs / higher-lows structure (25%) — confirmed swing
   pivots with no lookahead bias. Filters out chop dressed up as Stage 2.

This module is PURE — takes a weekly DataFrame, returns a score dict.
No state, no API calls, no side effects.

Notes on data requirements:
- Stage 2 needs at least 35 weeks of history.
- Mayer needs 200 weeks (≈4 years) — only BTC, ETH, and a handful of
  majors have that. Younger coins return a neutral Mayer component.
- Drawdown needs the full history available; longer = better.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Component 1: Weinstein Stage 2
# ---------------------------------------------------------------------------

def _weinstein_stage(weekly: pd.DataFrame) -> dict:
    """Classify the current weekly bar into Weinstein's 4-stage model and
    score Stage 2 (markup) entries.

    Stage 1 — basing: flat 30w MA, price chops around it.
    Stage 2 — markup: rising 30w MA, price above, breakout on volume.
    Stage 3 — distribution: flat 30w MA after a run, price at extremes.
    Stage 4 — decline: falling 30w MA, price below.

    Only Stage 2 scores high. Stage 1 scores middling (waiting for the
    breakout), Stage 3 scores slightly bearish (distribution risk),
    Stage 4 scores 0 (decline — do not buy).

    Score formula:
      - Stage 2 with fresh breakout + volume confirmation = 90-100
      - Stage 2 already running, no fresh breakout = 70-85
      - Stage 1 quiet base, no breakout yet = 45-55
      - Stage 3 distribution = 25-35
      - Stage 4 decline = 5-15
    """
    if len(weekly) < 35:
        return {"score": 50, "stage": "UNKNOWN",
                "detail": f"Need ≥35 weekly bars, have {len(weekly)}"}

    close = weekly["close"]
    volume = weekly["volume"] if "volume" in weekly.columns else None

    sma30 = close.rolling(30).mean()
    if sma30.iloc[-1] != sma30.iloc[-1]:  # NaN
        return {"score": 50, "stage": "UNKNOWN",
                "detail": "30w SMA still warming up"}

    # SMA slope over last 4 weeks (positive = rising)
    sma_slope_4w = float(sma30.iloc[-1] - sma30.iloc[-5]) \
        if len(sma30) >= 5 else 0.0
    sma_slope_pct = sma_slope_4w / float(sma30.iloc[-1]) * 100 \
        if sma30.iloc[-1] else 0.0

    last_close = float(close.iloc[-1])
    last_sma = float(sma30.iloc[-1])
    above_sma = last_close > last_sma

    # Breakout: this bar closed above the prior 30w high (excluding this bar)
    if len(close) >= 31:
        prior_30w_high = float(close.iloc[-31:-1].max())
        broke_out = last_close > prior_30w_high * 1.005  # 0.5% buffer
    else:
        broke_out = False

    # Volume confirmation on the breakout bar
    vol_confirm = False
    if volume is not None and len(volume) >= 30:
        vol_avg_30w = float(volume.rolling(30).mean().iloc[-1] or 1)
        last_vol = float(volume.iloc[-1])
        vol_confirm = last_vol >= 1.5 * vol_avg_30w

    # --- Stage classification ---
    if above_sma and sma_slope_pct > 0.5:
        stage = "STAGE_2_MARKUP"
        if broke_out and vol_confirm:
            score = 95
            detail = (f"Stage 2 markup, FRESH breakout on volume "
                      f"({sma_slope_pct:+.1f}%/4w slope, vol {last_vol / vol_avg_30w:.1f}x)")
        elif broke_out:
            score = 82
            detail = (f"Stage 2 markup, breakout (volume light) "
                      f"({sma_slope_pct:+.1f}%/4w slope)")
        else:
            score = 70
            detail = (f"Stage 2 already running ({sma_slope_pct:+.1f}%/4w slope) "
                      "— extended entry, no fresh breakout")
    elif above_sma and abs(sma_slope_pct) <= 0.5:
        stage = "STAGE_1_BASE"
        # Quiet base — waiting for ignition. Slight positive bias if forming
        # higher lows (handled by the HH/HL component separately).
        score = 50
        detail = "Stage 1 base — quiet, waiting for breakout"
    elif not above_sma and sma_slope_pct < -0.5:
        stage = "STAGE_4_DECLINE"
        score = 10
        detail = (f"Stage 4 decline ({sma_slope_pct:+.1f}%/4w slope) "
                  "— do not buy")
    elif not above_sma and abs(sma_slope_pct) <= 0.5:
        stage = "STAGE_3_DISTRIBUTION"
        score = 30
        detail = "Stage 3 distribution — caution, downside risk"
    else:
        stage = "TRANSITIONAL"
        score = 45
        detail = (f"Transitioning ({sma_slope_pct:+.1f}%/4w slope, "
                  f"price {'above' if above_sma else 'below'} 30w)")

    return {"score": score, "stage": stage, "detail": detail,
            "sma_slope_pct": round(sma_slope_pct, 2),
            "above_sma": above_sma, "broke_out": broke_out,
            "vol_confirm": vol_confirm}


# ---------------------------------------------------------------------------
# Component 2: Mayer Multiple
# ---------------------------------------------------------------------------

def _mayer_multiple(weekly: pd.DataFrame, is_btc_or_eth: bool = False) -> dict:
    """Mayer Multiple = close / 200w SMA. Long-term valuation anchor.

    Zones (historical, BTC/ETH):
      < 1.0  — deep value, generational buy zone
      1.0-1.2 — accumulation zone
      1.2-1.5 — neutral/fair
      1.5-2.4 — extended, late-cycle
      > 2.4  — distribution zone

    For alts: less reliable (often don't have 4+ years of history, cycles
    differ from BTC). When `is_btc_or_eth=False`, returns 50 (neutral)
    regardless of computed value — we surface the Mayer reading for
    information but don't let it dominate alt scoring.
    """
    if len(weekly) < 200:
        return {"score": 50, "mayer": None,
                "detail": f"Need ≥200 weekly bars, have {len(weekly)}"}

    sma200 = float(weekly["close"].rolling(200).mean().iloc[-1] or 0)
    if sma200 <= 0:
        return {"score": 50, "mayer": None, "detail": "200w SMA undefined"}

    mayer = float(weekly["close"].iloc[-1]) / sma200

    if not is_btc_or_eth:
        return {"score": 50, "mayer": round(mayer, 2),
                "detail": f"Mayer {mayer:.2f} (alt — informational only)"}

    # BTC/ETH scoring
    if mayer < 1.0:
        score = 95
        zone = "DEEP VALUE"
    elif mayer < 1.2:
        score = 80
        zone = "ACCUMULATION"
    elif mayer < 1.5:
        score = 60
        zone = "FAIR"
    elif mayer < 2.0:
        score = 40
        zone = "EXTENDED"
    elif mayer < 2.4:
        score = 25
        zone = "LATE CYCLE"
    else:
        score = 10
        zone = "DISTRIBUTION"
    return {"score": score, "mayer": round(mayer, 2),
            "detail": f"Mayer {mayer:.2f} — {zone}"}


# ---------------------------------------------------------------------------
# Component 3: Drawdown from ATH
# ---------------------------------------------------------------------------

def _drawdown_score(weekly: pd.DataFrame) -> dict:
    """Score the discount from all-time-high. Deeper drawdowns near a
    prior accumulation range are the highest base-rate long entries.

    Buy zones (% off ATH):
       <20%   no discount — neutral score (not a value buy)
       20-40% modest correction — slight positive
       40-60% bear-market discount — solid
       60-80% capitulation zone — strongest historical edge
       >80%   either a generational opportunity or a dead coin —
              require capitulation volume + multi-year support to score high.
    """
    if len(weekly) < 30:
        return {"score": 50, "dd_pct": 0,
                "detail": f"Need ≥30 weekly bars, have {len(weekly)}"}

    close = weekly["close"]
    ath = float(close.cummax().iloc[-1])
    if ath <= 0:
        return {"score": 50, "dd_pct": 0, "detail": "No ATH"}
    last = float(close.iloc[-1])
    dd = 1.0 - last / ath
    dd_pct = dd * 100

    # Capitulation check: current volume vs peak-area volume
    if "volume" in weekly.columns and len(weekly) >= 50:
        recent_vol = float(weekly["volume"].tail(8).mean() or 0)
        peak_vol = float(weekly["volume"].rolling(20).mean().max() or 1)
        capitulated = recent_vol < 0.5 * peak_vol
    else:
        capitulated = False

    if dd_pct < 20:
        score = 50
        detail = f"{dd_pct:.0f}% off ATH — no discount"
    elif dd_pct < 40:
        score = 60
        detail = f"{dd_pct:.0f}% off ATH — modest correction"
    elif dd_pct < 60:
        score = 75
        detail = f"{dd_pct:.0f}% off ATH — bear-market discount"
    elif dd_pct < 80:
        if capitulated:
            score = 90
            detail = f"{dd_pct:.0f}% off ATH + capitulated volume — strong zone"
        else:
            score = 80
            detail = f"{dd_pct:.0f}% off ATH — capitulation zone"
    else:  # >80% off
        if capitulated:
            score = 80
            detail = (f"{dd_pct:.0f}% off ATH + capitulated volume — "
                      "deep value OR dead coin, verify liveness")
        else:
            score = 55
            detail = (f"{dd_pct:.0f}% off ATH but no capitulation — "
                      "still distributing")

    return {"score": score, "dd_pct": round(dd_pct, 1),
            "capitulated": capitulated, "detail": detail}


# ---------------------------------------------------------------------------
# Component 4: Weekly higher-highs / higher-lows structure
# ---------------------------------------------------------------------------

def _swing_pivots(series: pd.Series, k: int = 3) -> tuple[list[int], list[int]]:
    """Detect swing-high and swing-low indices.

    No-lookahead rule: a pivot at index i is only declared when bars
    [i+1 .. i+k] have closed, so we never use future data. This means
    the most recent k bars cannot be pivots — that's correct behaviour
    and matches what a real trader sees.
    """
    n = len(series)
    s = series.to_numpy()
    highs: list[int] = []
    lows: list[int] = []
    for i in range(k, n - k):
        seg = s[i - k:i + k + 1]
        if s[i] >= seg.max():
            highs.append(i)
        if s[i] <= seg.min():
            lows.append(i)
    return highs, lows


def _hh_hl_structure(weekly: pd.DataFrame, k: int = 3) -> dict:
    """Confirm an uptrend via the last two swing highs being ascending
    AND the last two swing lows being ascending. No lookahead.
    """
    if len(weekly) < 4 * k + 6:
        return {"score": 50, "structure": "UNKNOWN",
                "detail": f"Need ≥{4 * k + 6} weekly bars, have {len(weekly)}"}

    high_pivots, low_pivots = _swing_pivots(weekly["high"], k)
    # Latest two swing highs and lows
    highs = [float(weekly["high"].iloc[i]) for i in high_pivots[-2:]]
    lows = [float(weekly["low"].iloc[i]) for i in
            _swing_pivots(weekly["low"], k)[1][-2:]]

    if len(highs) < 2 or len(lows) < 2:
        return {"score": 50, "structure": "UNCLEAR",
                "detail": f"Not enough confirmed pivots (highs={len(highs)}, "
                          f"lows={len(lows)})"}

    hh = highs[1] > highs[0]
    hl = lows[1] > lows[0]
    lh = highs[1] < highs[0]
    ll = lows[1] < lows[0]

    if hh and hl:
        # Strength scales with how much price has advanced
        adv_pct = (highs[1] / highs[0] - 1) * 100
        score = 80 + min(15, adv_pct / 5)
        return {"score": round(score), "structure": "UPTREND_HH_HL",
                "detail": f"Uptrend confirmed: HH (+{adv_pct:.1f}%) and HL"}
    if lh and ll:
        decline_pct = (highs[0] / highs[1] - 1) * 100 if highs[1] else 0
        score = max(10, 30 - decline_pct / 5)
        return {"score": round(score), "structure": "DOWNTREND_LH_LL",
                "detail": f"Downtrend confirmed: LH (-{decline_pct:.1f}%) and LL"}
    if hh and ll:
        return {"score": 55, "structure": "EXPANDING",
                "detail": "HH but LL — volatility expansion, no clean trend"}
    if lh and hl:
        return {"score": 45, "structure": "CONTRACTING",
                "detail": "LH but HL — coiling, no clean trend"}
    return {"score": 50, "structure": "UNCLEAR",
            "detail": "Structure unclear"}


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------

_WEIGHTS = {
    "weinstein": 0.35,  # most-validated long-entry filter
    "mayer":     0.20,  # valuation anchor (BTC/ETH meaningful, alts neutral)
    "drawdown":  0.20,  # discount-from-ATH base-rate
    "structure": 0.25,  # HH/HL confirmation
}


def score(bars: pd.DataFrame, is_btc_or_eth: bool = False,
          interval: str = "1w") -> dict:
    """Compute the long-term spot conviction score for one coin.

    Args:
        bars: OHLCV DataFrame in the chosen timeframe (1w default, but
              1d/3d/1w all work since the math is relative to bar count).
              Needs at least ~35 bars for Stage 2, ideally 200+ for full
              Mayer.
        is_btc_or_eth: enables BTC/ETH-tuned Mayer scoring. Pass False
                       for alts (Mayer becomes informational only).
        interval: the bar interval string (for display labels). Doesn't
                  affect calculations — those depend on bar count, not
                  the time-per-bar.

    Returns:
        {
          "score": 0-100,             # composite, gates at >=70 for picks board
          "side": "LONG",             # spot is long-only by definition
          "components": {...},        # per-component scores + details
          "stage": str,               # Weinstein stage label
          "tier": "STRONG"|"WATCH"|"AVOID",
          "interval": str,            # which TF was scored
        }
    """
    if bars is None or len(bars) < 20:
        return _empty_result(f"Insufficient {interval} data")

    components = {
        "weinstein":  _weinstein_stage(bars),
        "mayer":      _mayer_multiple(bars, is_btc_or_eth=is_btc_or_eth),
        "drawdown":   _drawdown_score(bars),
        "structure":  _hh_hl_structure(bars),
    }

    composite = sum(
        _WEIGHTS[k] * components[k]["score"] for k in _WEIGHTS
    )
    composite = float(np.clip(composite, 0, 100))

    # Tier label
    if composite >= 80:
        tier = "STRONG"
    elif composite >= 65:
        tier = "WATCH"
    else:
        tier = "AVOID"

    stage = components["weinstein"].get("stage", "UNKNOWN")

    # Side is always LONG for spot — but we surface the underlying trend
    # so callers can refuse to display AVOID-tier picks.
    return {
        "score": round(composite, 1),
        "side": "LONG",
        "tier": tier,
        "stage": stage,
        "interval": interval,
        "components": components,
    }


def _empty_result(reason: str) -> dict:
    return {
        "score": 50.0,
        "side": "LONG",
        "tier": "AVOID",
        "stage": "UNKNOWN",
        "components": {
            "weinstein":  {"score": 50, "stage": "UNKNOWN", "detail": reason},
            "mayer":      {"score": 50, "mayer": None,      "detail": reason},
            "drawdown":   {"score": 50, "dd_pct": 0,        "detail": reason},
            "structure":  {"score": 50, "structure": "UNKNOWN", "detail": reason},
        },
    }
