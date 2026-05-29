"""Backtest recovery_detector.py - V-bottom and trend reclaim patterns.

Verifies the patterns have edge before we wire them into the picks board.
"""
from __future__ import annotations

import time

import binance_client
import recovery_detector
from backtest import BacktestConfig, run_universe, _format_report


def make_component_scorer(component_key: str):
    """Score function that uses only one component of recovery_detector."""

    def _scorer(df):
        full = recovery_detector.score(df)
        comps = full.get("components") or {}
        c = comps.get(component_key) or {}
        return {
            "score": float(c.get("score") or 50),
            "side": str(c.get("side") or "NEUTRAL"),
        }

    _scorer.__name__ = f"recovery_{component_key}"
    return _scorer


def main():
    print("Loading top 20 universe...")
    try:
        top_df = binance_client.get_top_symbols(20)
        symbols = top_df["symbol"].tolist()
    except Exception as exc:
        print(f"Failed: {exc}")
        return

    cfg = BacktestConfig(
        interval="1h",
        klines_limit=1000,
        sample_every=4,
        threshold_long=70.0,
        threshold_short=0.0,  # LONG-only
    )

    print()
    print("=" * 78)
    print("FULL recovery_detector composite (score >= 70 LONG)")
    print("=" * 78)
    t0 = time.time()
    summary = run_universe(symbols, recovery_detector.score, cfg,
                           progress=lambda s, d, t: None)
    print(f"Done in {time.time() - t0:.1f}s")
    print(_format_report(summary))

    # Per-component breakdown
    print()
    print("=" * 78)
    print("PER-PATTERN BREAKDOWN")
    print("=" * 78)
    components = ["v_bottom_bounce", "trend_reclaim", "volume_shock"]
    by_comp = {}
    for comp in components:
        print(f"\n--- {comp} ---")
        score_fn = make_component_scorer(comp)
        s = run_universe(symbols, score_fn, cfg,
                         progress=lambda sy, d, t: None)
        by_comp[comp] = s
        long_12 = s["pooled"]["long"].get(12, {})
        long_24 = s["pooled"]["long"].get(24, {})
        long_48 = s["pooled"]["long"].get(48, {})
        for h, st in [(12, long_12), (24, long_24), (48, long_48)]:
            n = st.get("n", 0)
            w = st.get("win_rate", "—")
            a = st.get("avg_return_pct", "—")
            print(f"  +{h}bar: n={n}  win={w}%  avg={a}%")

    print()
    print("=" * 78)
    print("COMPONENT COMPARISON — LONG, multiple horizons")
    print("=" * 78)
    print(f"{'Component':<22} {'h':<4} {'n':>5} {'win%':>7} {'avg':>9}")
    print("-" * 60)
    for comp, s in by_comp.items():
        for h in (12, 24, 48):
            row = s["pooled"]["long"].get(h, {})
            n = row.get("n", 0)
            w = row.get("win_rate", "—")
            a = row.get("avg_return_pct", "—")
            w_str = f"{w}%" if isinstance(w, (int, float)) else f"{w}"
            a_str = f"{a:+.3f}%" if isinstance(a, (int, float)) else f"{a}"
            print(f"{comp:<22} +{h:<3} {n:>5} {w_str:>7} {a_str:>9}")

    # Baseline
    base = next(iter(by_comp.values()))["pooled"]["baseline"]
    print()
    for h in (12, 24, 48):
        b = base.get(h, {})
        print(f"BASELINE (random) +{h}bar: n={b.get('n', 0)}  "
              f"win={b.get('win_rate', '—')}%  "
              f"avg={b.get('avg_return_pct', '—')}%")


if __name__ == "__main__":
    main()
