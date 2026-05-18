"""Coin Oracle — a plain-English Q&A layer over the live Breakout Radar, and a
bullish-accumulation buy-zone finder.

There is no LLM call here: questions are parsed deterministically against the
radar DataFrame the engine already produced. Every answer is therefore exact,
instant, free, and perfectly consistent with the rest of the Breakout Radar —
the Oracle can never contradict the cards the user is looking at.

The query engine recognises a handful of intents — a named coin, a direction
(bullish / bearish / both), the safest setup, volume ignition — and replies
with a headline, an explanation, and the matching radar rows for the app to
render as full breakout cards.
"""
from __future__ import annotations

import re

import pandas as pd

from breakout import COIN_NAMES

# --- Intent keyword sets ---------------------------------------------------
_BULL = ("bull", "bullish", "long", "up", "upside", "moon", "pump", "rally",
         "rocket", "rise", "rising", "green", "breakout", "explode", "buy",
         "higher", "blow up")
_BEAR = ("bear", "bearish", "short", "down", "downside", "dump", "crash",
         "fall", "falling", "drop", "sink", "red", "breakdown", "tank",
         "lower", "sell off", "sell-off", "selloff")
_SAFE = ("safe", "safest", "low risk", "low-risk", "least risky",
         "lowest risk", "conservative", "earliest")
_VOL = ("volume", "igniting", "ignite", "ignition", "surging", "surge",
        "waking", "wake")

_STAGE = {"COILED": "Building Up", "FRESH": "Just Started",
          "EXTENDED": "Already Ran"}


def _has(text: str, words) -> bool:
    """True if any keyword appears as a whole word/phrase in the text."""
    return any(re.search(r"\b" + re.escape(w) + r"\b", text) for w in words)


def _find_coin(question: str, radar: pd.DataFrame) -> str | None:
    """Detect a coin the user named — by ticker (BTC), name (bitcoin) or
    $-prefixed ticker. Returns the upper-case base symbol, or None."""
    if radar is None or radar.empty:
        return None
    ql = question.lower()
    tokens = set(re.findall(r"[a-z0-9]{2,}", ql))
    bases = [str(b).upper() for b in radar["base"].unique()]

    # Coin name first — more specific (e.g. "bitcoin" -> BTC).
    for base in bases:
        for name in COIN_NAMES.get(base, []):
            if name in ql:
                return base
    # $TICKER anywhere in the original text.
    for base in bases:
        if re.search(r"\$" + re.escape(base) + r"\b", question, re.I):
            return base
    # Plain ticker — length >= 3 so it can't collide with English words.
    for base in bases:
        if len(base) >= 3 and base.lower() in tokens:
            return base
    return None


def _rank(df: pd.DataFrame, safe: bool = False) -> pd.DataFrame:
    """Rank candidates — by confidence then score when 'safe' is asked for,
    otherwise straight by radar opportunity score."""
    if safe:
        return df.sort_values(["confidence", "opportunity"], ascending=False)
    return df.sort_values("opportunity", ascending=False)


def _empty(headline: str, detail: str, tone: str = "mixed") -> dict:
    return {"headline": headline, "detail": detail,
            "coins": pd.DataFrame(), "tone": tone}


# ===========================================================================
# Intent handlers
# ===========================================================================
def _coin_answer(base: str, radar: pd.DataFrame) -> dict:
    rows = radar[radar["base"].astype(str).str.upper() == base.upper()]
    if rows.empty:
        return _empty(
            f"{base} isn't in the current scan.",
            "The radar covers the top USDT pairs by 24h volume — this coin "
            "may sit outside that set on this horizon.")
    r = rows.iloc[0]
    tone = ("bullish" if r["dir_word"] == "BULLISH"
            else "bearish" if r["dir_word"] == "BEARISH" else "mixed")
    conflict = " It is also fighting its own trend, so treat it with care." \
        if r.get("trend_conflict") else ""
    detail = (f"Radar score {r['opportunity']:.0f}/100 at {r['confidence']}% "
              f"confidence, graded {_STAGE.get(r['stage'], r['stage'])} and "
              f"leaning {r['dir_word'].lower()}.{conflict} The full read, "
              f"entry zone, stop and targets are on the card below.")
    return {"headline": f"{r['base']} — {r['verdict'].lower()}.",
            "detail": detail, "coins": rows.head(1), "tone": tone}


def _side_answer(radar: pd.DataFrame, want: str, safe: bool) -> dict:
    word = "bullish" if want == "BULLISH" else "bearish"
    pool = radar[(radar["dir_word"] == want)
                 & (radar["stage"] != "EXTENDED")]
    if safe:
        pool = pool[pool["stage"] == "COILED"]
    if pool.empty:
        extra = " with a coiled, low-risk entry" if safe else ""
        return _empty(
            f"No clean {word} blowout setup right now.",
            f"The engine isn't seeing a non-extended coin leaning {word}"
            f"{extra}. The market may be rotating — try the other horizon, "
            f"or wait for the next few candles to close.")
    ranked = _rank(pool, safe).head(5)
    top = ranked.iloc[0]
    safe_txt = "lowest-risk " if safe else ""
    headline = (f"{top['base']} is the strongest {safe_txt}{word} blowout "
                f"candidate — {top['verdict'].lower()}.")
    detail = (f"It scores {top['opportunity']:.0f}/100 at "
              f"{top['confidence']}% confidence, graded "
              f"{_STAGE.get(top['stage'], top['stage'])}. {len(pool)} coin(s) "
              f"currently lean {word}; the top {len(ranked)} are below, each "
              f"with its own entry, stop and targets.")
    return {"headline": headline, "detail": detail, "coins": ranked,
            "tone": word}


def _both_answer(radar: pd.DataFrame) -> dict:
    live = radar[radar["stage"] != "EXTENDED"]
    bulls = _rank(live[live["dir_word"] == "BULLISH"]).head(3)
    bears = _rank(live[live["dir_word"] == "BEARISH"]).head(3)
    parts = []
    if not bulls.empty:
        parts.append(f"{bulls.iloc[0]['base']} leads the upside")
    if not bears.empty:
        parts.append(f"{bears.iloc[0]['base']} leads the downside")
    if not parts:
        return _empty(
            "No decisive blowout setup right now.",
            "Nothing is coiled or freshly breaking with a clear direction on "
            "this horizon — the tape is indecisive. Check back shortly.")
    coins = pd.concat([bulls, bears])
    return {"headline": "Next in line — " + " · ".join(parts) + ".",
            "detail": ("Both sides of the board, ranked by radar score. "
                       "Green cards are longs, red cards are shorts — each "
                       "carries its own entry, stop and targets."),
            "coins": coins, "tone": "mixed"}


def _volume_answer(radar: pd.DataFrame) -> dict:
    pool = _rank(radar[radar["ignited"].fillna(False)]).head(5)
    if pool.empty:
        return _empty(
            "No coin has volume igniting right now.",
            "Volume ignition — the last few candles trading several times the "
            "prior quiet baseline — is the classic pre-move tell. Nothing is "
            "showing it on this horizon yet.")
    top = pool.iloc[0]
    return {"headline": f"{top['base']} has the strongest volume ignition.",
            "detail": (f"{len(pool)} coin(s) are showing volume waking off a "
                       f"dormant base — the textbook pre-parabola tell. "
                       f"Listed below, strongest first."),
            "coins": pool, "tone": "mixed"}


def _safe_answer(radar: pd.DataFrame) -> dict:
    pool = radar[(radar["stage"] == "COILED")
                 & (radar["dir_word"] != "UNCLEAR")]
    pool = pool.sort_values(["confidence", "opportunity"],
                            ascending=False).head(5)
    if pool.empty:
        return _empty(
            "No low-risk coiled setup right now.",
            "“Building Up” coins — coiled, with a clear direction but no move "
            "yet — are the safest entries. None are on the board this "
            "moment; try the other horizon.")
    top = pool.iloc[0]
    return {"headline": (f"{top['base']} is the safest setup — coiled and "
                         f"leaning {top['dir_word'].lower()}, not moved yet."),
            "detail": ("“Building Up” coins haven't broken out, so you can "
                       "get positioned BEFORE the move instead of chasing "
                       "it. Ranked by confidence below."),
            "coins": pool,
            "tone": ("bullish" if top["dir_word"] == "BULLISH"
                     else "bearish")}


def _default_answer(radar: pd.DataFrame) -> dict:
    pool = _rank(radar[radar["stage"] != "EXTENDED"]).head(5)
    if pool.empty:
        pool = _rank(radar).head(5)
    top = pool.iloc[0]
    return {"headline": f"{top['base']} tops the radar right now.",
            "detail": ("Here are the strongest blowout candidates overall. "
                       "Ask me about a direction (“bullish” / “bearish”), a "
                       "specific coin, “safest long”, or “volume igniting” "
                       "to narrow it down."),
            "coins": pool,
            "tone": ("bullish" if top["dir_word"] == "BULLISH"
                     else "bearish" if top["dir_word"] == "BEARISH"
                     else "mixed")}


def answer(question: str, radar: pd.DataFrame, backdrop: dict) -> dict:
    """Answer a plain-English question against the live radar.

    Returns {headline, detail, coins (DataFrame), tone}. `coins` is a subset
    of `radar` the app renders as full breakout cards.
    """
    q = (question or "").strip().lower()
    if radar is None or radar.empty:
        return _empty(
            "The radar has no data right now.",
            "Use the Refresh button in the sidebar, or switch the horizon.",
            tone="empty")
    if not q:
        return _default_answer(radar)

    coin = _find_coin(question, radar)
    if coin:
        return _coin_answer(coin, radar)

    bull, bear = _has(q, _BULL), _has(q, _BEAR)
    safe, vol = _has(q, _SAFE), _has(q, _VOL)

    if vol and not bull and not bear:
        return _volume_answer(radar)
    if bull and bear:
        return _both_answer(radar)
    if bear and not bull:
        return _side_answer(radar, "BEARISH", safe)
    if bull and not bear:
        return _side_answer(radar, "BULLISH", safe)
    if safe:
        return _safe_answer(radar)
    return _default_answer(radar)


# ===========================================================================
# Bullish buy-zone finder
# ===========================================================================
_CAP_TIERS = ((10, "Mega cap"), (30, "Large cap"), (100, "Mid cap"))


def market_cap_map(lc_rows: list | None) -> dict[str, dict]:
    """Build a {base: {market_cap, rank, circulating, max}} map from a
    LunarCrush coin list — the 'circulation' context for the buy zones."""
    out: dict[str, dict] = {}
    for row in lc_rows or []:
        sym = row.get("symbol")
        if not sym:
            continue
        out[str(sym).upper()] = {
            "market_cap": row.get("market_cap"),
            "market_cap_rank": row.get("market_cap_rank"),
            "circulating_supply": row.get("circulating_supply"),
            "max_supply": row.get("max_supply"),
        }
    return out


def _cap_tier(rank: float | None) -> str:
    if rank is None or rank != rank:
        return "—"
    for cutoff, label in _CAP_TIERS:
        if rank <= cutoff:
            return label
    return "Small cap"


def buy_zones(radar: pd.DataFrame, mcap_map: dict | None = None,
              limit: int = 12) -> pd.DataFrame:
    """Bullish-leaning coins with a concrete accumulation zone.

    Filters the radar to bullish COILED / FRESH coins, then attaches a buy
    zone, breakout trigger, stop, targets, and market-cap / circulating-supply
    context. Returns a DataFrame carrying every original engine field (so the
    app can still render full cards) plus the added columns.
    """
    if radar is None or radar.empty:
        return pd.DataFrame()
    df = radar[(radar["dir_word"] == "BULLISH")
               & (radar["stage"].isin(["COILED", "FRESH"]))].copy()
    if df.empty:
        return df
    df = df.sort_values("opportunity", ascending=False).head(limit)
    mcap_map = mcap_map or {}

    buy_low, buy_high, trigger = [], [], []
    stop, t1, t2 = [], [], []
    mcap, mrank, tier, circ = [], [], [], []
    for _, r in df.iterrows():
        idea = r["idea"]
        if r["stage"] == "COILED":
            # Accumulate inside the range, before the break — get positioned
            # rather than chase the breakout candle.
            span = max(float(r["win_high"]) - float(r["win_low"]), 0.0)
            lo = float(r["win_low"]) + 0.15 * span
            hi = float(r["win_high"])
        else:  # FRESH — buy the retest of the level just broken
            lo, hi = float(idea["entry_low"]), float(idea["entry_high"])
        buy_low.append(lo)
        buy_high.append(hi)
        trigger.append(float(r["win_high"]))
        stop.append(idea["stop"])
        t1.append(idea["target_1"])
        t2.append(idea["target_2"])

        m = mcap_map.get(str(r["base"]).upper(), {})
        cap, rank = m.get("market_cap"), m.get("market_cap_rank")
        mcap.append(cap)
        mrank.append(rank)
        tier.append(_cap_tier(rank))
        cs, ms = m.get("circulating_supply"), m.get("max_supply")
        circ.append(cs / ms * 100 if cs and ms else None)

    df["buy_low"] = buy_low
    df["buy_high"] = buy_high
    df["trigger"] = trigger
    df["bz_stop"] = stop
    df["bz_t1"] = t1
    df["bz_t2"] = t2
    df["market_cap"] = mcap
    df["market_cap_rank"] = mrank
    df["cap_tier"] = tier
    df["circ_pct"] = circ
    return df
