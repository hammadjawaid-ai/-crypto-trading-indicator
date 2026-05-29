"""Backtest CONVERGENCE vs pattern_scout-only to validate the architecture.

Question: Does stacking convergence conditions (Setups Forming pre-warning +
regime alignment + 4h trend support + BTC correlation favorable) actually
IMPROVE win rate over pattern_scout fires alone?

If yes → CONVERGENCE is real edge.
If no  → architecture is noise, simplify back to pattern_scout only.

Method:
  Walk-forward through 1h bars on top 19 coins (1000 bars each).
  For each pattern_scout fire (score >= 70):
    - Tag forward returns at +12, +24, +48 bars
    - Also evaluate convergence conditions AT THE SAME bar:
      * reversal_approach hit in last 3 bars on same side
      * regime composite at that historical bar
      * 4h trend support at that bar
      * BTC 4h change at that bar
    - Compute convergence score (base + bonuses - penalties)
    - Tag as "CONVERGENCE" if final >= 88

Compare pooled forward returns:
  - All pattern_scout fires (baseline)
  - Pattern_scout fires that ALSO qualified as CONVERGENCE
  - Pattern_scout fires that DIDN'T qualify

If CONVERGENCE subset has materially higher win rate → architecture validated.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

import binance_client
import indicators
import pattern_scout
import reversal_approach


def _historical_regime_composite(btc_daily: pd.DataFrame, idx: int) -> float:
    """Simplified regime score at a historical bar (matches market_regime
    detect_regime logic but at a specific historical index).

    Uses BTC daily 50/200 EMA stack:
      close > 50 > 200 + golden_cross → 70+
      close > 50 only                  → 60
      close < 50, golden cross intact  → 45
      close < 50 < 200 (death cross)   → 25
    """
    if idx >= len(btc_daily) or idx < 0:
        return 50
    bar = btc_daily.iloc[idx]
    close = float(bar["close"])
    ema_fast = float(bar.get("ema_fast") or 0)
    ema_slow = float(bar.get("ema_slow") or 0)
    if ema_fast <= 0 or ema_slow <= 0:
        return 50
    if close > ema_fast and ema_fast > ema_slow:
        return 75  # BULL
    if close > ema_slow and ema_fast < ema_slow:
        return 55
    if close < ema_fast and close > ema_slow:
        return 45
    if close < ema_fast and ema_fast < ema_slow:
        return 25  # BEAR
    return 50


def _4h_trend_at_bar(df_4h: pd.DataFrame, target_time, side: str) -> str:
    """Returns 'supports', 'opposes', or 'neutral' for the 4h trend
    relative to the requested side, evaluated at the historical bar
    closest to target_time."""
    if len(df_4h) < 10:
        return "neutral"
    idx = df_4h.index.searchsorted(target_time)
    idx = min(max(idx, 5), len(df_4h) - 1)
    bar = df_4h.iloc[idx]
    price = float(bar["close"])
    ema_slow = float(bar.get("ema_slow") or 0)
    ema_5_ago = float(df_4h["ema_slow"].iloc[idx - 5])
    if ema_slow <= 0:
        return "neutral"
    rising = ema_slow > ema_5_ago
    if side == "LONG":
        if price > ema_slow and rising:
            return "supports"
        if price < ema_slow and not rising:
            return "opposes"
    else:  # SHORT
        if price < ema_slow and not rising:
            return "supports"
        if price > ema_slow and rising:
            return "opposes"
    return "neutral"


def _btc_4h_change_at_bar(btc_4h: pd.DataFrame, target_time) -> float:
    """BTC 4h price change ending at the historical bar closest to target_time."""
    if len(btc_4h) < 2:
        return 0.0
    idx = btc_4h.index.searchsorted(target_time)
    idx = min(max(idx, 1), len(btc_4h) - 1)
    cur = float(btc_4h["close"].iloc[idx])
    prev = float(btc_4h["close"].iloc[idx - 1])
    if prev <= 0:
        return 0.0
    return (cur / prev - 1.0) * 100


def _compute_convergence_score(base: float, side: str,
                               ra_warned: bool,
                               regime_score: float,
                               trend_4h: str,
                               btc_4h_change: float) -> float:
    """Apply the convergence formula used in production."""
    score = base
    if ra_warned:
        score += 15
    if side == "LONG" and regime_score >= 50:
        score += 10
    elif side == "SHORT" and regime_score < 50:
        score += 10
    if trend_4h == "supports":
        score += 10
    elif trend_4h == "opposes":
        score -= 15
    if side == "LONG" and btc_4h_change <= -3.0:
        score -= 25
    elif side == "SHORT" and btc_4h_change >= 3.0:
        score -= 25
    return max(0, min(100, score))


def _stats(returns: list[float]) -> dict:
    if not returns:
        return {"n": 0, "win_rate": None, "avg": None}
    arr = np.array(returns)
    return {
        "n": len(arr),
        "win_rate": round(float((arr > 0).mean() * 100), 1),
        "avg": round(float(arr.mean()), 3),
        "median": round(float(np.median(arr)), 3),
    }


def main():
    print("Loading top 20 universe...")
    try:
        top_df = binance_client.get_top_symbols(20)
        symbols = top_df["symbol"].tolist()
    except Exception as exc:
        print(f"Failed: {exc}")
        return

    print("Fetching BTC daily and 4h for regime + correlation...")
    btc_daily = binance_client.get_klines("BTCUSDT", "1d", limit=300)
    btc_daily = indicators.enrich(btc_daily)
    btc_4h = binance_client.get_klines("BTCUSDT", "4h", limit=400)
    btc_4h = indicators.enrich(btc_4h)

    SAMPLE_EVERY = 4    # evaluate every 4 bars
    WARMUP = 200
    HORIZONS = (12, 24, 48)

    all_fires = []          # all pattern_scout fires
    convergence_fires = []  # subset that qualified as CONVERGENCE

    print()
    print(f"Walking forward through {len(symbols)} coins...")

    for s_idx, sym in enumerate(symbols, 1):
        try:
            df_1h = binance_client.get_klines(sym, "1h", limit=1000)
            df_1h = indicators.enrich(df_1h)
            df_4h_sym = binance_client.get_klines(sym, "4h", limit=400)
            df_4h_sym = indicators.enrich(df_4h_sym)
        except Exception as exc:
            print(f"  [{s_idx}/{len(symbols)}] {sym}: SKIP ({exc})")
            continue

        if len(df_1h) < WARMUP + max(HORIZONS) + 10:
            print(f"  [{s_idx}/{len(symbols)}] {sym}: SKIP (too few bars)")
            continue

        fires_this_sym = 0
        for t in range(WARMUP, len(df_1h) - max(HORIZONS) - 2, SAMPLE_EVERY):
            slice_1h = df_1h.iloc[:t + 1]
            try:
                ps = pattern_scout.scan_one(sym, slice_1h, pct_24h=0)
            except Exception:
                continue
            if ps.get("score", 50) < 70 or ps.get("side") == "NEUTRAL":
                continue

            side = ps["side"]
            base = float(ps["score"])

            # Forward returns
            entry = float(slice_1h["close"].iloc[-1])
            if entry <= 0:
                continue
            rets = {}
            for h in HORIZONS:
                exit_p = float(df_1h["close"].iloc[t + h])
                if side == "LONG":
                    r = (exit_p / entry - 1.0) * 100
                else:
                    r = (entry / exit_p - 1.0) * 100
                rets[h] = r

            # Convergence conditions at this historical bar
            target_time = slice_1h.index[-1]
            # 1. Reversal approach in last 3 bars
            ra_warned = False
            for back in range(1, 4):
                if t - back < WARMUP:
                    break
                try:
                    ra = reversal_approach.score(
                        df_1h.iloc[:t - back + 1], side)
                    if ra.get("conditions_met", 0) >= 4:
                        ra_warned = True
                        break
                except Exception:
                    continue
            # 2. Regime
            btc_d_idx = btc_daily.index.searchsorted(target_time)
            btc_d_idx = min(max(btc_d_idx, 0), len(btc_daily) - 1)
            regime_score = _historical_regime_composite(btc_daily, btc_d_idx)
            # 3. 4h trend (use sym's own 4h)
            trend_4h = _4h_trend_at_bar(df_4h_sym, target_time, side)
            # 4. BTC correlation
            btc_4h_change = _btc_4h_change_at_bar(btc_4h, target_time)

            cv_score = _compute_convergence_score(
                base, side, ra_warned, regime_score, trend_4h, btc_4h_change)

            fire_record = {
                "symbol": sym,
                "side": side,
                "base_score": base,
                "cv_score": cv_score,
                "ra_warned": ra_warned,
                "regime_score": regime_score,
                "trend_4h": trend_4h,
                "btc_4h_change": btc_4h_change,
                "ret_12": rets[12],
                "ret_24": rets[24],
                "ret_48": rets[48],
            }
            all_fires.append(fire_record)
            if cv_score >= 88:
                convergence_fires.append(fire_record)
            fires_this_sym += 1

        print(f"  [{s_idx}/{len(symbols)}] {sym}: {fires_this_sym} fires")

    print()
    print("=" * 78)
    print("RESULTS — Pattern Scout vs CONVERGENCE")
    print("=" * 78)
    print(f"Total pattern_scout fires: {len(all_fires)}")
    print(f"  of which qualified as CONVERGENCE: {len(convergence_fires)} "
          f"({len(convergence_fires) / max(1, len(all_fires)) * 100:.1f}%)")
    print()

    # Stats per horizon
    print(f"{'Group':<28} {'horizon':<8} {'n':>6} {'win%':>7} {'avg':>9}")
    print("-" * 70)
    for label, fires in [
        ("All pattern_scout fires", all_fires),
        ("CONVERGENCE qualified", convergence_fires),
        ("Pattern_scout NOT converged", [f for f in all_fires if f not in convergence_fires]),
    ]:
        for h in HORIZONS:
            rets = [f[f"ret_{h}"] for f in fires]
            s = _stats(rets)
            print(f"{label:<28} +{h:<7} {s['n']:>6} "
                  f"{s.get('win_rate', '—')!s:>7} "
                  f"{s.get('avg', '—')!s:>9}")

    # By side
    print()
    print("BREAKDOWN BY SIDE")
    print("-" * 70)
    for side in ("LONG", "SHORT"):
        for label, fires in [
            ("All", all_fires),
            ("CONV", convergence_fires),
        ]:
            side_fires = [f for f in fires if f["side"] == side]
            for h in HORIZONS:
                rets = [f[f"ret_{h}"] for f in side_fires]
                s = _stats(rets)
                print(f"{side} {label:<8} +{h:<3} n={s['n']:<4} "
                      f"win={s.get('win_rate', '—')}% "
                      f"avg={s.get('avg', '—')}%")
        print()

    # Verdict
    print("=" * 78)
    print("VERDICT")
    print("=" * 78)
    if len(convergence_fires) >= 5 and len(all_fires) >= 10:
        for h in HORIZONS:
            all_rets = [f[f"ret_{h}"] for f in all_fires]
            cv_rets = [f[f"ret_{h}"] for f in convergence_fires]
            all_win = float((np.array(all_rets) > 0).mean() * 100)
            cv_win = float((np.array(cv_rets) > 0).mean() * 100)
            all_avg = float(np.mean(all_rets))
            cv_avg = float(np.mean(cv_rets))
            uplift_win = cv_win - all_win
            uplift_avg = cv_avg - all_avg
            verdict = ("✅ VALIDATED" if uplift_win > 5 or uplift_avg > 0.20
                       else "⚠ MARGINAL" if uplift_win > 0 or uplift_avg > 0
                       else "❌ NO UPLIFT")
            print(f"  +{h}bar: convergence wins {cv_win:.1f}% vs baseline {all_win:.1f}% "
                  f"({uplift_win:+.1f}pp) · avg {cv_avg:+.2f}% vs {all_avg:+.2f}% "
                  f"({uplift_avg:+.2f}pp) → {verdict}")
    else:
        print("  Insufficient samples for verdict.")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print()
    print(f"Total runtime: {time.time() - t0:.1f}s")
