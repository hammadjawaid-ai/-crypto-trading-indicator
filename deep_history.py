"""Deep kline history via pagination — RESEARCH ONLY (not used by the app).

Discovery (2026-07-07): Binance /api/v3/klines caps at 1000 candles per
request, and binance_client.get_klines passes `limit` straight through — so
EVERY backtest to date silently ran on ~1000 1h bars (~41 days), regardless
of the limit requested. This module paginates backward with endTime to fetch
months of true history, mirroring get_klines' exact output shape.

Used by backtest harnesses for genuinely long, disjoint-time validation.
"""
from __future__ import annotations

import pandas as pd

import binance_client


def get_klines_deep(symbol: str, interval: str, bars: int) -> pd.DataFrame:
    """Fetch up to `bars` candles by paginating backward (1000/page).

    Returns the same shape as binance_client.get_klines: index = open_time
    (UTC), columns open/high/low/close/volume/quote_volume/trades/taker_base.
    Raises BinanceError if nothing could be fetched.
    """
    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_base", "taker_quote", "ignore",
    ]
    num = ["open", "high", "low", "close", "volume", "quote_volume",
           "trades", "taker_base"]
    pages: list[pd.DataFrame] = []
    got = 0
    end_time: int | None = None
    while got < bars:
        params = {"symbol": symbol, "interval": interval,
                  "limit": min(1000, bars - got)}
        if end_time is not None:
            params["endTime"] = end_time
        raw = binance_client._get("/api/v3/klines", params)
        if not raw:
            break
        df = pd.DataFrame(raw, columns=cols)
        df[num] = df[num].astype(float)
        df["open_time_ms"] = df["open_time"].astype("int64")
        pages.append(df)
        got += len(df)
        oldest = int(df["open_time_ms"].iloc[0])
        end_time = oldest - 1
        if len(raw) < 1000:          # reached the start of listing history
            break
    if not pages:
        raise binance_client.BinanceError(
            f"No deep klines for {symbol} {interval}")
    full = pd.concat(pages, ignore_index=True)
    full = full.drop_duplicates(subset="open_time_ms").sort_values(
        "open_time_ms")
    full["open_time"] = pd.to_datetime(full["open_time_ms"], unit="ms",
                                       utc=True)
    out = full.set_index("open_time")[num]
    return out.tail(bars)
