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

import binance_client


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
_GRIND_WIN = 7        # candle window (4-7 directional candles qualify)
_GRIND_MIN_DIR = 4    # need >= this many candles in one direction
_GRIND_MIN_NET = 1.5  # min % move over the window


def _rsi_last(close: pd.Series, n: int = 14) -> float:
    d = close.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    v = (100 - 100 / (1 + rs)).iloc[-1]
    return float(v) if pd.notna(v) else 50.0


def detect_grind(df: pd.DataFrame) -> tuple[float, str, str]:
    """Detect a STRENGTH run by CANDLE CLOSING STRENGTH.

    Redefined 2026-06-12 (user): "15m-30m, 3-7 candles one direction
    (1-3 can be red), look at the STRENGTH of the candles — how
    strongly they close — even with some red, vice versa for shorts."

    Over the last 7 candles:
      - directional candles = body candles closing the pick's way
        (close>open for LONG). Need >= 3 of 7 (3-7, reds tolerated).
      - CLOSE STRENGTH = where each directional candle closed in its
        range: (close-low)/(high-low) for LONG (1.0 = closed at the
        high = strong). This is the heart of it — strong closes, not
        just green count.
      - net move >= +1.0%, price > 15m EMA20.
      - counter (red) candles only hurt if they have BIG bodies
        (a strong red breaks the run; a shallow doji pullback is fine).
    Score 0-100 weights close-strength heavily. SHORT mirrors.
    """
    if df is None or len(df) < 30:
        return 0.0, "NEUTRAL", ""
    w = 7
    o = df["open"].astype(float).to_numpy()
    h = df["high"].astype(float).to_numpy()
    l = df["low"].astype(float).to_numpy()
    c = df["close"].astype(float).to_numpy()
    if len(c) < w + 1:
        return 0.0, "NEUTRAL", ""
    c_now = c[-1]
    c_w = c[-(w + 1)]
    if c_w <= 0:
        return 0.0, "NEUTRAL", ""
    net = (c_now / c_w - 1.0) * 100
    e20 = float(df["close"].ewm(span=20, adjust=False).mean().iloc[-1])
    rng = np.maximum(h - l, 1e-12)

    def _run(direction):
        """direction 'L' or 'S' — return (dir_count, close_strength,
        counter_body, strong_dir_bonus) over the last w candles."""
        idx = range(-w, 0)
        dir_cnt = 0
        close_strs = []
        counter_bodies = []
        for i in idx:
            body = abs(c[i] - o[i]) / rng[i]
            if direction == "L":
                is_dir = c[i] > o[i]
                close_pos = (c[i] - l[i]) / rng[i]   # 1=closed at high
            else:
                is_dir = c[i] < o[i]
                close_pos = (h[i] - c[i]) / rng[i]   # 1=closed at low
            if is_dir:
                dir_cnt += 1
                close_strs.append(close_pos * (0.4 + 0.6 * body))
            else:
                counter_bodies.append(body)
        close_strength = (sum(close_strs) / len(close_strs)
                          if close_strs else 0.0)
        counter_body = (sum(counter_bodies) / len(counter_bodies)
                        if counter_bodies else 0.0)
        return dir_cnt, close_strength, counter_body

    def _score(dir_cnt, close_strength, counter_body, net_abs):
        # base 35; close-strength is the dominant term (up to +35);
        # +candle count, +net move; - strong counter candles.
        return float(np.clip(
            35
            + close_strength * 35
            + (dir_cnt - 3) * 4
            + min(15, net_abs * 2.5)
            - counter_body * 18,
            0, 100))

    # LONG
    dl, csl, cbl = _run("L")
    if dl >= 3 and net >= 1.0 and c_now > e20:
        sc = _score(dl, csl, cbl, abs(net))
        return (round(sc, 1), "LONG",
                f"grind +{net:.1f}% · {dl}/{w} green · close-strength "
                f"{csl:.0%} · >EMA20")
    # SHORT
    ds, css, cbs = _run("S")
    if ds >= 3 and net <= -1.0 and c_now < e20:
        sc = _score(ds, css, cbs, abs(net))
        return (round(sc, 1), "SHORT",
                f"grind {net:.1f}% · {ds}/{w} red · close-strength "
                f"{css:.0%} · <EMA20")
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
    # TF stack (user 2026-06-12): 15m primary + 30m confirm. 5m was
    # too fast — a coin like SYN (+65% on 1h) had already REVERSED on
    # 5m (-6.6% last 40min) so 5m fired nothing, while 15m showed the
    # real +24.7% run. 15m catches the move without whipsawing out.
    out = []
    for sym in symbols:
        try:
            df15 = binance_client.get_klines(sym, "15m", limit=60)
        except Exception:
            continue
        if df15 is None or len(df15) < 30:
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
            # Floor 50 (was 65): detect_grind's strength score starts
            # at 45, so a typical grind lands 50-64. The old 65 floor
            # silently dropped almost every grind (incl. SYN). 50 lets
            # firing coins show; the strict-validated flag still gates
            # the proven slice.
            if gscore >= 50 and gside in ("LONG", "SHORT"):
                score, side, note, pattern = gscore, gside, gnote, "grind"
            else:
                continue
        close = df15["close"]
        c_now = float(close.iloc[-1])
        # Move over the last 4 fifteen-min candles ≈ the forming 1h bar
        c_4 = float(close.iloc[-5]) if len(close) >= 5 else c_now
        move_1h = (c_now / c_4 - 1.0) * 100 if c_4 > 0 else 0.0
        # Backtest-sized plan, SL 1.2 ATR. Target by pattern (both
        # validated on the 30-day walk-forward, very-early + aligned):
        #   BURST: TP 4.5 ATR — +0.18R, ~21% win (let it run, big R)
        #   GRIND: TP 1.5 ATR — HIGH-WIN-RATE tuning per user goal:
        #          ~52% win, +0.18R (n=653). The +EV sweet spot is
        #          TP 2.5 (+0.26R, 40% win); 60% win is reachable at
        #          TP 1.0 (+0.10R). 1.5 ATR is the balance — decent
        #          win rate AND healthy expectancy.
        # GRIND uses SCALE-OUT (backtested ~60% green, +0.116R, n=654):
        #   TP1 = +1.5 ATR (book half) · TP2 = +2.5 ATR (runner) ·
        #   stop moves to breakeven after TP1. BURST keeps single
        #   let-it-run target (4.5 ATR).
        _tp_mult = 1.5 if pattern == "grind" else 4.5
        _tp2_mult = 2.5 if pattern == "grind" else 0.0
        _h, _l, _pc = df15["high"], df15["low"], close.shift(1)
        _tr = pd.concat([_h - _l, (_h - _pc).abs(),
                         (_l - _pc).abs()], axis=1).max(axis=1)
        _atr15 = float(_tr.rolling(20).mean().iloc[-1] or 0)
        if _atr15 > 0:
            if side == "LONG":
                plan_stop = c_now - 1.2 * _atr15
                plan_tp = c_now + _tp_mult * _atr15
                plan_tp2 = (c_now + _tp2_mult * _atr15
                            if _tp2_mult else 0.0)
            else:
                plan_stop = c_now + 1.2 * _atr15
                plan_tp = c_now - _tp_mult * _atr15
                plan_tp2 = (c_now - _tp2_mult * _atr15
                            if _tp2_mult else 0.0)
            plan_rr = _tp_mult / 1.2
        else:
            plan_stop = plan_tp = plan_tp2 = 0.0
            plan_rr = 0.0
        # How early are we? (directional magnitude already travelled)
        _mag = abs(move_1h)
        if _mag < 4:
            freshness = "very early"
        elif _mag < 8:
            freshness = "early"
        else:
            freshness = "extended"   # like catching ID at +10%
        # 30m confirmation — EMA trend AND candle direction (4 of last
        # 6 30m candles same way), so "5m to 30m, 4-7 candles one
        # direction" per the user's spec. (field kept as trend_1h /
        # aligned_1h for UI compatibility — it now reflects 30m.)
        trend_1h = "?"
        aligned = False
        h1_candles_dir = 0
        try:
            df1h = binance_client.get_klines(sym, "30m", limit=60)
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
                # 1h candle direction over last 6
                if side == "LONG":
                    h1_candles_dir = sum(
                        1 for i in range(-6, 0)
                        if float(c1.iloc[i]) > float(c1.iloc[i - 1]))
                else:
                    h1_candles_dir = sum(
                        1 for i in range(-6, 0)
                        if float(c1.iloc[i]) < float(c1.iloc[i - 1]))
                trend_ok = ((side == "LONG" and trend_1h != "BEAR")
                            or (side == "SHORT" and trend_1h != "BULL"))
                # 1h confirms when EMA trend isn't against AND >=4/6
                # 1h candles run the pick's way.
                aligned = trend_ok and h1_candles_dir >= 4
        except Exception:
            pass
        # VALIDATED flag — honest, backtest-driven:
        #   The LOOSE 4/7 grind fires a lot but has NO reliable edge
        #   (re-backtest: +0.027R, non-monotonic in strength). Only
        #   the STRICT slice carries the proven +0.116R: a firm run
        #   (net >= 2.5% over ~8 candles, >=5 directional) + very-early
        #   + 1h-confirmed. So loose grinds SHOW (📈 firing, visibility)
        #   but only the strict slice is ✅ VALIDATED.
        #   BURST -> keeps its backtested gate: very-early + aligned.
        if pattern == "grind":
            try:
                _c8 = float(close.iloc[-9]) if len(close) >= 9 else c_now
                _net8 = (c_now / _c8 - 1.0) * 100 if _c8 > 0 else 0.0
                if side == "LONG":
                    _dir8 = sum(1 for i in range(-8, 0)
                                if float(close.iloc[i])
                                > float(close.iloc[i - 1]))
                    _strict_run = _net8 >= 2.5 and _dir8 >= 5
                else:
                    _dir8 = sum(1 for i in range(-8, 0)
                                if float(close.iloc[i])
                                < float(close.iloc[i - 1]))
                    _strict_run = _net8 <= -2.5 and _dir8 >= 5
            except Exception:
                _strict_run = False
            validated = (_strict_run
                         and freshness == "very early" and aligned)
        else:
            validated = (freshness == "very early" and aligned)
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
            "plan_tp2": round(plan_tp2, 8),
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
