"""Global crypto-market context from CoinGecko (public API, no key required)."""
from __future__ import annotations

import requests

import config

_session = requests.Session()
_session.headers.update({"User-Agent": "crypto-indicator/1.0"})


def global_market() -> dict:
    """Return total market cap (USD), 24h change %, and BTC/ETH dominance.

    Keys: market_cap_usd, market_cap_change_24h, btc_dominance,
    eth_dominance, volume_usd.
    """
    resp = _session.get(config.COINGECKO_GLOBAL_URL, timeout=config.HTTP_TIMEOUT)
    resp.raise_for_status()
    d = resp.json()["data"]
    pct = d["market_cap_percentage"]
    return {
        "market_cap_usd": float(d["total_market_cap"]["usd"]),
        "market_cap_change_24h": float(
            d["market_cap_change_percentage_24h_usd"]),
        "btc_dominance": float(pct.get("btc", 0.0)),
        "eth_dominance": float(pct.get("eth", 0.0)),
        "volume_usd": float(d["total_volume"]["usd"]),
    }
