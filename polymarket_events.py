"""Polymarket event radar — FREE public API, no key.

Prediction-market odds are the cleanest live read on binary macro events
(Fed decisions, regulation, ETF rulings, geopolitics). This module pulls
the highest-volume open events from Polymarket's public Gamma API and
surfaces the ones that are (a) macro/crypto-relevant, (b) resolving soon,
and (c) genuinely UNCERTAIN (odds between ~15-85%) — i.e. the coin-flips
that whipsaw crypto when they land.

INFORMATIONAL ONLY: used for the ⚠️ event line in the daily reports so
the trader knows a binary event is ahead. It gates nothing — any use as a
filter must first be validated like every other edge in this repo.

Endpoint: https://gamma-api.polymarket.com/events (public, no auth).
Cached 30 min; every function degrades to empty on any failure.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone

import requests

GAMMA = "https://gamma-api.polymarket.com"
_session = requests.Session()
_session.headers.update({"User-Agent": "crypto-indicator/1.0"})

# Macro / crypto relevance — whole-word match on the event title (plain
# substring matching is a trap: 'rate' hits 'Pirates', 'eth' hits
# 'Ethiopia', 'war' hits 'Warriors').
_KEYWORDS = (
    "fed", "fomc", "rate cut", "rate cuts", "rate hike", "interest rate",
    "powell", "cpi", "inflation", "recession", "tariff", "tariffs",
    "shutdown", "treasury", "bitcoin", "btc", "ethereum", "eth", "solana",
    "crypto", "etf", "sec", "stablecoin", "binance", "coinbase",
    "election", "war", "strike on", "ceasefire", "sanction", "sanctions",
)
_KW_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _KEYWORDS) + r")\b",
    re.IGNORECASE)

# Recurring price-bet markets ("Bitcoin Up or Down on July 11?") mirror the
# current price — they aren't scheduled events that whipsaw the market.
_NOISE_RE = re.compile(
    r"up or down|above ___|what price will|price on \w+|hit in \d{4}"
    r"|hit \w+ \d", re.IGNORECASE)

_cache: dict = {"ts": 0.0, "events": None}
_TTL = 1800.0


def _fetch(limit: int = 100) -> list:
    resp = _session.get(
        f"{GAMMA}/events",
        params={"closed": "false", "order": "volume24hr",
                "ascending": "false", "limit": limit},
        timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def _events() -> list:
    now = time.time()
    if _cache["events"] is not None and now - _cache["ts"] < _TTL:
        return _cache["events"]
    try:
        _cache["events"] = _fetch()
        _cache["ts"] = now
    except Exception:
        return _cache["events"] or []
    return _cache["events"]


def _ends_in_h(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return (dt - datetime.now(timezone.utc)).total_seconds() / 3600.0
    except Exception:
        return None


def _headline_prob(ev: dict) -> float | None:
    """Probability of the LEADING outcome across the event's markets
    (0..1). Multi-outcome events (e.g. a Fed decision with one market per
    bps bucket) list many longshots — the max first-outcome price is the
    front-runner, and 'is the front-runner still uncertain?' is the
    question that matters."""
    best = None
    for m in ev.get("markets") or []:
        try:
            prices = m.get("outcomePrices")
            if isinstance(prices, str):
                prices = json.loads(prices)
            p = float(prices[0])
        except Exception:
            continue
        if best is None or p > best:
            best = p
    return best


def upcoming_risks(hours: float = 72, min_vol24: float = 25000,
                   max_out: int = 5) -> list[dict]:
    """Macro/crypto-relevant, high-volume, UNCERTAIN events resolving
    within `hours`. Each: {title, ends_in_h, prob, vol24}."""
    out = []
    for ev in _events():
        title = str(ev.get("title") or "")
        if not _KW_RE.search(title) or _NOISE_RE.search(title):
            continue
        eih = _ends_in_h(ev.get("endDate"))
        if eih is None or not (0 < eih <= hours):
            continue
        try:
            vol24 = float(ev.get("volume24hr") or 0)
        except Exception:
            vol24 = 0.0
        if vol24 < min_vol24:
            continue
        prob = _headline_prob(ev)
        # a 97% market is already decided — only coin-flips whipsaw price
        if prob is not None and not (0.15 <= prob <= 0.85):
            continue
        out.append({"title": title, "ends_in_h": eih, "prob": prob,
                    "vol24": vol24})
    out.sort(key=lambda e: e["ends_in_h"])
    return out[:max_out]


def radar_line(hours: float = 72) -> str:
    """One digest-ready line, or '' when no qualifying events ahead."""
    evs = upcoming_risks(hours)
    if not evs:
        return ""
    parts = []
    for e in evs[:3]:
        p = (f" {e['prob'] * 100:.0f}%" if e.get("prob") is not None
             else "")
        eih = e["ends_in_h"]
        when = f"{eih / 24:.0f}d" if eih >= 24 else f"{eih:.0f}h"
        parts.append(f"{e['title'][:45]}{p} · {when}")
    return "⚠️ binary events ahead: " + " | ".join(parts)


if __name__ == "__main__":
    print("Fetching Polymarket events (public API)...")
    evs = upcoming_risks(hours=7 * 24)
    print(f"qualifying events (7d window): {len(evs)}")
    for e in evs:
        p = f"{e['prob']*100:.0f}%" if e.get("prob") is not None else "?"
        print(f"  {e['ends_in_h']:6.1f}h · {p:>4} · "
              f"${e['vol24']:>12,.0f} · {e['title']}")
    line = radar_line(72)
    print("digest line:", line or "(none in 72h)")
