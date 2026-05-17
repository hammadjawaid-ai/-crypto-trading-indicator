"""Live news aggregation from free RSS/Atom feeds, with sentiment scoring.

Feeds are parsed with the standard library (no third-party feed parser) so the
dependency set stays to pure wheels.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import pandas as pd
import requests

import config
import sentiment

_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0 (crypto-indicator/1.0)"})

# Atom namespace (RSS 2.0 uses no namespace).
_ATOM = "{http://www.w3.org/2005/Atom}"


def _text(element: ET.Element | None) -> str:
    return (element.text or "").strip() if element is not None else ""


def _parse_date(raw: str) -> datetime:
    raw = raw.strip()
    if not raw:
        return datetime.now(timezone.utc)
    # RSS uses RFC-822 dates; Atom uses ISO-8601.
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _extract_items(root: ET.Element) -> list[tuple[str, str, str, str]]:
    """Return (title, link, summary, date) tuples for RSS or Atom feeds."""
    items: list[tuple[str, str, str, str]] = []

    # RSS 2.0: <rss><channel><item>...
    for item in root.iter("item"):
        title = _text(item.find("title"))
        link = _text(item.find("link"))
        summary = _text(item.find("description"))
        date = _text(item.find("pubDate")) or _text(item.find("{*}date"))
        items.append((title, link, summary, date))

    if items:
        return items

    # Atom: <feed><entry>...
    for entry in root.iter(f"{_ATOM}entry"):
        title = _text(entry.find(f"{_ATOM}title"))
        link_el = entry.find(f"{_ATOM}link")
        link = link_el.get("href", "") if link_el is not None else ""
        summary = _text(entry.find(f"{_ATOM}summary"))
        date = (_text(entry.find(f"{_ATOM}published"))
                or _text(entry.find(f"{_ATOM}updated")))
        items.append((title, link, summary, date))
    return items


def _parse_feed(category: str, source: str, url: str) -> list[dict]:
    rows: list[dict] = []
    try:
        resp = _session.get(url, timeout=config.HTTP_TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except (requests.RequestException, ET.ParseError):
        return rows  # skip a broken feed rather than fail the whole fetch

    for title, link, summary, date in _extract_items(root)[:25]:
        if not title:
            continue
        score = sentiment.score_text(f"{title}. {summary}")
        rows.append(
            {
                "category": category,
                "source": source,
                "title": title,
                "link": link,
                "published": _parse_date(date),
                "sentiment": score,
                "mood": sentiment.classify(score),
            }
        )
    return rows


def fetch_news() -> pd.DataFrame:
    """Fetch and merge all configured feeds, newest first.

    Columns: category, source, title, link, published, sentiment, mood.
    """
    jobs = [
        (cat, src, url)
        for cat, feeds in config.NEWS_FEEDS.items()
        for src, url in feeds
    ]
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for result in pool.map(lambda j: _parse_feed(*j), jobs):
            rows.extend(result)

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("published", ascending=False).reset_index(drop=True)


def category_mood(df: pd.DataFrame, category: str | None = None) -> dict:
    """Average sentiment for a category (or all news if category is None)."""
    subset = df if category is None else df[df["category"] == category]
    if subset.empty:
        return {"score": 0.0, "mood": "Neutral", "count": 0}
    avg = float(subset["sentiment"].mean())
    return {"score": avg, "mood": sentiment.classify(avg), "count": len(subset)}
