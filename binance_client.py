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


def _get(path: str, params: dict | None = None,
         max_attempts: int = 4) -> object:
    """GET a Binance endpoint with rate-limit handling.

    On HTTP 418 (IP banned briefly) or 429 (rate-limited), waits with
    exponential backoff (1s -> 2s -> 4s) and retries. Cycles through
    base URLs on each attempt so a rate-limited mirror gets skipped.
    """
    global _active_base
    bases = config.BINANCE_BASES
    if _active_base:  # try the known-good base first
        bases = [_active_base] + [b for b in bases if b != _active_base]

    last_err: Exception | None = None
    for attempt in range(max_attempts):
        for base in bases:
            try:
                resp = _session.get(base + path, params=params,
                                    timeout=config.HTTP_TIMEOUT)
                if resp.status_code == 200:
                    _active_base = base
                    return resp.json()
                # 418 = IP banned briefly; 429 = rate-limited.
                # Sleep longer, then retry this attempt loop on the
                # OUTER iteration (so we don't burn through bases).
                if resp.status_code in (418, 429):
                    last_err = BinanceError(
                        f"{base}{path} -> HTTP {resp.status_code} "
                        f"(rate-limited, attempt {attempt+1}/{max_attempts})")
                    break  # break base loop, sleep+retry on attempt loop
                last_err = BinanceError(
                    f"{base}{path} -> HTTP {resp.status_code}")
            except requests.RequestException as exc:  # network / timeout
                last_err = exc
            time.sleep(0.2)
        else:
            # All bases tried for this attempt and none returned 200.
            # If it wasn't a rate-limit, no point retrying — fall through.
            if last_err and "rate-limited" not in str(last_err):
                break
        # Rate-limit hit on this attempt — exponential backoff.
        # Binance 418s need ~10-30s to clear; be patient.
        if attempt < max_attempts - 1:
            backoff = 2.0 * (2 ** attempt)  # 2s, 4s, 8s, 16s
            time.sleep(backoff)
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


def get_ticker_price(symbol: str) -> float | None:
    """Latest spot price for one symbol — the cheapest live-price endpoint.

    Used by the Paper Trader to refresh open-position prices every few
    seconds without paying for a 100-row klines fetch. Returns None if the
    symbol has no public price.
    """
    try:
        data = _get("/api/v3/ticker/price", {"symbol": symbol})
        return float(data["price"])
    except (BinanceError, KeyError, TypeError, ValueError):
        return None


_BYBIT_TF = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "4h": "240", "6h": "360",
    "12h": "720", "1d": "D", "1w": "W",
}


def _bybit_klines(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    """Fallback klines fetch via Bybit's public v5 endpoint.

    No auth required. Returns a DataFrame matching the Binance get_klines
    output shape — same columns, same UTC datetime index, so callers
    don't need to special-case the source. Taker_base is NOT available on
    Bybit's kline endpoint, so we approximate it as volume * 0.5 (neutral
    buy-pressure assumption) — the only downstream consumer (CVD
    derivation in indicators.enrich) will produce a neutral signal when
    we don't know the real split, which is safer than crashing.
    """
    tf = _BYBIT_TF.get(interval)
    if tf is None:
        raise BinanceError(f"Bybit fallback: interval {interval} unsupported")
    url = "https://api.bybit.com/v5/market/kline"
    params = {
        "category": "linear", "symbol": symbol,
        "interval": tf, "limit": min(int(limit), 1000),
    }
    resp = _session.get(url, params=params, timeout=config.HTTP_TIMEOUT)
    if resp.status_code != 200:
        raise BinanceError(
            f"Bybit fallback HTTP {resp.status_code} for {symbol}")
    data = (resp.json() or {}).get("result", {}).get("list") or []
    if not data:
        raise BinanceError(f"Bybit fallback: no klines for {symbol}")
    # Bybit returns NEWEST first; reverse to oldest-first (Binance order).
    data = list(reversed(data))
    rows = []
    for row in data:
        try:
            o, h, l, c, v = (float(row[1]), float(row[2]), float(row[3]),
                             float(row[4]), float(row[5]))
            qv = float(row[6]) if len(row) > 6 else v * c
            rows.append({
                "open_time": pd.to_datetime(int(row[0]), unit="ms", utc=True),
                "open": o, "high": h, "low": l, "close": c,
                "volume": v, "quote_volume": qv,
                "trades": 0.0,
                # Approximate taker_base — see docstring.
                "taker_base": v * 0.5,
            })
        except (ValueError, IndexError, TypeError):
            continue
    if not rows:
        raise BinanceError(f"Bybit fallback: malformed data for {symbol}")
    df = pd.DataFrame(rows).set_index("open_time")
    num = ["open", "high", "low", "close", "volume", "quote_volume",
           "trades", "taker_base"]
    return df[num]


def get_klines(symbol: str, interval: str,
               limit: int = config.KLINE_LIMIT) -> pd.DataFrame:
    """Return OHLCV candles for a symbol/interval as a DataFrame.

    Tries Binance first; falls back to Bybit's public v5 endpoint if
    Binance is rate-limited or unavailable. Same return shape regardless
    of source.

    Index is the candle open time (UTC). Columns: open, high, low, close,
    volume, quote_volume, trades.
    """
    try:
        raw = _get(
            "/api/v3/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
        )
        if not raw:
            raise BinanceError(f"No klines for {symbol} {interval}")
    except BinanceError:
        # Binance failed (rate-limit, network, etc.) — try Bybit.
        return _bybit_klines(symbol, interval, limit)

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
