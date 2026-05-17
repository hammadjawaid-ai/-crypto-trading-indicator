"""Social-sentiment signal from Reddit's public JSON endpoints.

Reddit's per-subreddit ``.json`` endpoints are free, key-less and permitted
for light read-only use — a legitimate, Terms-of-Service-compliant stand-in
for X/Twitter retail buzz, which is no longer reachable without a paid API.
Post titles are scored with the same VADER analyser used for news headlines.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd
import requests

import config
import sentiment

_session = requests.Session()
_session.headers.update(
    {"User-Agent": "crypto-indicator/1.0 (social sentiment reader)"})


def _fetch_subreddit(category: str, subreddit: str) -> list[dict]:
    rows: list[dict] = []
    url = f"https://www.reddit.com/r/{subreddit}/hot.json"
    try:
        resp = _session.get(url, params={"limit": config.SOCIAL_LIMIT},
                            timeout=config.HTTP_TIMEOUT)
        resp.raise_for_status()
        children = resp.json()["data"]["children"]
    except (requests.RequestException, ValueError, KeyError):
        return rows  # skip a broken subreddit rather than fail the whole fetch

    for child in children:
        d = child.get("data", {})
        title = d.get("title", "")
        if not title or d.get("stickied"):  # skip pinned mod posts
            continue
        score = sentiment.score_text(title)
        rows.append(
            {
                "category": category,
                "source": f"r/{subreddit}",
                "title": title,
                "link": "https://www.reddit.com" + d.get("permalink", ""),
                "published": datetime.fromtimestamp(
                    d.get("created_utc", 0), tz=timezone.utc),
                "upvotes": int(d.get("score", 0)),
                "comments": int(d.get("num_comments", 0)),
                "sentiment": score,
                "mood": sentiment.classify(score),
            }
        )
    return rows


def fetch_social() -> pd.DataFrame:
    """Fetch hot posts from all configured subreddits, newest first.

    Columns: category, source, title, link, published, upvotes, comments,
    sentiment, mood.
    """
    jobs = [
        (cat, sub)
        for cat, subs in config.SOCIAL_FEEDS.items()
        for sub in subs
    ]
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for result in pool.map(lambda j: _fetch_subreddit(*j), jobs):
            rows.extend(result)

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("published", ascending=False).reset_index(drop=True)


def social_mood(df: pd.DataFrame, category: str | None = None) -> dict:
    """Upvote-weighted social mood for a category (or all posts if None).

    Weighting by upvotes lets posts the crowd actually engaged with carry
    more signal than ignored ones.
    """
    subset = df if category is None else df[df["category"] == category]
    if subset.empty:
        return {"score": 0.0, "mood": "Neutral", "count": 0}
    weights = subset["upvotes"].clip(lower=1)
    avg = float((subset["sentiment"] * weights).sum() / weights.sum())
    return {"score": avg, "mood": sentiment.classify(avg), "count": len(subset)}
