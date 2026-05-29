"""BTC dominance + ETH/BTC alt-season regime filter.

Determines WHEN to rotate spot allocation from BTC into alts. Buying alts
when BTC.D is making higher highs is one of the most expensive mistakes
in a hold portfolio — the alt-vs-BTC relative drawdown often more than
overwhelms the alt's absolute appreciation.

This module is a REGIME GATE, not a per-coin signal. It returns a
multiplier (0.5 - 1.0) that callers apply to alt-coin spot scores to
fade them during BTC-dominance regimes and lift them during alt seasons.
"""
from __future__ import annotations

import time

import numpy as np
import requests

import binance_client

_CG_BASE = "https://api.coingecko.com/api/v3"
_session = requests.Session()
_session.headers.update({"User-Agent": "crypto-indicator/1.0"})

# Cached dominance reading (60-min TTL — slow-moving regime data)
_CACHE: dict = {"ts": 0.0, "payload": None}
_TTL = 3600


def _fetch_btc_d() -> dict | None:
    """Fetch BTC dominance from CoinGecko /global. Free, no key."""
    try:
        resp = _session.get(f"{_CG_BASE}/global", timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json().get("data") or {}
        mc_pct = data.get("market_cap_percentage") or {}
        return {
            "btc_dominance_pct": float(mc_pct.get("btc") or 0),
            "eth_dominance_pct": float(mc_pct.get("eth") or 0),
            "total_market_cap_usd": float(
                (data.get("total_market_cap") or {}).get("usd") or 0),
        }
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def _eth_btc_trend() -> dict | None:
    """ETH/BTC daily trend from Binance ETHBTC klines.

    Returns slope of last 50 daily closes (positive = ETH outperforming
    BTC) and percentile of current price vs the 200d range.
    """
    try:
        df = binance_client.get_klines("ETHBTC", "1d", limit=200)
        if df is None or len(df) < 50:
            return None
        recent = df.tail(50)
        # Trend slope normalised to mean (% per day)
        prices = recent["close"].to_numpy()
        x = np.arange(len(prices))
        slope_raw = np.polyfit(x, prices, 1)[0]
        slope_pct_per_day = float(slope_raw / prices.mean() * 100) \
            if prices.mean() > 0 else 0.0

        # Percentile of current price within last 200d
        all_prices = df["close"].to_numpy()
        cur = float(prices[-1])
        rank_pct = float(np.mean(all_prices <= cur))  # 0..1

        return {
            "ethbtc_slope_50d_pct": round(slope_pct_per_day, 4),
            "ethbtc_now": cur,
            "ethbtc_200d_percentile": round(rank_pct, 3),
        }
    except Exception:
        return None


def regime() -> dict:
    """Return the current alt-season regime read.

    Returns:
        {
          "regime": "ALT_FAVOURABLE" | "MIXED" | "BTC_DOMINANT",
          "alt_multiplier": 0.5 - 1.0,  # apply to alt scores
          "btc_dominance_pct": float,
          "ethbtc_slope_50d_pct": float,
          "ethbtc_200d_percentile": float,
          "detail": str,
        }
    """
    now = time.time()
    if _CACHE["payload"] is not None and (now - _CACHE["ts"]) < _TTL:
        return _CACHE["payload"]

    glob = _fetch_btc_d()
    eb = _eth_btc_trend()
    if glob is None:
        out = {"regime": "UNKNOWN", "alt_multiplier": 1.0,
               "btc_dominance_pct": None,
               "ethbtc_slope_50d_pct": None,
               "ethbtc_200d_percentile": None,
               "detail": "BTC dominance unavailable"}
        _CACHE.update(ts=now, payload=out)
        return out

    btc_d = glob["btc_dominance_pct"]
    slope = eb["ethbtc_slope_50d_pct"] if eb else 0.0
    pct = eb["ethbtc_200d_percentile"] if eb else 0.5

    # Classify regime
    if slope > 0.05 and pct > 0.55 and btc_d < 58:
        # ETH/BTC rising AND BTC.D moderate-low → alt-favourable
        regime_label = "ALT_FAVOURABLE"
        mult = 1.0
        detail = (f"Alt-favourable: ETH/BTC trending up "
                  f"({slope:+.2f}%/d, pct {pct:.0%}), BTC.D {btc_d:.1f}%")
    elif slope < -0.05 or btc_d > 62:
        # ETH/BTC falling OR BTC.D high → BTC-dominant
        regime_label = "BTC_DOMINANT"
        mult = 0.6
        detail = (f"BTC-dominant: ETH/BTC {slope:+.2f}%/d, "
                  f"BTC.D {btc_d:.1f}% — alts under-perform here")
    else:
        regime_label = "MIXED"
        mult = 0.85
        detail = (f"Mixed regime: ETH/BTC {slope:+.2f}%/d "
                  f"(pct {pct:.0%}), BTC.D {btc_d:.1f}%")

    out = {
        "regime": regime_label,
        "alt_multiplier": mult,
        "btc_dominance_pct": round(btc_d, 2),
        "ethbtc_slope_50d_pct": slope,
        "ethbtc_200d_percentile": pct,
        "detail": detail,
    }
    _CACHE.update(ts=now, payload=out)
    return out
