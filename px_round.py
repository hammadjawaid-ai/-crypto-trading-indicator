"""Exchange-accurate price formatting for futures trading — NON-BLOCKING.

Card plans used to display raw floats (SL 0.0344763) that no exchange
accepts — the user trades Bybit futures. `fmt_px(symbol, price)` rounds to
the symbol's REAL Bybit linear (USDT-perp) tick size.

PERF: tick sizes are batch-prefetched for ALL linear symbols in ONE call
(prefetch_ticks(), self-throttled to once/hour) and cached. During render,
`fmt_px`/`_tick_for` NEVER make a network call — a cache miss falls back
instantly to integer-safe significant-digit rounding. This keeps the paper
trader snappy (the old per-symbol 6s-timeout fetch stalled every render).
"""
from __future__ import annotations

import time
from decimal import Decimal, ROUND_HALF_UP

import requests

_S = requests.Session()
_CACHE: dict = {}          # symbol -> (expires_at, Decimal tick)
_TTL_OK = 24 * 3600.0
_ALL_FETCHED = [0.0]       # last full-universe prefetch timestamp
_PREFETCH_EVERY = 3600.0   # refresh the whole tick map at most once/hour


def prefetch_ticks() -> None:
    """Populate the tick cache for ALL Bybit linear symbols in ONE request.
    Self-throttled: no-ops if called again within the hour. Fail-soft."""
    now = time.time()
    if now - _ALL_FETCHED[0] < _PREFETCH_EVERY:
        return
    try:
        j = _S.get("https://api.bybit.com/v5/market/instruments-info",
                   params={"category": "linear"}, timeout=8).json()
        lst = (j.get("result") or {}).get("list") or []
        for it in lst:
            sym = it.get("symbol")
            ts = (it.get("priceFilter") or {}).get("tickSize")
            if sym and ts:
                try:
                    _CACHE[sym] = (now + _TTL_OK, Decimal(str(ts)))
                except Exception:
                    pass
        if lst:
            _ALL_FETCHED[0] = now
    except Exception:
        # leave _ALL_FETCHED so we retry sooner than an hour on failure
        pass


def _tick_for(symbol: str):
    """Cached tick or None — NON-BLOCKING (never fetches during render)."""
    hit = _CACHE.get(symbol)
    if hit and time.time() < hit[0]:
        return hit[1]
    return None


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
    copy-paste ready for a real order. Instant sig-digit fallback if the
    tick isn't cached (never blocks on the network)."""
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
