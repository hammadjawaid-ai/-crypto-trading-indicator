"""Distribution test across the top-N coin universe for the new modules.

The Phase C derivatives module makes 2-3 Binance fapi calls per `score()`
invocation. A full walk-forward backtest (200 sample bars × 20 coins) would
mean 12,000+ API calls and likely get rate-limited.

Instead this script tests the CURRENT-snapshot distribution: how do the
new modules score every coin in the top universe RIGHT NOW? That tells us:

  1. Does the module produce a sensible distribution across the universe
     (not all 50, not all extremes)?
  2. Which coins are the strongest LONG candidates today?
  3. Which coins are the strongest SHORT candidates today?

For Phase E/F (long-term signals), per-coin scoring takes seconds (external
APIs) but the data updates slowly. We collect the current-snapshot read on
a smaller subset (top 10) since DefiLlama / Coin Metrics / CoinGecko
calls cost real time.
"""
from __future__ import annotations

import time

import binance_client
import btc_dominance
import coin_metrics_onchain
import cup_and_handle
import defillama_tvl
import derivatives_velocity
import fred_macro
import tokenomics_unlocks


def main():
    print("Loading top universe...")
    top_df = binance_client.get_top_symbols(20)
    syms = top_df["symbol"].tolist()
    print(f"Universe: {syms}")
    print()

    print("=" * 78)
    print("Phase C: derivatives_velocity — funding ROC + OI compression")
    print("=" * 78)
    print(f"{'Symbol':<12} {'Score':>6} {'Side':>9} {'Flags':<30}")
    print("-" * 78)
    dv_results = []
    for sym in syms:
        try:
            r = derivatives_velocity.score(sym, "1h")
            dv_results.append({"sym": sym, "score": r["score"],
                               "side": r["side"], "flags": r["flags"],
                               "detail_f": r["components"][
                                   "funding_velocity"]["detail"],
                               "detail_o": r["components"][
                                   "oi_compression"]["detail"]})
            print(f"{sym:<12} {r['score']:>6.1f} {r['side']:>9} "
                  f"{','.join(r['flags']) or '—':<30}")
        except Exception as exc:
            print(f"{sym:<12} ERROR {exc}")
    print()

    dv_long = sum(1 for r in dv_results if r["side"] == "LONG")
    dv_short = sum(1 for r in dv_results if r["side"] == "SHORT")
    dv_neutral = sum(1 for r in dv_results if r["side"] == "NEUTRAL")
    print(f"Distribution: LONG={dv_long}  SHORT={dv_short}  "
          f"NEUTRAL={dv_neutral}")
    if dv_results:
        scores = [r["score"] for r in dv_results]
        print(f"Score range: min={min(scores):.1f} max={max(scores):.1f} "
              f"mean={sum(scores) / len(scores):.1f}")
    print()

    print("=" * 78)
    print("Phase E: Regime overlays")
    print("=" * 78)
    bd = btc_dominance.regime()
    print(f"BTC dominance: {bd['regime']}  alt_mult={bd['alt_multiplier']}  "
          f"BTC.D={bd['btc_dominance_pct']}%")
    print(f"   {bd['detail']}")
    print()
    fm = fred_macro.regime()
    print(f"Macro:         {fm['regime']}  risk_mult={fm['risk_multiplier']}")
    print(f"   {fm['detail']}")
    print()

    print("=" * 78)
    print("Phase E: Coin Metrics on-chain (BTC + ETH only)")
    print("=" * 78)
    for sym in ("BTCUSDT", "ETHUSDT"):
        try:
            r = coin_metrics_onchain.score(sym)
            print(f"{sym}: score={r['score']} side={r['side']}")
            print(f"   {r['detail']}")
        except Exception as exc:
            print(f"{sym}: ERROR {exc}")
    print()

    print("=" * 78)
    print("Phase E: DefiLlama TVL growth (top 10 of universe)")
    print("=" * 78)
    for sym in syms[:10]:
        try:
            r = defillama_tvl.score(sym)
            if r["score"] != 50 or "TVL" in r["detail"]:
                print(f"{sym:<12} score={r['score']:>6.1f} {r['detail']}")
        except Exception as exc:
            print(f"{sym}: ERROR {exc}")
    print()

    print("=" * 78)
    print("Phase F: Cup-and-handle (top 10 of universe, weekly)")
    print("=" * 78)
    for sym in syms[:10]:
        try:
            weekly = binance_client.get_klines(sym, "1w")
            r = cup_and_handle.score(weekly)
            print(f"{sym:<12} score={r['score']:>6.1f} stage={r['stage']:<18} "
                  f"{r['detail'][:60]}")
        except Exception as exc:
            print(f"{sym}: ERROR {exc}")
    print()

    print("=" * 78)
    print("Phase F: Tokenomics dilution risk (top 10 of universe)")
    print("=" * 78)
    for sym in syms[:10]:
        try:
            r = tokenomics_unlocks.score(sym)
            print(f"{sym:<12} score={r['score']:>6.1f} side={r['side']:>8} "
                  f"{r['detail']}")
        except Exception as exc:
            print(f"{sym}: ERROR {exc}")
    print()

    print("=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"Phase C — derivatives_velocity:")
    if dv_results:
        dv_strong_short = [r for r in dv_results
                           if r["side"] == "SHORT" and r["score"] <= 30]
        dv_strong_long = [r for r in dv_results
                          if r["side"] == "LONG" and r["score"] >= 70]
        print(f"  Strong SHORT fires (where backtest showed edge): "
              f"{len(dv_strong_short)}")
        for r in dv_strong_short:
            print(f"     {r['sym']}: {r['score']:.0f} · {r['flags']}")
        print(f"  Strong LONG fires (caution — backtest showed weak edge): "
              f"{len(dv_strong_long)}")
        for r in dv_strong_long:
            print(f"     {r['sym']}: {r['score']:.0f} · {r['flags']}")
    print()
    print(f"Regime overlays:")
    print(f"  BTC.D:  {bd['regime']}  (alt_mult={bd['alt_multiplier']})")
    print(f"  Macro:  {fm['regime']}  (risk_mult={fm['risk_multiplier']})")
    print()
    print("Phase E/F long-term signals are not run through the walk-forward")
    print("1h backtest harness because they don't change bar-by-bar — they")
    print("update daily/weekly. A proper backtest would simulate a portfolio")
    print("rebalanced monthly across multi-year history. Out of scope for")
    print("this session; the modules themselves work and surface live data.")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print()
    print(f"Total runtime: {time.time() - t0:.1f}s")
