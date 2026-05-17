"""Binance Futures derivatives data — funding, open interest, long/short ratio.

All endpoints used here are public (no API key required). The data adds a
leverage / positioning dimension to the signal engine on top of pure price
action: crowded longs warn of squeezes down, crowded shorts of squeezes up.
"""
from __future__ import annotations

import requests

import config

_session = requests.Session()
_session.headers.update({"User-Agent": "crypto-indicator/1.0"})

# The /futures/data/ endpoints only accept this fixed set of period strings.
_VALID_PERIODS = {"5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"}


class DerivativesUnavailable(RuntimeError):
    """Raised when a symbol has no perpetual market or the API is unreachable."""


def _fapi_get(path: str, params: dict | None = None):
    resp = _session.get(config.BINANCE_FAPI_BASE + path, params=params,
                        timeout=config.HTTP_TIMEOUT)
    if resp.status_code != 200:
        raise DerivativesUnavailable(f"{path} -> HTTP {resp.status_code}")
    return resp.json()


def all_funding_rates() -> dict[str, float]:
    """Latest funding rate for every perpetual symbol, in one request.

    Returns a {symbol: funding_rate} map. funding_rate is the per-interval
    rate (e.g. 0.0001 == 0.01%); positive means longs pay shorts.
    """
    try:
        data = _fapi_get("/fapi/v1/premiumIndex")
    except (DerivativesUnavailable, requests.RequestException):
        return {}
    out: dict[str, float] = {}
    for row in data:
        try:
            out[row["symbol"]] = float(row["lastFundingRate"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _period_for(interval: str) -> str:
    return interval if interval in _VALID_PERIODS else "4h"


def get_derivatives(symbol: str, interval: str = "4h") -> dict | None:
    """Return a derivatives snapshot for one symbol, or None if no perp market.

    Keys: funding, oi_now, oi_change_pct, long_short_ratio, period.
    Open interest and long/short ratio are best-effort — they stay None if
    that particular endpoint fails, while funding is required.
    """
    period = _period_for(interval)
    try:
        prem = _fapi_get("/fapi/v1/premiumIndex", {"symbol": symbol})
        funding = float(prem["lastFundingRate"])
    except (DerivativesUnavailable, requests.RequestException,
            KeyError, TypeError, ValueError):
        return None  # no perpetual market for this symbol

    oi_now: float | None = None
    oi_change: float | None = None
    try:
        hist = _fapi_get("/futures/data/openInterestHist",
                         {"symbol": symbol, "period": period,
                          "limit": config.DERIV_OI_LOOKBACK})
        if hist:
            first = float(hist[0]["sumOpenInterest"])
            oi_now = float(hist[-1]["sumOpenInterest"])
            if first > 0:
                oi_change = (oi_now - first) / first * 100
    except (DerivativesUnavailable, requests.RequestException,
            KeyError, TypeError, ValueError, IndexError):
        pass

    ls_ratio: float | None = None
    try:
        ls = _fapi_get("/futures/data/globalLongShortAccountRatio",
                       {"symbol": symbol, "period": period, "limit": 1})
        if ls:
            ls_ratio = float(ls[-1]["longShortRatio"])
    except (DerivativesUnavailable, requests.RequestException,
            KeyError, TypeError, ValueError, IndexError):
        pass

    return {
        "funding": funding,
        "oi_now": oi_now,
        "oi_change_pct": oi_change,
        "long_short_ratio": ls_ratio,
        "period": period,
    }
