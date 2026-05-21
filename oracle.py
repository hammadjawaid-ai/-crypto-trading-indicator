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
# Signal strength — how forcefully the breakout signal is backed
# ===========================================================================
_STRENGTH_BANDS = ((78, "Very Strong"), (60, "Strong"),
                   (42, "Moderate"), (0, "Weak"))


def signal_strength(row) -> dict:
    """How forcefully a breakout signal is backed — the breadth and force of
    the detection signals pulling the trade's way.

    This is an honest count of real agreement (the same philosophy as the
    engine's confidence score), not a flattering rescale: a setup backed by
    eight aligned forces firing hard scores far above one backed by three.

    Returns {score: 0-100, label: Weak | Moderate | Strong | Very Strong}.
    """
    drivers = row.get("drivers") or []
    sgn = 1 if row.get("dir_word") == "BULLISH" else -1
    signed = [d for d in drivers if d.get("signed")]
    unsigned = [d for d in drivers if not d.get("signed")]

    # breadth — share of directional forces leaning the trade's way
    aligned = [d for d in signed if d.get("score", 0) * sgn >= 12]
    breadth = len(aligned) / len(signed) if signed else 0.0
    # force — how hard those aligned forces are firing (saturates near 60)
    force = (sum(min(abs(d["score"]), 60) for d in aligned)
             / (len(aligned) * 60)) if aligned else 0.0
    # tailwind — non-directional forces (volume, volatility, social, news)
    tail = (sum(min(max(d.get("score", 0), 0), 100) for d in unsigned)
            / (len(unsigned) * 100)) if unsigned else 0.0

    score = (breadth * 46 + force * 30 + tail * 14
             + min(float(row.get("energy", 0.0)), 100) / 100 * 10)
    if row.get("ignited"):
        score += 6                       # volume igniting is a real edge
    if row.get("stage") == "EXTENDED":
        score -= 12                      # an exhausted move is not a fresh signal
    if row.get("trend_conflict"):
        score -= 10                      # fighting the trend undercuts it
    score = max(0.0, min(100.0, score))
    label = next(lbl for cut, lbl in _STRENGTH_BANDS if score >= cut)
    return {"score": round(score), "label": label}


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
    """Bullish-leaning coins with a concrete accumulation plan.

    Filters the radar to bullish COILED / FRESH coins, then attaches a buy
    zone, breakout trigger, stop, THREE targets — each with its own honest
    reward-to-risk and % gain measured from the buy zone — a signal-strength
    read, and market-cap / circulating-supply context. Returns a DataFrame
    carrying every original engine field (so the app can still render full
    cards) plus the added columns.
    """
    if radar is None or radar.empty:
        return pd.DataFrame()
    df = radar[(radar["dir_word"] == "BULLISH")
               & (radar["stage"].isin(["COILED", "FRESH"]))].copy()
    if df.empty:
        return df
    df = df.sort_values("opportunity", ascending=False).head(limit)
    mcap_map = mcap_map or {}

    cols: dict[str, list] = {k: [] for k in (
        "buy_low", "buy_high", "trigger", "bz_entry", "bz_stop",
        "bz_t1", "bz_t2", "bz_t3", "bz_rr1", "bz_rr2", "bz_rr3",
        "bz_gain1", "bz_gain2", "bz_gain3", "bz_risk_pct",
        "strength", "strength_label",
        "market_cap", "market_cap_rank", "cap_tier", "circ_pct")}

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
        entry = (lo + hi) / 2.0
        stop = idea["stop"]
        risk = entry - stop if (stop is not None and entry > stop) else 0.0
        t1, t2 = float(idea["target_1"]), float(idea["target_2"])
        t3 = t2 + (t2 - t1)              # the next measured leg higher

        cols["buy_low"].append(lo)
        cols["buy_high"].append(hi)
        cols["trigger"].append(float(r["win_high"]))
        cols["bz_entry"].append(entry)
        cols["bz_stop"].append(stop)
        cols["bz_t1"].append(t1)
        cols["bz_t2"].append(t2)
        cols["bz_t3"].append(t3)
        cols["bz_rr1"].append((t1 - entry) / risk if risk > 0 else 0.0)
        cols["bz_rr2"].append((t2 - entry) / risk if risk > 0 else 0.0)
        cols["bz_rr3"].append((t3 - entry) / risk if risk > 0 else 0.0)
        cols["bz_gain1"].append((t1 / entry - 1) * 100 if entry else 0.0)
        cols["bz_gain2"].append((t2 / entry - 1) * 100 if entry else 0.0)
        cols["bz_gain3"].append((t3 / entry - 1) * 100 if entry else 0.0)
        cols["bz_risk_pct"].append(risk / entry * 100 if entry else 0.0)

        strg = signal_strength(r)
        cols["strength"].append(strg["score"])
        cols["strength_label"].append(strg["label"])

        m = mcap_map.get(str(r["base"]).upper(), {})
        cap, rank = m.get("market_cap"), m.get("market_cap_rank")
        cols["market_cap"].append(cap)
        cols["market_cap_rank"].append(rank)
        cols["cap_tier"].append(_cap_tier(rank))
        cs, ms = m.get("circulating_supply"), m.get("max_supply")
        cols["circ_pct"].append(cs / ms * 100 if cs and ms else None)

    for key, values in cols.items():
        df[key] = values
    return df
