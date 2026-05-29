"""DefiLlama TVL + fee growth signals.

Free public API, no key. Differentiates revenue-positive protocols from
narrative-only tokens. Phase E addition for spot_signals long-term hold
scoring: revenue/TVL growth signals fundamental adoption that pure
price-and-volume scoring can't see.

Critical: only works for protocols DefiLlama tracks (DeFi + some L1s).
Pure memes, layer-2 infra without revenue, and assets with no on-chain
TVL footprint return empty.
"""
from __future__ import annotations

import time

import requests

_BASE = "https://api.llama.fi"
_session = requests.Session()
_session.headers.update({"User-Agent": "crypto-indicator/1.0"})

# Symbol -> slug map cached for 24h. Built lazily on first lookup.
_SLUG_MAP: dict[str, str] = {}
_SLUG_MAP_TS: float = 0.0
_SLUG_TTL = 86400

# Per-protocol metric cache (slug -> (ts, dict))
_METRIC_CACHE: dict[str, tuple[float, dict]] = {}
_METRIC_TTL = 3600  # hourly


def _refresh_slug_map() -> None:
    """Fetch the full protocols list and build a symbol->slug map."""
    global _SLUG_MAP, _SLUG_MAP_TS
    now = time.time()
    if (now - _SLUG_MAP_TS) < _SLUG_TTL and _SLUG_MAP:
        return
    try:
        resp = _session.get(f"{_BASE}/protocols", timeout=15)
        if resp.status_code != 200:
            return
        data = resp.json() or []
        mp: dict[str, str] = {}
        for row in data:
            symbol = (row.get("symbol") or "").upper().strip()
            slug = (row.get("slug") or "").strip()
            if not symbol or not slug or symbol == "-":
                continue
            # Prefer the largest-TVL entry when there are duplicates
            if symbol in mp:
                # Keep the one with higher current TVL
                existing_slug = mp[symbol]
                if _slug_tvl(slug, row) > _slug_tvl(existing_slug, None):
                    mp[symbol] = slug
            else:
                mp[symbol] = slug
        _SLUG_MAP = mp
        _SLUG_MAP_TS = now
    except (requests.RequestException, ValueError, KeyError, TypeError):
        pass


def _slug_tvl(slug: str, row: dict | None) -> float:
    """Get current TVL for a slug — cheap lookup from the row if provided."""
    if row is not None:
        try:
            return float(row.get("tvl") or 0)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _symbol_to_slug(symbol: str) -> str | None:
    """Resolve a ticker symbol (e.g. AAVE, UNI) to a DefiLlama slug."""
    _refresh_slug_map()
    if not _SLUG_MAP:
        return None
    s = symbol.upper().replace("USDT", "").replace("USDC", "")
    return _SLUG_MAP.get(s)


def get_metrics(symbol: str) -> dict:
    """Return TVL + fee/revenue metrics for one symbol's DeFi protocol.

    Returns {} if the symbol has no DefiLlama coverage (memes, L1s
    without DefiLlama presence, etc).

    Populated dict shape:
        {
          "slug": str,
          "tvl_now": float,
          "tvl_30d_ago": float,
          "tvl_90d_ago": float,
          "tvl_30d_growth_pct": float,
          "tvl_90d_growth_pct": float,
          "fees_24h": float,
          "revenue_24h": float,
          "fees_30d": float,
        }
    """
    slug = _symbol_to_slug(symbol)
    if slug is None:
        return {}

    now = time.time()
    cached = _METRIC_CACHE.get(slug)
    if cached and (now - cached[0]) < _METRIC_TTL:
        return cached[1]

    out: dict = {"slug": slug}

    # TVL history
    try:
        resp = _session.get(f"{_BASE}/protocol/{slug}", timeout=15)
        if resp.status_code == 200:
            data = resp.json() or {}
            tvl_series = data.get("tvl") or []
            if tvl_series:
                out["tvl_now"] = float(tvl_series[-1].get("totalLiquidityUSD") or 0)
                # 30d ≈ 30 entries back (daily series), 90d ≈ 90
                if len(tvl_series) >= 31:
                    out["tvl_30d_ago"] = float(
                        tvl_series[-31].get("totalLiquidityUSD") or 0)
                if len(tvl_series) >= 91:
                    out["tvl_90d_ago"] = float(
                        tvl_series[-91].get("totalLiquidityUSD") or 0)
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
        pass

    # Fees + revenue summary (best-effort; many protocols have no fees data)
    try:
        f_resp = _session.get(f"{_BASE}/summary/fees/{slug}",
                              params={"dataType": "dailyFees"}, timeout=10)
        if f_resp.status_code == 200:
            d = f_resp.json() or {}
            out["fees_24h"] = float(d.get("total24h") or 0)
            out["fees_30d"] = float(d.get("total30d") or 0)
    except (requests.RequestException, ValueError, KeyError, TypeError):
        pass
    try:
        r_resp = _session.get(f"{_BASE}/summary/fees/{slug}",
                              params={"dataType": "dailyRevenue"}, timeout=10)
        if r_resp.status_code == 200:
            d = r_resp.json() or {}
            out["revenue_24h"] = float(d.get("total24h") or 0)
    except (requests.RequestException, ValueError, KeyError, TypeError):
        pass

    # Compute growth rates
    if out.get("tvl_now") and out.get("tvl_30d_ago", 0) > 0:
        out["tvl_30d_growth_pct"] = (
            (out["tvl_now"] / out["tvl_30d_ago"] - 1.0) * 100)
    if out.get("tvl_now") and out.get("tvl_90d_ago", 0) > 0:
        out["tvl_90d_growth_pct"] = (
            (out["tvl_now"] / out["tvl_90d_ago"] - 1.0) * 100)

    _METRIC_CACHE[slug] = (now, out)
    return out


def score(symbol: str) -> dict:
    """Composite TVL/fee growth score 0-100 for a DeFi protocol.

    Scoring philosophy: long-term holders should prefer protocols where
    fundamental adoption (TVL, fees, revenue) is GROWING. Pure
    narrative tokens without revenue are penalised.

    Returns 50 neutral when no DefiLlama coverage exists — the caller
    should not let "no data" reflect badly on a non-DeFi project.
    """
    m = get_metrics(symbol)
    if not m or "tvl_now" not in m:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "No DefiLlama coverage"}

    tvl_30d = m.get("tvl_30d_growth_pct")
    tvl_90d = m.get("tvl_90d_growth_pct")
    revenue_24h = m.get("revenue_24h", 0)

    # TVL growth scoring
    if tvl_90d is not None:
        if tvl_90d > 50:
            tvl_score = 90
        elif tvl_90d > 20:
            tvl_score = 75
        elif tvl_90d > 0:
            tvl_score = 60
        elif tvl_90d > -20:
            tvl_score = 40
        elif tvl_90d > -50:
            tvl_score = 25
        else:
            tvl_score = 10
    elif tvl_30d is not None:
        # Fall back to 30d if we don't have 90d
        tvl_score = 50 + min(25, max(-25, tvl_30d / 2))
    else:
        tvl_score = 50

    # Revenue bonus — protocols with real revenue get a tilt
    rev_bonus = 0
    if revenue_24h and revenue_24h > 100_000:
        rev_bonus = 8
    elif revenue_24h and revenue_24h > 10_000:
        rev_bonus = 4

    composite = min(100, max(0, tvl_score + rev_bonus))
    side = "LONG" if composite >= 60 else "NEUTRAL" if composite >= 40 else "SHORT"

    detail_parts = []
    if tvl_90d is not None:
        detail_parts.append(f"TVL 90d {tvl_90d:+.1f}%")
    if tvl_30d is not None:
        detail_parts.append(f"30d {tvl_30d:+.1f}%")
    if revenue_24h:
        detail_parts.append(f"rev24h ${revenue_24h / 1000:.0f}k")
    detail = " · ".join(detail_parts) or "TVL data partial"

    return {
        "score": round(composite, 1),
        "side": side,
        "tvl_now_usd": m.get("tvl_now"),
        "tvl_30d_growth_pct": tvl_30d,
        "tvl_90d_growth_pct": tvl_90d,
        "fees_24h": m.get("fees_24h"),
        "revenue_24h": revenue_24h,
        "slug": m.get("slug"),
        "detail": detail,
    }
