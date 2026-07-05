"""Exchange-accurate price formatting for futures trading.

Card plans used to display raw floats (SL 0.0344763) that no exchange
accepts — the user trades Bybit futures and had to hand-round every level.
`fmt_px(symbol, price)` rounds to the symbol's REAL Bybit linear (USDT-perp)
tick size, fetched once and cached 24h. Fail-soft: if Bybit is unreachable,
falls back to 5-significant-digit rounding (close to typical ticks).
"""
from __future__ import annotations

import time
from decimal import Decimal, ROUND_HALF_UP

import requests

_S = requests.Session()
_CACHE: dict = {}          # symbol -> (expires_at, Decimal tick | None)
_TTL_OK = 24 * 3600.0
_TTL_FAIL = 1800.0


def _tick_for(symbol: str):
    now = time.time()
    hit = _CACHE.get(symbol)
    if hit and now < hit[0]:
        return hit[1]
    tick = None
    try:
        j = _S.get("https://api.bybit.com/v5/market/instruments-info",
                   params={"category": "linear", "symbol": symbol},
                   timeout=6).json()
        lst = (j.get("result") or {}).get("list") or []
        if lst:
            tick = Decimal(str(lst[0]["priceFilter"]["tickSize"]))
    except Exception:
        tick = None
    _CACHE[symbol] = (now + (_TTL_OK if tick else _TTL_FAIL), tick)
    return tick


def _sig5(price: float) -> str:
    # Never truncate the integer part (BTC 104623.79 must not become
    # 104620): >=1000 -> 1 decimal, >=1 -> 3 decimals, else 5 sig digits.
    if price >= 1000:
        return f"{price:.1f}"
    if price >= 1:
        return f"{price:.3f}".rstrip("0").rstrip(".")
    d = Decimal(f"{price:.5g}")
    return format(d.normalize(), "f")


def fmt_px(symbol: str, price) -> str:
    """Format a price rounded to the symbol's Bybit futures tick size —
    copy-paste ready for a real order. Fail-soft to 5 significant digits."""
    try:
        p = float(price)
    except (TypeError, ValueError):
        return "—"
    if p <= 0:
        return "—"
    try:
        tick = _tick_for(symbol)
        if tick and tick > 0:
            q = (Decimal(str(p)) / tick).to_integral_value(
                rounding=ROUND_HALF_UP) * tick
            return format(q.normalize(), "f")
    except Exception:
        pass
    return _sig5(p)
