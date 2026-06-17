"""Walk-forward backtest for the 15m GRIND detector (staircase moves).

Same methodology as backtest_early_burst: no lookahead, vectorized,
captures max-favorable-excursion so we can sweep TP, split by
freshness x 1h-alignment. Tests whether catching grind-up moves on
15m has any real edge.
"""
from __future__ import annotations
import sys, io, time
import numpy as np
import pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client

N_COINS = 25
LIMIT = 2880          # ~30 days of 15m
FORWARD = 32          # 8h
SL_MULT = 1.2
NET_MIN = 2.5         # grind: net move over last 8 bars
GREEN_MIN = 5

print(f"Fetching top {N_COINS}…")
syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]

def atr_series(df, n=20):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

sigs = []
t0 = time.time()
for idx, sym in enumerate(syms):
    try:
        df = binance_client.get_klines(sym, "15m", limit=LIMIT)
    except Exception:
        continue
    if df is None or len(df) < 300:
        continue
    df = df.reset_index(drop=True)
    close, high, low = df["close"], df["high"], df["low"]
    atr = atr_series(df)
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema80 = close.ewm(span=80, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()
    green = (close > close.shift(1)).astype(int)
    n = len(df)
    for t in range(210, n - FORWARD - 1):
        a = float(atr.iloc[t] or 0)
        if a <= 0:
            continue
        # NEW grind def (matches velocity_burst.detect_grind):
        # 7-candle 15m window, >=4 directional, net >= 1.5%, > EMA20.
        c_now = float(close.iloc[t]); c_w = float(close.iloc[t-7])
        if c_w <= 0:
            continue
        net = (c_now / c_w - 1) * 100
        greens = int(green.iloc[t-6:t+1].sum())   # last 7 candles
        reds = 7 - greens
        e20 = float(ema20.iloc[t])
        if net >= 1.5 and greens >= 4 and c_now > e20:
            side = "LONG"; dir_count = greens
        elif net <= -1.5 and reds >= 4 and c_now < e20:
            side = "SHORT"; dir_count = reds
        else:
            continue
        # strength score (matches detect_grind._strength)
        _up = close.diff().clip(lower=0).rolling(14).mean()
        _dn = (-close.diff().clip(upper=0)).rolling(14).mean().replace(0, np.nan)
        rsi = float((100 - 100/(1 + _up/_dn)).iloc[t] or 50)
        rsi_edge = max(0, rsi-50) if side == "LONG" else max(0, 50-rsi)
        strength = min(98.0, 45 + (dir_count-4)*6
                       + min(20, abs(net)*4) + min(12, rsi_edge*0.4))
        # 1h-equiv candle direction (every-4th 15m close, last 6) + trend
        h1_dir = 0
        for k in range(1, 7):
            a_i, b_i = t-4*(k-1), t-4*k
            if b_i < 0:
                break
            up = float(close.iloc[a_i]) > float(close.iloc[b_i])
            if (side == "LONG" and up) or (side == "SHORT" and not up):
                h1_dir += 1
        e80 = float(ema80.iloc[t])
        trend_ok = ((side == "LONG" and c_now > e80)
                    or (side == "SHORT" and c_now < e80))
        aligned = trend_ok and h1_dir >= 4
        validated_new = (strength >= 70 and aligned)
        fresh = "validated" if validated_new else "firing"
        # stash strength + aligned for bucket analysis
        _str_bucket = strength
        # SCALE-OUT simulation: half off at TP1 (+1.0 ATR), then move
        # stop to breakeven and let the runner go to TP2 (+2.5 ATR).
        # R unit = 1.2-ATR initial risk. Half-position each leg:
        #   full stop before TP1        -> -1.0R
        #   TP1 hit, runner stops at BE -> +0.417R (kept the partial)
        #   TP1 hit, runner hits TP2    -> +1.458R
        entry = c_now
        stop = entry - SL_MULT*a if side == "LONG" else entry + SL_MULT*a
        tp1 = entry + 1.0*a if side == "LONG" else entry - 1.0*a
        tp2 = entry + 2.5*a if side == "LONG" else entry - 2.5*a
        PART = 0.5*(1.0/SL_MULT)      # +0.417R booked at TP1 (half)
        RUN = 0.5*(2.5/SL_MULT)       # +1.042R if runner hits TP2
        phase = "pre"; tp1_hit = False; res = None
        for fb in range(1, FORWARD+1):
            fh = float(high.iloc[t+fb]); fl = float(low.iloc[t+fb])
            if phase == "pre":
                hit_stop = (fl <= stop) if side == "LONG" else (fh >= stop)
                hit_tp1 = (fh >= tp1) if side == "LONG" else (fl <= tp1)
                if hit_stop:            # pessimistic: stop first
                    res = -1.0; break
                if hit_tp1:
                    tp1_hit = True; phase = "runner"
                    hit_tp2 = (fh >= tp2) if side == "LONG" else (fl <= tp2)
                    if hit_tp2:
                        res = PART + RUN; break
            else:  # runner, stop at breakeven
                hit_be = (fl <= entry) if side == "LONG" else (fh >= entry)
                hit_tp2 = (fh >= tp2) if side == "LONG" else (fl <= tp2)
                if hit_be:
                    res = PART; break
                if hit_tp2:
                    res = PART + RUN; break
        if res is None:
            res = PART if tp1_hit else 0.0
        sigs.append((side, fresh, aligned, res, tp1_hit, _str_bucket))
    print(f"  [{idx+1}/{N_COINS}] {sym:12} cum {len(sigs)} "
          f"({time.time()-t0:.0f}s)")

# rows: (side, fresh, aligned, res_R, tp1_hit)
def scaleout(rows):
    if not rows:
        return 0, 0.0, 0.0
    n = len(rows)
    green = sum(1 for r in rows if r[4]) / n * 100      # booked partial
    exp = sum(r[3] for r in rows) / n
    full_win = sum(1 for r in rows if r[3] > 0.5) / n * 100  # runner ran
    return green, exp, full_win

def report(label, rows):
    if not rows:
        print(f"\n{label}: (none)"); return
    g, e, fw = scaleout(rows)
    print(f"\n{label} (n={len(rows)}):")
    print(f"   GREEN rate (booked +1ATR partial): {g:5.1f}%")
    print(f"   runner-to-TP2 rate:               {fw:5.1f}%")
    print(f"   expectancy:                        {e:+.3f}R")

print("\n" + "="*64)
print(f"15m GRIND (NEW DEF) SCALE-OUT — {len(sigs)} sigs, "
      f"{N_COINS} coins, ~30d")
print("  4/7 15m candles + net>=1.5% + >EMA20; 1h: 4/6 candles + trend")
print("  half off +1.0ATR -> stop to breakeven -> runner +2.5ATR")
print("="*64)
report("ALL fired (any strength/1h)", sigs)
print("\n--- 1h-CONFIRMED, by strength bucket ---")
_al = [r for r in sigs if r[2]]   # 1h-aligned only
report("  strength 70-79 + 1h", [r for r in _al if 70 <= r[5] < 80])
report("  strength 80-89 + 1h", [r for r in _al if 80 <= r[5] < 90])
report("  strength 90+   + 1h", [r for r in _al if r[5] >= 90])
report("  strength 80+   + 1h (candidate board)",
       [r for r in _al if r[5] >= 80])
print(f"\nDone in {time.time()-t0:.0f}s.")
