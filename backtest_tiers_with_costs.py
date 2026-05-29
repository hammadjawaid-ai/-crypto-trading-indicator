"""Honest tier-by-tier backtest WITH transaction costs and drawdown
tracking.

User reported losing money on trades opened from various Pattern Scout
tiers. This backtest separately evaluates each tier (S/A/B/C) with:
  - 0.08% round-trip transaction cost (Binance taker × 2)
  - 0.05% slippage assumption (realistic on alt-coin perps)
  - Maximum drawdown tracking
  - Win rate by horizon (12, 24, 48 bars)
  - Expectancy in $ per $1000 traded

GOAL: Identify which tier(s) actually have positive expectancy after
real-world costs. Restrict opening to validated tiers only.

Tier definitions:
  S: Convergence (Pattern Scout + Setups Forming pre-warned + regime
     + 4h trend + BTC correlation favorable)
  A: Pattern Scout STRONG (score ≥ 80) — confirmed pattern, single layer
  B: Setups Forming STRONG WATCH (score ≥ 80) — anticipatory entry
  C: Pattern Scout WATCH (score 65-79) — lower confidence pattern
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

import binance_client
import indicators
import pattern_scout
import reversal_approach


# Realistic transaction costs
TAKER_FEE_PCT = 0.04         # 0.04% per side on Binance perps (0.04% × 2 = 0.08%)
SLIPPAGE_PCT = 0.05          # 0.05% slippage estimate
ROUND_TRIP_COST_PCT = TAKER_FEE_PCT * 2 + SLIPPAGE_PCT * 2  # ~0.18% per trade


def _historical_regime_composite(btc_daily: pd.DataFrame, idx: int) -> float:
    if idx >= len(btc_daily) or idx < 0:
        return 50
    bar = btc_daily.iloc[idx]
    close = float(bar["close"])
    ema_fast = float(bar.get("ema_fast") or 0)
    ema_slow = float(bar.get("ema_slow") or 0)
    if ema_fast <= 0 or ema_slow <= 0:
        return 50
    if close > ema_fast > ema_slow:
        return 75
    if close > ema_slow:
        return 55
    if close < ema_fast and close > ema_slow:
        return 45
    if close < ema_fast < ema_slow:
        return 25
    return 50


def _4h_trend_at_bar(df_4h: pd.DataFrame, target_time, side: str) -> str:
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
    else:
        if price < ema_slow and not rising:
            return "supports"
        if price > ema_slow and rising:
            return "opposes"
    return "neutral"


def _btc_4h_change_at_bar(btc_4h: pd.DataFrame, target_time) -> float:
    if len(btc_4h) < 2:
        return 0.0
    idx = btc_4h.index.searchsorted(target_time)
    idx = min(max(idx, 1), len(btc_4h) - 1)
    cur = float(btc_4h["close"].iloc[idx])
    prev = float(btc_4h["close"].iloc[idx - 1])
    if prev <= 0:
        return 0.0
    return (cur / prev - 1.0) * 100


def _stats_with_costs(returns_pct: list[float]) -> dict:
    """Compute stats AFTER applying round-trip transaction cost."""
    if not returns_pct:
        return {"n": 0}
    arr_gross = np.array(returns_pct)
    arr_net = arr_gross - ROUND_TRIP_COST_PCT  # apply cost
    wins_net = arr_net > 0
    return {
        "n": len(arr_net),
        "win_rate_gross": round(float((arr_gross > 0).mean() * 100), 1),
        "win_rate_net": round(float(wins_net.mean() * 100), 1),
        "avg_gross": round(float(arr_gross.mean()), 3),
        "avg_net": round(float(arr_net.mean()), 3),
        "median_net": round(float(np.median(arr_net)), 3),
        "best": round(float(arr_net.max()), 2),
        "worst": round(float(arr_net.min()), 2),
        # Sharpe-like (mean / std)
        "sharpe_like": round(float(arr_net.mean() / arr_net.std())
                             if arr_net.std() > 0 else 0, 2),
        # Max consecutive loss (drawdown proxy)
        "max_consec_loss": int(_max_consecutive(arr_net <= 0)),
        # Expected loss for $1000 trade
        "expectancy_per_1k": round(float(arr_net.mean() * 10), 2),  # 1% notional ≈ $10
    }


def _max_consecutive(bool_arr) -> int:
    """Max consecutive True values in array."""
    count = max_count = 0
    for v in bool_arr:
        if v:
            count += 1
            max_count = max(max_count, count)
        else:
            count = 0
    return max_count


def _classify_tier(ps_result: dict, ra_warned: bool, regime_score: float,
                   trend_4h: str, btc_4h_change: float) -> str:
    """Classify a pattern_scout fire into S/A/B/C tier matching production."""
    base = float(ps_result.get("score", 50))
    side = ps_result.get("side", "NEUTRAL")
    if side == "NEUTRAL":
        return "NONE"

    # Compute convergence score (matches production formula)
    cv_score = base
    if ra_warned:
        cv_score += 15
    if side == "LONG" and regime_score >= 50:
        cv_score += 10
    elif side == "SHORT" and regime_score < 50:
        cv_score += 10
    if trend_4h == "supports":
        cv_score += 10
    elif trend_4h == "opposes":
        cv_score -= 15
    if side == "LONG" and btc_4h_change <= -3.0:
        cv_score -= 25
    elif side == "SHORT" and btc_4h_change >= 3.0:
        cv_score -= 25

    if cv_score >= 88:
        return "S"  # Convergence
    if base >= 80:
        return "A"  # Pattern Scout STRONG
    if base >= 65:
        return "C"  # Pattern Scout WATCH
    return "NONE"


def main():
    print("Loading top 20 universe...")
    try:
        top_df = binance_client.get_top_symbols(20)
        symbols = top_df["symbol"].tolist()
    except Exception as exc:
        print(f"Failed: {exc}")
        return

    print(f"Costs: taker {TAKER_FEE_PCT}% × 2 + slippage "
          f"{SLIPPAGE_PCT}% × 2 = {ROUND_TRIP_COST_PCT}% round-trip\n")

    print("Fetching BTC daily and 4h...")
    btc_daily = binance_client.get_klines("BTCUSDT", "1d", limit=300)
    btc_daily = indicators.enrich(btc_daily)
    btc_4h = binance_client.get_klines("BTCUSDT", "4h", limit=400)
    btc_4h = indicators.enrich(btc_4h)

    SAMPLE_EVERY = 4
    WARMUP = 200
    HORIZONS = (12, 24, 48)

    # Bucket fires by tier and horizon
    tiered_fires = {
        "S": [],  # Convergence
        "A": [],  # Pattern Scout STRONG
        "B": [],  # Setups Forming (anticipatory)
        "C": [],  # Pattern Scout WATCH
    }

    print(f"\nWalking forward through {len(symbols)} coins...")

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
            continue

        fires_this_sym = {"S": 0, "A": 0, "B": 0, "C": 0}
        for t in range(WARMUP, len(df_1h) - max(HORIZONS) - 2, SAMPLE_EVERY):
            slice_1h = df_1h.iloc[:t + 1]
            try:
                ps = pattern_scout.scan_one(sym, slice_1h, pct_24h=0)
            except Exception:
                continue
            score = ps.get("score", 50)
            side = ps.get("side", "NEUTRAL")
            if score < 65 or side == "NEUTRAL":
                # Check for Setups Forming (B-tier) standalone
                for ra_side in ("LONG", "SHORT"):
                    try:
                        ra = reversal_approach.score(slice_1h, ra_side)
                    except Exception:
                        continue
                    if ra.get("score", 50) >= 80:
                        # B-tier fire
                        entry = float(slice_1h["close"].iloc[-1])
                        if entry <= 0:
                            continue
                        rets = {}
                        for h in HORIZONS:
                            if t + h >= len(df_1h):
                                continue
                            exit_p = float(df_1h["close"].iloc[t + h])
                            if ra_side == "LONG":
                                rets[h] = (exit_p / entry - 1.0) * 100
                            else:
                                rets[h] = (entry / exit_p - 1.0) * 100
                        tiered_fires["B"].append({"sym": sym, "side": ra_side,
                                                   "rets": rets})
                        fires_this_sym["B"] += 1
                continue

            # Forward returns for pattern_scout fire
            entry = float(slice_1h["close"].iloc[-1])
            if entry <= 0:
                continue
            rets = {}
            for h in HORIZONS:
                if t + h >= len(df_1h):
                    continue
                exit_p = float(df_1h["close"].iloc[t + h])
                if side == "LONG":
                    rets[h] = (exit_p / entry - 1.0) * 100
                else:
                    rets[h] = (entry / exit_p - 1.0) * 100

            # Determine tier
            target_time = slice_1h.index[-1]
            ra_warned = False
            for back in range(1, 4):
                if t - back < WARMUP:
                    break
                try:
                    ra_check = reversal_approach.score(
                        df_1h.iloc[:t - back + 1], side)
                    if ra_check.get("conditions_met", 0) >= 4:
                        ra_warned = True
                        break
                except Exception:
                    pass
            btc_d_idx = btc_daily.index.searchsorted(target_time)
            btc_d_idx = min(max(btc_d_idx, 0), len(btc_daily) - 1)
            regime_score = _historical_regime_composite(btc_daily, btc_d_idx)
            trend_4h = _4h_trend_at_bar(df_4h_sym, target_time, side)
            btc_4h_change = _btc_4h_change_at_bar(btc_4h, target_time)

            tier = _classify_tier(ps, ra_warned, regime_score, trend_4h,
                                  btc_4h_change)
            if tier == "NONE":
                continue
            tiered_fires[tier].append({"sym": sym, "side": side, "rets": rets,
                                        "score": score})
            fires_this_sym[tier] += 1

        print(f"  [{s_idx}/{len(symbols)}] {sym}: "
              f"S={fires_this_sym['S']} A={fires_this_sym['A']} "
              f"B={fires_this_sym['B']} C={fires_this_sym['C']}")

    # === REPORT ===========================================================
    print("\n" + "=" * 82)
    print("TIER-BY-TIER RESULTS — WITH TRANSACTION COSTS")
    print("=" * 82)
    print(f"All stats apply 0.18% round-trip cost (Binance taker + slippage).")
    print()
    print(f"{'Tier':<5} {'Tier Name':<30} {'horizon':<8} {'n':>5} "
          f"{'win%(gross)':>12} {'win%(net)':>11} {'avg_net%':>9} "
          f"{'sharpe':>7}")
    print("-" * 82)
    tier_names = {
        "S": "Convergence (S)",
        "A": "Pattern Scout STRONG (A)",
        "B": "Setups Forming (B)",
        "C": "Pattern Scout WATCH (C)",
    }
    for tier in ("S", "A", "B", "C"):
        fires = tiered_fires[tier]
        for h in HORIZONS:
            rets = [f["rets"].get(h) for f in fires
                    if f["rets"].get(h) is not None]
            stats = _stats_with_costs(rets)
            if stats.get("n", 0) == 0:
                print(f"{tier:<5} {tier_names[tier]:<30} +{h:<7} "
                      f"{'0':>5} {'—':>12} {'—':>11} {'—':>9} {'—':>7}")
                continue
            print(f"{tier:<5} {tier_names[tier]:<30} +{h:<7} "
                  f"{stats['n']:>5} "
                  f"{stats['win_rate_gross']:>11}% "
                  f"{stats['win_rate_net']:>10}% "
                  f"{stats['avg_net']:>+8.3f}% "
                  f"{stats['sharpe_like']:>7.2f}")
        print()

    # === VERDICT ==========================================================
    print("=" * 82)
    print("TRADE/WATCH RECOMMENDATIONS")
    print("=" * 82)
    for tier in ("S", "A", "B", "C"):
        fires = tiered_fires[tier]
        # Use 24-bar horizon as primary judgment
        rets_24 = [f["rets"].get(24) for f in fires
                   if f["rets"].get(24) is not None]
        if not rets_24:
            print(f"{tier} {tier_names[tier]:<35}: no fires — N/A")
            continue
        stats = _stats_with_costs(rets_24)
        n = stats["n"]
        avg_net = stats["avg_net"]
        win_net = stats["win_rate_net"]
        if n < 10:
            verdict = "⚠ TOO FEW FIRES — small sample, treat as WATCH"
        elif avg_net > 0.5 and win_net > 50:
            verdict = "✅ TRADEABLE — positive expectancy after costs"
        elif avg_net > 0 and win_net >= 45:
            verdict = "⚠ MARGINAL — barely positive, trade selectively"
        else:
            verdict = "❌ DO NOT TRADE — negative expectancy after costs"
        print(f"{tier} {tier_names[tier]:<35}: n={n} "
              f"win={win_net}% avg={avg_net:+.2f}% → {verdict}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\nRuntime: {time.time() - t0:.1f}s")
