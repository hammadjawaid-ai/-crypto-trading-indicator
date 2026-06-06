"""Walk-forward backtest for the velocity_burst lane (Fix #3).

What it tests:
  - For each coin in the top-N universe over the last LOOKBACK_DAYS,
    walk through every 1h bar in order.
  - At each bar t, slice klines up to and including t and run
    velocity_burst.lane_velocity_burst on the slice (NO LOOKAHEAD).
  - When the lane fires (score >= floor), simulate opening a trade:
      LONG  : entry = close[t], stop = entry - 1.2*ATR,
              tp1 = entry + 2.0*ATR
      SHORT : entry = close[t], stop = entry + 1.2*ATR,
              tp1 = entry - 2.0*ATR
  - Walk forward up to FORWARD_BARS (24 = 1 day on 1h) checking the
    bar-by-bar high/low path:
      - If high crosses tp1 first  → WIN
      - If low crosses stop first  → LOSS
      - If neither hits in window  → flat (count as scratch, not loss)

What it CANNOT measure:
  - Slippage / fees / partial fills (paper-perfect execution)
  - Compounding (each trade is independent)
  - Concurrent-trade behaviour (we assume infinite capital)

Output: per-side and per-tier win rate, expectancy, total signals.
"""
from __future__ import annotations

import sys
import io
import time
from collections import defaultdict

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import binance_client
import velocity_burst

# ============================================================
# Config
# ============================================================
N_COINS = 30          # top N by 24h volume
LOOKBACK_DAYS = 90    # ~90 days = 2160 1h bars
FORWARD_BARS = 24     # window to detect TP/SL hit
ATR_PERIOD = 14
TP_MULT = 2.0
SL_MULT = 1.2
SCORE_FLOOR = 60      # what's a "real" burst signal
WARMUP_BARS = 25      # need this many bars before scoring


# ============================================================
# Universe
# ============================================================
print(f"Fetching top {N_COINS} symbols by volume...")
try:
    top_df = binance_client.get_top_symbols(N_COINS)
    universe = top_df["symbol"].tolist()[:N_COINS]
except Exception as exc:
    print(f"failed to fetch top symbols: {exc}")
    sys.exit(1)
print(f"  universe: {len(universe)} coins")


# ============================================================
# ATR helper
# ============================================================
def compute_atr(df: pd.DataFrame, n: int = ATR_PERIOD) -> pd.Series:
    high = df["high"]
    low = df["low"]
    pc = df["close"].shift(1)
    tr = pd.concat(
        [high - low, (high - pc).abs(), (low - pc).abs()],
        axis=1).max(axis=1)
    return tr.rolling(n).mean()


# ============================================================
# Walk forward
# ============================================================
all_signals = []
t_start = time.time()

# Fetch 90 days of 1h data per coin (limit 2160 == 90*24)
limit = LOOKBACK_DAYS * 24 + 50

for i, sym in enumerate(universe):
    try:
        df = binance_client.get_klines(sym, "1h", limit=limit)
    except Exception as exc:
        print(f"  [{i+1}/{N_COINS}] {sym}: fetch failed ({exc})")
        continue
    if df is None or len(df) < WARMUP_BARS + FORWARD_BARS + 50:
        continue
    df = df.reset_index(drop=True)
    df["atr"] = compute_atr(df, ATR_PERIOD)
    n_fires = 0
    # Walk: iterate bars from WARMUP_BARS to len(df) - FORWARD_BARS - 1
    # so we have enough lookback AND forward window for each test bar
    for t in range(WARMUP_BARS, len(df) - FORWARD_BARS - 1):
        slice_ = df.iloc[:t + 1]   # data up to and INCLUDING bar t
        score, side, note = velocity_burst.lane_velocity_burst(slice_)
        if score < SCORE_FLOOR or side not in ("LONG", "SHORT"):
            continue
        # Simulate trade open at close of bar t, stop / tp at fixed ATR
        entry = float(slice_["close"].iloc[-1])
        atr = float(df["atr"].iloc[t])
        if not (np.isfinite(atr) and atr > 0):
            continue
        if side == "LONG":
            stop = entry - SL_MULT * atr
            tp1 = entry + TP_MULT * atr
        else:
            stop = entry + SL_MULT * atr
            tp1 = entry - TP_MULT * atr
        # Look forward up to FORWARD_BARS for hit
        outcome = "flat"
        bars_to_outcome = FORWARD_BARS
        for fb in range(1, FORWARD_BARS + 1):
            future = df.iloc[t + fb]
            hi = float(future["high"])
            lo = float(future["low"])
            if side == "LONG":
                hit_tp = hi >= tp1
                hit_sl = lo <= stop
            else:
                hit_tp = lo <= tp1
                hit_sl = hi >= stop
            # Pessimistic: if both hit in same bar, assume SL hit first
            # (conservative — only matters in highly volatile bars)
            if hit_sl:
                outcome = "loss"
                bars_to_outcome = fb
                break
            elif hit_tp:
                outcome = "win"
                bars_to_outcome = fb
                break
        all_signals.append({
            "symbol": sym,
            "bar": t,
            "side": side,
            "score": score,
            "entry": entry,
            "atr": atr,
            "outcome": outcome,
            "bars_to_outcome": bars_to_outcome,
            "note": note,
        })
        n_fires += 1
    elapsed = time.time() - t_start
    print(f"  [{i+1:>2}/{N_COINS}] {sym:<12} {n_fires:>3} fires  "
          f"({elapsed:.0f}s elapsed)")


# ============================================================
# Report
# ============================================================
print()
print("=" * 75)
print(f"VELOCITY BURST WALK-FORWARD RESULTS")
print(f"  coins: {N_COINS}  lookback: {LOOKBACK_DAYS}d  "
      f"forward: {FORWARD_BARS}h  TP {TP_MULT}xATR  SL {SL_MULT}xATR")
print("=" * 75)

if not all_signals:
    print("NO SIGNALS — the lane is silent on this universe / window.")
    print("This usually means thresholds (3x vol + 2.5x ATR) are too "
          "strict for the volatility in this period. Consider lowering.")
    sys.exit(0)

total = len(all_signals)
wins = sum(1 for s in all_signals if s["outcome"] == "win")
losses = sum(1 for s in all_signals if s["outcome"] == "loss")
flats = sum(1 for s in all_signals if s["outcome"] == "flat")
non_flat = wins + losses
wr_total = (wins / non_flat * 100) if non_flat > 0 else 0
wr_with_flat = (wins / total * 100)

print(f"  Total signals     : {total}")
print(f"  Wins              : {wins} ({wr_with_flat:.1f}% of all,"
      f" {wr_total:.1f}% of resolved)")
print(f"  Losses            : {losses}")
print(f"  Flat (no hit)     : {flats}")
print()

# Expectancy — assuming R = 1 (each trade risks 1 unit):
#   win = +TP_MULT/SL_MULT  =  2.0 / 1.2 = +1.67R
#   loss = -1R
#   flat = 0R
r_win = TP_MULT / SL_MULT
expectancy = (wins * r_win - losses * 1.0) / total if total > 0 else 0
print(f"  R-per-win         : +{r_win:.2f}R")
print(f"  Expectancy        : {expectancy:+.3f}R per signal")
if expectancy > 0:
    print(f"  VERDICT           : POSITIVE EDGE - lane is profitable")
else:
    print(f"  VERDICT           : NEGATIVE EDGE - lane needs tuning")
print()

# Per-side breakdown
print("BY SIDE:")
for side in ("LONG", "SHORT"):
    sub = [s for s in all_signals if s["side"] == side]
    if not sub:
        continue
    w = sum(1 for s in sub if s["outcome"] == "win")
    l = sum(1 for s in sub if s["outcome"] == "loss")
    f = sum(1 for s in sub if s["outcome"] == "flat")
    n = w + l
    wr = (w / n * 100) if n > 0 else 0
    exp = (w * r_win - l * 1.0) / len(sub) if len(sub) > 0 else 0
    print(f"  {side:5}  total={len(sub):>4}  wins={w:>3}  losses={l:>3}  "
          f"flat={f:>3}  wr={wr:>5.1f}%  exp={exp:+.3f}R")

# Per-score-bucket breakdown
print()
print("BY SCORE BUCKET (where the edge is):")
buckets = [(60, 70), (70, 80), (80, 90), (90, 101)]
for lo, hi in buckets:
    sub = [s for s in all_signals
           if lo <= s["score"] < hi]
    if not sub:
        continue
    w = sum(1 for s in sub if s["outcome"] == "win")
    l = sum(1 for s in sub if s["outcome"] == "loss")
    n = w + l
    wr = (w / n * 100) if n > 0 else 0
    exp = (w * r_win - l * 1.0) / len(sub) if len(sub) > 0 else 0
    print(f"  {lo}-{hi-1:>2}   total={len(sub):>4}  wins={w:>3}  "
          f"losses={l:>3}  wr={wr:>5.1f}%  exp={exp:+.3f}R")

print()
print("=" * 75)
print(f"  Done in {time.time() - t_start:.0f}s.")
