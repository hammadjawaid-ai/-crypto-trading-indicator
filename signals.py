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


# Account-risk model: a professional desk risks a fixed slice of capital on
# each trade. Position size is then DERIVED from how far the stop sits — so a
# volatile coin with a wide stop gets a smaller position, never a copy-paste.
RISK_PER_TRADE_PCT = 1.0


def _nearest_levels(levels: list[float], ref: float, above: bool,
                    min_dist: float, cluster: float) -> list[float]:
    """Up to three swing levels on one side of `ref`, nearest first.

    Levels closer than `min_dist` are skipped (too close to be a real
    target); a level within `cluster` of one already chosen is merged out.
    """
    side = sorted((l for l in levels if (l > ref) == above),
                  reverse=not above)
    picked: list[float] = []
    for lvl in side:
        if abs(lvl - ref) < min_dist:
            continue
        if picked and abs(lvl - picked[-1]) < cluster:
            continue
        picked.append(lvl)
        if len(picked) >= 3:
            break
    return picked


def _move_maturity(df: pd.DataFrame, last: pd.Series, long: bool) -> dict:
    """Gauge how far the current move has already run — the 're-run' read.

    Tells a trader whether a signal is a fresh entry, a chase, or a
    second-leg ('re-run') setup after a pullback:
      EARLY    — move is young, room to run
      EXTENDED — already travelled far and stretched; chasing risk is high
      RE-RUN   — ran, then pulled back into support with the trend intact —
                 the high-quality second-leg entry
    Each carries its own confidence (how clear-cut the read is).
    """
    price = float(last["close"])
    atr = float(last["atr"])
    if np.isnan(atr) or atr <= 0:
        return {"stage": "UNKNOWN", "confidence": 0,
                "note": "Not enough history to gauge how far the move has run."}
    ef, es = float(last["ema_fast"]), float(last["ema_slow"])
    rsi = float(last["rsi"])
    stretch = (price - ef) / atr            # ATR units from the fast EMA
    if not long:
        stretch, rsi = -stretch, 100 - rsi
    trend_intact = price > es if long else price < es

    hi = float(df["high"].tail(30).max())
    lo = float(df["low"].tail(30).min())
    ran = (hi - lo) / atr                   # size of the recent swing, ATR units
    pullback = (hi - price) / atr if long else (price - lo) / atr

    if stretch >= 2.2 or rsi >= 76:
        conf = int(min(95, 58 + stretch * 9 + max(0.0, rsi - 70)))
        return {"stage": "EXTENDED", "confidence": conf,
                "note": (f"Price is stretched {stretch:+.1f} ATR from the fast "
                         "EMA and the move has already run — entering here is "
                         "chasing; wait for a pullback.")}
    if trend_intact and ran >= 4 and 1.0 <= pullback <= 4.0 and stretch <= 1.2:
        conf = int(min(93, 52 + ran * 4 + (12 if 40 <= rsi <= 62 else 0)))
        return {"stage": "RE-RUN", "confidence": conf,
                "note": ("Price ran, then pulled back into support with the "
                         "trend still intact — a second-leg ('re-run') setup, "
                         "typically the lowest-risk entry.")}
    conf = int(min(90, 60 + max(0.0, 2.0 - abs(stretch)) * 12))
    return {"stage": "EARLY", "confidence": conf,
            "note": ("Move is still young and not yet stretched — room to run "
                     "before it becomes a chase.")}


def _trade_plan(label: str, df: pd.DataFrame, regime: str,
                mode: str = "futures", confidence: float = 50.0) -> dict | None:
    """Structure-aware action plan: entry zone, stop, three targets, an
    honest per-coin risk/reward and a risk-based position size.

    Stops and targets are anchored to *real* swing structure — the pivot
    highs and lows price has actually reacted to (`indicators.swing_levels`)
    — not flat ATR multiples. That is why every coin gets its OWN R:R
    instead of a copy-paste 1.3R: the numbers come from where price can
    actually travel. Risk-multiple projections only fill in when a coin has
    no clean structure on one side.

    `mode`:
      'spot'    — long-only (you cannot short spot), no leverage, wider
                  swing-horizon targets.
      'futures' — both directions, leverage sized from conviction and capped
                  by volatility.

    Position size uses a fixed-fractional risk model: risk
    RISK_PER_TRADE_PCT of the account on the stop, so a wide-stop coin gets
    a smaller position automatically.
    """
    last = df.iloc[-1]
    atr = float(last["atr"])
    price = float(last["close"])
    if np.isnan(atr) or atr <= 0 or label == "NEUTRAL":
        return None
    long = "LONG" in label
    if mode == "spot" and not long:
        return None  # there is no short side to trade on spot

    supports, resistances = indicators.swing_levels(df)
    maturity = _move_maturity(df, last, long)

    # --- Entry zone: a real pullback band toward the nearest structure ---
    if long:
        below = [s for s in supports if s < price]
        anchor = max(below) if below else price - 0.6 * atr
        entry_low = max(anchor, price - 1.0 * atr)
        entry_high = price
    else:
        above = [r for r in resistances if r > price]
        anchor = min(above) if above else price + 0.6 * atr
        entry_high = min(anchor, price + 1.0 * atr)
        entry_low = price
    entry = (entry_low + entry_high) / 2

    # --- Stop: just beyond the structure that would invalidate the idea ---
    buf = 0.35 * atr
    atr_stop_mult = 2.2 if mode == "spot" else 1.6
    if long:
        protect = [s for s in supports if s < entry - buf]
        struct_stop = (max(protect) - buf) if protect else None
        atr_stop = entry - atr_stop_mult * atr
        if struct_stop is not None and struct_stop < atr_stop:
            stop, stop_basis = struct_stop, "structure"
        else:
            stop, stop_basis = atr_stop, "volatility"
        stop = min(max(stop, entry - 4.0 * atr), entry - 0.8 * atr)
    else:
        protect = [r for r in resistances if r > entry + buf]
        struct_stop = (min(protect) + buf) if protect else None
        atr_stop = entry + atr_stop_mult * atr
        if struct_stop is not None and struct_stop > atr_stop:
            stop, stop_basis = struct_stop, "structure"
        else:
            stop, stop_basis = atr_stop, "volatility"
        stop = max(min(stop, entry + 4.0 * atr), entry + 0.8 * atr)
    risk = abs(entry - stop)

    # --- Targets: the next swing levels price must clear, then projections ---
    struct_t = _nearest_levels(resistances if long else supports, entry, long,
                               max(0.6 * atr, 0.9 * risk), 0.8 * atr)
    targets = list(struct_t)
    proj_r = (2.0, 3.0, 4.5) if mode == "spot" else (1.5, 2.5, 4.0)
    pi = 0
    while len(targets) < 3 and pi < len(proj_r):
        proj = entry + proj_r[pi] * risk * (1 if long else -1)
        if not targets:
            ok = True
        elif long:
            ok = proj > max(targets) + 0.5 * atr
        else:
            ok = proj < min(targets) - 0.5 * atr
        if ok:
            targets.append(proj)
        pi += 1
    targets = sorted(set(targets), reverse=not long)[:3]
    while len(targets) < 3:
        base = targets[-1] if targets else entry
        targets.append(base + 1.5 * risk * (1 if long else -1))

    rrs = [abs(t - entry) / risk if risk else 0.0 for t in targets]
    risk_pct = risk / entry * 100 if entry else 0.0

    # --- Position size from the fixed-fractional risk model ---
    if risk_pct > 0:
        if mode == "spot":
            leverage = 1.0
            position_pct = min(100.0, RISK_PER_TRADE_PCT / risk_pct * 100)
        else:
            lev = min(10.0, confidence / 12.0)
            lev = min(lev, 6.0 / max(risk_pct, 0.3))  # wide stop -> less leverage
            leverage = max(1.0, round(lev, 1))        # never below 1x
            position_pct = min(
                100.0, RISK_PER_TRADE_PCT / (risk_pct * leverage) * 100)
    else:
        leverage, position_pct = 1.0, 0.0

    if regime == "Trending":
        fit = ("Trending market — momentum supports holding toward the far "
               "target; trail the stop behind each new structure level.")
    elif regime == "Ranging":
        fit = ("Ranging market — chop likely; bank Target 1 and tighten the "
               "stop, the directional edge is weaker here.")
    else:
        fit = ("Developing trend — scale in and confirm with momentum before "
               "sizing up to the full position.")

    return {
        "side": "LONG" if long else "SHORT",
        "mode": mode,
        "entry": entry,
        "entry_low": min(entry_low, entry_high),
        "entry_high": max(entry_low, entry_high),
        "stop_loss": stop,
        "stop_basis": stop_basis,
        "take_profit": targets[0],
        "take_profit_2": targets[1],
        "take_profit_3": targets[2],
        "targets": targets,
        "target_rr": [round(r, 2) for r in rrs],
        "risk_reward": rrs[0],
        "risk_reward_2": rrs[1],
        "risk_reward_3": rrs[2],
        "risk_pct": risk_pct,
        "position_pct": round(position_pct, 1),
        "leverage": leverage,
        "maturity": maturity,
        "regime_fit": fit,
    }


def analyze(df: pd.DataFrame, deriv: dict | None = None,
            social: dict | None = None, mode: str = "futures") -> dict:
    """Analyse one OHLCV DataFrame and return a decision dict.

    `df` may be raw OHLCV (it will be enriched) or already enriched. `deriv`,
    when supplied, is a derivatives snapshot and `social` a LunarCrush social
    snapshot ({galaxy_score, sentiment}); both join the directional-bias group
    when present. `mode` ('spot' | 'futures') shapes the trade plan only —
    the directional read is the same either way.

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
        "trade_plan": _trade_plan(label, df, regime, mode, confidence),
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
