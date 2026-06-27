"""Does COMPRESSION predict a forthcoming big move (any direction)?

Not about entry/direction — just: after a 'coiled' bar (tight 20-bar range vs
its last 100), is the forward K-bar range bigger than after a non-coiled bar?
If coiled bars are meaningfully more likely to be followed by a big swing, a
'🧨 COILED — move likely soon' heads-up on an alive setup is honest. If not,
the coil is noise and we say so.

Reports median forward range and P(forward range >= BIG%) for coiled vs not.
"""
from __future__ import annotations
import sys, io, time, os, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client

N_COINS = 50
TF = os.environ.get("BRK_TF", "15m")
LIMIT = 1000
K = 8
RANGE_LB = 20
COMP_PCTILE = 35.0
BIG = 5.0   # "big move" = forward K-bar range >= 5%


def _one(sym):
    try:
        df = binance_client.get_klines(sym, TF, limit=LIMIT)
    except Exception:
        return []
    if df is None or len(df) < 150:
        return []
    h = df["high"].to_numpy(); l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    rng = (h - l) / np.where(c > 0, c, 1)
    n = len(df); rows = []
    for t in range(100, n - K - 1):
        if c[t] <= 0:
            continue
        comp_now = float(np.mean(rng[t-RANGE_LB:t]))
        comp_thr = float(np.percentile(rng[t-100:t], COMP_PCTILE))
        compressed = comp_now <= comp_thr
        fwd = (float(np.max(h[t+1:t+1+K])) - float(np.min(l[t+1:t+1+K]))) / c[t]
        rows.append((bool(compressed), fwd * 100))
    return rows


syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]
print(f"Coil -> forward {K}-bar volatility — {TF}, {len(syms)} coins")
t0 = time.time()
rows = []
with ThreadPoolExecutor(max_workers=8) as pool:
    futs = {pool.submit(_one, s): s for s in syms}
    for fut in as_completed(futs):
        try:
            rows.extend(fut.result() or [])
        except Exception:
            pass


def stat(label, rs):
    if not rs:
        print(f"{label:18} | n=0")
        return
    fwd = [r[1] for r in rs]
    big = sum(1 for x in fwd if x >= BIG) / len(fwd) * 100
    print(f"{label:18} | n={len(rs):6} | fwd range med "
          f"{statistics.median(fwd):5.2f}% avg {sum(fwd)/len(fwd):5.2f}% | "
          f"P(>= {BIG:.0f}%) = {big:5.1f}%")


print(f"\nSamples: {len(rows)}  ({time.time()-t0:.0f}s)")
print("=" * 70)
stat("ALL bars", rows)
stat("COILED bars", [r for r in rows if r[0]])
stat("not coiled", [r for r in rows if not r[0]])
print("=" * 70)
print("Heads-up is honest only if COILED clearly beats 'not coiled' on "
      "P(big move).")
print(f"Done in {time.time()-t0:.0f}s.")
