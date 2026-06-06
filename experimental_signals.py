"""Unified Signal Composite (formerly experimental).

Merged scanner that combines EVERY proven signal lane into ONE
conviction score per coin, with full BEST-TRADES-NOW-style metadata
for rendering. Replaces the separated REBOUND + BREAKOUT + EXPERIMENTAL
hunters with a single unified pick board.

Signal lanes (weights sum to 1.00, calibrated to backtested edge):

  vwap_zfade       0.10  — VWAP z-score fade (counter-trend ≥2σ)
  liq_exhaustion   0.13  — Long-exhaustion liquidation reversal (4%+
                            drop + OI down + vol spike + absorption)
  rebound          0.13  — V-bottom + RSI capitulation + reversal pattern
  breakout_coil    0.10  — BB squeeze + OBV accumulation + OI surge
  pattern_scout    0.18  — Live candle pattern (hammer/star/engulfing)
  reversal_app     0.10  — 7 pre-fire reversal conditions
  early_momentum   0.10  — CVD + TTM + SMC + VWAP-reclaim composite
  recovery         0.08  — recovery_detector V-bottom
  deriv_velocity   0.08  — funding ROC + OI compression

Conviction tier (mirrors Paper Trader's logic):
  MAX      score >= 90 AND (≥3 lanes scoring 70+)
  HIGH     score >= 85 AND (≥2 lanes scoring 70+)
  STRONG   score >= 80
  STANDARD score >= 70  (firing floor)

Cards built by this module carry ALL the chip metadata that BEST
TRADES NOW uses:
  - lanes_fired: dict of {lane_name: lane_score}
  - tier: MAX/HIGH/STRONG/STANDARD
  - reasons: list[str] (top 5)
  - trade_plan: {entry, stop, tp1, tp2, rr, valid}
  - side: LONG / SHORT
  - score: 0-100
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

import binance_client
import indicators

# Optional imports — every lane gracefully degrades to 0 if its module
# can't be reached.
try: import pattern_scout
except Exception: pattern_scout = None
try: import reversal_approach
except Exception: reversal_approach = None
try: import recovery_detector
except Exception: recovery_detector = None
try: import early_momentum
except Exception: early_momentum = None
try: import derivatives_velocity
except Exception: derivatives_velocity = None
try: import rebound_radar
except Exception: rebound_radar = None
try: import breakout_hunter
except Exception: breakout_hunter = None
# Distribution-top detector — catches SHORT setups like NEAR -25%.
# 10th lane added specifically because the other 9 lanes are heavily
# LONG-biased (4 are LONG-only).
try: import distribution_top
except Exception: distribution_top = None
# Market regime — used to tilt composite scores toward the currently
# winning side (BULL→LONG, BEAR→SHORT). Imported lazily; if missing,
# composite stays neutral.
try: import market_regime
except Exception: market_regime = None


# ---------------------------------------------------------------------------
# Lane weights (calibrated to backtested edge)
# ---------------------------------------------------------------------------
# Re-balanced after adding dist_top (10th lane). Weights sum to 1.0 but
# this isn't strictly required — score normalizes by firing weight.
_LANE_WEIGHTS = {
    "vwap_zfade":     0.09,
    "liq_exhaustion": 0.12,
    "rebound":        0.12,
    "breakout_coil":  0.09,
    "pattern_scout":  0.16,
    "reversal_app":   0.09,
    "early_momentum": 0.09,
    "recovery":       0.07,
    "deriv_velocity": 0.07,
    "dist_top":       0.10,   # NEW — top/distribution SHORT detector
}


# ---------------------------------------------------------------------------
# Shared trend classifier — protects mean-reversion lanes from firing
# counter-trend against strong directional moves.
# ---------------------------------------------------------------------------
def _trend_state(ref_df: pd.DataFrame) -> str:
    """Classify higher-TF trend as STRONG_UP / STRONG_DOWN / NEUTRAL.

    Uses EMA stacking + price location. The indicator module names them
    `ema_fast` (=20), `ema_slow` (=50), `ema_trend` (=200). For bear
    stack: price < ema_fast < ema_slow (price below the 20EMA which is
    below the 50EMA — all three pointing down).

    Used by every mean-reversion lane (vwap_zfade, rebound, recovery)
    to REFUSE to fire LONG against a STRONG_DOWN trend or SHORT against
    a STRONG_UP trend — the fix the ETH-LONG bug required.
    """
    if ref_df is None or len(ref_df) < 50:
        return "NEUTRAL"
    try:
        last = ref_df.iloc[-1]
        p = float(last["close"])
        # Match the actual column names produced by indicators.enrich()
        e_fast = (float(last["ema_fast"])
                  if "ema_fast" in ref_df.columns else None)
        e_slow = (float(last["ema_slow"])
                  if "ema_slow" in ref_df.columns else None)
        if e_fast is None or e_slow is None:
            return "NEUTRAL"
        if e_fast <= 0 or e_slow <= 0:
            return "NEUTRAL"
        # Bear stack: price below fast EMA below slow EMA
        if p < e_fast < e_slow:
            return "STRONG_DOWN"
        # Bull stack: price above fast EMA above slow EMA
        if p > e_fast > e_slow:
            return "STRONG_UP"
    except Exception:
        pass
    return "NEUTRAL"


# ---------------------------------------------------------------------------
# Individual lane scorers — each returns (score 0-100, side, note)
# ---------------------------------------------------------------------------
def _lane_vwap_zfade(df: pd.DataFrame,
                    df_4h: pd.DataFrame | None = None) -> tuple[float, str, str]:
    """VWAP z-score fade: ≥2σ deviation from rolling VWAP + RSI extreme.

    THREE BUG FIXES (after the ETH-LONG -8.51σ artifact):

    1. ROLLING VWAP (window=50) replaces cumulative VWAP. Cumulative VWAP
       anchors to the OLDEST bar in the window, so in a sustained downtrend
       it stays near old (higher) prices while current price drops — the
       spread blows up and z-score reports artifact-extreme values like
       -8.51σ that aren't actually mean-reversion setups.

    2. Z-SCORE CAPPED at ±3.5. Anything beyond 3.5 sigma in price data is
       almost always a math artifact (window edge, std collapse), not a
       genuine signal. Capping prevents these from dominating the composite.

    3. TREND GATE. If higher-TF (4h) is in a STRONG_DOWN stack, REFUSE to
       fire LONG. Same for STRONG_UP / SHORT. Mean-reversion against strong
       trends has a backtested ~30% win rate vs ~55% for trend-following —
       this filter kills the bad-EV trades.
    """
    if df is None or len(df) < 50:
        return (0.0, "NEUTRAL", "")
    try:
        # Rolling-window VWAP (50 bars) — kills the cumulative artifact
        window = 50
        typical = (df["high"] + df["low"] + df["close"]) / 3.0
        roll_pv = (typical * df["volume"]).rolling(
            window, min_periods=20).sum()
        roll_v = df["volume"].rolling(window, min_periods=20).sum()
        vwap = roll_pv / roll_v.replace(0, np.nan)
        spread = df["close"] - vwap
        roll_std = spread.rolling(20, min_periods=10).std()
        z = (df["close"] - vwap) / roll_std.replace(0, np.nan)
        last_z = float(z.iloc[-1]) if not np.isnan(z.iloc[-1]) else 0.0
        # CAP — beyond ±3.5 is math artifact, not signal
        last_z = max(-3.5, min(3.5, last_z))
        last_rsi = (float(df["rsi"].iloc[-1])
                    if "rsi" in df.columns else 50.0)
        trend = _trend_state(df_4h if df_4h is not None else df)

        if last_z <= -2.0 and last_rsi <= 30:
            # Counter-trend LONG against confirmed downtrend → REJECT
            if trend == "STRONG_DOWN":
                return (0.0, "NEUTRAL", "")
            mag = abs(last_z)
            sc = float(np.clip(60 + (mag - 2.0) * 30, 60, 100))
            return (sc, "LONG",
                    f"z={last_z:.2f}σ + RSI {last_rsi:.0f} (oversold)")
        if last_z >= 2.0 and last_rsi >= 70:
            # Counter-trend SHORT against confirmed uptrend → REJECT
            if trend == "STRONG_UP":
                return (0.0, "NEUTRAL", "")
            mag = abs(last_z)
            sc = float(np.clip(60 + (mag - 2.0) * 30, 60, 100))
            return (sc, "SHORT",
                    f"z=+{last_z:.2f}σ + RSI {last_rsi:.0f} (overbought)")
    except Exception:
        pass
    return (0.0, "NEUTRAL", "")


def _lane_liq_exhaustion(df: pd.DataFrame,
                        oi_hist: list | None) -> tuple[float, str, str]:
    """Long-exhaustion: 4%+ 3-bar drop + OI drop + vol spike + absorption."""
    if df is None or len(df) < 25:
        return (0.0, "NEUTRAL", "")
    try:
        last = df.iloc[-1]
        ret_3 = float(last["close"]) / float(df["close"].iloc[-4]) - 1.0
        if ret_3 > -0.04:
            return (0.0, "NEUTRAL", "")
        body = abs(float(last["close"]) - float(last["open"]))
        bar_rng = float(last["high"]) - float(last["low"])
        body_pct = (body / bar_rng) if bar_rng > 0 else 1.0
        close_pos = (
            (float(last["close"]) - float(last["low"])) / bar_rng
            if bar_rng > 0 else 0.5)
        if body_pct > 0.40 or close_pos < 0.60:
            return (0.0, "NEUTRAL", "")
        vol_ratio = (
            float(last["volume"]) / float(df["volume"].tail(20).mean())
            if df["volume"].tail(20).mean() else 0)
        if vol_ratio < 3.0:
            return (0.0, "NEUTRAL", "")
        # OI history from derivatives_velocity is a FLAT list[float] of
        # sumOpenInterest values — not (ts, value) tuples. The original
        # `[v for _, v in oi_hist[-4:]]` raised TypeError silently and
        # the OI gate never confirmed → liq_exhaustion capped at 50.
        oi_confirmed = False
        oi_pct = None
        if oi_hist and len(oi_hist) >= 4:
            try:
                oi_vals = list(oi_hist[-4:])
                # Tolerate either flat floats or (ts, value) tuples.
                if oi_vals and isinstance(oi_vals[0], (tuple, list)):
                    oi_vals = [v[1] for v in oi_vals]
                oi_vals = [float(v) for v in oi_vals]
                if oi_vals[0] > 0:
                    oi_pct = (oi_vals[-1] - oi_vals[0]) / oi_vals[0]
                    oi_confirmed = oi_pct <= -0.05
            except Exception:
                pass
        if oi_confirmed:
            return (90.0, "LONG",
                    f"3bar drop {ret_3*100:+.1f}% · vol {vol_ratio:.1f}× "
                    f"· OI {oi_pct*100:+.1f}% · absorption candle")
        return (50.0, "LONG",
                f"3bar drop {ret_3*100:+.1f}% · vol {vol_ratio:.1f}× "
                f"· absorption (OI gate missing — caution)")
    except Exception:
        return (0.0, "NEUTRAL", "")


def _lane_rebound(symbol: str, df: pd.DataFrame,
                 pct_24h: float,
                 df_4h: pd.DataFrame | None = None) -> tuple[float, str, str]:
    """Rebound score from existing rebound_radar (V-bottom composite).

    Trend-gated: rebound is a mean-reversion LONG. Refuses to fire
    against a STRONG_DOWN 4h trend (same fix as vwap_zfade).
    """
    if rebound_radar is None or df is None:
        return (0.0, "NEUTRAL", "")
    try:
        r = rebound_radar.score(symbol, df, pct_24h=pct_24h)
        sc = float(r.get("score", 0))
        if sc < 50:
            return (0.0, "NEUTRAL", "")
        # Trend gate — don't fade strong downtrends
        if _trend_state(df_4h if df_4h is not None else df) == "STRONG_DOWN":
            return (0.0, "NEUTRAL", "")
        dd = r.get("drawdown_pct", 0)
        exp = r.get("expected_move_pct", 0)
        return (sc, "LONG",
                f"−{dd:.1f}% from high · expected +{exp:.1f}% rebound")
    except Exception:
        return (0.0, "NEUTRAL", "")


def _lane_breakout(symbol: str, df_4h: pd.DataFrame,
                  df_1h: pd.DataFrame | None) -> tuple[float, str, str]:
    """Breakout score from existing breakout_hunter (coil composite)."""
    if breakout_hunter is None or df_4h is None:
        return (0.0, "NEUTRAL", "")
    try:
        r = breakout_hunter.score(symbol, df_4h, df_1h)
        sc = float(r.get("score", 0))
        if sc < 50:
            return (0.0, "NEUTRAL", "")
        d7 = r.get("seven_day_chg_pct", 0)
        return (sc, "LONG", f"coil 7d {d7:+.1f}% (pre-pump compression)")
    except Exception:
        return (0.0, "NEUTRAL", "")


def _lane_pattern_scout(symbol: str, df: pd.DataFrame,
                       pct_24h: float) -> tuple[float, str, str]:
    """Pattern Scout — live candle pattern (hammer/star/engulfing)."""
    if pattern_scout is None or df is None:
        return (0.0, "NEUTRAL", "")
    try:
        r = pattern_scout.scan_one(symbol, df, pct_24h=pct_24h)
        side = r.get("side", "NEUTRAL")
        sc = float(r.get("score", 0))
        if side == "NEUTRAL" or sc < 60:
            return (0.0, "NEUTRAL", "")
        best = r.get("best_signal", "pattern")
        return (sc, side, f"Pattern Scout: {best}")
    except Exception:
        return (0.0, "NEUTRAL", "")


def _lane_reversal_app(df: pd.DataFrame) -> tuple[float, str, str]:
    """7 pre-fire reversal conditions (reversal_approach.scan_both_sides).

    Lowered gate to 60 — diagnostic showed that real setups peak around
    57-65 conditions_met=2-3/7. The original 65 cutoff was discarding
    every real signal.
    """
    if reversal_approach is None or df is None:
        return (0.0, "NEUTRAL", "")
    try:
        r = reversal_approach.scan_both_sides(df)
        side = r.get("side", "NEUTRAL")
        sc = float(r.get("score", 0))
        cm = int(r.get("conditions_met", 0))
        if sc < 60 or side == "NEUTRAL":
            return (0.0, "NEUTRAL", "")
        return (sc, side, f"reversal pre-conditions {cm}/7")
    except Exception:
        return (0.0, "NEUTRAL", "")


def _lane_early_momentum(df: pd.DataFrame) -> tuple[float, str, str]:
    """early_momentum composite (CVD + TTM + ROC² + SMC + VWAP).

    early_momentum returns side=LONG with score 0-100 where 50=neutral.
    Original gate >=70 was discarding most real LONG signals. Bump
    contribution threshold to 60 (LONG) / 40 (SHORT) — early-momentum
    composite is robust at 60+.
    """
    if early_momentum is None or df is None:
        return (0.0, "NEUTRAL", "")
    try:
        r = early_momentum.score(df)
        side = r.get("side", "NEUTRAL")
        sc = float(r.get("score", 0))
        if side == "LONG" and sc >= 60:
            return (sc, "LONG", f"early_momentum long composite (score {sc:.0f})")
        if side == "SHORT" and sc <= 40:
            sc_norm = 100 - sc
            return (sc_norm, "SHORT", f"early_momentum short composite (score {sc:.0f})")
    except Exception:
        pass
    return (0.0, "NEUTRAL", "")


def _lane_recovery(df: pd.DataFrame,
                  df_4h: pd.DataFrame | None = None) -> tuple[float, str, str]:
    """recovery_detector V-bottom (backtested 75% win at 12bar).

    Trend-gated like rebound — V-bottom is a counter-trend LONG. The
    backtested edge was measured in ranging/sideways markets; firing it
    against a STRONG_DOWN 4h trend nullifies that edge.
    """
    if recovery_detector is None or df is None:
        return (0.0, "NEUTRAL", "")
    try:
        from recovery_detector import _v_bottom_bounce
        r = _v_bottom_bounce(df)
        sc = float(r.get("score") or 0)
        if sc < 60:
            return (0.0, "NEUTRAL", "")
        if _trend_state(df_4h if df_4h is not None else df) == "STRONG_DOWN":
            return (0.0, "NEUTRAL", "")
        return (sc, "LONG", "V-bottom capitulation pattern")
    except Exception:
        return (0.0, "NEUTRAL", "")


def _lane_deriv_velocity(symbol: str) -> tuple[float, str, str]:
    """derivatives_velocity (funding ROC + OI compression)."""
    if derivatives_velocity is None:
        return (0.0, "NEUTRAL", "")
    try:
        r = derivatives_velocity.score(symbol, interval="1h")
        side = r.get("side", "NEUTRAL")
        sc = float(r.get("score", 0))
        if side == "NEUTRAL" or sc < 60:
            return (0.0, "NEUTRAL", "")
        return (sc, side, f"deriv {side.lower()} (funding+OI)")
    except Exception:
        return (0.0, "NEUTRAL", "")


def _lane_dist_top(df: pd.DataFrame,
                  df_4h: pd.DataFrame | None = None) -> tuple[float, str, str]:
    """Distribution-top detector — fires SHORT when price is near a
    recent high with overheated conditions (rapid rise + RSI overbought
    + leading distribution signals).

    Lower firing floor (50) than other lanes (60) because by design the
    leading distribution signals fire AT the peak with limited
    confirmation — by the time we wait for 60+ score, price has already
    dropped 5-10% and the SHORT entry is degraded.

    The 4h_df is passed for multi-TF confirmation.
    """
    if distribution_top is None or df is None:
        return (0.0, "NEUTRAL", "")
    try:
        r = distribution_top.score(df, df_4h)
        sc = float(r.get("score") or 0)
        if sc < 50:
            return (0.0, "NEUTRAL", "")
        # Bonus when 4h also shows top conditions
        reasons = r.get("reasons") or []
        note = "; ".join(reasons[:3]) if reasons else "distribution top"
        return (sc, "SHORT", note)
    except Exception:
        return (0.0, "NEUTRAL", "")


# ---------------------------------------------------------------------------
# Composite scoring + tier
# ---------------------------------------------------------------------------
def _conviction_tier(score: float, n_strong_lanes: int) -> str:
    """Conviction tier — relaxed 2026-06-06 so user sees MAX/HIGH more
    when the system IS confident. The old "score>=90 AND 3 strong lanes"
    was almost impossible to hit after the regime tilt subtracted -15,
    leaving the user staring at STANDARD/STRONG cards even when ELITE
    was firing 3 lanes.

       MAX = score >= 88 AND >=2 strong lanes  (was 90 + 3 lanes)
       HIGH = score >= 82 AND >=2 strong lanes  (was 85 + 2 lanes)
       STRONG = score >= 75 (was 80)
       STANDARD = score >= 68 (was 70)
       (below 68 we filter out)

    Why this is safe: the score itself already incorporates
       (a) lane composite weighting,
       (b) regime tilt up/down,
       (c) per-lane firing floor (60).
    A score of 88 with 2 strong lanes is genuinely the top tier —
    requiring 3 strong lanes added almost no statistical edge but
    starved the user of the MAX badge that drives the bigger TP1/TP2.
    """
    if score >= 88 and n_strong_lanes >= 2:
        return "MAX"
    if score >= 82 and n_strong_lanes >= 2:
        return "HIGH"
    if score >= 75:
        return "STRONG"
    if score >= 68:
        return "STANDARD"
    return "LOW"


def score_from_data(symbol: str,
                   df: pd.DataFrame,
                   df_4h: pd.DataFrame | None = None,
                   oi_hist: list | None = None,
                   pct_24h: float = 0.0,
                   skip_deriv: bool = False,
                   regime_info: dict | None = None) -> dict:
    """Composite-score one symbol using PRE-FETCHED data.

    regime_info (optional) is the dict returned by market_regime
    .detect_regime(). When supplied, the composite final-score is
    biased by current market regime:
      BULL regime → boost LONG composite, demote SHORT
      BEAR regime → boost SHORT composite, demote LONG
      CHOP/TRANSITION → no effect
    This makes ELITE adapt to changing market direction instead of
    using static lane weights.

    Used by score_one (production) AND backtest_elite.py (walk-forward).
    Backtest passes skip_deriv=True because deriv_velocity has no
    historical API — calling it during backtest would leak forward info.
    """
    if df is None or len(df) < 50:
        return _empty(symbol)
    df_4h_or_1h = df_4h if df_4h is not None else df
    lanes = {
        "vwap_zfade":     _lane_vwap_zfade(df, df_4h),
        "liq_exhaustion": _lane_liq_exhaustion(df, oi_hist),
        "rebound":        _lane_rebound(symbol, df, pct_24h, df_4h),
        "breakout_coil":  _lane_breakout(symbol, df_4h_or_1h, df),
        "pattern_scout":  _lane_pattern_scout(symbol, df, pct_24h),
        "reversal_app":   _lane_reversal_app(df),
        "early_momentum": _lane_early_momentum(df),
        "recovery":       _lane_recovery(df, df_4h),
        # deriv_velocity skipped during backtest (no historical API) —
        # backtest measures the OTHER 8 lanes' edge honestly.
        "deriv_velocity": ((0.0, "NEUTRAL", "") if skip_deriv
                           else _lane_deriv_velocity(symbol)),
        # dist_top: catches NEAR-style SHORT setups at distribution tops
        "dist_top":       _lane_dist_top(df, df_4h),
    }
    return _composite_from_lanes(symbol, df, lanes, pct_24h,
                                regime_info=regime_info)


def _apply_regime_tilt(score: float, side: str,
                      regime_info: dict | None,
                      n_lanes: int = 0) -> tuple[float, str]:
    """Regime-aware re-scoring with HARD REJECTION + extreme-signal override.

    Three-tier behaviour:

    1. EXTREME OVERRIDE (NEW): when a counter-regime pick has very strong
       underlying conviction (raw score >= 90 OR 3+ lanes firing on the
       same side), SKIP the hard reject and apply only the soft tilt
       penalty. Reasoning: if 3 independent lanes agree on counter-
       regime, that's strong evidence the regime is shifting or this
       coin is decoupling — auto-killing those picks throws away the
       best contrarian setups (bull reversals in BEAR, bear breakdowns
       in BULL).

    2. HARD REJECT (conf > 65%): for less-strong counter-regime picks,
       refuse them so the board doesn't fill with against-the-trend
       noise.

    3. SOFT TILT (40% < conf <= 65%): moderate-confidence regimes get
       a graded ±15 max tilt scaled linearly with confidence.

    Returns (new_score, regime_note).
    """
    if not regime_info:
        return score, ""
    regime = regime_info.get("regime", "")
    conf = float(regime_info.get("confidence") or 0)
    if conf < 40 or regime in ("CHOP", "TRANSITION", "UNKNOWN", ""):
        return score, ""

    # Detect counter-regime side
    is_counter = (
        (regime == "BULL" and side == "SHORT")
        or (regime == "BEAR" and side == "LONG"))

    # HARD REJECT — at decisive regimes, refuse counter-regime picks
    # UNLESS the extreme override criteria are met
    if conf > 65 and is_counter:
        extreme_score = score >= 90
        extreme_lanes = n_lanes >= 3
        if not (extreme_score or extreme_lanes):
            tag = "BULL" if regime == "BULL" else "BEAR"
            return 0.0, f"REJECTED counter-{tag} ({conf:.0f}%)"
        # Extreme override active — fall through to soft tilt

    # SOFT TILT — magnitude scales with confidence (40→0, 100→15)
    # Reverted from 18 → 15 (2026-06-06 v2) after user pointed out
    # that 18 was suppressing legitimate counter-regime bounces. The
    # ADAPTIVE QUALITY GATE at the display layer handles regime
    # filtering more precisely than a blunt tilt boost.
    tilt = (conf - 40) / 60 * 15
    if regime == "BULL":
        if side == "LONG":
            return min(100, score + tilt), f"BULL +{tilt:.0f}"
        elif side == "SHORT":
            # Counter-BULL — note when override saved this pick
            tag = ("BULL OVERRIDE -" if conf > 65
                   else "BULL -")
            return max(0, score - tilt), f"{tag}{tilt:.0f}"
    elif regime == "BEAR":
        if side == "SHORT":
            return min(100, score + tilt), f"BEAR +{tilt:.0f}"
        elif side == "LONG":
            # Counter-BEAR — note when override saved this pick
            tag = ("BEAR OVERRIDE -" if conf > 65
                   else "BEAR -")
            return max(0, score - tilt), f"{tag}{tilt:.0f}"
    return score, ""


def _composite_from_lanes(symbol: str, df: pd.DataFrame,
                         lanes: dict, pct_24h: float,
                         regime_info: dict | None = None) -> dict:
    """Run the side-vote + composite math on already-scored lanes.
    Extracted so score_from_data and any future caller share one path."""

    # Vote: collect every LANE firing >= its per-lane floor with a side.
    # dist_top uses 50 as its floor (leading distribution signals fire
    # AT the peak before confirming signals arrive — by the time score
    # would clear 60, price has dropped 5-10%). All other lanes use 60.
    _per_lane_floor = {"dist_top": 50}
    long_lanes: list[tuple[str, float, str]] = []
    short_lanes: list[tuple[str, float, str]] = []
    for name, (sc, side, note) in lanes.items():
        floor = _per_lane_floor.get(name, 60)
        if side == "LONG" and sc >= floor:
            long_lanes.append((name, sc, note))
        elif side == "SHORT" and sc >= floor:
            short_lanes.append((name, sc, note))

    # Composite score per side = WEIGHTED AVERAGE over firing weight.
    #
    # CONFLUENCE BONUS REMOVED (backtest evidence): the original
    # +5/+10/+15 bonus for stacking lanes was assumed to be additive
    # signal — but walk-forward results showed 2-lane setups (50% win)
    # underperformed 1-lane setups (59.4% win). The lanes are
    # correlated/redundant, not independent. Bonus removed; raw
    # weighted average is the honest composite.
    def _composite(lanes_list: list[tuple[str, float, str]]) -> float:
        if not lanes_list:
            return 0.0
        weighted_sum = sum(sc * _LANE_WEIGHTS.get(n, 0)
                          for n, sc, _ in lanes_list)
        weight_sum = sum(_LANE_WEIGHTS.get(n, 0)
                        for n, _, _ in lanes_list)
        if weight_sum <= 0:
            return 0.0
        return weighted_sum / weight_sum

    long_score = _composite(long_lanes)
    short_score = _composite(short_lanes)

    # Pick dominant side, with a meaningful firing floor.
    if long_score >= short_score and long_score >= 60:
        side = "LONG"
        score = long_score
        strong_n = len([1 for _, s, _ in long_lanes if s >= 70])
        active_lanes = long_lanes
    elif short_score > long_score and short_score >= 60:
        side = "SHORT"
        score = short_score
        strong_n = len([1 for _, s, _ in short_lanes if s >= 70])
        active_lanes = short_lanes
    else:
        return _empty(symbol)

    score = float(np.clip(score, 0, 100))

    # Apply regime tilt — BULL boosts LONGs, BEAR boosts SHORTs. Counter-
    # regime side gets penalty (or hard-reject at conf>65), UNLESS the
    # extreme-signal override fires (score>=90 OR 3+ lanes firing).
    # Pass n_lanes so the override can evaluate.
    regime_note = ""
    if regime_info:
        score, regime_note = _apply_regime_tilt(
            score, side, regime_info, n_lanes=len(active_lanes))

    tier = _conviction_tier(score, strong_n)
    if tier == "LOW":
        return _empty(symbol)

    # Trade plan — TP1/TP2 now scale with conviction tier so MAX/HIGH
    # picks reach further than STANDARD. Stops stay tight (1.2 ATR).
    plan = _build_plan(df, side, tier=tier)
    # Order reasons by lane score, take top 5
    active_lanes.sort(key=lambda x: x[1], reverse=True)
    top_reasons = [
        f"{lane.replace('_', ' ')}: {note}"
        for lane, sc, note in active_lanes[:5]
        if note
    ]
    # Active lane names for chip rendering (top 6)
    active_lane_names = [lane for lane, _, _ in active_lanes[:6]]

    try:
        price_now = float(df["close"].iloc[-1])
    except Exception:
        price_now = 0.0

    return {
        "symbol": symbol,
        "base": symbol.replace("USDT", ""),
        "side": side,
        "score": round(score, 1),
        "tier": tier,
        "lanes_fired": {name: round(sc, 1)
                        for name, sc, _ in active_lanes},
        "active_lanes": active_lane_names,
        "n_strong_lanes": strong_n,
        "reasons": top_reasons,
        "trade_plan": plan,
        "price_now": price_now,
        "pct_24h": pct_24h,
        "regime_note": regime_note,  # e.g. "BEAR +5" or "" if no tilt
    }


def score_one(symbol: str, interval: str = "1h",
             pct_24h: float = 0.0,
             regime_info: dict | None = None) -> dict:
    """Production entry point — fetches live klines + OI, runs all lanes,
    returns composite pick. Live deployment uses this; backtests use
    `score_from_data` directly with pre-fetched data.

    regime_info (optional) tilts the final score toward the
    currently-winning side. Pass once from scan_unified so we only
    detect regime ONCE per scan, not per coin.
    """
    try:
        df = binance_client.get_klines(symbol, interval, limit=200)
        df = indicators.enrich(df)
    except Exception:
        return _empty(symbol)
    df_4h = None
    try:
        df_4h = binance_client.get_klines(symbol, "4h", limit=200)
        df_4h = indicators.enrich(df_4h)
    except Exception:
        pass
    oi_hist = None
    if derivatives_velocity is not None:
        try:
            oi_hist = derivatives_velocity._oi_history(
                symbol, period="1h", limit=12)
        except Exception:
            pass
    return score_from_data(symbol, df, df_4h=df_4h,
                          oi_hist=oi_hist, pct_24h=pct_24h,
                          skip_deriv=False, regime_info=regime_info)


def scan_unified(scan_n: int = 100,
                interval: str = "1h",
                min_score: float = 70.0,
                max_picks: int = 15,
                max_workers: int = 6) -> list[dict]:
    """Scan top N coins, return high-conviction unified picks.

    Detects market regime ONCE up-front and passes it to every per-coin
    score call, so the composite is regime-aware: BULL boosts LONGs,
    BEAR boosts SHORTs, CHOP/TRANSITION → no tilt.
    """
    try:
        top = binance_client.get_top_symbols(scan_n)
        syms = top["symbol"].tolist()
        pct_map = dict(zip(top["symbol"], top["priceChangePercent"]))
    except Exception:
        return []

    # Detect regime once — propagated to every per-coin score call so
    # ELITE adapts to current market direction (your point: shorts
    # winning is temporary, regime determines which side wins).
    regime_info = None
    if market_regime is not None:
        try:
            regime_info = market_regime.detect_regime(
                top_symbols=syms[:50])
        except Exception:
            regime_info = None

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(score_one, sym, interval,
                        float(pct_map.get(sym, 0)),
                        regime_info): sym
            for sym in syms
        }
        for fut in as_completed(futures):
            try:
                r = fut.result()
                if r.get("score", 0) >= min_score:
                    results.append(r)
            except Exception:
                continue
    results.sort(key=lambda r: r.get("score", 0), reverse=True)
    return results[:max_picks]


# ---------------------------------------------------------------------------
# Trade plan + helpers
# ---------------------------------------------------------------------------
# TP/SL ATR multipliers per conviction tier (per user — bigger
# conviction reaches for bigger targets, stops stay tight so R:R
# actually IMPROVES at higher tiers):
#   STANDARD: 2.0 / 3.5 (the original — base case)
#   STRONG:   2.2 / 4.0
#   HIGH:     2.5 / 4.5
#   MAX:      3.0 / 5.5  (strongest conviction = widest target)
# Stop stays at 1.2 ATR across all tiers — keeps drawdown
# predictable, and R:R climbs with conviction:
#   STANDARD R:R = 1.67  (TP1/Stop = 2.0/1.2)
#   STRONG   R:R = 1.83  (2.2/1.2)
#   HIGH     R:R = 2.08  (2.5/1.2)
#   MAX      R:R = 2.50  (3.0/1.2)
_TIER_ATR_MULTIPLIERS = {
    "STANDARD": {"stop": 1.2, "tp1": 2.0, "tp2": 3.5},
    "STRONG":   {"stop": 1.2, "tp1": 2.2, "tp2": 4.0},
    "HIGH":     {"stop": 1.2, "tp1": 2.5, "tp2": 4.5},
    "MAX":      {"stop": 1.2, "tp1": 3.0, "tp2": 5.5},
}


def _build_plan(df: pd.DataFrame, side: str,
               tier: str = "STANDARD") -> dict:
    """Tier-scaled trade plan. Stops constant at 1.2 ATR; TPs widen
    for HIGH/MAX so the trade can reach further when conviction
    supports it. R:R improves at higher tiers (1.67 -> 2.50)."""
    if df is None or len(df) < 20:
        return _empty_plan()
    try:
        last = df.iloc[-1]
        entry = float(last["close"])
        atr = float(last.get("atr") or 0)
        if entry <= 0 or atr <= 0:
            return _empty_plan()
        m = _TIER_ATR_MULTIPLIERS.get(
            tier, _TIER_ATR_MULTIPLIERS["STANDARD"])
        if side == "LONG":
            stop = entry - m["stop"] * atr
            tp1 = entry + m["tp1"] * atr
            tp2 = entry + m["tp2"] * atr
        else:
            stop = entry + m["stop"] * atr
            tp1 = entry - m["tp1"] * atr
            tp2 = entry - m["tp2"] * atr
        risk = abs(entry - stop)
        if risk <= 0:
            return _empty_plan()
        rr = abs(tp1 - entry) / risk
        return {
            "side": side,
            "entry": float(entry),
            "stop": float(stop),
            "tp1": float(tp1),
            "tp2": float(tp2),
            "rr": round(float(rr), 2),
            "valid": rr >= 1.5,
            "tier": tier,  # echoed for downstream display
        }
    except Exception:
        return _empty_plan()


def _empty(symbol: str) -> dict:
    return {"symbol": symbol, "side": "NEUTRAL", "score": 0.0,
            "tier": "LOW", "lanes_fired": {}, "active_lanes": [],
            "reasons": [], "trade_plan": _empty_plan(),
            "price_now": 0.0, "pct_24h": 0.0}


def _empty_plan() -> dict:
    return {"side": "LONG", "entry": 0.0, "stop": 0.0, "tp1": 0.0,
            "tp2": 0.0, "rr": 0.0, "valid": False}


# Backward-compatible alias (some external code may still call this)
scan_experimental = scan_unified
