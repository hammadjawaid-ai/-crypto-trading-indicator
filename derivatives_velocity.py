"""Derivatives velocity signals (Phase C) — funding-rate ROC + OI delta
+ price compression.

The existing `derivatives.py` consumes funding rate LEVEL (crowded longs
warn of squeezes etc). That's a contrarian read at the extremes. This
module captures the *velocity* — the rate of change — which is a
genuinely leading signal:

1. **Funding velocity** — when funding flips sharply (e.g. -0.01% to
   +0.05% over 24h), sentiment is turning before price reflects it.
   Sudden velocity flips precede squeezes.

2. **Open Interest delta + price compression** — OI rising while price
   stays inside a tight range = new positions stacking inside a coil.
   When the coil breaks, the move is amplified. OI dropping during
   compression = stale positions clearing, often a fade signal.

This module is PURE — pulls Binance fapi endpoints with the same client
pattern as `derivatives.py`. Returns 0-100 score dicts compatible with
the backtest harness and the early_momentum chip family.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import requests

import binance_client
import config

_session = requests.Session()
_session.headers.update({"User-Agent": "crypto-indicator/1.0"})


# ---------------------------------------------------------------------------
# Funding history
# ---------------------------------------------------------------------------

def _funding_history(symbol: str, limit: int = 24) -> list[float]:
    """Fetch the last N funding-rate prints for a symbol via the Binance
    Futures /fapi/v1/fundingRate endpoint.

    Returns oldest-first list of rates (8h cadence by default). Empty
    list on any failure — caller should degrade gracefully.
    """
    try:
        resp = _session.get(
            config.BINANCE_FAPI_BASE + "/fapi/v1/fundingRate",
            params={"symbol": symbol, "limit": limit},
            timeout=config.HTTP_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [float(row["fundingRate"]) for row in data]
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return []


def funding_velocity(symbol: str, lookback: int = 24) -> dict:
    """Score the velocity (rate of change) of funding rates.

    A sharp flip in funding direction often precedes a squeeze in the
    OPPOSITE direction of the new crowd. e.g. funding turning sharply
    positive means longs are piling in — which historically precedes a
    long-squeeze down. So the signal SIDE is contrarian to the velocity
    direction.

    Score interpretation:
       >= 75 : strong contrarian SHORT (funding accelerating bullish,
               crowded longs forming — squeeze down likely)
       <= 25 : strong contrarian LONG (funding accelerating bearish,
               crowded shorts forming — squeeze up likely)
       40-60 : neutral
    """
    history = _funding_history(symbol, limit=lookback)
    if len(history) < 8:
        return {"score": 50, "side": "NEUTRAL",
                "detail": f"insufficient funding history ({len(history)})"}

    arr = np.array(history)
    current = float(arr[-1])
    # Use the most recent 3 prints (~24h) vs the prior 8 (~3d) for ROC
    recent = float(arr[-3:].mean())
    older = float(arr[-11:-3].mean()) if len(arr) >= 11 else float(arr[:-3].mean())
    velocity = recent - older  # absolute change in funding rate

    # Volatility-normalised z-score
    std = float(arr.std() or 1e-9)
    velocity_z = velocity / std if std > 0 else 0.0

    # Sharp sentiment flip detection
    flip_up = older < 0 and current > 0.0002  # was paying, now collecting
    flip_down = older > 0 and current < -0.0002  # was collecting, now paying

    # Contrarian sign: velocity positive (bullish crowding) => SHORT signal
    if velocity_z >= 1.5 or flip_up:
        # Funding accelerating positive — crowded longs forming. Contrarian short.
        strength = min(1.0, abs(velocity_z) / 3.0)
        score = 25 - 25 * strength * 0.6 if flip_up else 35 - 15 * strength
        return {"score": round(max(0, score)), "side": "SHORT",
                "detail": (f"Funding accelerating bullish "
                           f"(velocity z{velocity_z:+.1f}, "
                           f"current {current * 100:+.4f}%) — "
                           "crowded longs forming")}
    if velocity_z <= -1.5 or flip_down:
        # Funding accelerating negative — crowded shorts forming. Contrarian long.
        strength = min(1.0, abs(velocity_z) / 3.0)
        score = 75 + 25 * strength * 0.6 if flip_down else 65 + 15 * strength
        return {"score": round(min(100, score)), "side": "LONG",
                "detail": (f"Funding accelerating bearish "
                           f"(velocity z{velocity_z:+.1f}, "
                           f"current {current * 100:+.4f}%) — "
                           "crowded shorts forming")}
    return {"score": 50, "side": "NEUTRAL",
            "detail": (f"Funding velocity flat "
                       f"(z{velocity_z:+.1f}, current {current * 100:+.4f}%)")}


# ---------------------------------------------------------------------------
# Open-Interest delta + price compression
# ---------------------------------------------------------------------------

def _oi_history(symbol: str, period: str = "1h", limit: int = 24) -> list[float]:
    """Fetch OI history via /futures/data/openInterestHist."""
    try:
        resp = _session.get(
            config.BINANCE_FAPI_BASE + "/futures/data/openInterestHist",
            params={"symbol": symbol, "period": period, "limit": limit},
            timeout=config.HTTP_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [float(row["sumOpenInterest"]) for row in data]
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return []


def oi_compression(symbol: str, interval: str = "1h",
                   compression_threshold: float = 0.4,
                   oi_chg_threshold: float = 0.10) -> dict:
    """Score OI delta combined with price compression.

    The setup we want: OI rising sharply (>10% over the lookback)
    while price range is tight (recent 20-bar range < 40% of the
    longer 100-bar range). New positions stacking inside a coil.
    Resolution direction comes from funding sign (long-heavy → upward
    breakout more likely; short-heavy → downward).

    Mirror — OI dropping during compression = stale positions clearing.
    That precedes fades, not breakouts.
    """
    oi = _oi_history(symbol, period=interval if interval in
                     ("5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d")
                     else "1h",
                     limit=24)
    if len(oi) < 6:
        return {"score": 50, "side": "NEUTRAL",
                "detail": f"insufficient OI history ({len(oi)})"}

    oi_arr = np.array(oi)
    oi_chg = (oi_arr[-1] - oi_arr[0]) / oi_arr[0] if oi_arr[0] > 0 else 0.0

    # Pull kline data to measure price compression
    try:
        df = binance_client.get_klines(symbol, interval, limit=100)
    except Exception as exc:
        return {"score": 50, "side": "NEUTRAL",
                "detail": f"kline fetch failed: {exc}"}
    if len(df) < 50:
        return {"score": 50, "side": "NEUTRAL",
                "detail": f"insufficient klines ({len(df)})"}

    close_last = float(df["close"].iloc[-1])
    if close_last <= 0:
        return {"score": 50, "side": "NEUTRAL", "detail": "zero close"}

    short_range = float(df["high"].tail(20).max() - df["low"].tail(20).min())
    long_range = float(df["high"].tail(100).max() - df["low"].tail(100).min())
    if long_range <= 0:
        return {"score": 50, "side": "NEUTRAL", "detail": "zero long range"}
    compression = short_range / long_range
    compressed = compression <= compression_threshold

    # Get funding sign for breakout direction guess
    try:
        prem = _session.get(
            config.BINANCE_FAPI_BASE + "/fapi/v1/premiumIndex",
            params={"symbol": symbol},
            timeout=config.HTTP_TIMEOUT,
        )
        funding = float(prem.json()["lastFundingRate"]) if prem.status_code == 200 else 0.0
    except (requests.RequestException, ValueError, KeyError, TypeError):
        funding = 0.0

    if compressed and oi_chg >= oi_chg_threshold:
        # OI stacking inside coil — bullish or bearish based on funding
        side = "LONG" if funding >= 0 else "SHORT"
        # Stronger compression + larger OI delta = higher conviction
        strength = min(1.0,
                       ((compression_threshold - compression) /
                        compression_threshold) * 0.5
                       + min(oi_chg / 0.30, 1.0) * 0.5)
        if side == "LONG":
            score = 60 + strength * 35
        else:
            score = 40 - strength * 35
        return {"score": round(min(100, max(0, score))), "side": side,
                "detail": (f"OI stacking in coil "
                           f"(OI {oi_chg * 100:+.1f}%, compression "
                           f"{compression * 100:.0f}% of long range, "
                           f"funding {funding * 100:+.4f}%)")}
    if compressed and oi_chg <= -oi_chg_threshold:
        # OI clearing during compression — fade setup
        return {"score": 45, "side": "SHORT",
                "detail": (f"OI clearing in coil — fade likely "
                           f"(OI {oi_chg * 100:+.1f}%, compression "
                           f"{compression * 100:.0f}%)")}
    return {"score": 50, "side": "NEUTRAL",
            "detail": (f"No compression setup "
                       f"(OI {oi_chg * 100:+.1f}%, "
                       f"compression {compression * 100:.0f}% of long range)")}


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------

def score(symbol: str, interval: str = "1h") -> dict:
    """Composite derivatives velocity score.

    Blends funding velocity and OI/compression. Returns the same shape
    as early_momentum.score so it slots into the picks board / backtest
    harness identically.
    """
    fv = funding_velocity(symbol)
    oic = oi_compression(symbol, interval)

    # Side resolution: agreement = strong signal; disagreement = neutral
    fv_dev = fv["score"] - 50
    oic_dev = oic["score"] - 50
    if fv["side"] == oic["side"] and fv["side"] != "NEUTRAL":
        # Both agree — sum the deviations, capped
        combined_dev = fv_dev + oic_dev
        # Pull harder toward the more extreme component
        score = 50 + float(np.clip(combined_dev * 0.85, -50, 50))
        side = fv["side"]
    elif abs(fv_dev) > abs(oic_dev) and abs(fv_dev) >= 15:
        score = float(fv["score"])
        side = fv["side"]
    elif abs(oic_dev) >= 15:
        score = float(oic["score"])
        side = oic["side"]
    else:
        score = float((fv["score"] + oic["score"]) / 2)
        side = "NEUTRAL"

    flags = []
    if "accelerating" in fv["detail"]:
        flags.append("funding_flip")
    if "coil" in oic["detail"]:
        flags.append("oi_compression")

    return {
        "score": round(float(np.clip(score, 0, 100)), 1),
        "side": side,
        "components": {
            "funding_velocity": fv,
            "oi_compression": oic,
        },
        "flags": flags,
    }
