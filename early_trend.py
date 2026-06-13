"""Early-trend emergence detector — catch moves as they START.

USER NEED: catch coins turning bullish/bearish EARLY (e.g. TAO ripping)
that the proven lanes miss until the move is half-done. This is the
AGGRESSIVE lane — it fires on the FIRST signs of a trend turning,
trading confirmation for earliness.

HONEST TRADE-OFF: earlier entry = less confirmation = lower win rate
than the proven lanes. This lane is for the user who explicitly wants
to be aggressive and catch the start. It is surfaced as its own
clearly-labelled aggressive board, NEVER mixed into the proven picks.

A turn is "emerging" when several of these flip together on the 1h:
  - Price reclaims EMA20 (crosses above for a LONG, below for SHORT)
  - EMA20 slope turning in the new direction
  - RSI crossing back through 50 with momentum
  - MACD histogram flipping sign (or accelerating in-direction)
  - Volume picking up vs the 20-bar average (conviction behind the move)
  - Short-term ROC accelerating

Score 0-100: more confirmations + stronger readings = higher. Side is
the emerging direction.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import binance_client


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def detect(df: pd.DataFrame) -> tuple[float, str, str]:
    """Detect an emerging trend on the given klines.

    Returns (score, side, note). score 0-100, side LONG/SHORT/NEUTRAL.
    """
    if df is None or len(df) < 60:
        return 0.0, "NEUTRAL", ""
    close = df["close"]
    vol = df["volume"]
    price = float(close.iloc[-1])
    if price <= 0:
        return 0.0, "NEUTRAL", ""

    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    e20 = float(ema20.iloc[-1])
    e20_prev = float(ema20.iloc[-4]) if len(ema20) >= 4 else e20
    e50 = float(ema50.iloc[-1])

    # RSI
    d = close.diff()
    up = d.clip(lower=0).rolling(14).mean()
    dn = (-d.clip(upper=0)).rolling(14).mean()
    rs = up / dn.replace(0, np.nan)
    rsi_series = 100 - 100 / (1 + rs)
    rsi = float(rsi_series.iloc[-1]) if pd.notna(
        rsi_series.iloc[-1]) else 50.0
    rsi_prev = float(rsi_series.iloc[-4]) if len(
        rsi_series) >= 4 and pd.notna(rsi_series.iloc[-4]) else rsi

    # MACD histogram
    macd = _ema(close, 12) - _ema(close, 26)
    sig = _ema(macd, 9)
    hist = macd - sig
    h_now = float(hist.iloc[-1])
    h_prev = float(hist.iloc[-3]) if len(hist) >= 3 else h_now

    # Volume pickup
    vol_now = float(vol.iloc[-3:].mean() or 0)
    vol_avg = float(vol.iloc[-23:-3].mean() or 0)
    vol_ratio = (vol_now / vol_avg) if vol_avg > 0 else 1.0

    # Short-term ROC (last 6 bars)
    c6 = float(close.iloc[-7]) if len(close) >= 7 else price
    roc6 = (price / c6 - 1.0) if c6 > 0 else 0.0

    # ---- Build the LONG case ----
    long_pts = 0.0
    long_notes = []
    if price > e20 and price <= e20 * 1.04:    # just reclaimed, not extended
        long_pts += 22
        long_notes.append("reclaimed EMA20")
    if e20 > e20_prev:
        long_pts += 14
        long_notes.append("EMA20 turning up")
    if 50 <= rsi <= 68 and rsi > rsi_prev:
        long_pts += 16
        long_notes.append(f"RSI crossed up ({rsi:.0f})")
    if h_now > 0 and h_now > h_prev:
        long_pts += 16
        long_notes.append("MACD flipped positive")
    elif h_now > h_prev:
        long_pts += 8
        long_notes.append("MACD accelerating up")
    if vol_ratio >= 1.5:
        long_pts += 14
        long_notes.append(f"volume {vol_ratio:.1f}x avg")
    if 0.01 <= roc6 <= 0.08:
        long_pts += 10
        long_notes.append(f"+{roc6*100:.1f}% over 6 bars")

    # ---- Build the SHORT case ----
    short_pts = 0.0
    short_notes = []
    if price < e20 and price >= e20 * 0.96:
        short_pts += 22
        short_notes.append("lost EMA20")
    if e20 < e20_prev:
        short_pts += 14
        short_notes.append("EMA20 turning down")
    if 32 <= rsi <= 50 and rsi < rsi_prev:
        short_pts += 16
        short_notes.append(f"RSI crossed down ({rsi:.0f})")
    if h_now < 0 and h_now < h_prev:
        short_pts += 16
        short_notes.append("MACD flipped negative")
    elif h_now < h_prev:
        short_pts += 8
        short_notes.append("MACD accelerating down")
    if vol_ratio >= 1.5:
        short_pts += 14
        short_notes.append(f"volume {vol_ratio:.1f}x avg")
    if -0.08 <= roc6 <= -0.01:
        short_pts += 10
        short_notes.append(f"{roc6*100:.1f}% over 6 bars")

    if long_pts >= short_pts and long_pts >= 40:
        return (round(float(np.clip(long_pts, 0, 100)), 1), "LONG",
                " · ".join(long_notes))
    if short_pts > long_pts and short_pts >= 40:
        return (round(float(np.clip(short_pts, 0, 100)), 1), "SHORT",
                " · ".join(short_notes))
    return 0.0, "NEUTRAL", ""


def lane_early_trend(df: pd.DataFrame) -> tuple[float, str, str]:
    """ELITE-composite-compatible entrypoint."""
    return detect(df)


def scan(symbols: list[str], interval: str = "1h",
         min_score: float = 50.0,
         max_results: int = 20) -> list[dict]:
    """Standalone scan for the aggressive Early Momentum board.

    Returns a list of dicts sorted by score:
      {symbol, base, side, score, note, price}
    """
    out = []
    for sym in symbols:
        try:
            df = binance_client.get_klines(sym, interval, limit=120)
        except Exception:
            continue
        score, side, note = detect(df)
        if score >= min_score and side in ("LONG", "SHORT"):
            out.append({
                "symbol": sym,
                "base": sym.replace("USDT", ""),
                "side": side,
                "score": score,
                "note": note,
                "price": float(df["close"].iloc[-1]),
            })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:max_results]
