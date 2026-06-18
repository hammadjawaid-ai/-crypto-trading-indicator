"""Walk-forward validation of the Predictor (predict_next.py).

Two honest questions:
  1) DIRECTIONAL ACCURACY per horizon — when a horizon says Bullish/
     Bearish, does that timeframe's NEXT bar actually close that way?
     (Neutral calls excluded — they're not predictions.)
  2) SETUP EDGE — when build_setup() fires a LONG/SHORT (stop 1.2 /
     tp1 2.0 / tp2 3.0 ATR), does it make money after fees? Scale-out
     (book half at tp1 -> BE -> runner tp2), AFTER 0.06%/leg fees.

No lookahead: every TF slice is cut at the prediction timestamp; the
forward bar(s) are strictly after it.
"""
from __future__ import annotations
import sys, io, time
import numpy as np, pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import builtins
_op = builtins.print
def print(*a, **k):
    k.setdefault("flush", True); _op(*a, **k)

import binance_client
import predict_next as pn

N_COINS = 20
SAMPLE_EVERY = 8            # every 8h on the 1h clock
FORWARD = 48               # setup forward window (bars, 1h)
FEE_LEG = 0.0006           # 0.06%/leg (alt perp taker + slippage)
TURNOVER = 2.0
TP1_ATR, TP2_ATR, SL_ATR = 2.0, 3.0, 1.2

syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]

# per horizon: [ (predicted_up: bool, correct: bool) ]
dir_acc = {"15m": [], "1h": [], "4h": [], "1d": []}
# setups: (aligned, net_r, booked_partial)
setups = []

def _next_close_after(df, ts):
    """First close strictly after ts, and the close at/just before ts."""
    if df is None or len(df) < 2:
        return None, None
    pos = df.index.searchsorted(ts, side="right")  # first idx > ts
    if pos <= 0 or pos >= len(df):
        return None, None
    return float(df["close"].iloc[pos - 1]), float(df["close"].iloc[pos])

t0 = time.time()
for ci, sym in enumerate(syms):
    try:
        d15 = binance_client.get_klines(sym, "15m", limit=1500)
        d1 = binance_client.get_klines(sym, "1h", limit=1500)
        d4 = binance_client.get_klines(sym, "4h", limit=600)
        dd = binance_client.get_klines(sym, "1d", limit=400)
    except Exception:
        continue
    if d1 is None or len(d1) < 300:
        continue
    full = {"15m": d15, "1h": d1, "4h": d4, "1d": dd}
    n = len(d1)
    for t in range(220, n - FORWARD - 1, SAMPLE_EVERY):
        ts = d1.index[t]
        kl = {
            "15m": d15[d15.index <= ts] if d15 is not None else None,
            "1h": d1.iloc[:t + 1],
            "4h": d4[d4.index <= ts] if d4 is not None else None,
            "1d": dd[dd.index <= ts] if dd is not None else None,
        }
        pred = pn.predict(sym, klines_by_tf=kl)
        hz = pred.get("horizons", {})
        # 1) directional accuracy per horizon (next bar on that TF)
        for tf in ("15m", "1h", "4h", "1d"):
            d = hz.get(tf, {}).get("direction")
            if d not in ("Bullish", "Bearish"):
                continue
            c_at, c_next = _next_close_after(full[tf], ts)
            if c_at is None or c_at <= 0:
                continue
            up = c_next > c_at
            correct = (up and d == "Bullish") or (not up and d == "Bearish")
            dir_acc[tf].append((d == "Bullish", correct))
        # 2) setup edge (scale-out, after fees)
        setup = pn.build_setup(pred, d1.iloc[:t + 1],
                               stop_atr=SL_ATR, tp1_atr=TP1_ATR,
                               tp2_atr=TP2_ATR)
        if not setup:
            continue
        side = setup["side"]; entry = setup["entry"]
        stop = setup["stop"]; tp1 = setup["tp1"]; tp2 = setup["tp2"]
        atr_pct = setup["atr_pct"] / 100.0
        if entry <= 0 or atr_pct <= 0:
            continue
        feeR = (FEE_LEG * TURNOVER) / (SL_ATR * atr_pct)
        PART = 0.5 * (TP1_ATR / SL_ATR); RUN = 0.5 * (TP2_ATR / SL_ATR)
        fwd_h = d1["high"].to_numpy(); fwd_l = d1["low"].to_numpy()
        phase = "pre"; tp1_hit = False; res = None
        for fb in range(t + 1, min(t + FORWARD + 1, n)):
            fh, fl = fwd_h[fb], fwd_l[fb]
            if phase == "pre":
                hs = (fl <= stop) if side == "LONG" else (fh >= stop)
                ht = (fh >= tp1) if side == "LONG" else (fl <= tp1)
                if hs:
                    res = -1.0; break
                if ht:
                    tp1_hit = True; phase = "runner"
                    h2 = (fh >= tp2) if side == "LONG" else (fl <= tp2)
                    if h2:
                        res = PART + RUN; break
            else:
                hbe = (fl <= entry) if side == "LONG" else (fh >= entry)
                h2 = (fh >= tp2) if side == "LONG" else (fl <= tp2)
                if hbe:
                    res = PART; break
                if h2:
                    res = PART + RUN; break
        if res is None:
            res = PART if tp1_hit else 0.0
        setups.append((bool(setup.get("aligned")), res - feeR, tp1_hit))
    print(f"  [{ci+1}/{N_COINS}] {sym:12} "
          f"dir1h={len(dir_acc['1h'])} setups={len(setups)} "
          f"({time.time()-t0:.0f}s)")

print("\n" + "=" * 70)
print(f"PREDICTOR VALIDATION — {N_COINS} coins ({time.time()-t0:.0f}s)")
print("=" * 70)
print("\n--- DIRECTIONAL ACCURACY (next bar on each horizon's own TF) ---")
print("  (50% = coin flip; >55% = real directional information)")
for tf in ("15m", "1h", "4h", "1d"):
    rows = dir_acc[tf]
    if not rows:
        print(f"  {tf:4}: (no non-neutral calls)"); continue
    n = len(rows); acc = sum(1 for _, c in rows if c) / n * 100
    nb = sum(1 for u, _ in rows if u)
    print(f"  {tf:4}: {acc:5.1f}% correct  (n={n}, {nb} bull / {n-nb} bear)")

def setup_stats(rows):
    if not rows:
        return None
    n = len(rows); exp = sum(r[1] for r in rows) / n
    green = sum(1 for r in rows if r[2]) / n * 100
    return n, green, exp

print("\n--- SETUP EDGE (build_setup, scale-out, AFTER fees) ---")
for label, rows in (("ALL setups", setups),
                    ("ALIGNED (all horizons agree)",
                     [r for r in setups if r[0]]),
                    ("NOT aligned", [r for r in setups if not r[0]])):
    s = setup_stats(rows)
    if not s:
        print(f"  {label}: (none)"); continue
    n, green, exp = s
    print(f"  {label}: n={n}  booked-partial {green:.1f}%  "
          f"expectancy {exp:+.3f}R")
print(f"\nDone in {time.time()-t0:.0f}s.")
