"""Coinalyze derivatives-data client (FREE API).

Open interest, funding rate, predicted funding, long/short ratio and
liquidation history aggregated across exchanges. Free key from
https://coinalyze.net (account menu -> API). Limits that matter:

  * 40 API calls/minute — throttled here automatically.
  * Intraday (1hour) history reaches back roughly 60-80 days;
    daily history is kept forever.

Set ``COINALYZE_API_KEY`` in ``.env`` (local) and in Render env vars
(deployed). Every function degrades to ``None``/empty when the key is
missing or a request fails, so callers never crash.

Symbols: Coinalyze uses its own market codes like ``BTCUSDT_PERP.A``
(the suffix identifies the exchange). Use :func:`resolve_perp` to map a
Binance-style symbol ("BTCUSDT") or base asset ("BTC") to the best
available perp market code — discovery is live via /future-markets, so
nothing is hardcoded.
"""
from __future__ import annotations

import threading
import time

import pandas as pd
import requests

import config

_session = requests.Session()
_session.headers.update({"User-Agent": "crypto-indicator/1.0"})

# --- rate limiting: 40 calls/min, enforced with a sliding window ------------
_RATE_MAX = 38          # small safety margin under the 40/min cap
_RATE_WINDOW = 60.0
_call_times: list[float] = []
_rate_lock = threading.Lock()


def is_configured() -> bool:
    """True when a Coinalyze API key is available."""
    return bool(getattr(config, "COINALYZE_API_KEY", ""))


def _throttle() -> None:
    with _rate_lock:
        now = time.time()
        while _call_times and now - _call_times[0] > _RATE_WINDOW:
            _call_times.pop(0)
        if len(_call_times) >= _RATE_MAX:
            wait = _RATE_WINDOW - (now - _call_times[0]) + 0.1
            if wait > 0:
                time.sleep(wait)
        _call_times.append(time.time())


def _get(path: str, params: dict | None = None):
    if not is_configured():
        return None
    _throttle()
    resp = _session.get(
        config.COINALYZE_BASE + path,
        headers={"api_key": config.COINALYZE_API_KEY},
        params=params or {},
        timeout=getattr(config, "HTTP_TIMEOUT", 15))
    resp.raise_for_status()
    return resp.json()


# --- market discovery (cached) ----------------------------------------------
_mkt_cache: dict = {"ts": 0.0, "markets": None, "exchanges": None}
_MKT_TTL = 6 * 3600
# Preferred venues for a single-market read, most liquid first.
_EXCH_PREF = ("Binance", "Bybit", "OKX", "Bitget", "Gate.io")


def _discover() -> tuple[list, dict]:
    """(future_markets, exchange_code->name), cached 6h."""
    now = time.time()
    if _mkt_cache["markets"] is not None and now - _mkt_cache["ts"] < _MKT_TTL:
        return _mkt_cache["markets"], _mkt_cache["exchanges"]
    try:
        mkts = _get("/future-markets") or []
        exs = _get("/exchanges") or []
    except Exception:
        return _mkt_cache["markets"] or [], _mkt_cache["exchanges"] or {}
    code2name = {e.get("code"): e.get("name") for e in exs}
    _mkt_cache.update(ts=now, markets=mkts, exchanges=code2name)
    return mkts, code2name


def resolve_perp(symbol_or_base: str) -> str | None:
    """Map 'BTCUSDT' or 'BTC' to the best perp market code (e.g.
    'BTCUSDT_PERP.A'). Prefers the most liquid exchange available."""
    if not is_configured():
        return None
    q = symbol_or_base.upper()
    base = q[:-4] if q.endswith("USDT") else q
    mkts, code2name = _discover()
    cands = [m for m in mkts
             if m.get("is_perpetual")
             and str(m.get("base_asset", "")).upper() == base
             and str(m.get("quote_asset", "")).upper() in ("USDT", "USD")]
    if not cands:
        return None

    def _rank(m):
        name = code2name.get(str(m.get("symbol", "")).rsplit(".", 1)[-1], "")
        try:
            r = _EXCH_PREF.index(name)
        except ValueError:
            r = len(_EXCH_PREF)
        # prefer USDT-margined over USD/coin-margined at equal venue
        return (r, 0 if str(m.get("quote_asset", "")).upper() == "USDT" else 1)

    return sorted(cands, key=_rank)[0].get("symbol")


# --- history helpers ---------------------------------------------------------
def _hist_frame(payload, value_cols: dict[str, str]) -> pd.DataFrame | None:
    """Flatten [{'symbol':..,'history':[{'t':..,..}]}] into a tz-aware
    DataFrame. value_cols maps API field -> output column name."""
    if not payload:
        return None
    hist = payload[0].get("history") or []
    if not hist:
        return None
    rows = [{"ts": h.get("t"), **{out: h.get(src)
                                  for src, out in value_cols.items()}}
            for h in hist]
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True)
    return df.set_index("ts").sort_index()


def _span(days: float) -> tuple[int, int]:
    to = int(time.time())
    return to - int(days * 86400), to


def oi_history(market: str, interval: str = "1hour", days: float = 30,
               convert_to_usd: bool = True) -> pd.DataFrame | None:
    """Open-interest OHLC history. Columns: oi_o/oi_h/oi_l/oi_c."""
    frm, to = _span(days)
    try:
        pl = _get("/open-interest-history",
                  {"symbols": market, "interval": interval,
                   "from": frm, "to": to,
                   "convert_to_usd": "true" if convert_to_usd else "false"})
    except Exception:
        return None
    return _hist_frame(pl, {"o": "oi_o", "h": "oi_h", "l": "oi_l",
                            "c": "oi_c"})


def funding_history(market: str, interval: str = "1hour",
                    days: float = 30) -> pd.DataFrame | None:
    """Funding-rate OHLC history. Columns: fr_o/fr_h/fr_l/fr_c."""
    frm, to = _span(days)
    try:
        pl = _get("/funding-rate-history",
                  {"symbols": market, "interval": interval,
                   "from": frm, "to": to})
    except Exception:
        return None
    return _hist_frame(pl, {"o": "fr_o", "h": "fr_h", "l": "fr_l",
                            "c": "fr_c"})


def long_short_history(market: str, interval: str = "1hour",
                       days: float = 30) -> pd.DataFrame | None:
    """Long/short account-ratio history. Columns: ratio/longs/shorts."""
    frm, to = _span(days)
    try:
        pl = _get("/long-short-ratio-history",
                  {"symbols": market, "interval": interval,
                   "from": frm, "to": to})
    except Exception:
        return None
    return _hist_frame(pl, {"r": "ratio", "l": "longs", "s": "shorts"})


def liquidation_history(market: str, interval: str = "1hour",
                        days: float = 30,
                        convert_to_usd: bool = True) -> pd.DataFrame | None:
    """Liquidation history. Columns: liq_long/liq_short (USD if converted)."""
    frm, to = _span(days)
    try:
        pl = _get("/liquidation-history",
                  {"symbols": market, "interval": interval,
                   "from": frm, "to": to,
                   "convert_to_usd": "true" if convert_to_usd else "false"})
    except Exception:
        return None
    return _hist_frame(pl, {"l": "liq_long", "s": "liq_short"})


# --- current snapshots -------------------------------------------------------
def current_oi(markets: list[str]) -> dict[str, float]:
    """Latest open interest per market code."""
    try:
        pl = _get("/open-interest", {"symbols": ",".join(markets),
                                     "convert_to_usd": "true"}) or []
    except Exception:
        return {}
    return {r.get("symbol"): r.get("value") for r in pl}


def current_funding(markets: list[str]) -> dict[str, float]:
    """Latest funding rate per market code."""
    try:
        pl = _get("/funding-rate", {"symbols": ",".join(markets)}) or []
    except Exception:
        return {}
    return {r.get("symbol"): r.get("value") for r in pl}


def predicted_funding(markets: list[str]) -> dict[str, float]:
    """Predicted next funding rate per market code."""
    try:
        pl = _get("/predicted-funding-rate",
                  {"symbols": ",".join(markets)}) or []
    except Exception:
        return {}
    return {r.get("symbol"): r.get("value") for r in pl}


# --- convenience: everything for one coin in one call each ------------------
def coin_positioning(symbol_or_base: str, interval: str = "1hour",
                     days: float = 30) -> dict | None:
    """OI + funding + long/short + liquidation history for one coin.

    Four API calls (plus discovery on first use). Returns dict of
    DataFrames keyed oi/funding/long_short/liquidations, or None when the
    coin can't be resolved / key missing.
    """
    mkt = resolve_perp(symbol_or_base)
    if not mkt:
        return None
    return {
        "market": mkt,
        "oi": oi_history(mkt, interval, days),
        "funding": funding_history(mkt, interval, days),
        "long_short": long_short_history(mkt, interval, days),
        "liquidations": liquidation_history(mkt, interval, days),
    }


if __name__ == "__main__":
    import sys
    if not is_configured():
        print("COINALYZE_API_KEY missing — put it in .env first.")
        sys.exit(1)
    print("Key found. Testing discovery + BTC positioning (5 calls)...")
    mkt = resolve_perp("BTCUSDT")
    print(f"  BTCUSDT resolves to: {mkt}")
    pos = coin_positioning("BTC", days=7)
    for k in ("oi", "funding", "long_short", "liquidations"):
        df = pos.get(k) if pos else None
        n = 0 if df is None else len(df)
        last = "" if df is None or df.empty else \
            f" last={df.iloc[-1].to_dict()}"
        print(f"  {k:12} rows={n}{last}")
    print("Coinalyze client OK.")
