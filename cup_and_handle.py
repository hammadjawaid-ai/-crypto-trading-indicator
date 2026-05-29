"""Cup-and-handle multi-month base pattern detector (Phase F).

O'Neil / CANSLIM weekly bar pattern: a U-shaped accumulation base that
front-runs Stage 2 markup breakouts by 2–6 weeks. Highest-quality entry
point for swing-to-position trades on liquid majors.

Critical caveat from research: pattern-detection libraries have notorious
false-positive rates. We use this STRICTLY as a small score booster
within spot_signals, not as a standalone entry trigger.

Pattern requirements (Bulkowski + O'Neil rules):
  - U-shape base: depth 12-50% from left lip to bottom
  - Duration: 7-65 weeks
  - Right lip recovers to within 5% of left lip
  - Handle: pullback 8-15% on DECLINING volume
  - Breakout above right lip on volume > 1.5x avg

This module is PURE — takes weekly OHLCV, returns score dict. No state,
no API calls.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _find_cup(weekly: pd.DataFrame, min_weeks: int = 7,
              max_weeks: int = 65) -> dict | None:
    """Locate the most recent valid cup formation in the weekly bars.

    Cup criteria:
      - left lip: a local high
      - right lip: a later local high, within 5% of left lip
      - bottom: the lowest low between the two lips
      - depth: (left_lip - bottom) / left_lip in [0.12, 0.50]
      - duration (left lip to right lip): in [min_weeks, max_weeks]

    Returns the cup dict (lips, bottom, depth) or None if no cup found.
    """
    if len(weekly) < min_weeks + 3:
        return None

    high = weekly["high"].to_numpy()
    low = weekly["low"].to_numpy()
    n = len(weekly)

    # Walk back from the most recent bar searching for the right lip
    # (within last 5 bars of the series — pattern should be fresh).
    for right_idx in range(n - 1, max(0, n - 6), -1):
        right_lip = float(high[right_idx])
        # Search for left lip 7..65 bars back
        for left_idx in range(right_idx - min_weeks,
                              max(0, right_idx - max_weeks), -1):
            left_lip = float(high[left_idx])
            # Right lip within 5% of left lip
            if not (0.95 * left_lip <= right_lip <= 1.05 * left_lip):
                continue
            # Find bottom between the lips
            seg = low[left_idx:right_idx + 1]
            bottom = float(seg.min())
            bottom_idx = left_idx + int(seg.argmin())
            depth = (left_lip - bottom) / left_lip
            if not (0.12 <= depth <= 0.50):
                continue
            # Bottom should be in the middle 60% of the cup time range
            cup_len = right_idx - left_idx
            rel_pos = (bottom_idx - left_idx) / cup_len if cup_len else 0
            if not (0.20 <= rel_pos <= 0.80):
                continue
            return {
                "left_idx": left_idx,
                "right_idx": right_idx,
                "left_lip": left_lip,
                "right_lip": right_lip,
                "bottom_idx": bottom_idx,
                "bottom": bottom,
                "depth": depth,
                "duration_weeks": cup_len,
            }
    return None


def _validate_handle(weekly: pd.DataFrame, cup: dict) -> dict:
    """Check whether bars after the right lip form a valid handle.

    Handle requirements:
      - depth 8-15% from right lip
      - duration 1-5 weeks
      - volume DECLINING during the handle
    """
    right_idx = cup["right_idx"]
    n = len(weekly)
    if right_idx >= n - 1:
        return {"has_handle": False, "detail": "no bars after right lip yet"}

    after = weekly.iloc[right_idx + 1:]
    if len(after) > 5 or len(after) < 1:
        return {"has_handle": False,
                "detail": f"handle window too {'long' if len(after) > 5 else 'short'} "
                          f"({len(after)} weeks)"}

    handle_low = float(after["low"].min())
    handle_depth = (cup["right_lip"] - handle_low) / cup["right_lip"]
    if not (0.04 <= handle_depth <= 0.18):
        return {"has_handle": False,
                "detail": f"handle depth {handle_depth * 100:.1f}% out of band"}

    # Volume should be declining vs cup average
    if "volume" in weekly.columns:
        cup_vol_avg = float(weekly["volume"]
                            .iloc[cup["left_idx"]:cup["right_idx"] + 1]
                            .mean() or 1)
        handle_vol_avg = float(after["volume"].mean() or 0)
        vol_declining = handle_vol_avg < cup_vol_avg * 0.85
    else:
        vol_declining = False

    return {
        "has_handle": True,
        "handle_depth_pct": round(handle_depth * 100, 2),
        "handle_weeks": len(after),
        "handle_vol_declining": vol_declining,
        "detail": (f"handle {handle_depth * 100:.1f}% deep over "
                   f"{len(after)}w, vol {'declining ✓' if vol_declining else 'rising'}"),
    }


def _check_breakout(weekly: pd.DataFrame, cup: dict, handle: dict) -> dict:
    """Check whether the most recent bar broke out of the handle/cup."""
    last_close = float(weekly["close"].iloc[-1])
    breakout_level = max(cup["left_lip"], cup["right_lip"])

    broke_out = last_close > breakout_level * 1.005  # 0.5% buffer
    vol_confirm = False
    if "volume" in weekly.columns and len(weekly) >= 20:
        avg_vol = float(weekly["volume"].rolling(20).mean().iloc[-1] or 1)
        last_vol = float(weekly["volume"].iloc[-1])
        vol_confirm = last_vol >= 1.5 * avg_vol

    return {
        "broke_out": broke_out,
        "breakout_level": breakout_level,
        "vol_confirm": vol_confirm,
        "last_close": last_close,
    }


def score(weekly: pd.DataFrame) -> dict:
    """Detect and score a cup-and-handle setup on weekly bars.

    Score interpretation:
      90+ : fresh breakout above the handle with confirming volume
      75  : valid handle formed, awaiting breakout
      60  : valid cup, no handle yet (early stage)
      50  : no cup pattern detected (neutral, NOT bearish)
    """
    if weekly is None or len(weekly) < 12:
        return {"score": 50, "stage": "NO_DATA", "side": "NEUTRAL",
                "detail": "Insufficient weekly data"}

    cup = _find_cup(weekly)
    if cup is None:
        return {"score": 50, "stage": "NO_CUP", "side": "NEUTRAL",
                "detail": "No cup pattern detected"}

    handle = _validate_handle(weekly, cup)
    if not handle["has_handle"]:
        # Have a cup but no clean handle yet
        return {"score": 60, "stage": "CUP_NO_HANDLE", "side": "LONG",
                "detail": (f"Cup found ({cup['depth'] * 100:.0f}% deep, "
                           f"{cup['duration_weeks']}w) — "
                           f"{handle.get('detail', 'awaiting handle')}")}

    bo = _check_breakout(weekly, cup, handle)
    if bo["broke_out"]:
        # Fresh breakout above the handle — strongest read
        score_val = 95 if bo["vol_confirm"] else 82
        return {"score": score_val, "stage": "BREAKOUT", "side": "LONG",
                "detail": (f"Cup+handle BREAKOUT above "
                           f"{bo['breakout_level']:.4g}, "
                           f"{handle['detail']} · "
                           f"vol {'✓' if bo['vol_confirm'] else 'light'}")}

    # Valid handle, awaiting breakout
    score_val = 75 if handle["handle_vol_declining"] else 68
    return {"score": score_val, "stage": "HANDLE_FORMING", "side": "LONG",
            "detail": (f"Cup ({cup['depth'] * 100:.0f}% deep) + handle "
                       f"({handle['handle_depth_pct']:.1f}% deep, "
                       f"{handle['handle_weeks']}w) — "
                       f"awaiting breakout above {bo['breakout_level']:.4g}")}
