"""News-impact detection — surface the headlines that are MOVING the tape.

The dashboard already aggregates per-headline sentiment from RSS feeds.
This module sits on top: it scans the freshest headlines for high-impact
language (SEC / Fed / CPI / ETF / regulation / hack / liquidation / ETF
approval / delayed / rejected, etc.) and combines that with the
already-computed sentiment to flag the few headlines that actually explain
WHY price is moving right now.

The output feeds the 'Why this is happening' panel under the BTC banner
and the browser desktop-notification stream — when a new impactful headline
lands the user gets a real-time pop-up.

Pure logic, no Streamlit. Direction comes from the headline's own sentiment
(never invented); the keyword check only decides whether the headline is
IMPACTFUL — recognising the kind of event that moves markets.

Keyword matching uses WORD BOUNDARIES (so 'ath' never matches inside 'death'
and 'ban' never inside 'urban'). A tier system separates self-evident
market events (Tier 1 — always counts) from ambiguous terms (Tier 2 — only
counts when the headline also mentions a crypto / market / finance term),
which keeps unrelated news ('Ebola travel ban', 'World Cup sanctions') out
of the market-impact stream.
"""
from __future__ import annotations

import re

import pandas as pd

# ---- Tier 1: self-evidently market-moving — counts regardless of context.
_TIER1: dict[str, float] = {
    # Regulation / policy
    "sec": 1.00, "cftc": 0.90, "fomc": 1.00, "cpi": 1.00, "ppi": 0.85,
    # ETF / institutional product
    "spot etf": 1.10, "etf approval": 1.10, "etf delayed": 1.10,
    "blackrock": 0.70, "grayscale": 0.60, "fidelity": 0.55,
    # Monetary policy
    "rate hike": 1.00, "rate cut": 1.00, "interest rate": 0.85,
    "fed ": 1.00, "powell": 0.80,
    # Crypto-specific catalysts
    "halving": 0.85, "halved": 0.85, "all-time high": 0.85,
    "rug pull": 0.85, "rugpull": 0.85,
    # Crisis (these are almost always market-moving when reported)
    "hack": 1.00, "hacked": 1.00, "exploit": 0.95, "exploited": 0.95,
    "bankruptcy": 1.00, "insolvent": 0.95, "fraud": 0.95,
    "liquidations": 0.85, "liquidated": 0.85,
}

# ---- Tier 2: impactful BUT only when crypto / market / finance context is
# present in the headline (avoids "Ebola travel ban" type false positives).
_TIER2: dict[str, float] = {
    "regulator": 0.85, "regulation": 0.85, "regulatory": 0.85,
    "approved": 0.85, "approval": 0.85, "rejected": 0.95, "rejects": 0.95,
    "delayed": 0.90, "denied": 0.95, "banned": 1.00, "ban": 0.95,
    "crackdown": 0.95, "lawsuit": 0.85, "sued": 0.80,
    "etf": 1.00, "treasury": 0.55, "yields": 0.60,
    "tariff": 0.75, "tariffs": 0.75,
    "war": 0.90, "sanctions": 0.85, "geopolitical": 0.70,
    "recession": 0.80, "inflation": 0.75, "jobs report": 0.70,
    "collapse": 0.95, "collapsed": 0.95, "liquidation": 0.85,
    "scam": 0.85, "trillion": 0.70, "billion": 0.45,
}

# ---- Crypto / market / finance context terms. Tier-2 keywords only score
# when at least one of these appears in the headline (or the news category
# is itself 'Crypto').
_CONTEXT: set[str] = {
    "bitcoin", "btc", "ethereum", "eth", "crypto", "cryptocurrency",
    "blockchain", "stablecoin", "tether", "usdt", "usdc",
    "exchange", "binance", "coinbase", "kraken", "okx", "bybit",
    "stock", "stocks", "equities", "market", "markets", "trading",
    "trader", "wall street", "nasdaq", "nyse", "s&p", "dow",
    "dollar", "usd", "bond", "bonds", "fed", "fomc", "rate", "rates",
    "tradfi", "defi", "financial", "finance", "macro", "investor",
    "investors", "futures", "spot", "etf",
}

# Phrases the UI shows as the 'why' chip first (most informative).
_HIGHLIGHT_PRIORITY: tuple[str, ...] = (
    "spot etf", "etf approval", "etf delayed", "rate cut", "rate hike",
    "fomc", "cpi", "rejected", "denied", "delayed", "approved", "approval",
    "ban", "banned", "crackdown", "hack", "exploit", "liquidation",
    "liquidations", "collapse", "bankruptcy", "fraud", "war", "sanctions",
    "tariff", "tariffs", "halving", "all-time high", "lawsuit", "sued",
    "sec", "fomc", "cpi",
)


def _word_hit(text: str, term: str) -> bool:
    """True if `term` appears as a whole word / phrase in lowercase `text`."""
    return re.search(r"\b" + re.escape(term) + r"\b", text) is not None


def _has_context(text: str) -> bool:
    return any(_word_hit(text, ctx) for ctx in _CONTEXT)


def _impact_score(title: str, sentiment: float,
                  category: str = "") -> tuple[float, list[str]]:
    """Return (impact_score, matched_keywords) for one headline.

    impact_score >= 0.55 is the default 'high-impact' bar. Tier 2 hits only
    contribute when the headline carries crypto / market context (or is in
    the 'Crypto' news category). Direction comes from sentiment separately.
    """
    t = title.lower()
    matched: list[str] = []
    best_kw_weight = 0.0
    in_context = (category.strip().lower() == "crypto") or _has_context(t)

    for kw, weight in _TIER1.items():
        if _word_hit(t, kw.strip()):
            matched.append(kw.strip())
            if weight > best_kw_weight:
                best_kw_weight = weight
    if in_context:
        for kw, weight in _TIER2.items():
            if _word_hit(t, kw):
                matched.append(kw)
                if weight > best_kw_weight:
                    best_kw_weight = weight

    sent_strength = min(1.0, abs(float(sentiment or 0.0)))
    score = best_kw_weight * 0.65 + sent_strength * 0.35

    # Promote the most informative term to the front for the UI chip.
    matched.sort(key=lambda k: (k not in _HIGHLIGHT_PRIORITY, k))
    # Deduplicate preserving order.
    seen: set[str] = set()
    matched = [k for k in matched if not (k in seen or seen.add(k))]
    return score, matched


def detect_impactful(news_df: pd.DataFrame, *,
                     max_count: int = 8,
                     min_score: float = 0.62) -> list[dict]:
    """Pick the most impactful headlines from a freshly fetched news DataFrame.

    Returns a list of dicts the UI can render directly:
      {title, source, link, sentiment, direction, score, keywords, category,
       published}.

    Direction is taken from each headline's existing sentiment (never
    invented). Headlines are walked freshest-first; results are sorted
    strongest-first and trimmed to `max_count`. The higher default
    `min_score` keeps only genuinely market-moving stories — no flooding
    the impact panel with marginal mentions.
    """
    if news_df is None or len(news_df) == 0:
        return []
    items: list[dict] = []
    for _, row in news_df.head(120).iterrows():
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        sent = float(row.get("sentiment") or 0.0)
        category = str(row.get("category") or "")
        score, kws = _impact_score(title, sent, category)
        if score < min_score:
            continue
        direction = ("Bullish" if sent > 0.15
                     else "Bearish" if sent < -0.15 else "Neutral")
        items.append({
            "title": title,
            "source": str(row.get("source") or ""),
            "link": str(row.get("link") or ""),
            "category": category,
            "sentiment": round(sent, 2),
            "score": round(score, 2),
            "keywords": kws[:4],
            "direction": direction,
            "published": row.get("published"),   # datetime for time-ago UI
        })
        if len(items) >= max_count * 2:   # collect extra so the sort has range
            break
    items.sort(key=lambda i: i["score"], reverse=True)
    return items[:max_count]
