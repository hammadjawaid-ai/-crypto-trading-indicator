"""Tokenomics / supply-dilution proxy (Phase F).

There is NO truly free, complete unlock-calendar API. Cryptorank,
Tokenomist.ai, Messari, and TokenUnlocks all gate their unlock-schedule
APIs behind paid tiers ($50-200/mo).

What we CAN compute for free from CoinGecko's open /coins/{id} endpoint:

  - circulating_supply
  - total_supply
  - max_supply
  - mcap / fdv ratio

From those we derive:
  - "Dilution risk" — what fraction of max_supply is still locked.
    A coin at 30% circulating has 70% future dilution to absorb.
  - "FDV gap" — ratio of fully-diluted valuation to market cap. A
    >3x gap is a major future-sell-pressure red flag for long holds.

This is a DEFENSIVE FILTER — it penalises spot picks with high
future dilution. It does not generate buy signals.

Honest acknowledgement: this can't detect SPECIFIC unlock cliffs
(e.g. "30% supply unlock in 3 weeks"). For that we'd need the
paid APIs. What we have catches the systemic dilution risk.
"""
from __future__ import annotations

import time

import requests


_CG_BASE = "https://api.coingecko.com/api/v3"
_session = requests.Session()
_session.headers.update({"User-Agent": "crypto-indicator/1.0"})

# Cache symbol→coin-id map (CoinGecko coin_id != Binance symbol)
_ID_CACHE: dict[str, str] = {}
_ID_CACHE_TS: float = 0.0
_ID_CACHE_TTL = 86400  # 24h

# Cache per-coin tokenomics data
_DATA_CACHE: dict[str, tuple[float, dict]] = {}
_DATA_TTL = 21600  # 6h — supply data is slow-moving


def _refresh_id_map() -> None:
    """Build a SYMBOL -> CoinGecko id map. /coins/list is paginated, but
    the full list is small enough to fetch in one call."""
    global _ID_CACHE, _ID_CACHE_TS
    now = time.time()
    if (now - _ID_CACHE_TS) < _ID_CACHE_TTL and _ID_CACHE:
        return
    try:
        resp = _session.get(f"{_CG_BASE}/coins/list", timeout=20)
        if resp.status_code != 200:
            return
        rows = resp.json() or []
        # When duplicates exist, prefer the one with the "official" id
        # (e.g. "ethereum" not "ethereum-wormhole"). Crude heuristic: the
        # one whose id matches the symbol or has shortest id wins.
        candidates: dict[str, list[tuple[int, str]]] = {}
        for r in rows:
            sym = (r.get("symbol") or "").upper()
            cid = (r.get("id") or "").strip()
            if not sym or not cid:
                continue
            candidates.setdefault(sym, []).append((len(cid), cid))
        mp: dict[str, str] = {}
        for sym, opts in candidates.items():
            opts.sort()
            mp[sym] = opts[0][1]
        _ID_CACHE = mp
        _ID_CACHE_TS = now
    except (requests.RequestException, ValueError, KeyError, TypeError):
        pass


def _symbol_to_id(symbol: str) -> str | None:
    _refresh_id_map()
    if not _ID_CACHE:
        return None
    s = symbol.upper().replace("USDT", "").replace("USDC", "")
    return _ID_CACHE.get(s)


def _fetch_supply(coin_id: str) -> dict | None:
    """Fetch supply + valuation data from /coins/{id}.

    Skips the locale / market_data / community sub-resources to keep
    the response small.
    """
    try:
        resp = _session.get(
            f"{_CG_BASE}/coins/{coin_id}",
            params={"localization": "false", "tickers": "false",
                    "community_data": "false", "developer_data": "false",
                    "sparkline": "false"},
            timeout=20,
        )
        if resp.status_code != 200:
            return None
        d = resp.json() or {}
        market = d.get("market_data") or {}
        return {
            "name": d.get("name"),
            "circulating": float(market.get("circulating_supply") or 0),
            "total": float(market.get("total_supply") or 0)
            if market.get("total_supply") is not None else None,
            "max": float(market.get("max_supply") or 0)
            if market.get("max_supply") is not None else None,
            "price_usd": float((market.get("current_price") or {})
                               .get("usd") or 0),
            "mcap_usd": float((market.get("market_cap") or {})
                              .get("usd") or 0),
            "fdv_usd": float((market.get("fully_diluted_valuation") or {})
                             .get("usd") or 0),
        }
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def get_tokenomics(symbol: str) -> dict:
    """Return supply / valuation metrics for one symbol."""
    coin_id = _symbol_to_id(symbol)
    if coin_id is None:
        return {}
    now = time.time()
    cached = _DATA_CACHE.get(coin_id)
    if cached and (now - cached[0]) < _DATA_TTL:
        return cached[1]
    data = _fetch_supply(coin_id)
    if data is None:
        _DATA_CACHE[coin_id] = (now, {})
        return {}
    _DATA_CACHE[coin_id] = (now, data)
    return data


def score(symbol: str) -> dict:
    """Compute the dilution-risk score for a long-term spot hold.

    Score interpretation:
      85-100 — fully diluted (no future supply pressure)
      65-84  — most supply already circulating (mild dilution risk)
      45-64  — significant future dilution
      20-44  — high dilution risk (most supply still locked)
       0-19  — extreme dilution risk (red flag for long holds)

    Returns 50 (neutral) when CoinGecko has no data — we don't penalise
    coins for missing data, only for confirmed bad dilution.
    """
    t = get_tokenomics(symbol)
    if not t:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "No tokenomics data"}

    circulating = t.get("circulating", 0)
    max_supply = t.get("max")
    total_supply = t.get("total")
    mcap = t.get("mcap_usd", 0)
    fdv = t.get("fdv_usd", 0)

    # Circulating fraction of max supply
    if max_supply and max_supply > 0 and circulating > 0:
        circ_frac = circulating / max_supply
    elif total_supply and total_supply > 0 and circulating > 0:
        # Some coins have no published max (inflationary). Use total.
        circ_frac = circulating / total_supply
    else:
        circ_frac = None

    # FDV / mcap ratio (1.0 = fully diluted; >3.0 = high dilution to come)
    if mcap > 0 and fdv > 0:
        fdv_ratio = fdv / mcap
    else:
        fdv_ratio = None

    # Scoring
    if circ_frac is None and fdv_ratio is None:
        score_val = 50
        detail = "Supply data unavailable"
    else:
        # Start from circulating fraction (higher = less dilution to come)
        if circ_frac is not None:
            if circ_frac >= 0.95:
                circ_score = 95
            elif circ_frac >= 0.80:
                circ_score = 80
            elif circ_frac >= 0.60:
                circ_score = 60
            elif circ_frac >= 0.40:
                circ_score = 40
            elif circ_frac >= 0.20:
                circ_score = 25
            else:
                circ_score = 10
        else:
            circ_score = 50

        # FDV penalty — even if circulating fraction is high, a 5x FDV
        # gap means future selling pressure that hurts long holders.
        if fdv_ratio is None:
            fdv_score = 50
        elif fdv_ratio <= 1.1:
            fdv_score = 95
        elif fdv_ratio <= 1.5:
            fdv_score = 80
        elif fdv_ratio <= 2.5:
            fdv_score = 60
        elif fdv_ratio <= 4.0:
            fdv_score = 35
        else:
            fdv_score = 12

        # Blend — circ fraction is more direct, FDV ratio is the
        # market's pricing of dilution risk
        score_val = round(0.6 * circ_score + 0.4 * fdv_score, 1)
        parts = []
        if circ_frac is not None:
            parts.append(f"circulating {circ_frac * 100:.1f}% of max")
        if fdv_ratio is not None:
            parts.append(f"FDV/mcap {fdv_ratio:.2f}x")
        detail = " · ".join(parts)

    side = "LONG" if score_val >= 65 else "NEUTRAL" if score_val >= 35 else "SHORT"

    return {
        "score": score_val,
        "side": side,
        "circulating_fraction": round(circ_frac, 3) if circ_frac is not None else None,
        "fdv_mcap_ratio": round(fdv_ratio, 2) if fdv_ratio is not None else None,
        "detail": detail,
    }
