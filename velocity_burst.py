"""Velocity Burst detector — catches the FIRST 1-2 candles of major moves.

Motivation (user feedback 2026-06-06): coins like ASR (+48%), PORTAL
(+71%), FIDA (+58%) pumped massively but our existing lanes
(pattern_scout, early_momentum, breakout_coil) caught them too late —
after 5+ confirming candles by which time half the move was already
done.

What this lane does differently: it triggers on the FIRST or SECOND
candle of a major velocity burst. Specifically:

  - Volume on the trigger candle is >= 3x the recent average
  - Range (high-low) on the trigger candle is >= 2.5x recent ATR
  - Close is on the right side of the move (strong direction commitment)
  - RSI not already exhausted (room left to run)

Detection windows:
  - 1h timeframe → catches hour-1 of breakouts (best for typical trades)
  - 15m timeframe → catches the very first 15-min surge

Score is high (typically 75-95) because by definition this is a
breakout candle — these moves either continue or are immediately
faded by liquidity. Either way the setup is decisive.

Output mirrors other lanes: (score, side, note)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _atr(df: pd.DataFrame, n: int = 14) -> float:
    """Compute ATR over the last n candles (excluding the current burst
    candle so it doesn't contaminate the baseline)."""
    if len(df) < n + 2:
        return 0.0
    # Use candles [-n-1:-1] — exclude the most recent (burst) candle
    sub = df.iloc[-n - 1:-1]
    high = sub["high"]
    low = sub["low"]
    prev_close = sub["close"].shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return float(tr.mean())


def detect_burst(df: pd.DataFrame,
                vol_mult: float = 3.0,
                range_mult: float = 2.5,
                lookback: int = 20) -> tuple[float, str, str]:
    """Detect a velocity burst on the most recent candle.

    Args:
        df: OHLCV DataFrame with at least 25 rows. Most recent candle
            is iloc[-1].
        vol_mult: volume on burst candle must be >= this × average
            volume over the lookback window. Default 3.0.
        range_mult: range (high-low) on burst candle must be >= this
            × ATR of the lookback window. Default 2.5.
        lookback: number of prior candles for the baseline. Default 20.

    Returns:
        (score, side, note) tuple matching other lane signatures.
        score 0-100, side "LONG"|"SHORT"|"NEUTRAL", note human-readable
        reason string.
    """
    if df is None or len(df) < lookback + 2:
        return 0.0, "NEUTRAL", ""
    last = df.iloc[-1]
    prev_vol = df.iloc[-lookback - 1:-1]["volume"]
    if prev_vol.mean() <= 0:
        return 0.0, "NEUTRAL", ""
    vol_ratio = float(last["volume"]) / float(prev_vol.mean())

    last_range = float(last["high"]) - float(last["low"])
    atr = _atr(df, n=lookback)
    if atr <= 0:
        return 0.0, "NEUTRAL", ""
    range_ratio = last_range / atr

    # Both conditions must hit for a BURST candle
    if vol_ratio < vol_mult or range_ratio < range_mult:
        # Also try the SECOND-most-recent candle in case we just missed
        # it by one tick (still very fresh)
        if len(df) >= lookback + 3:
            prev_candle = df.iloc[-2]
            prev_prev_vol = df.iloc[-lookback - 2:-2]["volume"]
            if prev_prev_vol.mean() > 0:
                v2 = float(prev_candle["volume"]) / float(
                    prev_prev_vol.mean())
                r2 = (float(prev_candle["high"]) - float(
                    prev_candle["low"])) / atr if atr > 0 else 0
                if v2 >= vol_mult and r2 >= range_mult:
                    # Found burst one candle ago — slightly lower score
                    return _score_burst(
                        prev_candle, df.iloc[-3], v2, r2,
                        atr, freshness=0.85)
        return 0.0, "NEUTRAL", ""

    # Fresh burst on the latest candle
    prev_candle = df.iloc[-2]
    return _score_burst(last, prev_candle, vol_ratio, range_ratio,
                       atr, freshness=1.0)


def _score_burst(burst: pd.Series,
                prev: pd.Series,
                vol_ratio: float,
                range_ratio: float,
                atr: float,
                freshness: float = 1.0) -> tuple[float, str, str]:
    """Score a confirmed burst candle and decide side + score."""
    c = float(burst["close"])
    o = float(burst["open"])
    h = float(burst["high"])
    l = float(burst["low"])
    body = abs(c - o)
    range_ = h - l
    body_pct = body / range_ if range_ > 0 else 0
    # Direction: where in the range did it close?
    close_position = (c - l) / range_ if range_ > 0 else 0.5
    pct_change = (c - float(prev["close"])) / float(prev["close"]) \
        if float(prev["close"]) > 0 else 0

    # SIDE DECISION
    if close_position >= 0.65 and pct_change > 0:
        side = "LONG"
    elif close_position <= 0.35 and pct_change < 0:
        side = "SHORT"
    else:
        # Indecisive candle (long wicks both sides) — skip
        return 0.0, "NEUTRAL", "indecisive burst"

    # SCORE — base 75, scale up with extremity
    base = 75.0
    # Bonus for very high vol/range ratios
    vol_bonus = min(10, (vol_ratio - 3) * 2.5)
    range_bonus = min(8, (range_ratio - 2.5) * 4)
    # Bonus for strong body (low wick noise)
    body_bonus = min(5, body_pct * 7) if body_pct >= 0.5 else 0
    score = base + vol_bonus + range_bonus + body_bonus
    score = float(np.clip(score * freshness, 0, 100))

    note = (
        f"vol {vol_ratio:.1f}x · range {range_ratio:.1f}x ATR · "
        f"{pct_change * 100:+.1f}% candle"
    )
    return round(score, 1), side, note


# Convenience entrypoint for the ELITE composite to call directly
def detect_grind(df: pd.DataFrame) -> tuple[float, str, str]:
    """Detect a STEADY GRIND — a sustained staircase move that the
    single-candle burst detector misses (e.g. XPL: +4.65% over 2h via
    many small green candles, no explosive candle).

    LONG when, over the last 8 fifteen-min candles (~2h):
      - net move >= +2.5%
      - >= 5 of 8 candles closed green
      - price above the 15m EMA20 (uptrend intact)
      - EMA20 rising
    SHORT is the mirror. Returns (score, side, note).
    """
    if df is None or len(df) < 30:
        return 0.0, "NEUTRAL", ""
    close = df["close"]
    n = 8
    if len(close) < n + 1:
        return 0.0, "NEUTRAL", ""
    c_now = float(close.iloc[-1])
    c_n = float(close.iloc[-(n + 1)])
    if c_n <= 0:
        return 0.0, "NEUTRAL", ""
    net = (c_now / c_n - 1.0) * 100
    greens = sum(1 for i in range(-n, 0)
                 if float(close.iloc[i]) > float(close.iloc[i - 1]))
    reds = n - greens
    ema20 = close.ewm(span=20, adjust=False).mean()
    e20 = float(ema20.iloc[-1])
    e20_prev = float(ema20.iloc[-5]) if len(ema20) >= 5 else e20

    # LONG grind
    if (net >= 2.5 and greens >= 5 and c_now > e20 and e20 > e20_prev):
        score = min(95, 60 + net * 2 + (greens - 5) * 3)
        return (round(score, 1), "LONG",
                f"grind +{net:.1f}% over 2h · {greens}/8 green · "
                f"above EMA20")
    # SHORT grind
    if (net <= -2.5 and reds >= 5 and c_now < e20 and e20 < e20_prev):
        score = min(95, 60 + abs(net) * 2 + (reds - 5) * 3)
        return (round(score, 1), "SHORT",
                f"grind {net:.1f}% over 2h · {reds}/8 red · "
                f"below EMA20")
    return 0.0, "NEUTRAL", ""


def scan_15m_early(symbols: list[str],
                  max_results: int = 12) -> list[dict]:
    """🔥 Early Burst Radar — detect bursts BUILDING on the 15m clock.

    A big 1h burst is made of 15m candles that were each surging. By
    scanning 15m we catch the SAME move ~30-45 min before the 1h candle
    closes — earlier entry, same proven pattern, faster timeframe.

    HONEST: 15m is noisier than 1h (more false starts), and this is NOT
    yet walk-forward backtested on 15m. It surfaces candidates with a
    'how early' meter + the 1h-trend check so the user can confirm
    before acting. Trade these smaller.

    Returns dicts sorted by score:
      {symbol, base, side, score, note, move_1h_pct, freshness,
       trend_1h, aligned_1h, price}
    where freshness ∈ {'very early','early','extended'} based on how
    much of the move has already happened.
    """
    out = []
    for sym in symbols:
        try:
            df15 = binance_client.get_klines(sym, "15m", limit=60)
        except Exception:
            continue
        score, side, note = detect_burst(
            df15, vol_mult=2.5, range_mult=2.0, lookback=20)
        pattern = "burst"
        # If no explosive burst, check for a STEADY GRIND (XPL-style
        # staircase) — catches sustained moves the burst detector
        # misses. Grind is NOT yet backtested (burst is), so it's
        # tagged distinctly and never gets the VALIDATED badge.
        if score < 65 or side not in ("LONG", "SHORT"):
            gscore, gside, gnote = detect_grind(df15)
            if gscore >= 65 and gside in ("LONG", "SHORT"):
                score, side, note, pattern = gscore, gside, gnote, "grind"
            else:
                continue
        close = df15["close"]
        c_now = float(close.iloc[-1])
        # Move over the last 4 fifteen-min candles ≈ the forming 1h bar
        c_4 = float(close.iloc[-5]) if len(close) >= 5 else c_now
        move_1h = (c_now / c_4 - 1.0) * 100 if c_4 > 0 else 0.0
        # Backtest-validated trade plan: SL 1.2 ATR, TP 4.5 ATR (let it
        # run — the 30-day walk-forward showed +0.18R on very-early +
        # 1h-aligned at TP 4.5-5.0, vs ~breakeven at TP 2.0). ~21% win,
        # big R. ATR from the 15m series.
        _h, _l, _pc = df15["high"], df15["low"], close.shift(1)
        _tr = pd.concat([_h - _l, (_h - _pc).abs(),
                         (_l - _pc).abs()], axis=1).max(axis=1)
        _atr15 = float(_tr.rolling(20).mean().iloc[-1] or 0)
        if _atr15 > 0:
            if side == "LONG":
                plan_stop = c_now - 1.2 * _atr15
                plan_tp = c_now + 4.5 * _atr15
            else:
                plan_stop = c_now + 1.2 * _atr15
                plan_tp = c_now - 4.5 * _atr15
            plan_rr = 4.5 / 1.2
        else:
            plan_stop = plan_tp = 0.0
            plan_rr = 0.0
        # How early are we? (directional magnitude already travelled)
        _mag = abs(move_1h)
        if _mag < 4:
            freshness = "very early"
        elif _mag < 8:
            freshness = "early"
        else:
            freshness = "extended"   # like catching ID at +10%
        # 1h trend check — does the bigger clock agree?
        trend_1h = "?"
        aligned = False
        try:
            df1h = binance_client.get_klines(sym, "1h", limit=60)
            if df1h is not None and len(df1h) >= 50:
                c1 = df1h["close"]
                ema20 = c1.ewm(span=20, adjust=False).mean()
                ema50 = c1.ewm(span=50, adjust=False).mean()
                px = float(c1.iloc[-1])
                e20 = float(ema20.iloc[-1])
                e50 = float(ema50.iloc[-1])
                if px > e20 > e50:
                    trend_1h = "BULL"
                elif px < e20 < e50:
                    trend_1h = "BEAR"
                else:
                    trend_1h = "MIXED"
                aligned = ((side == "LONG" and trend_1h == "BULL")
                           or (side == "SHORT" and trend_1h == "BEAR"))
        except Exception:
            pass
        # VALIDATED-EDGE flag: BURST + very-early + 1h-aligned = the
        # +0.18R slice from the walk-forward. Grind is not backtested,
        # so it never gets the validated badge.
        validated = (pattern == "burst"
                     and freshness == "very early" and aligned)
        out.append({
            "symbol": sym,
            "base": sym.replace("USDT", ""),
            "side": side,
            "score": score,
            "pattern": pattern,
            "note": note,
            "move_1h_pct": round(move_1h, 2),
            "freshness": freshness,
            "trend_1h": trend_1h,
            "aligned_1h": aligned,
            "validated": validated,
            "plan_entry": round(c_now, 8),
            "plan_stop": round(plan_stop, 8),
            "plan_tp": round(plan_tp, 8),
            "plan_rr": round(plan_rr, 2),
            "price": c_now,
        })
    # Rank: VALIDATED slice first (very-early + aligned = +0.18R), then
    # aligned, then freshness, then score.
    _fresh_rank = {"very early": 2, "early": 1, "extended": 0}
    out.sort(key=lambda x: (1 if x["validated"] else 0,
                            1 if x["aligned_1h"] else 0,
                            _fresh_rank.get(x["freshness"], 0),
                            x["score"]),
             reverse=True)
    return out[:max_results]


def lane_velocity_burst(df: pd.DataFrame) -> tuple[float, str, str]:
    """ELITE-composite-compatible entrypoint.

    EARLIER DETECTION (2026-06-11, user request): thresholds lowered
    from 3.0x vol / 2.5x ATR to 2.5x vol / 2.0x ATR so a building burst
    registers ~1 candle sooner. This makes the SCORE rise earlier in a
    move. The proven-edge protection still holds because:
      - score 90+ is the standalone-proven band (+0.127R)
      - score 78-89 (the new earlier band) counts as a CONFLUENCE
        contributor only — the per-lane floor in _composite_from_lanes
        is 78, and the Paper Trader quality gate (2+ systems OR
        score>=85) + multi-TF gate, and Sure Shot's agent consensus,
        ensure an early burst NEVER surfaces alone. It only shows when
        the rest of the desk confirms it — exactly the user's ask."""
    return detect_burst(df, vol_mult=2.5, range_mult=2.0, lookback=20)
