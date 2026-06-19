"""Delayed-trigger edge test (user idea 2026-06-18).

Question: a strong ELITE setup (score>=80) often does NOT move
immediately — it can take 1-2 days to trigger. If it stays ALIVE
(neither TP1 nor SL hit in the first 24h), does it still WIN when it
finally resolves over the next few days? Or does the edge decay?

This decides whether the new "Active ELITE Setups (armed)" section is a
PROVEN board or a watch-only one.

Method (walk-forward, no lookahead, threaded like backtest_elite):
  - At each bar, score_from_data on the slice up to it (enriched).
  - Keep fires with score>=80 and a valid plan (entry/stop/tp1).
  - Resolve the plan over the next 96 bars (4 days) by the high/low path:
      IMMEDIATE  = TP1 or SL hit within the first 24 bars
      STILL-ALIVE@24h = neither hit in first 24 bars
        -> DELAYED outcome = which of TP1/SL hits first in bars 25..96
      DEAD@24h   = SL hit within 24 bars (the section would DROP these)
  - Report win rate for immediate vs delayed (the key number).
"""
from __future__ import annotations
import sys, io, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client, indicators
import experimental_signals as es

N_COINS = 15
BARS = 700
WARMUP = 200
SAMPLE = 6
SCORE_FLOOR = 80.0
IMMEDIATE_WIN = 24    # bars = 24h
FULL_WIN = 96         # bars = 4 days

def _resolve(side, entry, stop, tp1, hi, lo, t, n, a0, a1):
    """Which of tp1/stop hits first in bars [t+a0 .. t+a1]? returns
    'WIN'/'LOSS'/'NONE'."""
    for fb in range(t + a0, min(t + a1 + 1, n)):
        h = hi[fb]; l = lo[fb]
        if side == "LONG":
            hs = l <= stop; ht = h >= tp1
        else:
            hs = h >= stop; ht = l <= tp1
        if hs and ht:
            return "LOSS"     # pessimistic: stop first
        if hs:
            return "LOSS"
        if ht:
            return "WIN"
    return "NONE"

def _one(sym):
    try:
        d1 = indicators.enrich(binance_client.get_klines(sym, "1h", limit=BARS))
        d4 = indicators.enrich(binance_client.get_klines(sym, "4h", limit=300))
    except Exception:
        return []
    if d1 is None or len(d1) < WARMUP + FULL_WIN + 5:
        return []
    d4i = d4.copy()
    rows = []
    hi = d1["high"].to_numpy(); lo = d1["low"].to_numpy()
    n = len(d1)
    for t in range(WARMUP, n - FULL_WIN - 1, SAMPLE):
        s1 = d1.iloc[:t+1]; ts = s1.index[-1]
        try:
            s4 = d4i[d4i.index <= ts]
        except Exception:
            continue
        if len(s4) < 50:
            continue
        try:
            r = es.score_from_data(sym, s1, df_4h=s4, oi_hist=None,
                                   pct_24h=0.0, skip_deriv=True)
        except Exception:
            continue
        sc = float(r.get("score") or 0); side = r.get("side")
        if sc < SCORE_FLOOR or side not in ("LONG", "SHORT"):
            continue
        plan = r.get("trade_plan") or {}
        entry = float(plan.get("entry") or 0)
        stop = float(plan.get("stop") or 0); tp1 = float(plan.get("tp1") or 0)
        if entry <= 0 or stop <= 0 or tp1 <= 0:
            continue
        tier = r.get("tier")
        imm = _resolve(side, entry, stop, tp1, hi, lo, t, n, 1, IMMEDIATE_WIN)
        if imm in ("WIN", "LOSS"):
            rows.append((tier, "IMMEDIATE", imm))
        else:
            # still alive at 24h -> delayed resolution 25..96
            dly = _resolve(side, entry, stop, tp1, hi, lo, t, n,
                           IMMEDIATE_WIN + 1, FULL_WIN)
            rows.append((tier, "DELAYED", dly))
    return rows

print(f"Delayed-trigger test — top {N_COINS}, score>={SCORE_FLOOR:.0f}…")
syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]
all_rows = []
t0 = time.time()
with ThreadPoolExecutor(max_workers=6) as pool:
    futs = {pool.submit(_one, s): s for s in syms}
    for i, f in enumerate(as_completed(futs)):
        try:
            rr = f.result()
        except Exception:
            rr = []
        all_rows.extend(rr)
        print(f"  [{i+1}/{N_COINS}] {futs[f]:12} cum {len(all_rows)} "
              f"({time.time()-t0:.0f}s)", flush=True)

def wr(rows):
    res = [r for r in rows if r[2] in ("WIN", "LOSS")]
    n = len(res); w = sum(1 for r in res if r[2] == "WIN")
    return n, (w/n*100 if n else 0)

imm = [r for r in all_rows if r[1] == "IMMEDIATE"]
dly = [r for r in all_rows if r[1] == "DELAYED"]
dly_unres = sum(1 for r in dly if r[2] == "NONE")

print("\n" + "="*64)
print(f"DELAYED-TRIGGER — {len(all_rows)} strong fires (score>=80)")
print("="*64)
n_i, w_i = wr(imm)
n_d, w_d = wr(dly)
print(f"\nIMMEDIATE (resolved <=24h):  n={n_i:4}  win {w_i:.1f}%")
print(f"   share of all fires: {len(imm)/max(1,len(all_rows))*100:.0f}%")
print(f"\nSTILL-ALIVE @24h -> DELAYED (resolved 24-96h):")
print(f"   n={n_d:4}  win {w_d:.1f}%   ({dly_unres} never resolved in 4d)")
print(f"   share of all fires: {len(dly)/max(1,len(all_rows))*100:.0f}%")
print("\n--- delayed win rate by tier (does holding still win?) ---")
for tier in ("MAX", "HIGH", "STRONG", "STANDARD"):
    sub = [r for r in dly if r[0] == tier]
    nn, ww = wr(sub)
    if nn:
        print(f"   {tier:9} delayed: n={nn:4} win {ww:.1f}%")
print(f"\nDone in {time.time()-t0:.0f}s.")
