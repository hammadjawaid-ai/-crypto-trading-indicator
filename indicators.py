"""Technical-analysis indicators computed with pandas/numpy.

Every function takes/returns pandas objects so they compose cleanly. The
public entry point is `enrich`, which adds all indicator columns to an OHLCV
DataFrame produced by `binance_client.get_klines`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(close: pd.Series, period: int = config.RSI_PERIOD) -> pd.Series:
    """Wilder's Relative Strength Index (0-100)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder smoothing == EMA with alpha = 1/period
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)  # neutral when undefined


def macd(close: pd.Series) -> pd.DataFrame:
    """MACD line, signal line and histogram."""
    fast = ema(close, config.MACD_FAST)
    slow = ema(close, config.MACD_SLOW)
    line = fast - slow
    signal = ema(line, config.MACD_SIGNAL)
    return pd.DataFrame(
        {"macd": line, "macd_signal": signal, "macd_hist": line - signal}
    )


def bollinger(close: pd.Series, period: int = config.BB_PERIOD,
              n_std: float = config.BB_STD) -> pd.DataFrame:
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + n_std * std
    lower = mid - n_std * std
    width = (upper - lower) / mid.replace(0, np.nan)
    # %B: where price sits inside the bands (0 = lower, 1 = upper)
    pct_b = (close - lower) / (upper - lower).replace(0, np.nan)
    return pd.DataFrame(
        {"bb_upper": upper, "bb_mid": mid, "bb_lower": lower,
         "bb_width": width, "bb_pct": pct_b}
    )


def atr(df: pd.DataFrame, period: int = config.ATR_PERIOD) -> pd.Series:
    """Average True Range (absolute price units)."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False).mean()


def stochastic(df: pd.DataFrame, period: int = config.STOCH_PERIOD) -> pd.Series:
    """Stochastic %K oscillator (0-100)."""
    low_n = df["low"].rolling(period).min()
    high_n = df["high"].rolling(period).max()
    k = 100 * (df["close"] - low_n) / (high_n - low_n).replace(0, np.nan)
    return k.fillna(50)


def adx(df: pd.DataFrame, period: int = config.ADX_PERIOD) -> pd.DataFrame:
    """Average Directional Index with +DI / -DI (Wilder).

    ADX measures trend *strength* (not direction): high ADX == a real trend
    where trend-following signals are reliable, low ADX == a chop/range.
    """
    high, low, close = df["high"], df["low"], df["close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr_ = true_range.ewm(alpha=1 / period, adjust=False).mean()

    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False).mean()
                     / atr_.replace(0, np.nan))
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False).mean()
                      / atr_.replace(0, np.nan))
    dx = 100 * ((plus_di - minus_di).abs()
                / (plus_di + minus_di).replace(0, np.nan))
    adx_ = dx.ewm(alpha=1 / period, adjust=False).mean()
    return pd.DataFrame(
        {"adx": adx_, "plus_di": plus_di, "minus_di": minus_di}
    )


def vwap(df: pd.DataFrame, period: int = config.VWAP_PERIOD) -> pd.Series:
    """Rolling volume-weighted average price — the volume 'fair value' line."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    pv = (typical * df["volume"]).rolling(period).sum()
    vol = df["volume"].rolling(period).sum().replace(0, np.nan)
    return pv / vol


def obv(df: pd.DataFrame) -> pd.Series:
    """On-balance volume — cumulative volume signed by candle direction."""
    direction = np.sign(df["close"].diff()).fillna(0.0)
    return (direction * df["volume"]).cumsum()


def swing_levels(df: pd.DataFrame, window: int = 4,
                 lookback: int = 140) -> tuple[list[float], list[float]]:
    """Find recent pivot lows (support) and pivot highs (resistance).

    A pivot is a candle whose high/low is the extreme of the surrounding
    +/-`window` candles — the swing points price has reacted to before.
    """
    recent = df.tail(lookback)
    highs = recent["high"].to_numpy()
    lows = recent["low"].to_numpy()
    supports: list[float] = []
    resistances: list[float] = []
    for i in range(window, len(recent) - window):
        seg_hi = highs[i - window:i + window + 1]
        seg_lo = lows[i - window:i + window + 1]
        if highs[i] >= seg_hi.max():
            resistances.append(float(highs[i]))
        if lows[i] <= seg_lo.min():
            supports.append(float(lows[i]))
    return sorted(set(supports)), sorted(set(resistances))


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of an OHLCV DataFrame with all indicator columns added."""
    out = df.copy()
    close = out["close"]

    out["ema_fast"] = ema(close, config.EMA_FAST)
    out["ema_slow"] = ema(close, config.EMA_SLOW)
    out["ema_trend"] = ema(close, config.EMA_TREND)
    out["rsi"] = rsi(close)
    out = out.join(macd(close))
    out = out.join(bollinger(close))
    out["atr"] = atr(out)
    out["atr_pct"] = out["atr"] / close.replace(0, np.nan) * 100
    out["stoch"] = stochastic(out)
    out["vol_ma"] = out["volume"].rolling(config.VOLUME_MA).mean()
    out["vol_ratio"] = out["volume"] / out["vol_ma"].replace(0, np.nan)
    out = out.join(adx(out))
    out["vwap"] = vwap(out)
    out["obv"] = obv(out)
    # Per-candle buy pressure: taker-buy volume as a share of total volume.
    if "taker_base" in out.columns:
        out["buy_pressure"] = (
            out["taker_base"] / out["volume"].replace(0, np.nan)
        ).clip(0, 1)
    else:
        out["buy_pressure"] = np.nan
    return out
