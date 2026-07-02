"""Funding-velocity fade — validated early-warning directional lane.

Backtested 2026-07-02 (backtest_deriv_frontier.py, 30 coins, 681 events):
when the funding rate prints in the TOP decile of its trailing 90 prints AND
is accelerating (above its recent average), FADING the crowded side returned
+0.91% over 24h (54% direction) and +2.49% over 48h (59%) vs a -0.04% / 43%
baseline. Mirror for the bottom decile. The OI-delta variant tested negative
and is NOT implemented.

Used as a context/consensus edge (APEX), never a standalone gate. Fail-soft.
"""
from __future__ import annotations

import time

import requests

import config

_FAPI = getattr(config, "BINANCE_FAPI_BASE", "https://fapi.binance.com")
_S = requests.Session()
_CACHE: dict = {}
_TTL = 900.0   # funding updates every 8h — 15 min cache is plenty


def signal(symbol: str) -> dict:
    """Return {"fade_side": "LONG"|"SHORT"|None, "rate": float, "pct": float}.

    fade_side is the direction the fade edge FAVOURS (SHORT when the crowd is
    long on extreme+accelerating positive funding; LONG on the mirror).
    None = funding not extreme -> no signal. Fail-soft on any error."""
    now = time.time()
    hit = _CACHE.get(symbol)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    out = {"fade_side": None, "rate": 0.0, "pct": 50.0}
    try:
        data = _S.get(_FAPI + "/fapi/v1/fundingRate",
                      params={"symbol": symbol, "limit": 94},
                      timeout=10).json()
        rates = [float(d["fundingRate"]) for d in data]
        if len(rates) >= 91:
            trail, cur = rates[:-1][-90:], rates[-1]
            recent = sum(rates[-4:-1]) / 3.0
            below = sum(1 for r in trail if r < cur)
            pct = below / len(trail) * 100.0
            out["rate"] = cur
            out["pct"] = round(pct, 1)
            if pct >= 90 and cur > recent and cur > 0:
                out["fade_side"] = "SHORT"
            elif pct <= 10 and cur < recent and cur < 0:
                out["fade_side"] = "LONG"
    except Exception:
        pass
    _CACHE[symbol] = (now, out)
    return out
