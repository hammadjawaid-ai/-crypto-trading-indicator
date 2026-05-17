"""TradingView technical-rating data via the tradingview-ta library.

Exposes TradingView's own consolidated recommendation (Strong Buy .. Strong
Sell) plus its oscillator and moving-average sub-ratings — an independent,
expert cross-check alongside the in-house signal engine. `config` is imported
first so truststore routes TLS through the OS certificate store (needed behind
the corporate proxy).
"""
from __future__ import annotations

import config  # noqa: F401 — imported for the truststore SSL side effect
from tradingview_ta import Interval, get_multiple_analysis

# Map the app's timeframes onto tradingview-ta intervals.
_INTERVALS = {
    "15m": Interval.INTERVAL_15_MINUTES,
    "1h": Interval.INTERVAL_1_HOUR,
    "4h": Interval.INTERVAL_4_HOURS,
    "1d": Interval.INTERVAL_1_DAY,
}

# TradingView recommendation string -> -100..+100 score.
REC_SCORE = {
    "STRONG_BUY": 100, "BUY": 50, "NEUTRAL": 0,
    "SELL": -50, "STRONG_SELL": -100,
}


def _pretty(rec: str) -> str:
    return (rec or "NEUTRAL").replace("_", " ").title()


def _pack(analysis) -> dict | None:
    if analysis is None:
        return None
    summary = analysis.summary
    rec = summary.get("RECOMMENDATION", "NEUTRAL")
    return {
        "recommendation": _pretty(rec),
        "score": REC_SCORE.get(rec, 0),
        "buy": int(summary.get("BUY", 0)),
        "sell": int(summary.get("SELL", 0)),
        "neutral": int(summary.get("NEUTRAL", 0)),
        "oscillators": _pretty(
            analysis.oscillators.get("RECOMMENDATION", "NEUTRAL")),
        "moving_averages": _pretty(
            analysis.moving_averages.get("RECOMMENDATION", "NEUTRAL")),
    }


_BATCH = 50  # symbols per TradingView scanner request


def get_ratings(symbols: list[str], interval: str,
                exchange: str = "BINANCE") -> dict[str, dict]:
    """Batch TradingView ratings for many symbols, in chunks of 50.

    Returns {symbol: rating} keyed by the bare symbol (e.g. "BTCUSDT").
    Symbols TradingView has no data for are simply omitted.
    """
    tv_interval = _INTERVALS.get(interval, Interval.INTERVAL_4_HOURS)
    out: dict[str, dict] = {}
    for start in range(0, len(symbols), _BATCH):
        chunk = symbols[start:start + _BATCH]
        tickers = [f"{exchange}:{s}" for s in chunk]
        try:
            raw = get_multiple_analysis(screener="crypto",
                                        interval=tv_interval,
                                        symbols=tickers)
        except Exception:
            continue  # skip a failed chunk, keep the rest
        for ticker, analysis in (raw or {}).items():
            packed = _pack(analysis)
            if packed:
                out[ticker.split(":", 1)[-1]] = packed
    return out


def get_rating(symbol: str, interval: str,
               exchange: str = "BINANCE") -> dict | None:
    """TradingView rating for one symbol/interval, or None on failure."""
    return get_ratings([symbol], interval, exchange).get(symbol)
