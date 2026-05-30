"""Premium Picks Agent — top-N high-conviction candidates from Binance USDT-perps.

Scans the top `scan_n` Binance USDT pairs by 24h quote volume, runs the
lightweight conviction screen from `coin_deep_analyzer.analyze(symbol, tf)` in
parallel, and returns the highest-conviction picks that clear the PREMIUM bar
(default conviction_score >= 85).

This module is the "Section 2" surface from the 24/7 Agent design: it never
duplicates symbols that already live in `watchlist_agent.PORTFOLIO_COINS`
(imported lazily to avoid circular imports), and it returns an empty list when
nothing qualifies — the UI then renders the "no premium picks right now"
empty state.

Public API:
    scan_premium_picks(timeframe='1h',
                       scan_n=200,
                       min_conviction=85,
                       max_picks=10) -> list[dict]

Each result dict carries:
    symbol, base, side, conviction_score, tier, trade_plan,
    top_3_reasons, price_now, pct_24h
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import binance_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: PREMIUM bar — picks must clear this conviction_score to be shown.
PREMIUM_BAR: int = 85

#: Max parallel workers for the conviction scan (matches the spec).
MAX_WORKERS: int = 8

#: Default scan universe size — top-N Binance USDT pairs by 24h quote volume.
DEFAULT_SCAN_N: int = 200

#: Default cap on returned picks.
DEFAULT_MAX_PICKS: int = 10

#: Default timeframe for the lightweight conviction screen.
DEFAULT_TIMEFRAME: str = "1h"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _portfolio_excludes() -> set[str]:
    """Lazily import `watchlist_agent.PORTFOLIO_COINS` and return as a set.

    Imported inside the function to avoid circular imports (watchlist_agent
    and premium_picks_agent are sibling sub-section modules of the 24/7
    Agent and may both be imported by app.py at startup).

    Returns an empty set if the module or constant isn't available yet —
    the scan still works, it just doesn't dedupe against the watchlist.
    """
    try:
        import watchlist_agent  # noqa: WPS433 (intentional lazy import)
        coins = getattr(watchlist_agent, "PORTFOLIO_COINS", None)
        if coins is None:
            return set()
        return {str(s).upper() for s in coins}
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("watchlist_agent.PORTFOLIO_COINS unavailable: %s", exc)
        return set()


def _base_of(symbol: str, quote: str = "USDT") -> str:
    """Strip the quote asset suffix from a symbol (e.g. BTCUSDT → BTC)."""
    sym = str(symbol).upper()
    if sym.endswith(quote):
        return sym[: -len(quote)]
    return sym


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Best-effort float coercion that never raises."""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    """Best-effort int coercion that never raises."""
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _build_universe(scan_n: int, exclude: set[str]) -> list[tuple[str, dict]]:
    """Fetch the top-N Binance USDT pairs and drop any in `exclude`.

    Returns a list of (symbol, ticker_row) tuples preserving Binance's
    volume-descending order so we scan the most liquid coins first.
    """
    try:
        df = binance_client.get_top_symbols(scan_n)
    except Exception as exc:
        logger.warning("get_top_symbols(%d) failed: %s", scan_n, exc)
        return []

    universe: list[tuple[str, dict]] = []
    for _, row in df.iterrows():
        symbol = str(row.get("symbol", "")).upper()
        if not symbol or symbol in exclude:
            continue
        # Belt-and-braces: also exclude by base in case the watchlist is
        # specified without the USDT suffix.
        base = str(row.get("base", _base_of(symbol))).upper()
        if base in exclude or f"{base}USDT" in exclude:
            continue
        universe.append((symbol, row.to_dict()))
    return universe


def _analyze_one(symbol: str, timeframe: str) -> dict | None:
    """Call coin_deep_analyzer.analyze(symbol, tf) and swallow any errors.

    The import is performed lazily so this module stays importable even
    when coin_deep_analyzer is being iterated on (or before it's wired
    into app.py).
    """
    try:
        import coin_deep_analyzer  # noqa: WPS433 (intentional lazy import)
    except Exception as exc:
        logger.debug("coin_deep_analyzer import failed for %s: %s", symbol, exc)
        return None

    try:
        result = coin_deep_analyzer.analyze(symbol, timeframe)
    except Exception as exc:
        logger.debug("coin_deep_analyzer.analyze(%s, %s) failed: %s",
                     symbol, timeframe, exc)
        return None

    if not isinstance(result, dict):
        return None
    return result


def _normalize_pick(symbol: str,
                    analysis: dict,
                    ticker: dict) -> dict:
    """Coerce the analyzer result into the public premium-pick schema.

    The analyzer may return scores under a few different keys depending on
    which version of the conviction engine is wired in. We accept the most
    common aliases and fall back to sensible defaults so a single bad row
    can't blow up the whole scan.
    """
    sym = str(symbol).upper()
    base = str(analysis.get("base") or ticker.get("base") or _base_of(sym))

    conviction = analysis.get("conviction_score")
    if conviction is None:
        # Common aliases used elsewhere in the codebase.
        for key in ("score", "blended_score", "confidence"):
            if key in analysis and analysis[key] is not None:
                conviction = analysis[key]
                break
    conviction = _safe_float(conviction, default=0.0)

    side = str(analysis.get("side") or "NEUTRAL").upper()
    tier = analysis.get("tier") or analysis.get("bull_bear") or ""

    trade_plan = (analysis.get("trade_plan")
                  or analysis.get("plan")
                  or {})
    if not isinstance(trade_plan, dict):
        trade_plan = {}

    reasons = (analysis.get("top_3_reasons")
               or analysis.get("reasons")
               or analysis.get("drivers")
               or [])
    if not isinstance(reasons, list):
        reasons = []
    # Trim to 3 + coerce each item to a string for safe rendering.
    top_3_reasons = [str(r) if not isinstance(r, dict)
                     else str(r.get("note") or r.get("lane") or r)
                     for r in reasons[:3]]

    price_now = analysis.get("price_now")
    if price_now is None:
        price_now = ticker.get("lastPrice")
    price_now = _safe_float(price_now, default=0.0)

    pct_24h = analysis.get("pct_24h")
    if pct_24h is None:
        pct_24h = ticker.get("priceChangePercent")
    pct_24h = _safe_float(pct_24h, default=0.0)

    return {
        "symbol": sym,
        "base": base,
        "side": side,
        "conviction_score": round(conviction, 1),
        "tier": str(tier),
        "trade_plan": trade_plan,
        "top_3_reasons": top_3_reasons,
        "price_now": price_now,
        "pct_24h": pct_24h,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_premium_picks(timeframe: str = DEFAULT_TIMEFRAME,
                       scan_n: int = DEFAULT_SCAN_N,
                       min_conviction: int = PREMIUM_BAR,
                       max_picks: int = DEFAULT_MAX_PICKS) -> list[dict]:
    """Scan the top-N Binance USDT pairs and return high-conviction picks.

    Parameters
    ----------
    timeframe:
        Timeframe passed to `coin_deep_analyzer.analyze`. Defaults to ``"1h"``.
    scan_n:
        How many top Binance USDT pairs (by 24h quote volume) to scan.
        Defaults to 200.
    min_conviction:
        Minimum conviction_score for a pick to qualify. Defaults to the
        PREMIUM bar (85).
    max_picks:
        Hard cap on the number of picks returned. Defaults to 10.

    Returns
    -------
    list[dict]
        Up to `max_picks` picks, sorted by conviction_score DESC. Each dict
        carries: symbol, base, side, conviction_score, tier, trade_plan,
        top_3_reasons, price_now, pct_24h. Returns an empty list if nothing
        clears the bar — the UI then shows "no premium picks right now".
    """
    # Exclude the watchlist so this section never duplicates Section 1.
    exclude = _portfolio_excludes()

    universe = _build_universe(scan_n, exclude)
    if not universe:
        return []

    # Run the lightweight conviction screen in parallel. We use
    # as_completed so the slowest coin doesn't stall the rest, and
    # short-circuit at the end via the conviction filter + sort.
    picks: list[dict] = []
    workers = min(MAX_WORKERS, max(1, len(universe)))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_analyze_one, sym, timeframe): (sym, ticker)
            for sym, ticker in universe
        }
        for fut in as_completed(futures):
            sym, ticker = futures[fut]
            try:
                analysis = fut.result()
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("conviction worker raised for %s: %s", sym, exc)
                continue
            if not analysis:
                continue
            pick = _normalize_pick(sym, analysis, ticker)
            if pick["conviction_score"] >= min_conviction:
                picks.append(pick)

    if not picks:
        return []

    picks.sort(key=lambda p: p["conviction_score"], reverse=True)
    return picks[: max(0, int(max_picks))]


__all__ = ["scan_premium_picks", "PREMIUM_BAR"]
