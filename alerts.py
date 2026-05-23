"""Trade Alerts — distil a fresh market scan into the few setups actually
worth acting on right now, each with the evidence behind it.

Pure logic, no Streamlit: the app renders the result, fires the toast
pop-ups and tracks which alerts are new since the user last looked. Alerts
are always computed for one timeframe at a time, so a 1h alert is built only
from 1h data and a 4h alert only from 4h data.
"""
from __future__ import annotations

import pandas as pd

# A call must clear these bars before it is allowed to raise an alert.
# CONF_ALERT tuned to 72 — a middle ground. 70 admitted too much noise
# in chop, 75 dropped legitimate setups in the 72-74 band. 72 keeps the
# picks board curated while letting marginal-but-valid setups through.
# Real money safety isn't affected: Live Trading's auto-trade gate sits
# at 85 (configurable), and counter-trend rejected unless conf >= 88.
CONF_ALERT = 72        # signal confidence (%) for a high-conviction setup
VOL_SURGE = 2.0        # last-candle volume vs its 20-candle average
FORECAST_CONF = 62     # confidence (%) for a high-conviction aligned forecast


def _proof(row: dict, bullish: bool) -> list[str]:
    """The strongest reasons, drawn from the signal breakdown, that back the
    call — so every alert is shown WITH its evidence, never bare."""
    want = "Bullish" if bullish else "Bearish"
    items = [b for b in (row.get("breakdown") or [])
             if b.get("signal") == want]
    items.sort(key=lambda b: abs(b.get("score", 0)), reverse=True)
    return [b.get("detail", "") for b in items[:3] if b.get("detail")]


def build_alerts(merged: pd.DataFrame, timeframe: str) -> dict:
    """Turn a Market-Scanner DataFrame into actionable alerts.

    Returns {setups, surges, timeframe}:
      setups — high-confidence directional calls (confidence >= CONF_ALERT)
               that carry a concrete trade plan, each with its proof.
      surges — coins whose latest candle traded >= VOL_SURGE x its average
               volume — the classic pre-move tell.
    Both lists are sorted strongest-first.
    """
    setups: list[dict] = []
    surges: list[dict] = []
    if merged is None or len(merged) == 0:
        return {"setups": setups, "surges": surges, "timeframe": timeframe}

    for _, r in merged.iterrows():
        row = r.to_dict()
        conf = int(row.get("confidence") or 0)
        plan = row.get("trade_plan")
        label = str(row.get("bias_label") or "")
        bullish, bearish = "LONG" in label, "SHORT" in label
        base = str(row.get("symbol", "")).replace("USDT", "")

        if (bullish or bearish) and conf >= CONF_ALERT \
                and isinstance(plan, dict):
            setups.append({
                "symbol": row["symbol"], "base": base,
                "side": "LONG" if bullish else "SHORT",
                "confidence": conf,
                "score": float(row.get("score") or 0.0),
                "label": label,
                "proof": _proof(row, bullish),
                "entry_low": plan.get("entry_low"),
                "entry_high": plan.get("entry_high"),
                "stop": plan.get("stop_loss"),
                "target": plan.get("take_profit"),
                "rr": plan.get("risk_reward", 0.0) or 0.0,
                "regime": row.get("regime", ""),
            })

        vr = row.get("vol_ratio")
        if vr is not None and vr == vr and vr >= VOL_SURGE:
            surges.append({
                "symbol": row["symbol"], "base": base,
                "vol_ratio": float(vr),
                "confidence": conf,
                "label": label or "NEUTRAL",
                "change_24h": row.get("priceChangePercent"),
            })

    setups.sort(key=lambda a: a["confidence"], reverse=True)
    surges.sort(key=lambda a: a["vol_ratio"], reverse=True)
    return {"setups": setups, "surges": surges, "timeframe": timeframe}


def build_forecast_alerts(fc_df) -> list[dict]:
    """High-conviction forecasts worth flagging — coins the multi-timeframe
    forecast projects the SAME way across all three horizons (15m, 1h, 4h)
    with strong confidence. Sorted strongest-first."""
    out: list[dict] = []
    if fc_df is None or len(fc_df) == 0:
        return out
    for _, r in fc_df.iterrows():
        row = r.to_dict()
        word = row.get("outlook_word")
        conf = int(row.get("confidence") or 0)
        if (not row.get("aligned") or conf < FORECAST_CONF
                or word not in ("Bullish", "Bearish")):
            continue
        hz = row.get("horizons") or {}
        h4 = hz.get("4h") or {}
        out.append({
            "symbol": row.get("symbol", ""),
            "base": row.get("base", ""),
            "outlook": word,
            "confidence": conf,
            "net_lean": float(row.get("net_lean") or 0.0),
            "ignited": bool(row.get("ignited")),
            "proj_4h_pct": float(h4.get("move_pct") or 0.0),
        })
    out.sort(key=lambda a: a["confidence"], reverse=True)
    return out
