"""LunarCrush social-intelligence integration (API v4).

LunarCrush aggregates X/Twitter and other social platforms into crypto
metrics — Galaxy Score (overall health 0-100), AltRank (combined price +
social rank, lower is better) and social sentiment.

It is a PAID API (an active Individual+ subscription is required). Set
``LUNARCRUSH_API_KEY`` in a ``.env`` file in the project folder. Every
function degrades to ``None``/``{}`` when no key is configured or a request
fails, so the rest of the app is unaffected.

The rich social fields (sentiment, interactions, social dominance) live on the
``/coins/list/v1`` endpoint, so single-coin lookups are served from that list
rather than the lightweight ``/coins/{coin}/v1`` endpoint.
"""
from __future__ import annotations

import requests

import config

_session = requests.Session()
_session.headers.update({"User-Agent": "crypto-indicator/1.0"})


def is_configured() -> bool:
    """True when a LunarCrush API key is available."""
    return bool(config.LUNARCRUSH_API_KEY)


def _get(path: str, params: dict | None = None):
    headers = {"Authorization": f"Bearer {config.LUNARCRUSH_API_KEY}"}
    resp = _session.get(config.LUNARCRUSH_BASE + path, headers=headers,
                        params=params, timeout=config.HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def coin_list() -> list:
    """Raw coin list with full social fields — one request covers all coins."""
    if not is_configured():
        return []
    try:
        return _get("/coins/list/v1").get("data") or []
    except Exception:
        return []


def _aggregate(rows: list, limit: int = 100) -> dict | None:
    """Average social sentiment / Galaxy Score across the top `limit` rows."""
    sentiments = [r["sentiment"] for r in rows[:limit]
                  if r.get("sentiment") is not None]
    galaxies = [r["galaxy_score"] for r in rows[:limit]
                if r.get("galaxy_score") is not None]
    if not sentiments:
        return None
    avg_sent = sum(sentiments) / len(sentiments)
    mood = ("Bullish" if avg_sent >= 55
            else "Bearish" if avg_sent <= 45 else "Neutral")
    return {
        "sentiment": avg_sent,
        "galaxy": sum(galaxies) / len(galaxies) if galaxies else None,
        "mood": mood,
        "count": len(sentiments),
    }


def coin_metrics(base_asset: str, rows: list | None = None) -> dict | None:
    """Social metrics for one coin by base-asset symbol (e.g. 'BTC').

    Pass a pre-fetched `coin_list()` as `rows` to avoid refetching. Returns
    None when LunarCrush is unavailable or the coin is not covered.
    """
    target = base_asset.upper()
    source = coin_list() if rows is None else rows
    row = next((r for r in source
                if str(r.get("symbol", "")).upper() == target), None)
    if row is None:
        return None
    return {
        "galaxy_score": row.get("galaxy_score"),
        "galaxy_score_prev": row.get("galaxy_score_previous"),
        "alt_rank": row.get("alt_rank"),
        "alt_rank_prev": row.get("alt_rank_previous"),
        "sentiment": row.get("sentiment"),
        "social_dominance": row.get("social_dominance"),
        "interactions_24h": row.get("interactions_24h"),
        "social_volume_24h": row.get("social_volume_24h"),
        "market_cap_rank": row.get("market_cap_rank"),
        "percent_change_24h": row.get("percent_change_24h"),
    }


def top_coins(rows: list | None = None) -> dict[str, dict]:
    """Galaxy Score / AltRank / sentiment for every covered coin.

    Keyed by upper-case base symbol (e.g. "BTC").
    """
    source = coin_list() if rows is None else rows
    out: dict[str, dict] = {}
    for row in source:
        sym = row.get("symbol")
        if not sym:
            continue
        out[str(sym).upper()] = {
            "galaxy_score": row.get("galaxy_score"),
            "alt_rank": row.get("alt_rank"),
            "sentiment": row.get("sentiment"),
            "social_dominance": row.get("social_dominance"),
        }
    return out


def crypto_social(rows: list | None = None) -> dict | None:
    """Aggregate crypto-market social mood across the top coins."""
    return _aggregate(coin_list() if rows is None else rows)


def stock_social() -> dict | None:
    """Aggregate equities social mood — equities sentiment spills into crypto."""
    if not is_configured():
        return None
    try:
        rows = _get("/stocks/list/v1").get("data") or []
    except Exception:
        return None
    return _aggregate(rows)
