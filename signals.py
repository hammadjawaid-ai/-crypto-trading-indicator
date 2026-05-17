"""Signal engine: turns indicator values into trading decisions.

Each indicator casts a weighted vote in the range -1 (max bearish) .. +1 (max
bullish). Votes are split into two independent groups so the app can surface
two separate, expert-style read-outs:

* DIRECTIONAL BIAS  — LONG / SHORT / NEUTRAL: which side of the market to be
  on (trend, MACD momentum and derivatives positioning).
* ENTRY ACTION      — BUY / SELL / NEUTRAL: whether *now* is a good moment to
  act (RSI, Stochastic, Bollinger %B and volume conviction).

A trader can be long-biased yet have the timing say "wait" — keeping the two
apart is exactly how a real desk frames a decision.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config
import indicators

# Indicators that define directional BIAS (which side to hold).
DIRECTION_WEIGHTS = {"Trend (EMA)": 0.55, "MACD": 0.45}
DIRECTION_DERIV_WEIGHT = 0.30   # derivatives join the direction group
DIRECTION_SOCIAL_WEIGHT = 0.22  # LunarCrush social sentiment joins direction

# Indicators that define ENTRY TIMING (whether to act now).
TIMING_WEIGHTS = {"RSI": 0.35, "Stochastic": 0.27,
                  "Bollinger %B": 0.23, "Volume": 0.15}

# Which group each indicator belongs to (used by the breakdown view).
_GROUP = {
    "Trend (EMA)": "Direction", "MACD": "Direction",
    "Derivatives": "Direction", "Social": "Direction",
    "RSI": "Timing", "Stochastic": "Timing",
    "Bollinger %B": "Timing", "Volume": "Timing",
}


def _trend_vote(last: pd.Series) -> tuple[float, str]:
    close, ef, es, et = (last["close"], last["ema_fast"],
                         last["ema_slow"], last["ema_trend"])
    if np.isnan(et):  # not enough history for the 200 EMA
        et = es
    if close > ef > es and close > et:
        return 1.0, "Price above all EMAs — strong uptrend"
    if close > es and close > et:
        return 0.55, "Price above slow/trend EMA — uptrend"
    if close < ef < es and close < et:
        return -1.0, "Price below all EMAs — strong downtrend"
    if close < es and close < et:
        return -0.55, "Price below slow/trend EMA — downtrend"
    return 0.0, "EMAs mixed — no clear trend"


def _rsi_vote(last: pd.Series) -> tuple[float, str]:
    r = last["rsi"]
    if r < 30:
        return 0.85, f"RSI {r:.0f} — oversold, bounce likely"
    if r > 70:
        return -0.85, f"RSI {r:.0f} — overbought, pullback likely"
    if r < 45:
        return -0.35, f"RSI {r:.0f} — weak momentum"
    if r > 55:
        return 0.35, f"RSI {r:.0f} — positive momentum"
    return 0.0, f"RSI {r:.0f} — neutral"


def _macd_vote(last: pd.Series, prev: pd.Series) -> tuple[float, str]:
    hist, prev_hist = last["macd_hist"], prev["macd_hist"]
    if np.isnan(hist):
        return 0.0, "MACD — insufficient data"
    rising = hist > prev_hist
    if hist > 0:
        return (1.0 if rising else 0.6), (
            f"MACD bullish{' & expanding' if rising else ' but fading'}")
    return (-1.0 if not rising else -0.6), (
        f"MACD bearish{' & expanding' if not rising else ' but fading'}")


def _bollinger_vote(last: pd.Series) -> tuple[float, str]:
    pb = last["bb_pct"]
    if np.isnan(pb):
        return 0.0, "Bollinger — insufficient data"
    if pb < 0.05:
        return 0.7, "Price at lower band — stretched, bounce zone"
    if pb > 0.95:
        return -0.7, "Price at upper band — stretched, fade zone"
    # Linear lean from band centre.
    return float(np.clip((pb - 0.5) * 1.2, -1, 1) * 0.5), (
        f"Price at {pb * 100:.0f}% of band range")


def _stoch_vote(last: pd.Series) -> tuple[float, str]:
    k = last["stoch"]
    if k < 20:
        return 0.7, f"Stochastic {k:.0f} — oversold"
    if k > 80:
        return -0.7, f"Stochastic {k:.0f} — overbought"
    return float((k - 50) / 50 * 0.3), f"Stochastic {k:.0f}"


def _volume_vote(last: pd.Series) -> tuple[float, str]:
    ratio = last["vol_ratio"]
    if np.isnan(ratio):
        return 0.0, "Volume — insufficient data"
    direction = 1.0 if last["close"] >= last["open"] else -1.0
    if ratio >= 1.5:
        strength = min(ratio, 3.0) / 3.0
        side = "buying" if direction > 0 else "selling"
        return direction * strength, (
            f"Volume {ratio:.1f}x average — {side} pressure")
    if ratio < 0.6:
        return direction * 0.1, f"Volume {ratio:.1f}x average — thin, low conviction"
    return direction * 0.3, f"Volume {ratio:.1f}x average"


def _deriv_vote(deriv: dict) -> tuple[float, str]:
    """Positioning / leverage vote from funding, long/short ratio and OI trend.

    Read contrarian at the extremes: crowded longs (hot positive funding, high
    long/short ratio) warn of a squeeze down, crowded shorts warn of a squeeze
    up. Moderate funding instead confirms the prevailing trend.
    """
    parts: list[float] = []
    notes: list[str] = []

    funding = deriv.get("funding")
    if funding is not None:
        if funding >= config.FUNDING_HOT:
            parts.append(-0.6)
            notes.append(f"funding {funding * 100:+.3f}% — crowded longs")
        elif funding <= -config.FUNDING_HOT:
            parts.append(0.6)
            notes.append(f"funding {funding * 100:+.3f}% — crowded shorts")
        elif funding >= config.FUNDING_WARM:
            parts.append(0.3)
            notes.append(f"funding {funding * 100:+.3f}% — bullish bias")
        elif funding <= config.FUNDING_COLD:
            parts.append(0.2)
            notes.append(f"funding {funding * 100:+.3f}% — shorts paying")
        else:
            notes.append(f"funding {funding * 100:+.3f}% — flat")

    ls = deriv.get("long_short_ratio")
    if ls is not None:
        if ls >= 2.5:
            parts.append(-0.5)
            notes.append(f"L/S {ls:.2f} — longs crowded")
        elif ls >= 1.8:
            parts.append(-0.25)
            notes.append(f"L/S {ls:.2f} — long-heavy")
        elif ls <= 0.8:
            parts.append(0.5)
            notes.append(f"L/S {ls:.2f} — shorts crowded")
        elif ls <= 1.1:
            parts.append(0.25)
            notes.append(f"L/S {ls:.2f} — short-heavy")
        else:
            notes.append(f"L/S {ls:.2f} — balanced")

    oi = deriv.get("oi_change_pct")
    if oi is not None:
        # Rising OI with positive funding = leveraged longs piling in (trend
        # conviction up); falling OI unwinds that conviction. Mirror for shorts.
        if abs(oi) >= 5 and funding is not None:
            lean = (0.3 if funding >= 0 else -0.3) * (1 if oi > 0 else -1)
            parts.append(lean)
        notes.append(f"OI {oi:+.1f}%")

    if not parts:
        return 0.0, "Derivatives — no positioning edge"
    vote = float(np.clip(sum(parts) / len(parts) * 1.5, -1, 1))
    return vote, " · ".join(notes)


def _social_vote(social: dict) -> tuple[float, str]:
    """Social-sentiment vote from LunarCrush Galaxy Score and sentiment.

    Pro-cyclical: a healthy, positively-discussed coin (high Galaxy Score,
    bullish social sentiment) supports the directional bias; a neglected or
    negatively-discussed one weighs against it.
    """
    parts: list[float] = []
    notes: list[str] = []

    galaxy = social.get("galaxy_score")
    if galaxy is not None:
        parts.append(float(np.clip((galaxy - 50) / 40, -1, 1)))
        notes.append(f"Galaxy {galaxy:.0f}")

    sentiment = social.get("sentiment")
    if sentiment is not None:
        parts.append(float(np.clip((sentiment - 50) / 30, -1, 1)))
        notes.append(f"sentiment {sentiment:.0f}%")

    if not parts:
        return 0.0, "Social — no data"
    return float(sum(parts) / len(parts)), "LunarCrush · " + ", ".join(notes)


def _weighted(votes: dict, weights: dict) -> float:
    """Weighted average of selected votes, scaled to -100..+100."""
    total = sum(weights.values())
    if total == 0:
        return 0.0
    raw = sum(weights[name] * votes[name][0] for name in weights)
    return float(np.clip(raw / total * 100, -100, 100))


def _bias_label(score: float) -> str:
    """Map a directional score to a LONG / SHORT positioning label."""
    if score >= config.SCORE_STRONG:
        return "STRONG LONG"
    if score >= config.SCORE_MILD:
        return "LONG"
    if score <= -config.SCORE_STRONG:
        return "STRONG SHORT"
    if score <= -config.SCORE_MILD:
        return "SHORT"
    return "NEUTRAL"


def _action_label(score: float) -> str:
    """Map a timing score to a BUY / SELL / NEUTRAL action label."""
    if score >= config.SCORE_STRONG:
        return "STRONG BUY"
    if score >= config.SCORE_MILD:
        return "BUY"
    if score <= -config.SCORE_STRONG:
        return "STRONG SELL"
    if score <= -config.SCORE_MILD:
        return "SELL"
    return "NEUTRAL"


def _label(score: float) -> tuple[str, str]:
    """Map the -100..100 composite score to (overall label, bias word)."""
    if score >= config.SCORE_STRONG:
        return "STRONG LONG", "Bullish"
    if score >= config.SCORE_MILD:
        return "LONG", "Bullish"
    if score <= -config.SCORE_STRONG:
        return "STRONG SHORT", "Bearish"
    if score <= -config.SCORE_MILD:
        return "SHORT", "Bearish"
    return "NEUTRAL", "Neutral"


def _regime(last: pd.Series) -> str:
    """Classify the market regime from ADX trend strength."""
    adx = last["adx"]
    if np.isnan(adx):
        return "Unknown"
    if adx >= config.ADX_TRENDING:
        return "Trending"
    if adx <= config.ADX_RANGING:
        return "Ranging"
    return "Developing"


def _trade_plan(label: str, last: pd.Series, regime: str) -> dict | None:
    """ATR-based action plan: entry zone, stop, two targets and R:R.

    Targets are placed at 2.0 and 3.5 ATR; the stop at 1.5 ATR. `risk_pct`
    is the stop distance as a % of price, which the UI turns into a
    position-sizing hint.
    """
    atr = last["atr"]
    price = last["close"]
    if np.isnan(atr) or atr <= 0 or label == "NEUTRAL":
        return None
    long = "LONG" in label
    entry_lo = price - 0.25 * atr
    entry_hi = price + 0.25 * atr
    if long:
        stop = price - 1.5 * atr
        tp1 = price + 2.0 * atr
        tp2 = price + 3.5 * atr
    else:
        stop = price + 1.5 * atr
        tp1 = price - 2.0 * atr
        tp2 = price - 3.5 * atr
    risk = abs(price - stop)

    if regime == "Trending":
        fit = ("Trending market — momentum supports holding toward the "
               "2nd target; trail the stop behind structure.")
    elif regime == "Ranging":
        fit = ("Ranging market — chop likely; bank the 1st target and keep "
               "the stop tight, the directional edge is weaker here.")
    else:
        fit = ("Developing trend — consider scaling in and confirming with "
               "momentum before sizing up.")

    return {
        "side": "LONG" if long else "SHORT",
        "entry": price,
        "entry_low": min(entry_lo, entry_hi),
        "entry_high": max(entry_lo, entry_hi),
        "stop_loss": stop,
        "take_profit": tp1,
        "take_profit_2": tp2,
        "risk_reward": abs(tp1 - price) / risk if risk else 0.0,
        "risk_reward_2": abs(tp2 - price) / risk if risk else 0.0,
        "risk_pct": risk / price * 100 if price else 0.0,
        "regime_fit": fit,
    }


def analyze(df: pd.DataFrame, deriv: dict | None = None,
            social: dict | None = None) -> dict:
    """Analyse one OHLCV DataFrame and return a decision dict.

    `df` may be raw OHLCV (it will be enriched) or already enriched. `deriv`,
    when supplied, is a derivatives snapshot and `social` a LunarCrush social
    snapshot ({galaxy_score, sentiment}); both join the directional-bias group
    when present.

    The result carries two separate verdicts: `bias_label` (LONG/SHORT/NEUTRAL)
    and `action_label` (BUY/SELL/NEUTRAL), plus a blended composite `score`.
    """
    if "rsi" not in df.columns:
        df = indicators.enrich(df)
    if len(df) < 2:
        raise ValueError("Need at least 2 candles to analyse.")

    last, prev = df.iloc[-1], df.iloc[-2]
    regime = _regime(last)
    votes = {
        "Trend (EMA)": _trend_vote(last),
        "RSI": _rsi_vote(last),
        "MACD": _macd_vote(last, prev),
        "Bollinger %B": _bollinger_vote(last),
        "Stochastic": _stoch_vote(last),
        "Volume": _volume_vote(last),
    }
    dir_weights = dict(DIRECTION_WEIGHTS)
    if deriv:
        votes["Derivatives"] = _deriv_vote(deriv)
        dir_weights["Derivatives"] = DIRECTION_DERIV_WEIGHT
    if social and (social.get("galaxy_score") is not None
                   or social.get("sentiment") is not None):
        votes["Social"] = _social_vote(social)
        dir_weights["Social"] = DIRECTION_SOCIAL_WEIGHT

    # Two independent read-outs, then a blended composite for ranking.
    bias_score = _weighted(votes, dir_weights)
    action_score = _weighted(votes, TIMING_WEIGHTS)
    score = float(np.clip(0.6 * bias_score + 0.4 * action_score, -100, 100))

    bias_label = _bias_label(bias_score)
    action_label = _action_label(action_score)
    label, bias = _label(score)

    # Confidence blends raw score magnitude with how much weight agrees on
    # the dominant direction.
    all_w = {**dir_weights, **TIMING_WEIGHTS}
    total_w = sum(all_w.values())
    sign = np.sign(score) or 1
    agree = sum(all_w[n] for n, (v, _) in votes.items()
                if np.sign(v) == sign and v != 0)
    confidence = round(min(99.0, abs(score) * 0.55 + agree / total_w * 45))

    breakdown = []
    for name, (v, detail) in votes.items():
        if v > 0.15:
            tag = "Bullish"
        elif v < -0.15:
            tag = "Bearish"
        else:
            tag = "Neutral"
        breakdown.append(
            {"indicator": name, "group": _GROUP.get(name, ""),
             "signal": tag, "score": round(v * 100), "detail": detail}
        )

    return {
        "score": round(score, 1),
        "label": label,
        "bias": bias,
        "bias_score": round(bias_score, 1),
        "bias_label": bias_label,
        "action_score": round(action_score, 1),
        "action_label": action_label,
        "confidence": confidence,
        "price": float(last["close"]),
        "rsi": round(float(last["rsi"]), 1),
        "atr_pct": round(float(last["atr_pct"]), 2)
        if not np.isnan(last["atr_pct"]) else None,
        "vol_ratio": round(float(last["vol_ratio"]), 2)
        if not np.isnan(last["vol_ratio"]) else None,
        "trend": _trend_vote(last)[1],
        "regime": regime,
        "adx": round(float(last["adx"]), 1)
        if not np.isnan(last["adx"]) else None,
        "plus_di": round(float(last["plus_di"]), 1)
        if not np.isnan(last["plus_di"]) else None,
        "minus_di": round(float(last["minus_di"]), 1)
        if not np.isnan(last["minus_di"]) else None,
        "buy_pressure": round(float(last["buy_pressure"]) * 100, 1)
        if not np.isnan(last["buy_pressure"]) else None,
        "vwap": float(last["vwap"]) if not np.isnan(last["vwap"]) else None,
        "breakdown": breakdown,
        "trade_plan": _trade_plan(label, last, regime),
        "derivatives": deriv,
    }


def aggregate(per_tf: dict[str, dict]) -> dict:
    """Combine per-timeframe analyses into one multi-timeframe verdict.

    Higher timeframes carry more weight (a 1d signal outranks a 15m signal).
    Bias and action scores are aggregated separately, mirroring `analyze`.
    """
    tf_weight = {"15m": 0.15, "1h": 0.25, "4h": 0.30, "1d": 0.30}
    total = sum(tf_weight.get(tf, 0.25) for tf in per_tf) or 1

    def wavg(key: str) -> float:
        return sum(tf_weight.get(tf, 0.25) * a[key]
                   for tf, a in per_tf.items()) / total

    score = wavg("score")
    bias_score = wavg("bias_score")
    action_score = wavg("action_score")
    label, bias = _label(score)
    return {
        "score": round(score, 1),
        "label": label,
        "bias": bias,
        "bias_score": round(bias_score, 1),
        "bias_label": _bias_label(bias_score),
        "action_score": round(action_score, 1),
        "action_label": _action_label(action_score),
    }
