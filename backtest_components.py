"""Per-component backtest — diagnose which early_momentum components
have edge, which are noise, and which are backwards.

The combined Phase B backtest showed the composite LONG signal under-
performs baseline. To know what to fix, we need to test each component
in isolation: if CVD divergence has edge but ROC accel is backwards,
the composite is contaminated. If ALL components are weak, the design
is wrong, not just the recipe.

For each of the 5 components, this script:
  1. Wraps the component's per-bar reading as a stand-alone score/side
     function that the harness can consume.
  2. Runs the walk-forward backtest.
  3. Reports forward-return stats vs the same baseline.

We can then decide which components to keep, drop, or invert.
"""
from __future__ import annotations

import time

import binance_client
import early_momentum
import indicators
from backtest import BacktestConfig, run_universe, _format_report


COMPONENTS = [
    "cvd_divergence",
    "ttm_squeeze",
    "roc_acceleration",
    "smc_sweep",
    "vwap_reclaim",
]


def make_component_scorer(component_key: str):
    """Return a score_fn that uses ONLY the named component for the
    composite — same threshold semantics, but the test is honest about
    whether that one component leads forward returns."""

    def _scorer(df):
        full = early_momentum.score(df)
        comps = full.get("components") or {}
        c = comps.get(component_key) or {}
        return {
            "score": float(c.get("score") or 50),
            "side": str(c.get("side") or "NEUTRAL"),
        }

    _scorer.__name__ = f"component_{component_key}"
    return _scorer


def main(symbols=None, interval: str = "1h", klines_limit: int = 1000,
         sample_every: int = 4):
    if not symbols:
        try:
            top_df = binance_client.get_top_symbols(20)
            symbols = top_df["symbol"].tolist()
        except Exception as exc:
            print(f"Failed to fetch top symbols: {exc}")
            return

    cfg = BacktestConfig(
        interval=interval,
        klines_limit=klines_limit,
        sample_every=sample_every,
        threshold_long=70.0,
        threshold_short=30.0,
    )

    all_summaries: dict[str, dict] = {}
    for comp in COMPONENTS:
        print()
        print("#" * 72)
        print(f"# COMPONENT: {comp}")
        print("#" * 72)
        score_fn = make_component_scorer(comp)
        t0 = time.time()
        summary = run_universe(symbols, score_fn, cfg, workers=6,
                               progress=lambda s, d, t: None)
        print(f"Done in {time.time() - t0:.1f}s")
        print(_format_report(summary))
        all_summaries[comp] = summary

    # Component comparison table
    print()
    print("=" * 72)
    print("COMPONENT COMPARISON — LONG side, 12-bar horizon")
    print("=" * 72)
    print(f"{'Component':<25} {'n':>5} {'win%':>6} {'avg':>8} "
          f"{'med':>8} {'exp':>8}")
    print("-" * 72)
    for comp, s in all_summaries.items():
        long_12 = s["pooled"]["long"].get(12, {})
        n = long_12.get("n", 0)
        win = long_12.get("win_rate", "—")
        avg = long_12.get("avg_return_pct", "—")
        med = long_12.get("median_return_pct", "—")
        exp = long_12.get("expectancy_pct", "—")
        win_str = f"{win:>5}%" if isinstance(win, (int, float)) else f"{win:>6}"
        avg_str = f"{avg:>+7.3f}%" if isinstance(avg, (int, float)) else f"{avg:>8}"
        med_str = f"{med:>+7.3f}%" if isinstance(med, (int, float)) else f"{med:>8}"
        exp_str = f"{exp:>+7.3f}%" if isinstance(exp, (int, float)) else f"{exp:>8}"
        print(f"{comp:<25} {n:>5} {win_str} {avg_str} {med_str} {exp_str}")

    print()
    print("=" * 72)
    print("COMPONENT COMPARISON — SHORT side, 12-bar horizon")
    print("=" * 72)
    print(f"{'Component':<25} {'n':>5} {'win%':>6} {'avg':>8} "
          f"{'med':>8} {'exp':>8}")
    print("-" * 72)
    for comp, s in all_summaries.items():
        short_12 = s["pooled"]["short"].get(12, {})
        n = short_12.get("n", 0)
        win = short_12.get("win_rate", "—")
        avg = short_12.get("avg_return_pct", "—")
        med = short_12.get("median_return_pct", "—")
        exp = short_12.get("expectancy_pct", "—")
        win_str = f"{win:>5}%" if isinstance(win, (int, float)) else f"{win:>6}"
        avg_str = f"{avg:>+7.3f}%" if isinstance(avg, (int, float)) else f"{avg:>8}"
        med_str = f"{med:>+7.3f}%" if isinstance(med, (int, float)) else f"{med:>8}"
        exp_str = f"{exp:>+7.3f}%" if isinstance(exp, (int, float)) else f"{exp:>8}"
        print(f"{comp:<25} {n:>5} {win_str} {avg_str} {med_str} {exp_str}")

    # Baseline reference (same for all components since universe is same)
    base = next(iter(all_summaries.values()))["pooled"]["baseline"].get(12, {})
    print()
    print(f"BASELINE (random entry, all bars) +12bar: "
          f"n={base.get('n', 0)}  win={base.get('win_rate', '—')}%  "
          f"avg={base.get('avg_return_pct', '—')}%")
    print()


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    interval = args[0] if len(args) > 0 else "1h"
    klines_limit = int(args[1]) if len(args) > 1 else 1000
    sample_every = int(args[2]) if len(args) > 2 else 4
    main(interval=interval, klines_limit=klines_limit,
         sample_every=sample_every)
