"""Coin Metrics on-chain signals — MVRV / NUPL / Realized Price for BTC/ETH.

Free Community-tier API, no key required. The only on-chain metrics
with documented cycle-low base rate. Critical caveat: only BTC and ETH
have meaningful coverage on the community tier; alts return empty.

Used by spot_signals.py as a regime / valuation tilt for BTC and ETH
long-term hold decisions. Not used for futures (per-coin cycle position
matters less on multi-day swings).

MVRV interpretation (per cycle analysis):
    < 1.0   — deep value (market underwater on cost basis)
    1.0-1.5 — accumulation zone
    1.5-2.4 — fair value
    > 2.4   — distribution zone

NUPL interpretation:
    < 0       — capitulation (most coins underwater)
    0 to 0.25 — hope/optimism (post-bottom recovery)
    0.25-0.50 — belief/denial (mid-cycle)
    0.50-0.75 — anxiety/euphoria (late cycle)
    > 0.75    — greed/distribution
"""
from __future__ import annotations

import time

import requests


_BASE = "https://community-api.coinmetrics.io/v4"
_session = requests.Session()
_session.headers.update({"User-Agent": "crypto-indicator/1.0"})
_CACHE: dict[str, tuple[float, dict]] = {}  # symbol -> (ts, payload)
_TTL = 86400  # 24h — community metrics update daily


def _supported(symbol: str) -> str | None:
    """Map ticker symbol to Coin Metrics asset code, or None if unsupported."""
    s = symbol.upper().replace("USDT", "").replace("USDC", "")
    return {"BTC": "btc", "ETH": "eth"}.get(s)


def _fetch(asset: str, metrics: list[str]) -> dict | None:
    """Fetch the latest value for the requested metrics on one asset.

    Returns {metric: float} or None on failure. The community endpoint
    returns one row per asset/time pair so we read the last row.

    IMPORTANT: must request a recent start_time. Without it the endpoint
    returns rows from the *start* of available history (2009 etc) and
    these don't have the modern metrics populated.
    """
    import datetime as _dt
    start = (_dt.datetime.utcnow() - _dt.timedelta(days=14)).strftime(
        "%Y-%m-%d")
    try:
        resp = _session.get(
            f"{_BASE}/timeseries/asset-metrics",
            params={
                "assets": asset,
                "metrics": ",".join(metrics),
                "frequency": "1d",
                "start_time": start,
                "page_size": 30,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        data = resp.json().get("data") or []
        if not data:
            return None
        # Pick the newest row that has all requested metrics populated
        for row in reversed(data):
            out = {}
            ok = True
            for m in metrics:
                v = row.get(m)
                if v is None:
                    ok = False
                    break
                try:
                    out[m] = float(v)
                except (TypeError, ValueError):
                    ok = False
                    break
            if ok:
                out["_date"] = str(row.get("time", "")[:10])
                return out
        return None
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def get_metrics(symbol: str) -> dict:
    """Return on-chain metrics for one symbol. Returns {} when the asset
    is not BTC or ETH (community tier doesn't cover alts).

    Returned dict (when populated):
        {
          "mvrv": float,
          "nupl": float,
          "realized_price": float,
          "date": "YYYY-MM-DD",
        }
    """
    asset = _supported(symbol)
    if asset is None:
        return {}

    now = time.time()
    cached = _CACHE.get(asset)
    if cached and (now - cached[0]) < _TTL:
        return cached[1]

    # One round-trip fetches MVRV + the components for NUPL + supply.
    metrics = ["CapMVRVCur", "CapMrktCurUSD", "CapRealUSD", "SplyCur"]
    raw = _fetch(asset, metrics)
    if raw is None:
        out: dict = {}
        _CACHE[asset] = (now, out)
        return out

    mvrv = raw.get("CapMVRVCur")
    mc = raw.get("CapMrktCurUSD")
    rc = raw.get("CapRealUSD")
    sply = raw.get("SplyCur")
    if mc is None or rc is None or mc <= 0:
        out = {}
    else:
        nupl = (mc - rc) / mc
        realized_price = rc / sply if (sply and sply > 0) else None
        out = {
            "mvrv": float(mvrv) if mvrv is not None else None,
            "nupl": float(nupl),
            "realized_price": float(realized_price) if realized_price else None,
            "date": raw.get("_date", ""),
        }
    _CACHE[asset] = (now, out)
    return out


def score(symbol: str) -> dict:
    """Composite on-chain score 0-100 for BTC or ETH spot conviction.

    Score reflects "is this a good zone to accumulate for a multi-month
    hold?" — high when MVRV/NUPL are in capitulation/accumulation zones,
    low when in distribution/euphoria zones.

    Returns 50 (neutral) for unsupported assets so callers don't have to
    special-case BTC/ETH vs alts.
    """
    m = get_metrics(symbol)
    if not m:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "Not available (BTC/ETH only on community tier)"}

    mvrv = m.get("mvrv")
    nupl = m.get("nupl")

    # MVRV scoring (heavier weight — more cycle-tested)
    if mvrv is None:
        mvrv_score = 50
    elif mvrv < 1.0:
        mvrv_score = 95
    elif mvrv < 1.2:
        mvrv_score = 80
    elif mvrv < 1.5:
        mvrv_score = 65
    elif mvrv < 2.0:
        mvrv_score = 45
    elif mvrv < 2.4:
        mvrv_score = 25
    else:
        mvrv_score = 10

    # NUPL scoring
    if nupl is None:
        nupl_score = 50
    elif nupl < 0:
        nupl_score = 90
    elif nupl < 0.25:
        nupl_score = 75
    elif nupl < 0.50:
        nupl_score = 55
    elif nupl < 0.75:
        nupl_score = 30
    else:
        nupl_score = 12

    composite = 0.6 * mvrv_score + 0.4 * nupl_score
    side = "LONG" if composite >= 55 else "NEUTRAL" if composite >= 45 else "SHORT"

    return {
        "score": round(composite, 1),
        "side": side,
        "mvrv": mvrv,
        "nupl": round(nupl, 4) if nupl is not None else None,
        "realized_price": m.get("realized_price"),
        "date": m.get("date", ""),
        "detail": (f"MVRV {mvrv:.2f} · NUPL {nupl:+.2f}"
                   if mvrv is not None and nupl is not None
                   else "partial on-chain data"),
    }
