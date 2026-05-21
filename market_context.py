"""Global crypto-market context — total market cap, 24h change and BTC/ETH
dominance.

Providers are tried in order (CoinGecko, then CoinLore, then CoinPaprika) so
that a single unreachable API never blanks the market header. CoinGecko's
public endpoint is frequently connection-reset or rate-limited from some
networks, which is why the fallbacks exist.
"""
from __future__ import annotations

import requests

import config

_session = requests.Session()
_session.headers.update({"User-Agent": "crypto-indicator/1.0"})


def _from_coingecko() -> dict:
    resp = _session.get(config.COINGECKO_GLOBAL_URL,
                        timeout=config.HTTP_TIMEOUT)
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
        "source": "CoinGecko",
    }


def _from_coinlore() -> dict:
    """CoinLore global — carries BTC *and* ETH dominance plus the 24h change."""
    resp = _session.get("https://api.coinlore.com/api/global/",
                         timeout=config.HTTP_TIMEOUT)
    resp.raise_for_status()
    d = resp.json()[0]
    return {
        "market_cap_usd": float(d["total_mcap"]),
        "market_cap_change_24h": float(d.get("mcap_change") or 0.0),
        "btc_dominance": float(d["btc_d"]),
        "eth_dominance": float(d.get("eth_d") or 0.0),
        "volume_usd": float(d["total_volume"]),
        "source": "CoinLore",
    }


def _from_coinpaprika() -> dict:
    """CoinPaprika global — BTC dominance only (no ETH dominance field)."""
    resp = _session.get("https://api.coinpaprika.com/v1/global",
                         timeout=config.HTTP_TIMEOUT)
    resp.raise_for_status()
    d = resp.json()
    return {
        "market_cap_usd": float(d["market_cap_usd"]),
        "market_cap_change_24h": float(d.get("market_cap_change_24h") or 0.0),
        "btc_dominance": float(d["bitcoin_dominance_percentage"]),
        "eth_dominance": 0.0,
        "volume_usd": float(d["volume_24h_usd"]),
        "source": "CoinPaprika",
    }


def global_market() -> dict:
    """Return total market cap (USD), 24h change %, BTC/ETH dominance and the
    `source` provider that answered.

    Keys: market_cap_usd, market_cap_change_24h, btc_dominance,
    eth_dominance, volume_usd, source.

    Each provider is tried in turn; the first that succeeds wins. Only when
    every source fails does this raise.
    """
    errors: list[str] = []
    for fetch in (_from_coingecko, _from_coinlore, _from_coinpaprika):
        try:
            return fetch()
        except Exception as exc:  # noqa: BLE001 — fall through to next source
            errors.append(f"{fetch.__name__}: {exc}")
    raise RuntimeError(
        "all global-market sources failed — " + "; ".join(errors))
