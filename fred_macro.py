"""FRED macro overlay — DXY + M2 + real yields.

Crypto is a long-duration risk asset. A multi-month tilt based on macro
regime saves spot hodlers from buying into tightening cycles. The
overlay is slow-moving (months, not days), so a daily cache is fine.

Requires a free FRED API key set as FRED_API_KEY in .env or Streamlit
secrets. Without it, this module returns a neutral default — the macro
overlay simply disables itself, not breaking spot scoring.

Series used:
  DTWEXBGS — Nominal Broad USD Index (DXY proxy, daily)
  M2SL     — US M2 Money Stock (monthly, SA, billions)
  DFII10   — 10Y TIPS yield (real yield proxy, daily)
"""
from __future__ import annotations

import time

import requests

import config


_BASE = "https://api.stlouisfed.org/fred"
_session = requests.Session()
_session.headers.update({"User-Agent": "crypto-indicator/1.0"})

_CACHE: dict = {"ts": 0.0, "payload": None}
_TTL = 86400  # daily


def _api_key() -> str:
    """Read FRED key from config (which already handles .env + st.secrets)."""
    if hasattr(config, "_secret"):
        key = config._secret("FRED_API_KEY") if callable(config._secret) else ""
    else:
        import os
        key = os.environ.get("FRED_API_KEY", "").strip()
    return key or ""


def _fetch_series(series_id: str, key: str, limit: int = 200) -> list[tuple[str, float]]:
    """Fetch the most-recent `limit` observations for a FRED series.

    Returns oldest-first list of (date, value) tuples. Empty on failure.
    Missing values ('.') are skipped.
    """
    try:
        params = {
            "series_id": series_id,
            "api_key": key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": limit,
        }
        resp = _session.get(f"{_BASE}/series/observations",
                            params=params, timeout=15)
        if resp.status_code != 200:
            return []
        obs = resp.json().get("observations") or []
        out: list[tuple[str, float]] = []
        for row in obs:
            val = row.get("value")
            if val in (None, ".", ""):
                continue
            try:
                out.append((row.get("date", ""), float(val)))
            except (TypeError, ValueError):
                continue
        return list(reversed(out))  # oldest-first
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return []


def regime() -> dict:
    """Return the current macro regime read.

    Returns:
        {
          "regime": "RISK_ON" | "MIXED" | "RISK_OFF" | "UNKNOWN",
          "risk_multiplier": 0.5 - 1.2,
          "dxy_3mo_change_pct": float,
          "m2_yoy_pct": float,
          "real_yield_3mo_change_bps": float,
          "detail": str,
        }

    risk_multiplier interpretation (multiply spot scores by this):
      1.2 = lift conviction (true risk-on, all three favouring crypto)
      1.0 = neutral
      0.5 = strongly defensive (DXY rallying + tightening cycle)
    """
    key = _api_key()
    if not key:
        return {"regime": "UNKNOWN", "risk_multiplier": 1.0,
                "dxy_3mo_change_pct": None, "m2_yoy_pct": None,
                "real_yield_3mo_change_bps": None,
                "detail": "FRED_API_KEY not set — macro overlay disabled"}

    now = time.time()
    if _CACHE["payload"] is not None and (now - _CACHE["ts"]) < _TTL:
        return _CACHE["payload"]

    dxy = _fetch_series("DTWEXBGS", key, limit=200)
    m2 = _fetch_series("M2SL", key, limit=24)
    real_y = _fetch_series("DFII10", key, limit=200)

    def _change_pct(series: list[tuple[str, float]], lookback: int) -> float | None:
        if len(series) < lookback + 1:
            return None
        a = series[-(lookback + 1)][1]
        b = series[-1][1]
        if a <= 0:
            return None
        return (b / a - 1.0) * 100

    def _change_bps(series: list[tuple[str, float]], lookback: int) -> float | None:
        if len(series) < lookback + 1:
            return None
        return (series[-1][1] - series[-(lookback + 1)][1]) * 100  # %-pts -> bps

    # DXY: 3-month change. Lower DXY = risk-on for crypto.
    dxy_3mo = _change_pct(dxy, 63)  # ~63 trading days in 3 months
    # M2: 12-month change. Positive YoY = monetary expansion = risk-on.
    m2_yoy = _change_pct(m2, 12)
    # Real yields: 3-month change. Falling real yields = risk-on.
    real_y_3mo_bps = _change_bps(real_y, 63)

    # Score each axis on -1..+1 (risk-off..risk-on)
    dxy_score = 0.0
    if dxy_3mo is not None:
        # -2% / +2% over 3mo as a soft saturation point
        dxy_score = float(-max(-1.0, min(1.0, dxy_3mo / 2.0)))
    m2_score = 0.0
    if m2_yoy is not None:
        m2_score = float(max(-1.0, min(1.0, m2_yoy / 5.0)))  # 5% YoY saturation
    yld_score = 0.0
    if real_y_3mo_bps is not None:
        yld_score = float(-max(-1.0, min(1.0, real_y_3mo_bps / 75.0)))  # 75bps sat

    composite = (dxy_score + m2_score + yld_score) / 3.0
    # Map composite to multiplier 0.5..1.2
    risk_multiplier = round(1.0 + composite * 0.35, 3)
    if composite > 0.4:
        regime_label = "RISK_ON"
    elif composite < -0.4:
        regime_label = "RISK_OFF"
    else:
        regime_label = "MIXED"

    parts = []
    if dxy_3mo is not None:
        parts.append(f"DXY 3mo {dxy_3mo:+.2f}%")
    if m2_yoy is not None:
        parts.append(f"M2 YoY {m2_yoy:+.2f}%")
    if real_y_3mo_bps is not None:
        parts.append(f"real-10Y 3mo {real_y_3mo_bps:+.0f}bps")

    out = {
        "regime": regime_label,
        "risk_multiplier": risk_multiplier,
        "dxy_3mo_change_pct": dxy_3mo,
        "m2_yoy_pct": m2_yoy,
        "real_yield_3mo_change_bps": real_y_3mo_bps,
        "detail": " · ".join(parts) or "Macro data partial",
    }
    _CACHE.update(ts=now, payload=out)
    return out
