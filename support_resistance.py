"""Support and resistance ZONES with strength scoring.

Builds on indicators.swing_levels() (raw pivot detection) and clusters
nearby pivots into ZONES so the UI can show meaningful price levels
instead of dozens of individual swing points.

Returns the N nearest zones above (resistance) and below (support) the
current price, each with a strength score (number of touches × age weight).

Usage from app.py:

    sr = load_support_resistance(symbol, timeframe)
    sr["supports"]      # list of {"price", "strength", "touches", "distance_pct"}
    sr["resistances"]   # same
    sr["nearest_support"]
    sr["nearest_resistance"]
    sr["price_now"]
"""
from __future__ import annotations

import pandas as pd

import binance_client
import indicators


# -----------------------------------------------------------------------------
# Core: cluster raw pivots into zones
# -----------------------------------------------------------------------------

def _cluster_levels(levels: list[float],
                    tolerance_pct: float = 0.6) -> list[dict]:
    """Cluster nearby price levels into ZONES.

    Pivots within `tolerance_pct` % of each other are merged into one zone.
    The zone price is the arithmetic mean of its members; strength is the
    member count (touches).

    Args:
        levels: sorted list of raw pivot prices
        tolerance_pct: cluster width — 0.6 % default suits crypto on 1h/4h.

    Returns:
        List of {"price": float, "touches": int}, sorted by price ASC.
    """
    if not levels:
        return []
    sorted_levels = sorted(levels)
    zones: list[dict] = []
    cur_members = [sorted_levels[0]]
    for px in sorted_levels[1:]:
        ref = cur_members[0]
        if ref <= 0:
            cur_members = [px]
            continue
        diff_pct = abs(px - ref) / ref * 100
        if diff_pct <= tolerance_pct:
            cur_members.append(px)
        else:
            zones.append({
                "price": sum(cur_members) / len(cur_members),
                "touches": len(cur_members),
            })
            cur_members = [px]
    if cur_members:
        zones.append({
            "price": sum(cur_members) / len(cur_members),
            "touches": len(cur_members),
        })
    return zones


def _score_zone(touches: int, distance_pct: float) -> float:
    """Strength score 0-100 for a zone.

    Heavier weight when:
      - more touches (proven reaction)
      - closer to current price (more relevant)
    """
    # Touches: 1 -> 30, 2 -> 50, 3 -> 65, 4 -> 75, 5+ -> 85+
    touch_score = min(85, 25 + 12 * touches)
    # Proximity: 0% away -> +15, 5% -> 0, 15%+ -> -15
    proximity = max(-15, min(15, 15 - abs(distance_pct) * 2))
    return max(0, min(100, touch_score + proximity))


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def compute_support_resistance(df: pd.DataFrame,
                               n_above: int = 3,
                               n_below: int = 3,
                               window: int = 4,
                               lookback: int = 200,
                               tolerance_pct: float = 0.6) -> dict:
    """Compute support and resistance ZONES for a price series.

    Args:
        df: OHLCV DataFrame (assumed enriched by indicators.enrich).
        n_above: number of resistance zones above current price to return.
        n_below: number of support zones below to return.
        window: pivot detection window (±N candles).
        lookback: candles to scan.
        tolerance_pct: zone clustering tolerance.

    Returns:
        dict with keys: supports, resistances, nearest_support,
        nearest_resistance, price_now.
    """
    if df is None or len(df) < window * 2 + 10:
        return {
            "supports": [], "resistances": [],
            "nearest_support": None, "nearest_resistance": None,
            "price_now": 0.0,
        }

    supports_raw, resistances_raw = indicators.swing_levels(
        df, window=window, lookback=lookback)
    price_now = float(df["close"].iloc[-1])
    if price_now <= 0:
        return {
            "supports": [], "resistances": [],
            "nearest_support": None, "nearest_resistance": None,
            "price_now": 0.0,
        }

    # Cluster into zones
    support_zones = _cluster_levels(supports_raw, tolerance_pct)
    resistance_zones = _cluster_levels(resistances_raw, tolerance_pct)

    # Annotate with distance + strength, filter to relevant side
    enriched_supports: list[dict] = []
    for z in support_zones:
        if z["price"] >= price_now:
            continue  # supports are below price by definition
        distance_pct = (z["price"] / price_now - 1.0) * 100  # negative
        z["distance_pct"] = round(distance_pct, 2)
        z["strength"] = round(_score_zone(z["touches"], distance_pct), 1)
        enriched_supports.append(z)

    enriched_resistances: list[dict] = []
    for z in resistance_zones:
        if z["price"] <= price_now:
            continue
        distance_pct = (z["price"] / price_now - 1.0) * 100  # positive
        z["distance_pct"] = round(distance_pct, 2)
        z["strength"] = round(_score_zone(z["touches"], distance_pct), 1)
        enriched_resistances.append(z)

    # Sort by distance to price (closest first), keep top N
    enriched_supports.sort(key=lambda z: -z["distance_pct"])  # closest first
    enriched_resistances.sort(key=lambda z: z["distance_pct"])

    supports = enriched_supports[:n_below]
    resistances = enriched_resistances[:n_above]

    nearest_support = supports[0] if supports else None
    nearest_resistance = resistances[0] if resistances else None

    return {
        "supports": supports,
        "resistances": resistances,
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "price_now": price_now,
    }


def fetch_and_compute(symbol: str, interval: str = "1h",
                      limit: int = 300, **kwargs) -> dict:
    """Convenience: fetch klines + compute S/R in one call."""
    try:
        df = binance_client.get_klines(symbol, interval, limit=limit)
        df = indicators.enrich(df)
    except Exception:
        return {
            "supports": [], "resistances": [],
            "nearest_support": None, "nearest_resistance": None,
            "price_now": 0.0,
        }
    return compute_support_resistance(df, **kwargs)
