"""Coiled-spring BREAKOUT detector validation (user idea 2026-06-27):
PORTAL coiled for 26h then sliced ~20% in minutes. Can we measurably flag the
RELEASE as it starts and call "take it now — big one"?

Trigger ("BREAKING NOW") at bar t:
  - range break: close breaks the prior RANGE_LB-bar low (short) / high (long)
  - volume explosion: vol > VOL_MULT x 20-bar avg
  - volatility expansion: true range > ATR_EXP x ATR14
  - strong body: |close-open| > BODY_FRAC x (high-low), in the break direction
Optional precondition ("was it coiled?"): the 20-bar range ratio just before
the break sits in the bottom COMP_PCTILE percentile of the last 100 bars.

For each trigger we enter at the breakout close and measure, over the next K
bars: MFE (max favourable move), MAE (max adverse move), and a TP-before-SL
outcome at TP_PCT / SL_PCT. A real "take it now" edge = TP-before-SL win rate
clearly >50% at this R:R AND MFE meaningfully bigger than MAE. We also split
compressed vs not, to see if the coil actually matters. Cooldown of K bars
after each trigger so one move isn't counted many times.

Threaded; pure OHLCV math (fast). Env: BRK_TF (default 15m).
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
K = 8                 # forward bars measured (2h on 15m)
VOL_MULT = 2.0
BODY_FRAC = 0.55
ATR_EXP = 1.7
RANGE_LB = 20
COMP_PCTILE = 35.0
TP_PCT = 0.03
SL_PCT = 0.015


def _atr(h, l, c, n=14):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(n).mean().to_numpy(), tr


def _one(sym):
    try:
        df = binance_client.get_klines(sym, TF, limit=LIMIT)
    except Exception:
        return []
    if df is None or len(df) < 150:
        return []
    o = df["open"].to_numpy(); h = df["high"].to_numpy()
    l = df["low"].to_numpy(); c = df["close"].to_numpy()
    v = df["volume"].to_numpy()
    a, tr = _atr(h, l, c, 14)
    vma = pd.Series(v).rolling(20).mean().to_numpy()
    rng = (h - l) / np.where(c > 0, c, 1)
    n = len(df); rows = []
    t = 100
    while t < n - K - 1:
        atr_t = a[t]
        if not (atr_t > 0 and vma[t] > 0):
            t += 1; continue
        prior_low = float(np.min(l[t-RANGE_LB:t]))
        prior_high = float(np.max(h[t-RANGE_LB:t]))
        vol_ok = v[t] > VOL_MULT * vma[t]
        expand = tr[t] > ATR_EXP * atr_t
        body = abs(c[t] - o[t]) > BODY_FRAC * max(h[t] - l[t], 1e-12)
        down = (c[t] < prior_low and c[t] < o[t] and body and vol_ok and expand)
        up = (c[t] > prior_high and c[t] > o[t] and body and vol_ok and expand)
        if not (down or up):
            t += 1; continue
        comp_now = float(np.mean(rng[t-RANGE_LB:t]))
        comp_thr = float(np.percentile(rng[t-100:t], COMP_PCTILE))
        compressed = comp_now <= comp_thr
        side = "SHORT" if down else "LONG"
        entry = c[t]
        fh = h[t+1:t+1+K]; fl = l[t+1:t+1+K]
        if side == "SHORT":
            mfe = (entry - float(np.min(fl))) / entry
            mae = (float(np.max(fh)) - entry) / entry
            tp, sl = entry * (1 - TP_PCT), entry * (1 + SL_PCT)
            out = "NONE"
            for i in range(t+1, t+1+K):
                if h[i] >= sl:
                    out = "LOSS"; break
                if l[i] <= tp:
                    out = "WIN"; break
        else:
            mfe = (float(np.max(fh)) - entry) / entry
            mae = (entry - float(np.min(fl))) / entry
            tp, sl = entry * (1 + TP_PCT), entry * (1 - SL_PCT)
            out = "NONE"
            for i in range(t+1, t+1+K):
                if l[i] <= sl:
                    out = "LOSS"; break
                if h[i] >= tp:
                    out = "WIN"; break
        rows.append((side, bool(compressed), mfe * 100, mae * 100, out))
        t += K   # cooldown: skip the move we just measured
    return rows


def _wr(rs):
    res = [r for r in rs if r[4] in ("WIN", "LOSS")]
    w = sum(1 for r in res if r[4] == "WIN")
    return len(res), (w / len(res) * 100 if res else 0.0)


def _med(x):
    return statistics.median(x) if x else 0.0


syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]
print(f"Breakout backtest — {TF}, {len(syms)} coins, "
      f"TP {TP_PCT*100:.1f}% / SL {SL_PCT*100:.1f}% over {K} bars")
t0 = time.time()
rows = []
with ThreadPoolExecutor(max_workers=8) as pool:
    futs = {pool.submit(_one, s): s for s in syms}
    for fut in as_completed(futs):
        try:
            rows.extend(fut.result() or [])
        except Exception:
            pass

print(f"\nTriggers: {len(rows)}  ({time.time()-t0:.0f}s)")
print("=" * 64)


def report(label, rs):
    if not rs:
        print(f"{label:22} | n=0")
        return
    n, wr = _wr(rs)
    mfe = [r[2] for r in rs]
    mae = [r[3] for r in rs]
    print(f"{label:22} | trig {len(rs):4} | TP-1st {n:4} @ {wr:5.1f}% | "
          f"MFE med {_med(mfe):5.2f}% avg {sum(mfe)/len(mfe):5.2f}% | "
          f"MAE med {_med(mae):5.2f}%")


report("ALL", rows)
report("compressed (coiled)", [r for r in rows if r[1]])
report("not compressed", [r for r in rows if not r[1]])
report("SHORT breaks", [r for r in rows if r[0] == "SHORT"])
report("LONG breaks", [r for r in rows if r[0] == "LONG"])
report("SHORT + coiled", [r for r in rows if r[0] == "SHORT" and r[1]])
report("LONG + coiled", [r for r in rows if r[0] == "LONG" and r[1]])
print("=" * 64)
print("Edge if: TP-1st >55% (beats 2:1 breakeven 33%) AND MFE >> MAE.")
print(f"Done in {time.time()-t0:.0f}s.")
