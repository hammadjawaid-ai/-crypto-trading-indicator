"""Breakout Radar — predicts which coins are about to blow out, and how early.

A coin that has *already* run hard is the worst thing to chase — the move is
priced in and the signal is most likely to be a false top/bottom. So the radar
does not just measure "is something happening"; it also measures **how far
along** the move is, and grades every coin into a stage:

* COILED   — wound tight, has NOT fired yet. The predictive, lowest-risk
             setup: get positioned before the break. Direction is read from
             *leading* tells (order flow, accumulation, 1h trend, sentiment,
             funding) rather than price that has not moved.
* FRESH    — broke out recently and is still early; room left to run. Join it.
* EXTENDED — already made the move; RSI stretched, price far from value.
             Chasing here is the risk the radar is built to flag.

For every coin the engine produces:

* ENERGY       (0-100)        — how loaded the spring is (volume, volatility
                                coil, social heat, news catalyst).
* DIRECTION    (-100..+100)   — which way it fires / leans.
* EXTENSION    (0-100)        — how much of the move is already spent.
* OPPORTUNITY  (0-100)        — the headline rank: energy rewarded for COILED /
                                FRESH stages, heavily penalised for EXTENDED.

Each candidate carries an explicit entry zone, stop and two exit targets.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

import binance_client
import config
import indicators

# --- Coin name lexicon — maps base symbols to words used in news headlines. --
COIN_NAMES: dict[str, list[str]] = {
    "BTC": ["bitcoin"], "ETH": ["ethereum", "ether"], "SOL": ["solana"],
    "XRP": ["xrp", "ripple"], "BNB": ["bnb"], "DOGE": ["dogecoin"],
    "ADA": ["cardano"], "AVAX": ["avalanche"], "LINK": ["chainlink"],
    "DOT": ["polkadot"], "MATIC": ["polygon"], "POL": ["polygon"],
    "LTC": ["litecoin"], "TRX": ["tron"], "SHIB": ["shiba inu"],
    "PEPE": ["pepe"], "WIF": ["dogwifhat"], "SUI": ["sui network"],
    "APT": ["aptos"], "ARB": ["arbitrum"], "OP": ["optimism"],
    "TON": ["toncoin"], "NEAR": ["near protocol"], "INJ": ["injective"],
    "TIA": ["celestia"], "SEI": ["sei network"], "RUNE": ["thorchain"],
    "FIL": ["filecoin"], "ATOM": ["cosmos"], "HBAR": ["hedera"],
    "ICP": ["internet computer"], "RNDR": ["render"], "RENDER": ["render"],
    "FET": ["fetch.ai", "artificial superintelligence"], "KAITO": ["kaito"],
    "ENA": ["ethena"], "ONDO": ["ondo finance"], "JUP": ["jupiter"],
    "PYTH": ["pyth network"], "STRK": ["starknet"], "AAVE": ["aave"],
    "UNI": ["uniswap"], "LDO": ["lido"], "CRV": ["curve finance"],
    "MKR": ["maker"], "BONK": ["bonk"], "FLOKI": ["floki"],
    "JTO": ["jito"], "ETHFI": ["ether.fi"], "ENS": ["ethereum name service"],
    "TAO": ["bittensor"], "WLD": ["worldcoin"], "ORDI": ["ordinals"],
    "GALA": ["gala games"], "SAND": ["the sandbox"], "MANA": ["decentraland"],
    "AXS": ["axie infinity"], "IMX": ["immutable"], "GRT": ["the graph"],
    "ALGO": ["algorand"], "VET": ["vechain"], "XLM": ["stellar"],
    "EOS": ["eos"], "S": ["sonic"], "VIRTUAL": ["virtuals"],
    "AI16Z": ["ai16z"], "PNUT": ["peanut"], "MOVE": ["movement"],
    "ME": ["magic eden"], "PENGU": ["pudgy penguins"], "HYPE": ["hyperliquid"],
}

# Bases whose plain symbol collides with common English words.
_NAME_STOPWORDS = {
    "near", "sand", "gas", "sun", "win", "mask", "gods", "high", "time",
    "cake", "jam", "move", "people", "ach", "id", "home", "look", "alpha",
    "snt", "rare", "super", "city", "lit", "key", "dia", "ray",
}


def _fmt(value: float) -> str:
    """Compact price formatter for written notes."""
    if value is None:
        return "—"
    if value >= 100:
        return f"${value:,.2f}"
    if value >= 1:
        return f"${value:,.4f}"
    return f"${value:.8f}".rstrip("0").rstrip(".")


def _renorm(parts: list[tuple[float, float]]) -> float:
    """Weighted average of (score, weight) pairs; ignores zero-weight noise."""
    total = sum(w for _, w in parts)
    if total <= 0:
        return 0.0
    return sum(s * w for s, w in parts) / total


# ===========================================================================
# Per-force scoring helpers  ── ENERGY group (how loaded the spring is)
# ===========================================================================
def _volume(d15: pd.DataFrame) -> tuple[float, float, float, bool, str]:
    """Volume score (0-100), peak multiple, ignition multiple, an `ignited`
    flag and a note.

    Two patterns matter. A short SPIKE — a recent candle far above its
    20-period average — is the obvious one. Far more powerful is volume
    IGNITING off a dormant base: the last few candles trading several times
    the prior quiet baseline. That "the coin is waking up" pattern is the
    single best tell that a big move is starting, before price has run — it
    is exactly what precedes a parabolic leg.
    """
    vol = d15["volume"]
    vr = d15["vol_ratio"].tail(4).dropna()
    if vr.empty:
        return 0.0, 1.0, 1.0, False, "volume history thin"
    peak = float(vr.max())
    latest = float(vr.iloc[-1])
    surge = float(np.clip((peak - 1.0) / 4.0 * 100, 0, 100))
    if latest >= peak * 0.85 and peak >= 1.8:
        surge = min(100.0, surge + 12)

    ignition = 1.0
    if len(vol) >= 30:
        recent = float(vol.tail(6).mean())
        dormant = float(vol.iloc[-28:-8].median())
        if dormant > 0:
            ignition = recent / dormant
    ign_score = float(np.clip((ignition - 1.0) / 5.0 * 100, 0, 100))
    ignited = ignition >= 2.5 and surge >= 28

    score = max(surge, ign_score)
    if ignited:
        score = min(100.0, score + 14)
        note = (f"volume is igniting off a dormant base — the last few candles "
                f"are trading ~{ignition:.1f}x the prior quiet baseline; a coin "
                f"waking up like this is the classic pre-move tell")
    elif peak >= 1.8:
        note = (f"a volume spike to {peak:.1f}x its 20-candle average fired "
                f"in the last hour")
    elif ignition >= 1.8:
        note = (f"volume is starting to build — ~{ignition:.1f}x the recent "
                f"baseline; early participation, worth watching")
    else:
        note = f"volume only {peak:.1f}x average — no surge yet"
    return score, peak, ignition, ignited, note


def _volatility(d15: pd.DataFrame) -> tuple[float, bool, str]:
    """Volatility score (0-100), an `expanding` flag and a note.

    A tight Bollinger coil = stored energy; a fast-widening band = a move
    already underway. Both register as breakout energy.
    """
    bw = d15["bb_width"].dropna()
    if len(bw) < 30:
        return 0.0, False, "volatility history thin"
    recent = bw.tail(60)
    cur = float(bw.iloc[-1])
    pctile = float((recent < cur).mean() * 100)
    prior = float(bw.iloc[-6]) if len(bw) >= 6 else cur
    expanding_ratio = cur / prior if prior > 0 else 1.0

    coil = max(0.0, (32 - pctile) / 32 * 100)
    expansion = float(np.clip((expanding_ratio - 1.0) / 0.8 * 100, 0, 100))
    score = max(coil, expansion)
    is_expanding = expanding_ratio > 1.25

    if pctile < 22:
        note = (f"Bollinger bands are coiled tight — band width is in the "
                f"{pctile:.0f}th percentile of the last 60 candles; volatility "
                f"this compressed rarely lasts and releases violently")
    elif is_expanding:
        note = (f"volatility is expanding fast — band width is up "
                f"{(expanding_ratio - 1) * 100:.0f}% in six candles")
    else:
        note = f"volatility is mid-range ({pctile:.0f}th percentile of width)"
    return score, is_expanding, note


# ===========================================================================
# Per-force scoring helpers  ── REALIZED group (how far it has already moved)
# ===========================================================================
def _momentum(d15: pd.DataFrame, d1h: pd.DataFrame) -> tuple[float, str]:
    """Signed momentum score (-100..+100) and a note. ATR-normalised."""
    c = d15["close"].to_numpy(dtype=float)
    atrp = d15["atr_pct"].iloc[-1]
    norm = max(float(atrp) if pd.notna(atrp) and atrp > 0 else 0.8, 0.4)

    def roc(n: int, off: int = 0) -> float:
        i, j = -1 - off, -1 - off - n
        if len(c) < n + 1 + off:
            return 0.0
        return (c[i] / c[j] - 1) * 100

    r4, r8 = roc(4), roc(8)
    accel = r4 - roc(4, 1)
    raw = (r4 / norm) * 26 + (r8 / norm) * 9 + (accel / norm) * 16

    c1 = d1h["close"].to_numpy(dtype=float)
    r1h = (c1[-1] / c1[-4] - 1) * 100 if len(c1) >= 5 else 0.0
    if r4 != 0 and np.sign(r1h) == np.sign(r4):
        raw += np.sign(r1h) * min(abs(r1h) / norm, 4) * 8

    score = float(np.clip(raw, -100, 100))
    word = ("accelerating higher" if score >= 35
            else "drifting higher" if score >= 12
            else "accelerating lower" if score <= -35
            else "drifting lower" if score <= -12 else "flat")
    note = (f"price is {word} — {r4:+.2f}% over the last hour, {r8:+.2f}% over "
            f"two hours, with the 1h candle {r1h:+.2f}%")
    return score, note


def _range_break(d15: pd.DataFrame) -> tuple[float, float, float, bool, str]:
    """Signed range-break score, the 24-candle high & low, a `recent` flag
    and a note."""
    high = d15["high"].to_numpy(dtype=float)
    low = d15["low"].to_numpy(dtype=float)
    close = float(d15["close"].iloc[-1])
    if len(high) < 26:
        return 0.0, close, close, False, "range history thin"
    win_h = float(high[-25:-1].max())
    win_l = float(low[-25:-1].min())
    span = win_h - win_l
    if span <= 0:
        return 0.0, win_h, win_l, False, "range history thin"

    close_5 = float(d15["close"].iloc[-6]) if len(d15) >= 6 else close
    if close > win_h:
        over = (close - win_h) / span * 100
        score = float(np.clip(48 + over * 4, 0, 100))
        recent = close_5 <= win_h
        note = (f"price has broken above its 6-hour high of {_fmt(win_h)}"
                + (" just now" if recent else " and has been extending"))
    elif close < win_l:
        under = (win_l - close) / span * 100
        score = float(np.clip(-48 - under * 4, -100, 0))
        recent = close_5 >= win_l
        note = (f"price has broken below its 6-hour low of {_fmt(win_l)}"
                + (" just now" if recent else " and has been extending"))
    else:
        pos = (close - (win_h + win_l) / 2) / (span / 2)
        score = float(np.clip(pos * 46, -100, 100))
        recent = False
        edge = ("coiled just under resistance" if pos > 0.45
                else "pressing on support" if pos < -0.45 else "mid-range")
        note = (f"price is {edge} inside a {_fmt(win_l)}–{_fmt(win_h)} "
                f"6-hour range — no break yet")
    return score, win_h, win_l, recent, note


# ===========================================================================
# Per-force scoring helpers  ── LEADING group (pre-move pressure)
# ===========================================================================
def _order_flow(d15: pd.DataFrame) -> tuple[float, str]:
    """Signed order-flow score from per-candle taker-buy pressure."""
    bp = d15["buy_pressure"].tail(4).dropna()
    if bp.empty:
        return 0.0, "taker-flow data unavailable"
    val = float(bp.mean())
    score = float(np.clip((val - 0.5) * 420, -100, 100))
    if score >= 18:
        note = (f"aggressive order flow is buy-led — {val * 100:.0f}% of taker "
                f"volume over the last hour hit the ask")
    elif score <= -18:
        note = (f"aggressive order flow is sell-led — {(1 - val) * 100:.0f}% of "
                f"taker volume over the last hour hit the bid")
    else:
        note = f"taker order flow is balanced ({val * 100:.0f}% buys)"
    return score, note


def _accumulation(d15: pd.DataFrame) -> tuple[float, str]:
    """Signed OBV-trend score — net directional volume = quiet accumulation /
    distribution, a tell that leads price."""
    obv = d15["obv"].to_numpy(dtype=float)
    if len(obv) < 13:
        return 0.0, "accumulation data thin"
    change = obv[-1] - obv[-13]
    vol_sum = float(d15["volume"].tail(12).sum()) or 1.0
    score = float(np.clip(change / vol_sum * 150, -100, 100))
    if score >= 18:
        note = "on-balance volume is rising — quiet accumulation under the price"
    elif score <= -18:
        note = "on-balance volume is falling — quiet distribution under the price"
    else:
        note = "on-balance volume is flat — no accumulation edge"
    return score, note


def _relative_strength(d15: pd.DataFrame,
                       btc_d15: pd.DataFrame | None) -> tuple[float, str]:
    """Signed strength of the coin versus BTC over the recent ~4h window.

    A coin outperforming BTC is making an idiosyncratic, news/narrative-driven
    move — the real thing. One simply tracking BTC is just market beta.
    """
    if btc_d15 is None or len(btc_d15) < 18:
        return 0.0, "no BTC reference available for relative strength"
    c = d15["close"].to_numpy(dtype=float)
    bt = btc_d15["close"].to_numpy(dtype=float)
    if len(c) < 17 or len(bt) < 17:
        return 0.0, "history thin for relative strength"
    coin_ret = (c[-1] / c[-17] - 1) * 100
    btc_ret = (bt[-1] / bt[-17] - 1) * 100
    rs = coin_ret - btc_ret
    score = float(np.clip(rs * 7, -100, 100))
    if score >= 20:
        note = (f"strongly outperforming BTC — {coin_ret:+.1f}% vs BTC "
                f"{btc_ret:+.1f}% over 4h; an idiosyncratic move, not just "
                f"market beta")
    elif score <= -20:
        note = (f"underperforming BTC — {coin_ret:+.1f}% vs BTC {btc_ret:+.1f}% "
                f"over 4h; independent weakness, not just the market")
    else:
        note = (f"tracking BTC closely ({coin_ret:+.1f}% vs {btc_ret:+.1f}% "
                f"over 4h) — little independent strength either way")
    return score, note


def _tf_lean(d: pd.DataFrame) -> float:
    """A single timeframe's trend lean, -1 (down) .. +1 (up)."""
    last = d.iloc[-1]
    close, ef, es = last["close"], last["ema_fast"], last["ema_slow"]
    et = last["ema_trend"]
    if pd.isna(et):
        et = es
    if close > ef > es and close > et:
        return 1.0
    if close > es and close > et:
        return 0.55
    if close < ef < es and close < et:
        return -1.0
    if close < es and close < et:
        return -0.55
    if close > es:
        return 0.3
    if close < es:
        return -0.3
    return 0.0


def _htf_lean(d1h: pd.DataFrame,
              d4h: pd.DataFrame) -> tuple[float, str, str]:
    """Signed multi-timeframe trend lean from the 1h and 4h charts.

    The 4h chart carries more weight — it sets the dominant trend a 15m coil
    is most likely to resolve with. Also returns a 4h regime word.
    """
    l1 = _tf_lean(d1h)
    l4 = _tf_lean(d4h)
    score = float(np.clip((l1 * 0.4 + l4 * 0.6) * 100, -100, 100))

    def word(v: float) -> str:
        return "up" if v > 0.2 else "down" if v < -0.2 else "flat"

    regime = ("4h uptrend" if l4 > 0.2 else "4h downtrend" if l4 < -0.2
              else "4h range")
    adx4 = d4h["adx"].iloc[-1]
    strong = pd.notna(adx4) and adx4 >= config.ADX_TRENDING
    note = (f"the 1h trend is {word(l1)} and the 4h trend is {word(l4)}"
            + (" with real strength behind it (4h ADX confirms)"
               if strong and abs(l4) > 0.2 else "")
            + " — the higher-timeframe backdrop a 15m setup resolves into")
    return score, note, regime


def _funding_fuel(funding: float | None,
                  realized: float) -> tuple[float, str]:
    """Signed derivatives-squeeze score from the perpetual funding rate."""
    if funding is None:
        return 0.0, "no perpetual market / funding data"
    pct = funding * 100
    if funding >= config.FUNDING_HOT:
        if realized < -8:
            return -58.0, (f"funding is hot at {pct:+.3f}% while price falls — "
                           f"trapped longs are long-squeeze fuel for a drop")
        return 16.0, f"funding {pct:+.3f}% — leveraged longs crowding in"
    if funding <= -config.FUNDING_HOT:
        if realized > 8:
            return 58.0, (f"funding is deeply negative at {pct:+.3f}% while "
                          f"price rises — trapped shorts are short-squeeze fuel")
        return -16.0, f"funding {pct:+.3f}% — shorts pressing the move"
    if funding >= config.FUNDING_WARM:
        return 8.0, f"funding {pct:+.3f}% — a mild long lean"
    if funding <= config.FUNDING_COLD:
        return -8.0, f"funding {pct:+.3f}% — a mild short lean"
    return 0.0, f"funding {pct:+.3f}% — neutral, no leverage extreme"


# ===========================================================================
# Stage & extension
# ===========================================================================
def _extension(d15: pd.DataFrame, win_h: float,
               win_l: float) -> tuple[float, str]:
    """How much of the move is already spent (0 = fresh, 100 = exhausted)."""
    last = d15.iloc[-1]
    close = float(last["close"])
    atr = float(last["atr"]) if pd.notna(last["atr"]) and last["atr"] > 0 \
        else close * 0.01
    rsi = float(last["rsi"]) if pd.notna(last["rsi"]) else 50.0
    ef = float(last["ema_fast"]) if pd.notna(last["ema_fast"]) else close
    atrp = float(last["atr_pct"]) if pd.notna(last["atr_pct"]) \
        and last["atr_pct"] > 0 else 0.8

    rsi_stretch = min(abs(rsi - 50) / 50, 1.0) * 100 * (
        1.5 if (rsi >= 75 or rsi <= 25) else 0.75)
    ema_stretch = min(abs(close - ef) / atr / 3.0, 1.0) * 100
    if close > win_h:
        break_stretch = min((close - win_h) / atr / 2.5, 1.0) * 100
    elif close < win_l:
        break_stretch = min((win_l - close) / atr / 2.5, 1.0) * 100
    else:
        break_stretch = 0.0
    c = d15["close"].to_numpy(dtype=float)
    run = abs(c[-1] / c[-9] - 1) * 100 if len(c) >= 9 else 0.0
    run_stretch = min(run / max(atrp, 0.4) / 4.0, 1.0) * 100

    score = float(np.clip(
        (rsi_stretch + ema_stretch + break_stretch + run_stretch) / 4, 0, 100))
    return score, f"RSI {rsi:.0f}"


def _stage(d15: pd.DataFrame, range_score: float, recent_break: bool,
           extension: float, rsi: float) -> str:
    """Grade the coin: COILED (not fired), FRESH (early), EXTENDED (late)."""
    broke = abs(range_score) >= 46
    if rsi >= 77 or rsi <= 23 or extension >= 60:
        return "EXTENDED"
    if broke:
        if recent_break or extension < 45:
            return "FRESH"
        return "EXTENDED"
    return "COILED"


# ===========================================================================
# Social & news indices
# ===========================================================================
def _build_social_index(lc_rows: list) -> dict[str, dict]:
    """Per-coin social-heat index from a LunarCrush coin list."""
    if not lc_rows:
        return {}
    inter = pd.Series(
        [r.get("interactions_24h") or 0 for r in lc_rows], dtype=float)
    rank_pct = inter.rank(pct=True) * 100

    out: dict[str, dict] = {}
    for i, row in enumerate(lc_rows):
        sym = row.get("symbol")
        if not sym:
            continue
        heat = float(rank_pct.iloc[i]) if not inter.empty else 0.0
        galaxy = row.get("galaxy_score")
        galaxy_prev = row.get("galaxy_score_previous")
        if galaxy is not None and galaxy_prev is not None:
            jump = galaxy - galaxy_prev
            if jump >= 4:
                heat = min(100.0, heat + 14)
            elif jump <= -4:
                heat = max(0.0, heat - 8)
        alt, alt_prev = row.get("alt_rank"), row.get("alt_rank_previous")
        if alt is not None and alt_prev is not None and alt_prev - alt >= 80:
            heat = min(100.0, heat + 10)

        sentiment = row.get("sentiment")
        chg = row.get("percent_change_24h")
        direction = 0.0
        if sentiment is not None:
            direction += float(np.clip((sentiment - 50) * 2.6, -75, 75))
        if chg is not None:
            direction += float(np.clip(chg * 2.0, -25, 25))

        out[str(sym).upper()] = {
            "heat": heat,
            "direction": float(np.clip(direction, -100, 100)),
            "galaxy": galaxy,
            "sentiment": sentiment,
            "interactions": row.get("interactions_24h"),
        }
    return out


def _build_news_index(news_df, symbols: list[str],
                       lc_rows: list) -> dict[str, dict]:
    """Per-coin news-catalyst index — fresh headlines naming each coin."""
    out: dict[str, dict] = {}
    if news_df is None or getattr(news_df, "empty", True):
        return out

    lc_name = {str(r.get("symbol", "")).upper(): str(r.get("name", "")).lower()
               for r in lc_rows if r.get("symbol")}
    titles = news_df.copy()
    titles["lower"] = titles["title"].astype(str).str.lower()
    now = pd.Timestamp.now(tz="UTC")

    for sym in symbols:
        base = sym[:-4] if sym.endswith("USDT") else sym
        terms: set[str] = set(COIN_NAMES.get(base, []))
        nm = lc_name.get(base.upper(), "")
        if len(nm) >= 4 and nm not in ("coin", "token"):
            terms.add(nm)
        bl = base.lower()
        if (base not in COIN_NAMES and len(bl) >= 4 and bl.isalpha()
                and bl not in _NAME_STOPWORDS):
            terms.add(bl)
        if not terms:
            continue

        pattern = r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b"
        hits = titles[titles["lower"].str.contains(pattern, regex=True,
                                                   na=False)]
        if hits.empty:
            continue

        weighted_sent, weight_sum, fresh = 0.0, 0.0, 0
        for _, h in hits.head(12).iterrows():
            age_h = max((now - h["published"]).total_seconds() / 3600, 0.1)
            w = 1.0 if age_h <= 6 else 0.6 if age_h <= 18 else 0.3
            weighted_sent += h["sentiment"] * w
            weight_sum += w
            if age_h <= 18:
                fresh += 1
        if weight_sum == 0:
            continue
        avg_sent = weighted_sent / weight_sum
        out[base.upper()] = {
            "score": float(np.clip(len(hits) * 16 + fresh * 14, 0, 100)),
            "direction": float(np.clip(avg_sent * 110, -100, 100)),
            "count": int(len(hits)),
            "fresh": fresh,
            "headline": hits.iloc[0]["title"],
            "sentiment": avg_sent,
        }
    return out


# ===========================================================================
# Market backdrop — the broad-tape context every per-coin read sits inside
# ===========================================================================
def _market_backdrop(fear_greed: int | None, mcap_change: float | None,
                      btc_d4h: pd.DataFrame | None) -> dict:
    """Build the broad-market regime read from Fear & Greed, BTC's 4h trend
    and the 24h move in total crypto market cap.

    A breakout fights or rides this backdrop — a bullish setup in a risk-off
    tape is far less trustworthy than the same setup in a risk-on tape.
    """
    parts: list[tuple[float, float]] = []
    notes: list[str] = []

    fg_word = "unknown"
    if fear_greed is not None:
        parts.append((float(np.clip((fear_greed - 50) / 45 * 100, -100, 100)),
                      0.40))
        fg_word = ("extreme greed" if fear_greed >= 75
                   else "greed" if fear_greed >= 55
                   else "extreme fear" if fear_greed <= 25
                   else "fear" if fear_greed <= 45 else "neutral")
        notes.append(f"Fear & Greed {fear_greed} ({fg_word})")

    btc_lean = 0.0
    if btc_d4h is not None and len(btc_d4h) > 0:
        btc_lean = _tf_lean(btc_d4h)
        parts.append((btc_lean * 90, 0.40))
        notes.append(f"BTC 4h trend "
                     + ("up" if btc_lean > 0.2 else "down" if btc_lean < -0.2
                        else "flat"))

    if mcap_change is not None:
        parts.append((float(np.clip(mcap_change * 14, -100, 100)), 0.20))
        notes.append(f"total market cap {mcap_change:+.2f}% over 24h")

    score = round(_renorm(parts), 1) if parts else 0.0
    label = ("Risk-on" if score >= 22 else "Risk-off" if score <= -22
             else "Neutral / mixed")
    return {
        "score": score,
        "label": label,
        "note": " · ".join(notes) if notes else "market context unavailable",
        "fear_greed": fear_greed,
        "fg_word": fg_word,
        "btc_lean": btc_lean,
        "mcap_change": mcap_change,
    }


# ===========================================================================
# Trade idea — entry zone, stop and exit targets, stage-aware
# ===========================================================================
def _trade_idea(stage: str, dir_word: str, price: float, atr: float,
                win_h: float, win_l: float, ema_fast: float) -> dict:
    """A concrete entry/exit plan tuned to the coin's stage and direction."""
    atr = atr if atr and atr > 0 else price * 0.01

    if dir_word == "BULLISH":
        t1, t2 = price + 2.2 * atr, price + 4.0 * atr
        if stage == "COILED":
            return {
                "side": "LONG", "chasing_risk": False,
                "play": (f"Loading for an upside break. Enter on a 15m close "
                         f"above {_fmt(win_h)} — that confirmation is the "
                         f"lowest-risk entry; or scale in early near "
                         f"{_fmt(win_l + 0.2 * (win_h - win_l))} with a wider "
                         f"stop."),
                "entry_low": win_h, "entry_high": win_h + 0.5 * atr,
                "stop": win_l - 0.5 * atr,
                "target_1": win_h + 2.4 * atr, "target_2": win_h + 4.2 * atr,
                "exit_note": (f"Targets {_fmt(win_h + 2.4 * atr)} then "
                              f"{_fmt(win_h + 4.2 * atr)}. A 15m close back "
                              f"below {_fmt(win_l)} kills the thesis — stand "
                              f"aside or flip."),
            }
        if stage == "FRESH":
            return {
                "side": "LONG", "chasing_risk": False,
                "play": (f"Fresh breakout, still early. Buy the retest into "
                         f"{_fmt(win_h)}–{_fmt(price)} rather than chasing the "
                         f"candle."),
                "entry_low": min(win_h, price - 0.5 * atr),
                "entry_high": price + 0.3 * atr,
                "stop": win_h - 1.3 * atr,
                "target_1": t1, "target_2": t2,
                "exit_note": (f"Scale out — about half at {_fmt(t1)}, the rest "
                              f"at {_fmt(t2)}; move the stop to break-even once "
                              f"target 1 fills."),
            }
        return {                                       # EXTENDED
            "side": "LONG", "chasing_risk": True,
            "play": (f"Already extended — chasing a fresh long here is the "
                     f"risky trade. No new entry; wait for a pullback to "
                     f"{_fmt(ema_fast)} that holds."),
            "entry_low": ema_fast - 0.4 * atr, "entry_high": ema_fast,
            "stop": ema_fast - 1.6 * atr,
            "target_1": price + 1.6 * atr, "target_2": price + 3.0 * atr,
            "exit_note": (f"If already long: trail the stop under "
                          f"{_fmt(ema_fast)} and bank into strength near "
                          f"{_fmt(price + 1.6 * atr)}. Expect a stall or "
                          f"pullback soon."),
        }

    if dir_word == "BEARISH":
        t1, t2 = price - 2.2 * atr, price - 4.0 * atr
        if stage == "COILED":
            return {
                "side": "SHORT", "chasing_risk": False,
                "play": (f"Loading for a downside break. Enter on a 15m close "
                         f"below {_fmt(win_l)} — that confirmation is the "
                         f"lowest-risk short."),
                "entry_low": win_l - 0.5 * atr, "entry_high": win_l,
                "stop": win_h + 0.5 * atr,
                "target_1": win_l - 2.4 * atr, "target_2": win_l - 4.2 * atr,
                "exit_note": (f"Targets {_fmt(win_l - 2.4 * atr)} then "
                              f"{_fmt(win_l - 4.2 * atr)}. A 15m close back "
                              f"above {_fmt(win_h)} kills the thesis."),
            }
        if stage == "FRESH":
            return {
                "side": "SHORT", "chasing_risk": False,
                "play": (f"Fresh breakdown, still early. Short the retrace into "
                         f"{_fmt(price)}–{_fmt(win_l)} rather than the lows."),
                "entry_low": price - 0.3 * atr,
                "entry_high": max(win_l, price + 0.5 * atr),
                "stop": win_l + 1.3 * atr,
                "target_1": t1, "target_2": t2,
                "exit_note": (f"Cover about half at {_fmt(t1)}, the rest at "
                              f"{_fmt(t2)}; move the stop to break-even once "
                              f"target 1 fills."),
            }
        return {                                       # EXTENDED
            "side": "SHORT", "chasing_risk": True,
            "play": (f"Already extended to the downside — shorting the lows "
                     f"here is the risky trade. Wait for a bounce to "
                     f"{_fmt(ema_fast)} that fails."),
            "entry_low": ema_fast, "entry_high": ema_fast + 0.4 * atr,
            "stop": ema_fast + 1.6 * atr,
            "target_1": price - 1.6 * atr, "target_2": price - 3.0 * atr,
            "exit_note": (f"If already short: trail the stop above "
                          f"{_fmt(ema_fast)} and cover into weakness near "
                          f"{_fmt(price - 1.6 * atr)}. Expect a bounce soon."),
        }

    # UNCLEAR — coiled with no directional lean: trade the break either way.
    return {
        "side": "EITHER", "chasing_risk": False,
        "play": (f"Wound tight with no clear lean — trade the break, do not "
                 f"pre-guess. Long above {_fmt(win_h)}, short below "
                 f"{_fmt(win_l)}; stay flat inside."),
        "entry_low": win_l, "entry_high": win_h,
        "stop": None,
        "target_1": win_h + 2.2 * atr, "target_2": win_l - 2.2 * atr,
        "exit_note": (f"Long break → target {_fmt(win_h + 2.2 * atr)}. "
                      f"Short break → target {_fmt(win_l - 2.2 * atr)}."),
    }


# ===========================================================================
# Per-coin analysis
# ===========================================================================
def _analyze(symbol: str, d15: pd.DataFrame, d1h: pd.DataFrame,
             d4h: pd.DataFrame, funding: float | None, social: dict | None,
             news: dict | None, btc_d15: pd.DataFrame | None = None,
             backdrop: dict | None = None) -> dict | None:
    """Score one coin's blowout potential, stage and direction."""
    last = d15.iloc[-1]
    price = float(last["close"])
    atr = float(last["atr"]) if pd.notna(last["atr"]) else price * 0.01
    rsi = float(last["rsi"]) if pd.notna(last["rsi"]) else 50.0
    ema_fast = float(last["ema_fast"]) if pd.notna(last["ema_fast"]) else price

    vol_score, vol_peak, ignition, ignited, vol_note = _volume(d15)
    vlt_score, expanding, vlt_note = _volatility(d15)
    mom_score, mom_note = _momentum(d15, d1h)
    brk_score, win_h, win_l, recent_brk, brk_note = _range_break(d15)
    flow_score, flow_note = _order_flow(d15)
    obv_score, obv_note = _accumulation(d15)
    htf_score, htf_note, regime_4h = _htf_lean(d1h, d4h)
    rs_score, rs_note = _relative_strength(d15, btc_d15)

    # Realized move so far (lagging) and funding fuel (uses realized sign).
    realized = float(np.clip(0.6 * mom_score + 0.4 * brk_score, -100, 100))
    fund_score, fund_note = _funding_fuel(funding, realized)

    soc_heat = float(social["heat"]) if social else 0.0
    soc_dir = float(social["direction"]) if social else 0.0
    news_score = float(news["score"]) if news else 0.0
    news_dir = float(news["direction"]) if news else 0.0

    extension, _ext_note = _extension(d15, win_h, win_l)
    stage = _stage(d15, brk_score, recent_brk, extension, rsi)

    # ENERGY — how loaded the spring is (no realized-move terms).
    e_parts = [(vol_score, 0.34), (vlt_score, 0.30)]
    if social:
        e_parts.append((soc_heat, 0.22))
    if news:
        e_parts.append((news_score, 0.14))
    energy = _renorm(e_parts)

    # LEADING pressure — what hints at the move before price confirms it.
    l_parts = [(flow_score, 0.22), (obv_score, 0.17), (htf_score, 0.19),
               (rs_score, 0.16), (soc_dir, 0.13), (news_dir, 0.13)]
    if funding is not None:
        l_parts.append((fund_score, 0.16))
    leading = float(np.clip(_renorm(l_parts), -100, 100))

    # DIRECTION — a coil leans on leading tells; a fired move on realized price.
    if stage == "COILED":
        direction = float(np.clip(0.72 * leading + 0.28 * realized, -100, 100))
    else:
        direction = float(np.clip(0.55 * realized + 0.45 * leading, -100, 100))

    thresh = 16 if stage == "COILED" else 20
    if direction >= thresh:
        dir_word = "BULLISH"
    elif direction <= -thresh:
        dir_word = "BEARISH"
    else:
        dir_word = "UNCLEAR"

    # Conviction — agreement of the forces that fed the direction.
    comps = ([(realized, 1.0), (leading, 1.0)] if stage != "COILED"
             else [(leading, 1.3), (realized, 0.5)])
    sign = np.sign(direction) or 1
    agree = sum(w for v, w in comps if v != 0 and np.sign(v) == sign)
    total = sum(w for v, w in comps if v != 0) or 1
    confidence = round(min(95.0, abs(direction) * 0.5 + agree / total * 48))
    if stage == "COILED":
        confidence = max(0, confidence - 10)   # a coil is inherently less sure

    # OPPORTUNITY — the headline rank: rewards COILED/FRESH, punishes EXTENDED.
    stage_mult = {"COILED": 1.0, "FRESH": 1.06, "EXTENDED": 0.5}[stage]
    room = 1 - extension / 100
    opportunity = energy * stage_mult * (0.60 + 0.40 * room)
    opportunity += news_score * 0.08
    # Volume igniting off a base while the move is still early is the textbook
    # pre-parabola setup — push it to the very top of the radar.
    if ignited and stage in ("COILED", "FRESH") and extension < 38:
        opportunity += 11
    if dir_word == "UNCLEAR":
        opportunity *= 0.9

    # MARKET BACKDROP — a lean that rides the broad tape is more trustworthy;
    # one that fights it is less so. Modest by design: it tilts, never rules.
    backdrop_note = ""
    if backdrop and dir_word != "UNCLEAR" and abs(backdrop["score"]) >= 22:
        aligned = (backdrop["score"] > 0) == (dir_word == "BULLISH")
        confidence = int(np.clip(confidence + (6 if aligned else -9), 0, 96))
        opportunity += 4 if aligned else -7
        backdrop_note = (
            f"The broad market is {backdrop['label'].lower()} "
            f"({backdrop['note']}), which "
            + ("backs this lean — a tailwind."
               if aligned else
               "works against this lean — treat it as a headwind and size "
               "down."))

    opportunity = float(np.clip(opportunity, 0, 100))

    verdict, emoji = _verdict(stage, dir_word)
    chasing_risk = stage == "EXTENDED"

    c = d15["close"].to_numpy(dtype=float)
    chg1h = (c[-1] / c[-5] - 1) * 100 if len(c) >= 5 else 0.0
    chg4h = (c[-1] / c[-17] - 1) * 100 if len(c) >= 17 else 0.0
    chg24 = (c[-1] / c[-97] - 1) * 100 if len(c) >= 97 else 0.0

    drivers = [
        {"force": "Volume", "score": round(vol_score), "signed": False,
         "note": vol_note},
        {"force": "Volatility", "score": round(vlt_score), "signed": False,
         "note": vlt_note},
        {"force": "Momentum", "score": round(mom_score), "signed": True,
         "note": mom_note},
        {"force": "Range break", "score": round(brk_score), "signed": True,
         "note": brk_note},
        {"force": "Order flow", "score": round(flow_score), "signed": True,
         "note": flow_note},
        {"force": "Accumulation", "score": round(obv_score), "signed": True,
         "note": obv_note},
        {"force": "Multi-TF trend", "score": round(htf_score), "signed": True,
         "note": htf_note},
        {"force": "Rel. strength", "score": round(rs_score), "signed": True,
         "note": rs_note},
        {"force": "Derivatives fuel", "score": round(fund_score),
         "signed": True, "note": fund_note},
    ]
    if social:
        drivers.append({
            "force": "Social heat", "score": round(soc_heat), "signed": False,
            "note": (f"social attention in the {soc_heat:.0f}th percentile of "
                     f"all tracked coins"
                     + (f", sentiment {social['sentiment']:.0f}% positive"
                        if social.get("sentiment") is not None else ""))})
    if news:
        drivers.append({
            "force": "News catalyst", "score": round(news_score),
            "signed": False,
            "note": (f"{news['count']} headline(s) name this coin, "
                     f"{news['fresh']} fresh — “{news['headline'][:88]}”")})

    news_read = _news_read(news)
    summary = _summary(symbol, stage, dir_word, energy, opportunity,
                       extension, confidence, drivers, win_h, win_l, rsi)
    if backdrop_note:
        summary += " " + backdrop_note
    idea = _trade_idea(stage, dir_word, price, atr, win_h, win_l, ema_fast)
    window = _window(stage, expanding)

    return {
        "symbol": symbol,
        "base": symbol[:-4] if symbol.endswith("USDT") else symbol,
        "price": price,
        "atr": atr,
        "rsi": round(rsi, 1),
        "funding": funding,
        "chg_1h": round(chg1h, 2),
        "chg_4h": round(chg4h, 2),
        "chg_24h": round(chg24, 2),
        "energy": round(energy, 1),
        "direction": round(direction, 1),
        "extension": round(extension, 1),
        "opportunity": round(opportunity, 1),
        "confidence": confidence,
        "stage": stage,
        "regime_4h": regime_4h,
        "dir_word": dir_word,
        "verdict": verdict,
        "emoji": emoji,
        "chasing_risk": chasing_risk,
        "ignited": ignited,
        "vol_peak": round(vol_peak, 1),
        "win_high": win_h,
        "win_low": win_l,
        "expanding": expanding,
        "window": window,
        "drivers": drivers,
        "news_read": news_read,
        "summary": summary,
        "idea": idea,
    }


def _verdict(stage: str, dir_word: str) -> tuple[str, str]:
    """Map (stage, direction) to a display verdict string and emoji."""
    if stage == "COILED":
        if dir_word == "BULLISH":
            return "LOADING · BULLISH LEAN", "🔋"
        if dir_word == "BEARISH":
            return "LOADING · BEARISH LEAN", "🔋"
        return "COILED · DIRECTION UNCLEAR", "⚡"
    if stage == "FRESH":
        if dir_word == "BULLISH":
            return "FRESH BULL BREAKOUT", "🚀"
        if dir_word == "BEARISH":
            return "FRESH BEAR BREAKDOWN", "🔻"
        return "FRESH BREAK · UNCLEAR", "⚡"
    if dir_word == "BEARISH":
        return "EXTENDED SHORT · CHASING RISK", "⚠️"
    return "EXTENDED LONG · CHASING RISK", "⚠️"


def _window(stage: str, expanding: bool) -> str:
    """A plain-language estimate of when the move is expected."""
    if stage == "COILED":
        return ("has not fired yet — the coil typically resolves within the "
                "next 1–6 hours; get positioned on the trigger")
    if stage == "FRESH":
        return ("underway now — expect the bulk of the follow-through over the "
                "next 15–90 minutes")
    return ("the move is mature — late-stage; a stall or pullback is more "
            "likely than a clean continuation from here")


def _news_read(news: dict | None) -> str:
    """A one-line news read for the coin."""
    if not news:
        return ("No specific headline catalyst right now — this is a "
                "technical, volume and order-flow setup.")
    tone = ("bullish" if news["sentiment"] >= 0.12
            else "bearish" if news["sentiment"] <= -0.12 else "mixed")
    return (f"{news['count']} headline(s) name this coin "
            f"({news['fresh']} in the last 18h), tone {tone} — latest: "
            f"“{news['headline']}”.")


def _summary(symbol: str, stage: str, dir_word: str, energy: float,
             opportunity: float, extension: float, confidence: int,
             drivers: list, win_h: float, win_l: float, rsi: float) -> str:
    """Synthesise the scores into one expert, stage-aware paragraph."""
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    ranked = sorted(drivers, key=lambda d: abs(d["score"]), reverse=True)
    lead = [d for d in ranked if abs(d["score"]) >= 28][:3] or ranked[:2]
    body = " ".join(f"{d['note'].capitalize()}." for d in lead)

    if stage == "COILED":
        if dir_word == "UNCLEAR":
            head = (f"{base} is wound tight but has not picked a side — the "
                    f"leading tells are mixed. ")
            close = (f"Do not pre-guess it: trade the break above "
                     f"{_fmt(win_h)} or below {_fmt(win_l)}.")
        else:
            way = "an upside" if dir_word == "BULLISH" else "a downside"
            head = (f"{base} is coiled and loading for {way} break — it has "
                    f"NOT fired yet, which is the whole point: this is a "
                    f"predictive, early entry rather than a chase. ")
            lvl = win_h if dir_word == "BULLISH" else win_l
            close = (f"The leading tells (order flow, accumulation, 1h/4h "
                     f"trend, sentiment) lean {dir_word.lower()}; enter on the "
                     f"break of {_fmt(lvl)} for the lowest-risk entry.")
    elif stage == "FRESH":
        way = "higher" if dir_word == "BULLISH" else "lower"
        head = (f"{base} has just broken {way} and is still early — there is "
                f"room left before the move is extended. ")
        close = ("Join the breakout on the retest; this is a continuation "
                 "setup with the move already confirmed.")
    else:  # EXTENDED
        head = (f"{base} has ALREADY made its move — RSI {rsi:.0f}, price "
                f"stretched and {extension:.0f}/100 on the extension gauge. "
                f"Chasing it here is exactly the risky, late trade this radar "
                f"is built to flag. ")
        close = ("Wait for a pullback to value before any fresh entry; "
                 "holders should be trailing stops and banking profit.")

    art = "an" if dir_word == "UNCLEAR" else "a"
    return (f"{head}{body} Opportunity scores {opportunity:.0f}/100 "
            f"(energy {energy:.0f}, extension {extension:.0f}) with {art} "
            f"{dir_word.lower()} read at {confidence}% conviction. {close}")


# ===========================================================================
# Scan entry point
# ===========================================================================
def _fetch(symbol: str):
    """Fetch and enrich 15m + 1h + 4h candles for one symbol.

    15m drives the breakout signal; 1h and 4h supply the higher-timeframe
    trend backdrop a 15m setup resolves into. Enough candles are pulled for
    the 200-period trend EMA to be meaningful on each timeframe.
    """
    try:
        d15 = indicators.enrich(
            binance_client.get_klines(symbol, "15m", limit=220))
        d1h = indicators.enrich(
            binance_client.get_klines(symbol, "1h", limit=240))
        d4h = indicators.enrich(
            binance_client.get_klines(symbol, "4h", limit=260))
        return symbol, d15, d1h, d4h
    except Exception:
        return symbol, None, None, None


def scan(symbols: list[str], funding_map: dict | None = None,
         lc_rows: list | None = None, news_df=None,
         fear_greed: int | None = None,
         mcap_change: float | None = None) -> tuple[pd.DataFrame, dict]:
    """Scan a list of symbols for blowout candidates.

    Returns ``(DataFrame, backdrop)`` — the DataFrame sorted by OPPORTUNITY
    (highest first) and the market-backdrop read every coin was scored
    against. `funding_map`, `lc_rows` (a LunarCrush coin list), `news_df`,
    `fear_greed` and `mcap_change` are optional — the scan degrades
    gracefully when any are missing.
    """
    funding_map = funding_map or {}
    social_idx = _build_social_index(lc_rows or [])
    news_idx = _build_news_index(news_df, symbols, lc_rows or [])

    # Pass 1 — fetch every coin's candles in parallel.
    frames: dict[str, tuple] = {}
    with ThreadPoolExecutor(max_workers=config.SCAN_WORKERS) as pool:
        for symbol, d15, d1h, d4h in pool.map(_fetch, symbols):
            if (d15 is None or d1h is None or d4h is None
                    or len(d15) < 40 or len(d1h) < 26 or len(d4h) < 26):
                continue
            frames[symbol] = (d15, d1h, d4h)

    # The broad-market backdrop, built once, from BTC + Fear & Greed + mcap.
    btc = frames.get("BTCUSDT")
    btc_d15 = btc[0] if btc else None
    btc_d4h = btc[2] if btc else None
    backdrop = _market_backdrop(fear_greed, mcap_change, btc_d4h)

    # Pass 2 — score every coin against that backdrop and the BTC reference.
    rows: list[dict] = []
    for symbol, (d15, d1h, d4h) in frames.items():
        base = symbol[:-4] if symbol.endswith("USDT") else symbol
        try:
            res = _analyze(symbol, d15, d1h, d4h, funding_map.get(symbol),
                           social_idx.get(base.upper()),
                           news_idx.get(base.upper()), btc_d15, backdrop)
        except Exception:
            res = None
        if res:
            rows.append(res)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(
            "opportunity", ascending=False).reset_index(drop=True)
    return df, backdrop
