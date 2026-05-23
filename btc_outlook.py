"""BTC 24h Outlook — the most important read on the dashboard.

When BTC moves, the whole market follows. This module fuses the strongest
leading indicators of BTC's next 24-hour direction into one calibrated
lean and surfaces the evidence — drivers — and the specific risks — flags —
behind it.

Confidence is built from BREADTH of agreement across INDEPENDENT categories
(technicals across 4h / 1d / 1w, derivatives positioning, macro backdrop,
rotational flow, alt-vs-BTC divergence) — when many uncorrelated lenses
point the same way that is a genuinely stronger signal, not a multiplied
number. A strong-trend regime (1d ADX >= 25) earns a small extra weight on
the technicals because the trend signal itself is more reliable there.

Lesson the module is built to flag (the user lived it): alts surging while
BTC stalls/extends is a classic pattern that resolves with BTC catching
down — alts often follow BTC into the drop hours later. The 'Alt-vs-BTC
divergence' driver spots that BEFORE it resolves.

Honest by design: not a crystal ball. BTC's next 24 hours cannot be
predicted with certainty; the output is a probabilistic lean. Every input
TILTS the read within bounds, none of them overrides it. Warning flags are
shown whether they confirm or contradict the net direction, so the trader
can respect the caution even when the model leans the other way.
"""
from __future__ import annotations

# Thresholds — chosen to match the engine's existing positioning signals.
_FUNDING_HOT = 0.0006     # 0.06% per 8h => crowded longs / shorts
_FUNDING_WARM = 0.0001
_FNG_EUPHORIA = 78
_FNG_CAPITULATION = 22
_LS_CROWD_LONG = 2.0
_LS_CROWD_SHORT = 0.6
_ADX_TRENDING = 25        # 1d ADX above this counts as a strong trend


def _band(score: float) -> str:
    if score >= 15:
        return "Up"
    if score <= -15:
        return "Down"
    return "Neutral"


def _takeaway(direction: str, confidence: int, flags: list[str]) -> str:
    if direction == "Up":
        base = ("BTC LEANS UP over the next 24h — strong conviction."
                if confidence >= 75
                else "BTC LEANS UP over the next 24h — meaningful conviction."
                if confidence >= 60
                else "BTC tilting up over the next 24h.")
    elif direction == "Down":
        base = ("BTC LEANS DOWN over the next 24h — strong conviction."
                if confidence >= 75
                else "BTC LEANS DOWN over the next 24h — meaningful conviction."
                if confidence >= 60
                else "BTC tilting down over the next 24h.")
    else:
        base = "BTC has no clear 24h edge — the tape can chop either way."
    if flags:
        base += " Respect the caution flags below regardless of the lean."
    return base


def compute(btc_4h: dict | None, btc_1d: dict | None,
            deriv: dict | None, fear_greed: int | None,
            mcap_change: float | None, btc_change_24h: float,
            alt_change_24h_median: float,
            btc_1w: dict | None = None,
            news: dict | None = None) -> dict:
    """Build the BTC 24h Outlook from every input we can get our hands on.

    Inputs (any may be None, the module degrades gracefully):
      btc_4h, btc_1d, btc_1w — signals.analyze(...) for BTCUSDT on each TF.
                               The weekly is the dominant trend backbone.
      deriv                  — BTC derivatives snapshot
                               (funding, long_short_ratio, oi_change_pct).
      fear_greed             — Fear & Greed 0-100.
      mcap_change            — total crypto market cap 24h % change.
      btc_change_24h         — BTC's own 24h % change.
      alt_change_24h_median  — median 24h % change of the top alts.

    Returns: {direction, bias_score, confidence, expected_range_pct,
              drivers, flags, takeaway, aligned_categories}.
    """
    drivers: list[dict] = []
    flags: list[str] = []
    confs: list[float] = []

    def add(force: str, lean: float, weight: float, note: str,
            category: str) -> None:
        lean = max(-1.0, min(1.0, lean))
        drivers.append({"force": force, "lean": round(lean, 2),
                        "weight": weight, "note": note,
                        "category": category})

    # ---- Technicals: 4h + 1d + 1w backbone, weekly weighs the heaviest ---
    has_any_tech = bool(btc_4h or btc_1d or btc_1w)
    if has_any_tech:
        s4 = float((btc_4h or {}).get("score") or 0.0) / 100.0
        s1d = float((btc_1d or {}).get("score") or 0.0) / 100.0
        s1w = float((btc_1w or {}).get("score") or 0.0) / 100.0
        if btc_1w:
            # 1w (the macro trend) 30%, 1d (the actionable day) 50%,
            # 4h (recent momentum) 20% — a 24h call still hangs on the 1d.
            tech_lean = 0.20 * s4 + 0.50 * s1d + 0.30 * s1w
            note = (f"4h {(btc_4h or {}).get('score', 0):+.0f} · "
                    f"1d {(btc_1d or {}).get('score', 0):+.0f} · "
                    f"1w {(btc_1w or {}).get('score', 0):+.0f}")
            label = "Technicals (4h + 1d + 1w)"
        else:
            tech_lean = 0.4 * s4 + 0.6 * s1d
            note = (f"4h {(btc_4h or {}).get('score', 0):+.0f} · "
                    f"1d {(btc_1d or {}).get('score', 0):+.0f}")
            label = "Technicals (4h + 1d)"
        # Strong-trend regime — the technical signal is more reliable; lift
        # its weight modestly. This is calibration, not inflation.
        adx_1d = float((btc_1d or {}).get("adx") or 0.0)
        strong_trend = adx_1d >= _ADX_TRENDING
        tech_weight = 40 if strong_trend else 32
        add(label, tech_lean, tech_weight, note, "tech")
        if btc_1d:
            confs.append(float(btc_1d.get("confidence") or 50))
        if btc_4h:
            confs.append(float(btc_4h.get("confidence") or 50))
        if btc_1w:
            confs.append(float(btc_1w.get("confidence") or 50))
        # Extension flag via 1d RSI — BTC overbought / oversold on the daily.
        rsi_1d = float((btc_1d or {}).get("rsi") or 50)
        if rsi_1d >= 76:
            flags.append(f"1d RSI {rsi_1d:.0f} — BTC overbought on the daily; "
                         "mean-reversion risk to the downside")
        elif rsi_1d <= 24:
            flags.append(f"1d RSI {rsi_1d:.0f} — BTC oversold on the daily; "
                         "squeeze-up risk for late shorts")

    # ---- Derivatives positioning (geo-blocked on cloud → may be None) ----
    if deriv:
        funding = deriv.get("funding")
        ls = deriv.get("long_short_ratio")
        oi = deriv.get("oi_change_pct")
        if funding is not None:
            f_pct = funding * 100
            if funding >= _FUNDING_HOT:
                add("BTC funding", -0.7, 25,
                    f"funding {f_pct:+.3f}% — crowded longs (contrarian short)",
                    "deriv")
                flags.append(f"BTC funding {f_pct:+.3f}% — crowded longs, "
                             "SQUEEZE-DOWN risk")
            elif funding <= -_FUNDING_HOT:
                add("BTC funding", 0.7, 25,
                    f"funding {f_pct:+.3f}% — crowded shorts (squeeze up)",
                    "deriv")
                flags.append(f"BTC funding {f_pct:+.3f}% — crowded shorts, "
                             "SQUEEZE-UP risk")
            elif funding >= _FUNDING_WARM:
                add("BTC funding", 0.25, 15,
                    f"funding {f_pct:+.3f}% — moderate bullish bias", "deriv")
            elif funding <= -_FUNDING_WARM:
                add("BTC funding", 0.25, 15,
                    f"funding {f_pct:+.3f}% — shorts paying, modest "
                    "squeeze-up bias", "deriv")
            else:
                add("BTC funding", 0.0, 5,
                    f"funding {f_pct:+.3f}% — flat / balanced", "deriv")
        if ls is not None:
            if ls >= _LS_CROWD_LONG:
                add("Long/short ratio", -0.5, 12,
                    f"L/S {ls:.2f} — longs crowded", "deriv")
                flags.append(f"Long/short {ls:.2f} — too many longs")
            elif ls <= _LS_CROWD_SHORT:
                add("Long/short ratio", 0.5, 12,
                    f"L/S {ls:.2f} — shorts crowded", "deriv")
                flags.append(f"Long/short {ls:.2f} — too many shorts")
            else:
                add("Long/short ratio", 0.0, 5,
                    f"L/S {ls:.2f} — balanced", "deriv")
        if oi is not None and funding is not None and abs(oi) >= 5:
            lean = (0.3 if funding >= 0 else -0.3) * (1 if oi > 0 else -1)
            add("Open interest", lean, 10,
                f"OI {oi:+.1f}% — leveraged "
                + ("longs piling in" if (funding >= 0 and oi > 0)
                   else "shorts piling in" if (funding < 0 and oi > 0)
                   else "unwinding"), "deriv")

    # ---- Macro / sentiment backdrop --------------------------------------
    if fear_greed is not None:
        if fear_greed >= _FNG_EUPHORIA:
            add("Fear & Greed", -0.5, 12,
                f"F&G {fear_greed} — extreme greed (mean-revert risk)",
                "macro")
            flags.append(f"Fear & Greed {fear_greed} — extreme greed; "
                         "trim risk, euphoria does not last")
        elif fear_greed <= _FNG_CAPITULATION:
            add("Fear & Greed", 0.5, 12,
                f"F&G {fear_greed} — extreme fear (capitulation near bottoms)",
                "macro")
            flags.append(f"Fear & Greed {fear_greed} — extreme fear; "
                         "capitulation can mark bottoms")
        elif fear_greed >= 60:
            add("Fear & Greed", -0.15, 6, f"F&G {fear_greed} — greedy",
                "macro")
        elif fear_greed <= 40:
            add("Fear & Greed", 0.15, 6, f"F&G {fear_greed} — fearful",
                "macro")
        else:
            add("Fear & Greed", 0.0, 3, f"F&G {fear_greed} — neutral",
                "macro")

    if mcap_change is not None:
        add("Total market cap 24h",
            max(-1.0, min(1.0, mcap_change / 5)), 8,
            f"crypto market cap 24h {mcap_change:+.2f}%", "macro")

        # ---- BTC dominance momentum — BTC outperformance vs total mcap.
        # When BTC outperforms the market, dominance rises (a real flow
        # signal: capital rotating INTO BTC out of alts).
        dom_mo = btc_change_24h - mcap_change
        if abs(dom_mo) >= 1.0:
            add("BTC dominance momentum",
                max(-1.0, min(1.0, dom_mo / 5)),
                12, f"BTC {btc_change_24h:+.1f}% vs market "
                f"{mcap_change:+.1f}% — BTC "
                f"{'leading the market' if dom_mo > 0 else 'lagging the market'}"
                f" ({dom_mo:+.1f}pp)", "flow")

    # ---- News & geopolitical signals ------------------------------------
    # News and macro / political headlines often LEAD price by hours — a Fed
    # decision, a CPI print, an ETF flow or a big BTC-specific headline can
    # move the tape before the chart catches up. Each is added as its OWN
    # driver with its own category so that when many uncorrelated lenses
    # (technicals + deriv + macro + news + flow + divergence) align, the
    # confluence bonus genuinely raises confidence.
    if news:
        btc = news.get("btc") or {}
        if btc.get("count"):
            avg_sent = float(btc.get("sentiment") or 0.0)
            n = int(btc.get("count") or 0)
            lean = max(-1.0, min(1.0, avg_sent * 1.2))
            weight = min(16, 5 + n // 2)
            mood_word = ("bullish" if avg_sent > 0.05
                         else "bearish" if avg_sent < -0.05 else "mixed")
            add("BTC news", lean, weight,
                f"{n} BTC headlines · avg sentiment {avg_sent:+.2f} "
                f"({mood_word})", "news")
            if n >= 4 and abs(avg_sent) >= 0.25:
                flags.append(
                    f"{n} BTC headlines with a {mood_word} tone — "
                    "catalyst-driven volatility likely")

        macro_n = news.get("macro") or {}
        if macro_n.get("count"):
            score = float(macro_n.get("score") or 0.0)
            n = int(macro_n.get("count") or 0)
            tone = ("risk-on" if score > 0.05
                    else "risk-off" if score < -0.05 else "neutral")
            lean = max(-1.0, min(1.0, score * 1.2))
            add("Macro / geopolitical news", lean, 12,
                f"{n} macro headlines · {macro_n.get('mood', 'Neutral')} "
                f"({score:+.2f}) — {tone} tone", "macro")
            if abs(score) >= 0.30 and n >= 3:
                flags.append(
                    f"Macro news {tone} ({score:+.2f}) across {n} headlines "
                    "— Fed / regulation / politics is dragging risk this "
                    "way; respect it even if technicals disagree")

        crypto_n = news.get("crypto") or {}
        if crypto_n.get("count"):
            score = float(crypto_n.get("score") or 0.0)
            n = int(crypto_n.get("count") or 0)
            lean = max(-1.0, min(1.0, score))
            add("Crypto news mood", lean, 8,
                f"{n} crypto headlines · "
                f"{crypto_n.get('mood', 'Neutral')} ({score:+.2f})", "news")

    # ---- Alt-vs-BTC divergence — the user's lesson, surfaced as a flag ---
    divergence = alt_change_24h_median - btc_change_24h
    if divergence >= 4 and abs(btc_change_24h) < 2:
        # Alts ripping while BTC stalls — alts usually catch DOWN.
        add("Alt-vs-BTC divergence", -0.6, 18,
            f"alts +{alt_change_24h_median:.1f}% vs BTC "
            f"{btc_change_24h:+.1f}% — alts running while BTC stalls",
            "divergence")
        flags.append(
            f"Alts {alt_change_24h_median:+.1f}% vs BTC {btc_change_24h:+.1f}%"
            f" over 24h — alts often catch DOWN to BTC when this divergence "
            f"resolves; trim alt size or hedge")
    elif divergence <= -4 and abs(btc_change_24h) < 2:
        # Alts capitulating into a flat BTC — alt-bottom signal.
        add("Alt-vs-BTC divergence", 0.3, 12,
            f"alts {alt_change_24h_median:+.1f}% vs BTC "
            f"{btc_change_24h:+.1f}% — alts capitulating into flat BTC",
            "divergence")
        flags.append(f"Alts {alt_change_24h_median:+.1f}% capitulating into "
                     f"a flat BTC — potential alt-bottom, watch for stabilisation")
    elif divergence >= 2:
        add("Alt-vs-BTC", -0.2, 8,
            f"alts mildly outperforming BTC ({divergence:+.1f}%)",
            "divergence")
    elif divergence <= -2:
        add("Alt-vs-BTC", 0.1, 6,
            f"alts mildly underperforming BTC ({divergence:+.1f}%)",
            "divergence")

    # ---- Aggregate -------------------------------------------------------
    total_weight = sum(d["weight"] for d in drivers) or 1.0
    bias_score = (sum(d["lean"] * d["weight"] for d in drivers)
                  / total_weight * 100)
    bias_score = max(-100.0, min(100.0, bias_score))
    direction = _band(bias_score)

    sign = 1 if bias_score >= 0 else -1

    # Per-driver breadth (how many of the individual drivers lean the trade's way).
    agree_w = sum(d["weight"] for d in drivers
                  if (d["lean"] > 0.05 and sign > 0)
                  or (d["lean"] < -0.05 and sign < 0))
    breadth = agree_w / total_weight

    # Category confluence — how many INDEPENDENT categories agree. Diverse
    # confirmation across uncorrelated lenses is a genuinely stronger signal.
    cat_lean: dict[str, float] = {}
    for d in drivers:
        cat = d.get("category", "other")
        cat_lean[cat] = cat_lean.get(cat, 0.0) + d["lean"] * d["weight"]
    aligned_categories = sum(
        1 for v in cat_lean.values()
        if (v > 0 and sign > 0) or (v < 0 and sign < 0))
    if aligned_categories >= 4:
        confluence_bonus = 16
    elif aligned_categories >= 3:
        confluence_bonus = 10
    elif aligned_categories >= 2:
        confluence_bonus = 5
    else:
        confluence_bonus = 0

    # ---- Classic trading strategies firing -------------------------------
    # Name the recognisable patterns on each timeframe so the trader can tie
    # the abstract score back to specific, well-known setups (trend
    # continuation, mean reversion, range, multi-TF alignment). Strategies
    # are detected from the same data the technicals driver uses, so they
    # are NOT counted as a separate driver (no double-weighting). They add a
    # small, capped confidence bonus when many confirm — and serve as a
    # diagnostic the user can scan at a glance.
    strategies: list[dict] = []
    for tf_name, a in [("4h", btc_4h), ("1d", btc_1d), ("1w", btc_1w)]:
        if not a:
            continue
        sc = float(a.get("score") or 0.0)
        rsi = float(a.get("rsi") or 50.0)
        regime = str(a.get("regime") or "")
        if abs(sc) >= 30 and regime == "Trending":
            strategies.append({
                "name": "Trend continuation",
                "direction": "Bullish" if sc > 0 else "Bearish",
                "tf": tf_name,
            })
        if rsi >= 72:
            strategies.append({
                "name": f"Mean reversion (RSI {rsi:.0f})",
                "direction": "Bearish", "tf": tf_name,
            })
        elif rsi <= 28:
            strategies.append({
                "name": f"Mean reversion (RSI {rsi:.0f})",
                "direction": "Bullish", "tf": tf_name,
            })
        if regime == "Ranging":
            strategies.append({
                "name": "Range / coil — watch for breakout",
                "direction": "Neutral", "tf": tf_name,
            })

    # Multi-TF stack — all three timeframes leaning the same way is a
    # textbook continuation setup that materially raises trust.
    if btc_4h and btc_1d and btc_1w:
        s4 = float((btc_4h or {}).get("score") or 0.0)
        sd = float((btc_1d or {}).get("score") or 0.0)
        sw = float((btc_1w or {}).get("score") or 0.0)
        if s4 > 15 and sd > 15 and sw > 15:
            strategies.append({
                "name": "Multi-timeframe uptrend alignment (4h+1d+1w)",
                "direction": "Bullish", "tf": "all",
            })
        elif s4 < -15 and sd < -15 and sw < -15:
            strategies.append({
                "name": "Multi-timeframe downtrend alignment (4h+1d+1w)",
                "direction": "Bearish", "tf": "all",
            })

    # Strategy confluence — how many classic patterns confirm the net lean.
    want = "Bullish" if sign > 0 else "Bearish"
    strategy_agree = sum(1 for s in strategies if s["direction"] == want)
    strategy_bonus = min(6, strategy_agree * 2)

    base_conf = sum(confs) / len(confs) if confs else 50
    confidence = round(min(95.0,
                           0.45 * abs(bias_score)
                           + 0.25 * base_conf
                           + 15 * breadth
                           + confluence_bonus
                           + strategy_bonus))
    if not drivers:
        confidence = 0

    expected_range_pct = float((btc_1d or {}).get("atr_pct") or 3.0)

    return {
        "direction": direction,
        "bias_score": round(bias_score, 1),
        "confidence": int(confidence),
        "expected_range_pct": round(expected_range_pct, 2),
        "drivers": drivers,
        "flags": flags,
        "takeaway": _takeaway(direction, int(confidence), flags),
        "aligned_categories": aligned_categories,
        "total_categories": len(cat_lean),
        "strategies": strategies,
    }
