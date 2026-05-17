"""Binance public market-data client (no API key required)."""
from __future__ import annotations

import time

import pandas as pd
import requests

import config

_session = requests.Session()
_session.headers.update({"User-Agent": "crypto-indicator/1.0"})

# Remember which base URL last worked so we don't retry dead ones every call.
_active_base: str | None = None


class BinanceError(RuntimeError):
    """Raised when no Binance endpoint could satisfy a request."""


def _get(path: str, params: dict | None = None) -> object:
    """GET a Binance endpoint, trying each base URL until one responds."""
    global _active_base
    bases = config.BINANCE_BASES
    if _active_base:  # try the known-good base first
        bases = [_active_base] + [b for b in bases if b != _active_base]

    last_err: Exception | None = None
    for base in bases:
        try:
            resp = _session.get(base + path, params=params,
                                timeout=config.HTTP_TIMEOUT)
            if resp.status_code == 200:
                _active_base = base
                return resp.json()
            last_err = BinanceError(f"{base}{path} -> HTTP {resp.status_code}")
        except requests.RequestException as exc:  # network / timeout
            last_err = exc
        time.sleep(0.2)
    raise BinanceError(f"All Binance endpoints failed for {path}: {last_err}")


def _is_tradeable(symbol: str, base: str) -> bool:
    """Filter out leveraged tokens and stablecoin-vs-stablecoin pairs."""
    if any(tok in symbol for tok in config.EXCLUDE_SUBSTRINGS):
        return False
    if base in config.EXCLUDE_BASES:
        return False
    return True


def get_top_symbols(n: int = config.TOP_N) -> pd.DataFrame:
    """Return the top-n USDT pairs ranked by 24h quote volume.

    Columns: symbol, base, lastPrice, priceChangePercent, quoteVolume,
    highPrice, lowPrice.
    """
    data = _get("/api/v3/ticker/24hr")
    rows = []
    suffix = config.QUOTE_ASSET
    for item in data:
        sym = item["symbol"]
        if not sym.endswith(suffix):
            continue
        base = sym[: -len(suffix)]
        if not _is_tradeable(sym, base):
            continue
        rows.append(
            {
                "symbol": sym,
                "base": base,
                "lastPrice": float(item["lastPrice"]),
                "priceChangePercent": float(item["priceChangePercent"]),
                "quoteVolume": float(item["quoteVolume"]),
                "highPrice": float(item["highPrice"]),
                "lowPrice": float(item["lowPrice"]),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        raise BinanceError("No USDT pairs returned by Binance ticker endpoint.")
    df = df.sort_values("quoteVolume", ascending=False).head(n)
    return df.reset_index(drop=True)


def get_klines(symbol: str, interval: str,
               limit: int = config.KLINE_LIMIT) -> pd.DataFrame:
    """Return OHLCV candles for a symbol/interval as a DataFrame.

    Index is the candle open time (UTC). Columns: open, high, low, close,
    volume, quote_volume, trades.
    """
    raw = _get(
        "/api/v3/klines",
        {"symbol": symbol, "interval": interval, "limit": limit},
    )
    if not raw:
        raise BinanceError(f"No klines for {symbol} {interval}")

    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_base", "taker_quote", "ignore",
    ]
    df = pd.DataFrame(raw, columns=cols)
    # taker_base is the taker BUY base volume — kept so indicators can derive
    # per-candle buy pressure without an extra request.
    num = ["open", "high", "low", "close", "volume", "quote_volume",
           "trades", "taker_base"]
    df[num] = df[num].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("open_time")[num]
    return df


def get_recent_trades(symbol: str,
                      limit: int = config.ORDERFLOW_TRADES_LIMIT) -> pd.DataFrame:
    """Return the most recent executed trades for a symbol.

    Columns: price, qty, quote_qty, time, is_buyer_maker. `is_buyer_maker`
    True means the trade hit the bid (an aggressive SELL); False means it
    lifted the ask (an aggressive BUY).
    """
    raw = _get("/api/v3/trades", {"symbol": symbol, "limit": limit})
    if not raw:
        raise BinanceError(f"No recent trades for {symbol}")
    df = pd.DataFrame(raw)
    for col in ("price", "qty", "quoteQty"):
        df[col] = df[col].astype(float)
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    return df.rename(columns={"quoteQty": "quote_qty",
                              "isBuyerMaker": "is_buyer_maker"})[
        ["price", "qty", "quote_qty", "time", "is_buyer_maker"]]


def get_depth(symbol: str,
              limit: int = config.ORDERFLOW_DEPTH_LIMIT) -> dict:
    """Return an order-book snapshot as {"bids": DataFrame, "asks": DataFrame}.

    Each DataFrame has price/qty columns, bids sorted high→low, asks low→high.
    """
    raw = _get("/api/v3/depth", {"symbol": symbol, "limit": limit})

    def _side(rows: list) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame(columns=["price", "qty"])
        return pd.DataFrame(rows, columns=["price", "qty"]).astype(float)

    return {"bids": _side(raw.get("bids", [])),
            "asks": _side(raw.get("asks", []))}
