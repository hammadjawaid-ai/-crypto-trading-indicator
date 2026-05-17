"""Market-sentiment helpers: Crypto Fear & Greed index + text scoring."""
from __future__ import annotations

import pandas as pd
import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

import config

_session = requests.Session()
_session.headers.update({"User-Agent": "crypto-indicator/1.0"})
_analyzer = SentimentIntensityAnalyzer()


def fear_greed() -> dict:
    """Return the Crypto Fear & Greed index.

    Keys: value (0-100), label, yesterday, week_ago, history (DataFrame).
    """
    resp = _session.get(config.FEAR_GREED_URL, timeout=config.HTTP_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()["data"]

    hist = pd.DataFrame(data)
    hist["value"] = hist["value"].astype(int)
    hist["timestamp"] = pd.to_datetime(hist["timestamp"].astype(int),
                                       unit="s", utc=True)
    hist = hist.sort_values("timestamp")

    latest = data[0]
    return {
        "value": int(latest["value"]),
        "label": latest["value_classification"],
        "yesterday": int(data[1]["value"]) if len(data) > 1 else None,
        "week_ago": int(data[7]["value"]) if len(data) > 7 else None,
        "history": hist[["timestamp", "value"]],
    }


def score_text(text: str) -> float:
    """VADER compound sentiment for a headline (-1 bearish .. +1 bullish)."""
    if not text:
        return 0.0
    return _analyzer.polarity_scores(text)["compound"]


def classify(score: float) -> str:
    if score >= 0.25:
        return "Bullish"
    if score <= -0.25:
        return "Bearish"
    return "Neutral"
