"""Backtest the new long_patterns.py module against the same universe.

Compares forward returns of LONG fires (score >= 70) vs baseline.
Also runs per-component to identify which patterns have edge.
"""
from __future__ import annotations

import time

import binance_client
import long_patterns
from backtest import BacktestConfig, run_universe, _format_report


def make_component_scorer(component_key: str):
    """Score function that uses only one component of long_patterns."""

    def _scorer(df):
        full = long_patterns.score(df)
        comps = full.get("components") or {}
        c = comps.get(component_key) or {}
        return {
            "score": float(c.get("score") or 50),
            "side": str(c.get("side") or "NEUTRAL"),
        }

    _scorer.__name__ = f"long_{component_key}"
    return _scorer


def main():
    print("Loading top 20 universe...")
    try:
        top_df = binance_client.get_top_symbols(20)
        symbols = top_df["symbol"].tolist()
    except Exception as exc:
        print(f"Failed to fetch top symbols: {exc}")
        return

    cfg = BacktestConfig(
        interval="1h",
        klines_limit=1000,
        sample_every=4,
        # LONG-only test — set short threshold so low nothing fires
        threshold_long=70.0,
        threshold_short=0.0,
    )

    print()
    print("=" * 78)
    print("FULL long_patterns composite (score >= 70 LONG)")
    print("=" * 78)
    t0 = time.time()
    summary = run_universe(symbols, long_patterns.score, cfg,
                           progress=lambda s, d, t: None)
    print(f"Done in {time.time() - t0:.1f}s")
    print(_format_report(summary))

    # Per-component breakdown
    print()
    print("=" * 78)
    print("PER-COMPONENT BREAKDOWN")
    print("=" * 78)
    components = ["rsi_div", "reclaim", "hl_struct", "engulfing"]
    by_comp = {}
    for comp in components:
        print(f"\n--- {comp} ---")
        score_fn = make_component_scorer(comp)
        s = run_universe(symbols, score_fn, cfg,
                         progress=lambda sy, d, t: None)
        by_comp[comp] = s
        long_12 = s["pooled"]["long"].get(12, {})
        n = long_12.get("n", 0)
        win = long_12.get("win_rate", "—")
        avg = long_12.get("avg_return_pct", "—")
        print(f"  +12bar LONG: n={n}  win={win}%  avg={avg}%")

    print()
    print("=" * 78)
    print("COMPONENT COMPARISON — LONG +12bar")
    print("=" * 78)
    print(f"{'Component':<22} {'n':>5} {'win%':>7} {'avg':>9}")
    print("-" * 60)
    for comp, s in by_comp.items():
        l12 = s["pooled"]["long"].get(12, {})
        n = l12.get("n", 0)
        w = l12.get("win_rate", "—")
        a = l12.get("avg_return_pct", "—")
        w_str = f"{w}%" if isinstance(w, (int, float)) else f"{w}"
        a_str = f"{a:+.3f}%" if isinstance(a, (int, float)) else f"{a}"
        print(f"{comp:<22} {n:>5} {w_str:>7} {a_str:>9}")

    # Baseline
    base = next(iter(by_comp.values()))["pooled"]["baseline"].get(12, {})
    print()
    print(f"BASELINE (random) +12bar: n={base.get('n', 0)}  "
          f"win={base.get('win_rate', '—')}%  "
          f"avg={base.get('avg_return_pct', '—')}%")


if __name__ == "__main__":
    main()
