"""Multi-horizon price-direction forecaster (1h / 4h / 1d).

HONEST SCOPE — read this before trusting it:
  - This predicts a probabilistic DIRECTIONAL LEAN and an EXPECTED
    ATR-based move per horizon. It is NOT a price oracle. Crypto is
    not reliably predictable to an exact price; anyone claiming
    otherwise is selling something.
  - The "projected" price is `entry × (1 + strength × ATR%)` — a
    typical-move estimate, not a target. Treat the DIRECTION and the
    CONFIDENCE as the signal; treat the price as a rough envelope.

Method per horizon (computed from that horizon's own klines):
  - Trend     : EMA20 vs EMA50 stack + EMA20 slope
  - Momentum  : RSI(14) position + MACD histogram sign/slope
  - Structure : higher-highs / lower-lows over last 10 bars
  - Volatility: ATR% sizes the expected move
Each contributes to a -100..+100 score; the sign is the direction,
the magnitude scales confidence and the expected move.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import binance_client

_HORIZONS = (("15m", "15m", 200), ("1h", "1h", 200),
             ("4h", "4h", 200), ("1d", "1d", 200))


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi(close: pd.Series, n: int = 14) -> float:
    d = close.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    v = rsi.iloc[-1]
    return float(v) if pd.notna(v) else 50.0


def _atr_pct(df: pd.DataFrame, n: int = 14) -> float:
    high, low, close = df["high"], df["low"], df["close"]
    pc = close.shift(1)
    tr = pd.concat([high - low, (high - pc).abs(),
                    (low - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n).mean().iloc[-1]
    price = float(close.iloc[-1])
    return float(atr / price * 100) if price > 0 and pd.notna(atr) else 0.0


def _score_one_tf(df: pd.DataFrame) -> dict:
    """Score a single timeframe → directional lean + drivers."""
    if df is None or len(df) < 60:
        return {"score": 0.0, "confidence": 0, "drivers": [],
                "atr_pct": 0.0, "price": 0.0}
    close = df["close"]
    price = float(close.iloc[-1])
    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    e20, e50 = float(ema20.iloc[-1]), float(ema50.iloc[-1])
    score = 0.0
    drivers = []

    # Trend stack (±35)
    if price > e20 > e50:
        score += 30
        drivers.append("price > EMA20 > EMA50 (uptrend)")
    elif price < e20 < e50:
        score -= 30
        drivers.append("price < EMA20 < EMA50 (downtrend)")
    elif price > e20:
        score += 10
    elif price < e20:
        score -= 10
    # EMA20 slope over 10 bars (±15)
    if len(ema20) >= 11 and ema20.iloc[-11] > 0:
        slope = (e20 - float(ema20.iloc[-11])) / float(ema20.iloc[-11])
        score += float(np.clip(slope * 600, -15, 15))
        if abs(slope) > 0.004:
            drivers.append(
                f"EMA20 {'rising' if slope > 0 else 'falling'} "
                f"{slope*100:+.1f}%")

    # Momentum — RSI (±20)
    rsi = _rsi(close)
    if rsi >= 55:
        score += min(20, (rsi - 50))
        drivers.append(f"RSI {rsi:.0f} (bullish momentum)")
    elif rsi <= 45:
        score -= min(20, (50 - rsi))
        drivers.append(f"RSI {rsi:.0f} (bearish momentum)")
    if rsi >= 78:
        score -= 10
        drivers.append("RSI overbought — exhaustion risk")
    elif rsi <= 22:
        score += 10
        drivers.append("RSI oversold — bounce risk")

    # MACD histogram sign + slope (±18)
    macd = _ema(close, 12) - _ema(close, 26)
    sig = _ema(macd, 9)
    hist = macd - sig
    h_now = float(hist.iloc[-1])
    h_prev = float(hist.iloc[-2]) if len(hist) >= 2 else h_now
    if h_now > 0:
        score += 9
    elif h_now < 0:
        score -= 9
    if h_now > h_prev:
        score += 9
        drivers.append("MACD histogram rising")
    elif h_now < h_prev:
        score -= 9
        drivers.append("MACD histogram falling")

    # Structure — HH/LL over last 10 bars (±12)
    recent = df.iloc[-11:]
    hh = recent["high"].iloc[-1] >= recent["high"].iloc[:-1].max()
    ll = recent["low"].iloc[-1] <= recent["low"].iloc[:-1].min()
    if hh and not ll:
        score += 12
        drivers.append("printing higher highs")
    elif ll and not hh:
        score -= 12
        drivers.append("printing lower lows")

    score = float(np.clip(score, -100, 100))
    confidence = int(min(95, 40 + abs(score) * 0.55))
    return {"score": round(score, 1), "confidence": confidence,
            "drivers": drivers[:4], "atr_pct": _atr_pct(df),
            "price": price}


def _word(score: float) -> str:
    if score >= 22:
        return "Bullish"
    if score <= -22:
        return "Bearish"
    return "Neutral"


def predict(symbol: str,
            klines_by_tf: dict | None = None) -> dict:
    """Forecast 1h / 4h / 1d for one symbol.

    klines_by_tf: optional {"1h": df, "4h": df, "1d": df} to avoid
    refetching. Missing TFs are fetched via binance_client.

    Returns:
      {
        "symbol": str,
        "horizons": {"1h": {...}, "4h": {...}, "1d": {...}},
        "outlook": "Bullish" | "Bearish" | "Mixed" | "Neutral",
        "summary": "1h ↑ · 4h ↑ · 1d → (aligned bullish, 71%)",
        "aligned": bool,
      }
    Each horizon: direction, score, confidence, move_pct, projected,
    range_pct, drivers.
    """
    klines_by_tf = klines_by_tf or {}
    horizons = {}
    dirs = []
    confs = []
    for tf, interval, limit in _HORIZONS:
        df = klines_by_tf.get(tf)
        if df is None:
            try:
                df = binance_client.get_klines(symbol, interval,
                                              limit=limit)
            except Exception:
                df = None
        s = _score_one_tf(df)
        price = s["price"]
        strength = s["score"] / 100.0
        move_pct = strength * s["atr_pct"]
        horizons[tf] = {
            "direction": _word(s["score"]),
            "score": s["score"],
            "confidence": s["confidence"],
            "range_pct": round(s["atr_pct"], 2),
            "move_pct": round(move_pct, 2),
            "projected": round(price * (1 + move_pct / 100.0), 8)
            if price else 0.0,
            "drivers": s["drivers"],
        }
        if s["price"]:
            dirs.append(horizons[tf]["direction"])
            confs.append(s["confidence"])

    arrow = {"Bullish": "↑", "Bearish": "↓", "Neutral": "→"}
    if not dirs:
        return {"symbol": symbol, "horizons": horizons,
                "outlook": "No data", "summary": "no data",
                "aligned": False}
    ups = dirs.count("Bullish")
    downs = dirs.count("Bearish")
    n = len(dirs)
    if ups == n:
        outlook = "Bullish"
    elif downs == n:
        outlook = "Bearish"
    elif ups > downs:
        outlook = "Leaning bullish"
    elif downs > ups:
        outlook = "Leaning bearish"
    else:
        outlook = "Mixed"
    aligned = (ups == n or downs == n)
    avg_conf = round(sum(confs) / len(confs)) if confs else 0
    summary = (
        " · ".join(f"{tf} {arrow.get(horizons[tf]['direction'], '→')}"
                   for tf, _i, _l in _HORIZONS if tf in horizons)
        + f"  ({outlook.lower()}, {avg_conf}%)")
    return {"symbol": symbol, "horizons": horizons, "outlook": outlook,
            "summary": summary, "aligned": aligned,
            "confidence": avg_conf}
