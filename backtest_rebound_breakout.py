"""Walk-forward backtest for rebound_radar and breakout_hunter.

For each module:
 1. Pick a sample of liquid coins
 2. Walk forward through historical klines
 3. At each bar, run the score function on data UP TO that bar
 4. If score >= threshold, simulate opening a position
 5. Track forward returns at +12, +24, +48 bars
 6. Compute win rate, avg return, R:R hit rate

Reports REAL numbers — if either module has no edge, this script will
say so and the commit message should be honest about it.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

import binance_client
import indicators
import rebound_radar
import breakout_hunter


def _walk_forward_one(symbol: str, df: pd.DataFrame, score_fn,
                     min_score: float, score_kwargs: dict,
                     horizons: tuple = (12, 24, 48),
                     warmup: int = 80,
                     sample_every: int = 4) -> list[dict]:
    """For one symbol's enriched dataframe, walk forward, score at each
    bar (after warmup), and collect forward returns for fires."""
    fires = []
    n = len(df)
    if n < warmup + max(horizons) + 10:
        return fires
    for t in range(warmup, n - max(horizons) - 2, sample_every):
        slice_df = df.iloc[:t + 1]
        try:
            r = score_fn(symbol, slice_df, **score_kwargs)
        except Exception:
            continue
        if r.get("score", 0) < min_score:
            continue
        entry = float(slice_df["close"].iloc[-1])
        if entry <= 0:
            continue
        rets = {}
        for h in horizons:
            try:
                exit_p = float(df["close"].iloc[t + h])
            except Exception:
                continue
            rets[h] = (exit_p / entry - 1.0) * 100  # LONG-side
        fires.append({
            "symbol": symbol,
            "score": r.get("score", 0),
            "entry": entry,
            "ret_12": rets.get(12, 0),
            "ret_24": rets.get(24, 0),
            "ret_48": rets.get(48, 0),
        })
    return fires


def _stats(returns: list[float]) -> dict:
    if not returns:
        return {"n": 0, "win_rate": None, "avg": None, "median": None}
    arr = np.array(returns)
    return {
        "n": len(arr),
        "win_rate": round(float((arr > 0).mean() * 100), 1),
        "avg": round(float(arr.mean()), 3),
        "median": round(float(np.median(arr)), 3),
    }


def _backtest_rebound(symbols: list[str]) -> dict:
    """Backtest rebound_radar on 1h data."""
    all_fires = []
    for i, sym in enumerate(symbols, 1):
        try:
            df = binance_client.get_klines(sym, "1h", limit=1000)
            df = indicators.enrich(df)
        except Exception:
            continue
        fires = _walk_forward_one(
            sym, df,
            score_fn=lambda s, d, **kw: rebound_radar.score(s, d, **kw),
            min_score=70.0, score_kwargs={"pct_24h": 0.0})
        all_fires.extend(fires)
        print(f"  [{i}/{len(symbols)}] {sym}: {len(fires)} fires")

    results = {}
    for h in (12, 24, 48):
        rets = [f[f"ret_{h}"] for f in all_fires]
        results[f"+{h}bar"] = _stats(rets)
    return {
        "module": "rebound_radar",
        "tf": "1h",
        "min_score": 70.0,
        "total_fires": len(all_fires),
        "results": results,
    }


def _backtest_breakout(symbols: list[str]) -> dict:
    """Backtest breakout_hunter on 4h data."""
    all_fires = []
    for i, sym in enumerate(symbols, 1):
        try:
            df_4h = binance_client.get_klines(sym, "4h", limit=500)
            df_4h = indicators.enrich(df_4h)
        except Exception:
            continue
        fires = _walk_forward_one(
            sym, df_4h,
            score_fn=lambda s, d, **kw: breakout_hunter.score(s, d),
            min_score=70.0, score_kwargs={}, horizons=(6, 18, 42),
            warmup=80, sample_every=2)
        all_fires.extend(fires)
        print(f"  [{i}/{len(symbols)}] {sym}: {len(fires)} fires")

    results = {}
    # For breakout — horizons are 4h bars: 6 = 24h, 18 = 3 days, 42 = 7 days
    for h, label in zip((6, 18, 42), ("+24h", "+3d", "+7d")):
        rets = [f[f"ret_{h}"] for f in all_fires]
        results[label] = _stats(rets)
    return {
        "module": "breakout_hunter",
        "tf": "4h",
        "min_score": 70.0,
        "total_fires": len(all_fires),
        "results": results,
    }


def main():
    print("Loading top-25 universe by Binance volume...")
    try:
        top = binance_client.get_top_symbols(25)
        symbols = top["symbol"].tolist()
    except Exception as exc:
        print(f"Universe fetch failed: {exc}")
        return

    print()
    print("=" * 78)
    print("REBOUND RADAR — 1h walk-forward backtest")
    print("=" * 78)
    t0 = time.time()
    rebound_results = _backtest_rebound(symbols)
    print(f"\n  Total runtime: {time.time() - t0:.1f}s")
    print()
    print(f"  Total fires (score >= 70): {rebound_results['total_fires']}")
    for h, stats in rebound_results["results"].items():
        print(f"  {h} forward: n={stats['n']} win%={stats['win_rate']} "
              f"avg={stats['avg']}% median={stats['median']}%")

    print()
    print("=" * 78)
    print("BREAKOUT HUNTER — 4h walk-forward backtest")
    print("=" * 78)
    t0 = time.time()
    breakout_results = _backtest_breakout(symbols)
    print(f"\n  Total runtime: {time.time() - t0:.1f}s")
    print()
    print(f"  Total fires (score >= 70): {breakout_results['total_fires']}")
    for h, stats in breakout_results["results"].items():
        print(f"  {h} forward: n={stats['n']} win%={stats['win_rate']} "
              f"avg={stats['avg']}% median={stats['median']}%")

    print()
    print("=" * 78)
    print("VERDICT")
    print("=" * 78)
    # Rebound verdict: win rate at +24bar (~1 day)
    reb = rebound_results["results"].get("+24bar") or {}
    if (reb.get("n") or 0) >= 5 and (reb.get("win_rate") or 0) >= 55:
        print(f"  REBOUND: VALIDATED — win {reb['win_rate']}% avg "
              f"{reb['avg']}% (n={reb['n']})")
    elif (reb.get("n") or 0) >= 5:
        print(f"  REBOUND: MARGINAL — win {reb['win_rate']}% avg "
              f"{reb['avg']}% (n={reb['n']}) — be cautious sizing up")
    else:
        print(f"  REBOUND: INSUFFICIENT — only n={reb.get('n', 0)} fires "
              "in the sample")

    bk = breakout_results["results"].get("+3d") or {}
    if (bk.get("n") or 0) >= 5 and (bk.get("win_rate") or 0) >= 50:
        print(f"  BREAKOUT: VALIDATED — win {bk['win_rate']}% avg "
              f"{bk['avg']}% (n={bk['n']})")
    elif (bk.get("n") or 0) >= 5:
        print(f"  BREAKOUT: MARGINAL — win {bk['win_rate']}% avg "
              f"{bk['avg']}% (n={bk['n']}) — be cautious sizing up")
    else:
        print(f"  BREAKOUT: INSUFFICIENT — only n={bk.get('n', 0)} fires "
              "in the sample")


if __name__ == "__main__":
    main()
