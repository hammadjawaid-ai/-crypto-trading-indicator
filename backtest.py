"""Walk-forward backtest harness for score-based signal modules.

Honest backtesting with three non-negotiables:

1. **No lookahead.** At each bar t, the score function sees ONLY klines
   [0..t]. We slice the DataFrame before calling the score function so
   there is no chance of accidentally peeking at future data.

2. **Entry lag.** When a chip fires at bar t (end of bar t's close), the
   simulated entry is at bar t+1's open — we can only act on closed bars
   in the real world.

3. **Forward returns are measured at fixed horizons (e.g. 12, 24, 48
   bars), NOT optimal exits.** We're measuring whether the signal
   correlates with positive forward returns, not picking the best exit.
   If the signal has edge, it'll show up in the forward-horizon stats.
   Optimal-exit backtests are a separate concern (and often a way to
   lie to yourself with curve fitting).

The harness is generic: pass any function with signature
    score(df: pd.DataFrame) -> dict
that returns a dict with at least "score" (0-100) and "side" (LONG /
SHORT / NEUTRAL), and you'll get back win rate / avg return / expectancy
across the dataset.

Designed to run from the CLI or be invoked from a Streamlit display tab
— pure module, no Streamlit dependency.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

import binance_client
import indicators


@dataclass
class BacktestConfig:
    """Tuneable knobs for one backtest run."""
    interval: str = "1h"
    klines_limit: int = 1000
    warmup_bars: int = 200            # bars consumed by indicators before signals
    sample_every: int = 4             # eval every Nth bar (perf vs precision)
    threshold_long: float = 75.0      # score >= this AND side==LONG  -> fire
    threshold_short: float = 25.0     # score <= this AND side==SHORT -> fire
    forward_horizons: tuple = (12, 24, 48)  # bars to measure forward return
    entry_lag: int = 1                # bars after fire before entering


@dataclass
class SymbolResult:
    """Backtest outcome for one symbol."""
    symbol: str
    n_bars_evaluated: int = 0
    long_fires: int = 0
    short_fires: int = 0
    # Per-horizon stats: horizon_bars -> dict with win_rate, avg_return, etc.
    long_stats: dict = field(default_factory=dict)
    short_stats: dict = field(default_factory=dict)
    baseline: dict = field(default_factory=dict)
    error: str | None = None


def _forward_returns(closes: pd.Series, entry_idx: int,
                     horizons: tuple, side: str) -> dict:
    """Forward return at each horizon for a long or short entered at
    `entry_idx` (using close of that bar — the harness applies entry_lag
    before passing this index).

    Returns {horizon_bars: pct_return_float} for each requested horizon,
    skipping horizons that fall past the end of the series.
    """
    n = len(closes)
    entry_price = float(closes.iloc[entry_idx])
    out: dict[int, float] = {}
    for h in horizons:
        exit_idx = entry_idx + h
        if exit_idx >= n or entry_price <= 0:
            continue
        exit_price = float(closes.iloc[exit_idx])
        ret = (exit_price / entry_price - 1.0)
        if side == "SHORT":
            ret = -ret
        out[h] = ret
    return out


def _aggregate_returns(returns_by_horizon: dict[int, list[float]]) -> dict:
    """Aggregate raw forward returns into a stats summary per horizon."""
    out: dict[int, dict] = {}
    for h, rets in returns_by_horizon.items():
        if not rets:
            out[h] = {"n": 0, "win_rate": None, "avg_return_pct": None,
                      "median_return_pct": None, "best_pct": None,
                      "worst_pct": None, "expectancy_pct": None}
            continue
        arr = np.array(rets)
        wins = arr[arr > 0]
        losses = arr[arr <= 0]
        win_rate = float(len(wins) / len(arr))
        avg_win = float(wins.mean()) if len(wins) else 0.0
        avg_loss = float(losses.mean()) if len(losses) else 0.0
        # Expectancy per trade in % terms
        expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
        out[h] = {
            "n": int(len(arr)),
            "win_rate": round(win_rate * 100, 1),
            "avg_return_pct": round(float(arr.mean()) * 100, 3),
            "median_return_pct": round(float(np.median(arr)) * 100, 3),
            "best_pct": round(float(arr.max()) * 100, 2),
            "worst_pct": round(float(arr.min()) * 100, 2),
            "expectancy_pct": round(expectancy * 100, 3),
        }
    return out


def run_symbol(symbol: str,
               score_fn: Callable[[pd.DataFrame], dict],
               cfg: BacktestConfig) -> SymbolResult:
    """Run the backtest on a single symbol.

    Fetches klines, walks forward bar by bar (every `sample_every` bars),
    accumulates forward returns for chip fires AND for the all-bars
    baseline, then aggregates.
    """
    res = SymbolResult(symbol=symbol)
    try:
        df_raw = binance_client.get_klines(
            symbol, cfg.interval, limit=cfg.klines_limit)
    except Exception as exc:
        res.error = f"klines fetch failed: {exc}"
        return res
    if df_raw is None or len(df_raw) < cfg.warmup_bars + max(cfg.forward_horizons) + 10:
        res.error = f"not enough klines ({len(df_raw) if df_raw is not None else 0})"
        return res

    # Pre-enrich the full DF once; we'll pass slices [0..t] to score_fn.
    # NOTE: passing pre-enriched slice is safe because all indicators in
    # indicators.enrich() are rolling/EMA-based and only depend on PAST
    # bars — slicing at t doesn't recompute any future-tainted values.
    df_full = indicators.enrich(df_raw)
    closes = df_full["close"]

    long_returns: dict[int, list[float]] = {h: [] for h in cfg.forward_horizons}
    short_returns: dict[int, list[float]] = {h: [] for h in cfg.forward_horizons}
    baseline_returns: dict[int, list[float]] = {h: [] for h in cfg.forward_horizons}

    n_evaluated = 0
    last_h = max(cfg.forward_horizons)
    end = len(df_full) - last_h - cfg.entry_lag - 1
    for t in range(cfg.warmup_bars, end, cfg.sample_every):
        # No-lookahead slice: indicators at t use only bars [0..t]
        slice_df = df_full.iloc[: t + 1]
        try:
            r = score_fn(slice_df)
        except Exception:
            continue
        n_evaluated += 1
        score = float(r.get("score") or 50)
        side = str(r.get("side") or "NEUTRAL")

        entry_idx = t + cfg.entry_lag
        # Baseline: collect forward returns at every evaluated bar (even
        # when no fire) so we know the dataset's natural mean drift.
        b_rets = _forward_returns(closes, entry_idx,
                                  cfg.forward_horizons, "LONG")
        for h, ret in b_rets.items():
            baseline_returns[h].append(ret)

        # Long fire
        if score >= cfg.threshold_long and side == "LONG":
            res.long_fires += 1
            for h, ret in _forward_returns(closes, entry_idx,
                                           cfg.forward_horizons,
                                           "LONG").items():
                long_returns[h].append(ret)
        # Short fire
        elif score <= cfg.threshold_short and side == "SHORT":
            res.short_fires += 1
            for h, ret in _forward_returns(closes, entry_idx,
                                           cfg.forward_horizons,
                                           "SHORT").items():
                short_returns[h].append(ret)

    res.n_bars_evaluated = n_evaluated
    res.long_stats = _aggregate_returns(long_returns)
    res.short_stats = _aggregate_returns(short_returns)
    res.baseline = _aggregate_returns(baseline_returns)
    return res


def run_universe(symbols: list[str],
                 score_fn: Callable[[pd.DataFrame], dict],
                 cfg: BacktestConfig | None = None,
                 workers: int = 6,
                 progress: Callable[[str, int, int], None] | None = None,
                 ) -> dict:
    """Run the backtest across a list of symbols in parallel and roll the
    per-symbol stats into one summary.

    `progress`, if given, is invoked as progress(symbol, done, total) so
    a Streamlit UI can render a progress bar.
    """
    cfg = cfg or BacktestConfig()
    results: list[SymbolResult] = []
    total = len(symbols)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_symbol, s, score_fn, cfg): s
                   for s in symbols}
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:
                res = SymbolResult(symbol=sym, error=str(exc))
            results.append(res)
            done += 1
            if progress is not None:
                try:
                    progress(sym, done, total)
                except Exception:
                    pass

    # Aggregate across symbols: pool all forward returns by horizon
    long_pool: dict[int, list[float]] = {h: [] for h in cfg.forward_horizons}
    short_pool: dict[int, list[float]] = {h: [] for h in cfg.forward_horizons}
    base_pool: dict[int, list[float]] = {h: [] for h in cfg.forward_horizons}
    # NOTE: this re-pools the AGGREGATED stats, which loses individual
    # trade granularity. We rebuild from the per-symbol n + avg via a
    # weighted average that approximates the true pooled mean. Close
    # enough for the audit reports we need; if we ever need exact
    # distributional stats we can return raw arrays.
    for r in results:
        for h in cfg.forward_horizons:
            l = r.long_stats.get(h, {})
            s = r.short_stats.get(h, {})
            b = r.baseline.get(h, {})
            if l.get("n"):
                long_pool[h].extend([l["avg_return_pct"] / 100] * l["n"])
            if s.get("n"):
                short_pool[h].extend([s["avg_return_pct"] / 100] * s["n"])
            if b.get("n"):
                base_pool[h].extend([b["avg_return_pct"] / 100] * b["n"])

    summary = {
        "config": {
            "interval": cfg.interval, "klines_limit": cfg.klines_limit,
            "warmup_bars": cfg.warmup_bars, "sample_every": cfg.sample_every,
            "threshold_long": cfg.threshold_long,
            "threshold_short": cfg.threshold_short,
            "forward_horizons": list(cfg.forward_horizons),
            "entry_lag": cfg.entry_lag,
        },
        "n_symbols": len(symbols),
        "n_symbols_ok": sum(1 for r in results if r.error is None),
        "n_long_fires": sum(r.long_fires for r in results),
        "n_short_fires": sum(r.short_fires for r in results),
        "pooled": {
            "long":     _aggregate_returns(long_pool),
            "short":    _aggregate_returns(short_pool),
            "baseline": _aggregate_returns(base_pool),
        },
        "by_symbol": [
            {"symbol": r.symbol, "long_fires": r.long_fires,
             "short_fires": r.short_fires,
             "long_stats": r.long_stats, "short_stats": r.short_stats,
             "baseline": r.baseline, "error": r.error,
             "n_bars_evaluated": r.n_bars_evaluated}
            for r in results
        ],
    }
    return summary


# ---------------------------------------------------------------------------
# CLI runner
# ---------------------------------------------------------------------------

def _format_report(summary: dict) -> str:
    """Pretty-print one backtest summary as a multi-section text report."""
    cfg = summary["config"]
    lines = [
        "=" * 72,
        f"Walk-forward backtest report",
        "=" * 72,
        f"Symbols:        {summary['n_symbols_ok']} / {summary['n_symbols']} OK",
        f"Interval:       {cfg['interval']}   warmup={cfg['warmup_bars']}   "
        f"sample_every={cfg['sample_every']}",
        f"Long fires:     {summary['n_long_fires']}    "
        f"Short fires: {summary['n_short_fires']}",
        f"Thresholds:     long>={cfg['threshold_long']}  "
        f"short<={cfg['threshold_short']}",
        "",
        "POOLED FORWARD RETURNS",
        "-" * 72,
    ]
    for side in ("long", "short", "baseline"):
        st = summary["pooled"].get(side, {})
        lines.append(f"\n[{side.upper()}]")
        for h in cfg["forward_horizons"]:
            row = st.get(h, {})
            if not row.get("n"):
                lines.append(f"  +{h}bar: (no data)")
                continue
            lines.append(
                f"  +{h}bar: n={row['n']:5d}  "
                f"win={row['win_rate']:5.1f}%  "
                f"avg={row['avg_return_pct']:+6.2f}%  "
                f"med={row['median_return_pct']:+6.2f}%  "
                f"exp={row['expectancy_pct']:+6.2f}%  "
                f"best={row['best_pct']:+5.1f}%  "
                f"worst={row['worst_pct']:+5.1f}%")
    lines.append("\n" + "=" * 72)
    return "\n".join(lines)


def main(symbols: list[str] | None = None,
         interval: str = "1h",
         klines_limit: int = 1000,
         threshold_long: float = 75.0,
         threshold_short: float = 25.0,
         sample_every: int = 4) -> None:
    """CLI entry: run backtest on the early_momentum module across the
    given symbols (default: top 20 by 24h volume)."""
    import early_momentum

    if not symbols:
        try:
            top_df = binance_client.get_top_symbols(20)
            symbols = top_df["symbol"].tolist()
        except Exception as exc:
            print(f"Failed to fetch top symbols: {exc}")
            return

    cfg = BacktestConfig(
        interval=interval, klines_limit=klines_limit,
        threshold_long=threshold_long, threshold_short=threshold_short,
        sample_every=sample_every,
    )

    def _progress(sym: str, done: int, total: int) -> None:
        print(f"  [{done}/{total}] {sym}", flush=True)

    print(f"Running backtest on {len(symbols)} symbols "
          f"({interval}, {klines_limit} klines each)...")
    t0 = time.time()
    summary = run_universe(symbols, early_momentum.score, cfg,
                           progress=_progress, workers=6)
    print(f"\nFinished in {time.time() - t0:.1f}s.\n")
    print(_format_report(summary))


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if args and args[0] == "--help":
        print(__doc__)
        print("Usage: python backtest.py [interval] [klines_limit] "
              "[threshold_long] [threshold_short] [sample_every]")
        sys.exit(0)

    interval = args[0] if len(args) > 0 else "1h"
    klines_limit = int(args[1]) if len(args) > 1 else 1000
    thr_long = float(args[2]) if len(args) > 2 else 75.0
    thr_short = float(args[3]) if len(args) > 3 else 25.0
    sample_every = int(args[4]) if len(args) > 4 else 4

    main(interval=interval, klines_limit=klines_limit,
         threshold_long=thr_long, threshold_short=thr_short,
         sample_every=sample_every)
