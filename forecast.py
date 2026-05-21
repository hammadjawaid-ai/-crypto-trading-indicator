"""Multi-horizon forecast — a forward projection for the next 15m, 1h and 4h
candle that fuses two lenses:

* the per-timeframe TECHNICAL read (signals.analyze on each timeframe) — the
  timing and structure backbone, and
* the comprehensive BREAKOUT RADAR read for the coin — which already folds in
  news catalysts, the macro / geopolitical backdrop, volume ignition, social
  heat and funding.

Honest by design: a forecast is a probabilistic directional LEAN with an
expected move sized from that timeframe's own ATR (its typical candle range)
— never a guaranteed price. Every extra input TILTS the read within bounds;
none of them overrides it, and a flat read still resolves to 'Sideways'.
Volume ignition lifts the expected move SIZE, never invents a direction.
"""
from __future__ import annotations

import config

# The horizons the forecast covers — each is "the next candle" of that TF.
HORIZONS = (("15m", "next 15 min"),
            ("1h", "next hour"),
            ("4h", "next 4 hours"))

# How much the comprehensive radar read counts vs the raw per-TF technicals.
# The radar (news / macro / volume / social) matters more the further out
# the horizon; microstructure dominates the very short term.
_RADAR_WEIGHT = {"15m": 0.30, "1h": 0.40, "4h": 0.50}


def _direction(score: float) -> str:
    if score >= config.SCORE_MILD:
        return "Up"
    if score <= -config.SCORE_MILD:
        return "Down"
    return "Sideways"


def predict_one(per_tf: dict, radar: dict | None = None,
                backdrop: dict | None = None) -> dict:
    """Build the fused per-horizon forecast for one coin.

    `per_tf`   — {tf: signals.analyze(...) result} for each horizon.
    `radar`    — that coin's Breakout Radar row (news, macro, volume, social,
                 funding already fused), or None.
    `backdrop` — the market-wide macro / geopolitical backdrop dict.

    Returns {horizons, outlook, outlook_word, confidence, net_lean, aligned,
    ignited, news_read, drivers, backdrop_label}.
    """
    radar = radar or {}
    backdrop = backdrop or {}
    radar_dir = float(radar.get("direction") or 0.0)        # -100..100 fused
    radar_conf = float(radar.get("confidence") or 0.0)
    vol_peak = float(radar.get("vol_peak") or 1.0)
    ignited = bool(radar.get("ignited"))
    backdrop_score = max(-100.0, min(100.0,
                                     float(backdrop.get("score") or 0.0)))
    # A volume surge lifts how MUCH a move is likely to travel (capped).
    vol_factor = 1.0 + min(0.5, max(0.0, 0.12 * (vol_peak - 1.5)))

    horizons: dict[str, dict] = {}
    dirs: list[str] = []
    confs: list[float] = []
    net_lean = 0.0

    for tf, _label in HORIZONS:
        a = per_tf.get(tf)
        if not a:
            continue
        tf_score = float(a["score"])
        weight = _RADAR_WEIGHT.get(tf, 0.35)
        fused = (1.0 - weight) * tf_score + weight * radar_dir
        fused += backdrop_score * 0.12          # macro tilt — bounded, modest
        fused = max(-100.0, min(100.0, fused))

        atr_pct = float(a.get("atr_pct") or 0.0)
        strength = max(-1.0, min(1.0, fused / 100.0))
        move_pct = strength * atr_pct * vol_factor
        price = float(a["price"])

        tf_conf = float(a["confidence"])
        conf = (0.6 * tf_conf + 0.4 * radar_conf) if radar_conf else tf_conf
        if ignited:
            conf = min(99.0, conf + 5)

        horizons[tf] = {
            "direction": _direction(fused),
            "score": round(fused, 1),
            "confidence": int(round(conf)),
            "range_pct": round(atr_pct, 2),     # typical full candle range
            "move_pct": round(move_pct, 2),     # expected net move
            "projected": price * (1 + move_pct / 100.0),
        }
        dirs.append(horizons[tf]["direction"])
        confs.append(conf)
        net_lean += move_pct

    drivers = radar.get("drivers") or []
    top = sorted((d for d in drivers if d.get("signed")),
                 key=lambda d: abs(d.get("score", 0)), reverse=True)[:3]
    driver_notes = [f"{d.get('force', '')} {d.get('score', 0):+d}"
                    for d in top]

    if not dirs:
        return {"horizons": {}, "outlook": "No data",
                "outlook_word": "Neutral", "confidence": 0, "net_lean": 0.0,
                "aligned": False, "ignited": ignited,
                "news_read": radar.get("news_read") or "",
                "drivers": driver_notes,
                "backdrop_label": backdrop.get("label", "")}

    n = len(dirs)
    ups, downs = dirs.count("Up"), dirs.count("Down")
    if ups == n:
        outlook, word = "Bullish — aligned across every horizon", "Bullish"
    elif downs == n:
        outlook, word = "Bearish — aligned across every horizon", "Bearish"
    elif ups > downs:
        outlook, word = "Leaning bullish", "Bullish"
    elif downs > ups:
        outlook, word = "Leaning bearish", "Bearish"
    else:
        outlook, word = "Mixed — no clear cross-horizon edge", "Neutral"

    aligned = (ups == n or downs == n)
    confidence = round(sum(confs) / len(confs))
    if aligned:
        confidence = min(99, confidence + 8)

    return {"horizons": horizons, "outlook": outlook, "outlook_word": word,
            "confidence": confidence, "net_lean": round(net_lean, 2),
            "aligned": aligned, "ignited": ignited,
            "news_read": radar.get("news_read") or "",
            "drivers": driver_notes,
            "backdrop_label": backdrop.get("label", "")}
