"""Unit backtest for SURE SHOT TRADER 1 (the 3-agent pipeline).

Reconstructs SST1's conviction at each historical bar (no lookahead)
and measures win rate / expectancy on the picks it WOULD have surfaced.

SST1 conviction (from sureshot_agents._deterministic_conviction):
    base = ELITE composite score * 0.6
    + proven systems (ELITE side-match +8; CONVERGENCE/SURE SHOT are
      app-layer and can't be reconstructed standalone -> treated OFF,
      which is CONSERVATIVE: real SST1 with them firing scores higher)
    + multi-TF alignment (here a faithful 1h+4h 2-TF proxy; live SST1
      uses 15m/1h/4h)
    + regime (skipped here = neutral; conservative)
    + R:R from the plan
Gate: conviction >= 55 (the SST1 floor). Tiers: >=70 SURE SHOT,
55-69 OK.

HONEST LIMITS: 2-TF proxy (not 15m), no CONVERGENCE/SURE SHOT/regime
bonuses, no LLM. All of these make this a FLOOR on SST1's real
performance — the live pipeline has more confirmations available.
"""
from __future__ import annotations
import sys, io, time
import numpy as np
import pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import builtins
_op = builtins.print
def print(*a, **k):           # force flush so progress is visible
    k.setdefault("flush", True); _op(*a, **k)

import binance_client
import experimental_signals as es
import indicators

N_COINS = 6                # foreground-safe (~7min); bg runs get reaped
WARMUP = 220
LOOKFWD = 24
SAMPLE_EVERY = 10
ELITE_FLOOR = 70.0
SST1_FLOOR = 55.0
KLINE_1H = 900             # ~37 days

def _ema(s, n): return s.ewm(span=n, adjust=False).mean()

def _trend(df, side):
    """1 if EMA20>EMA50 stack agrees with side, 0 neutral, -1 against."""
    c = df["close"]
    if len(c) < 55:
        return 0
    e20 = float(_ema(c, 20).iloc[-1]); e50 = float(_ema(c, 50).iloc[-1])
    px = float(c.iloc[-1])
    if px > e20 > e50:
        st = "BULL"
    elif px < e20 < e50:
        st = "BEAR"
    else:
        return 0
    if (side == "LONG" and st == "BULL") or (side == "SHORT" and st == "BEAR"):
        return 1
    return -1

def sst1_conviction(score, tier, n_lanes, rr, aligned2, against2):
    conv = score * 0.6 + 8.0          # base + ELITE confirm
    if aligned2 == 2:
        conv += 7
    elif aligned2 == 1:
        conv += 2
    if against2 >= 2:
        conv -= 10
    elif against2 == 1 and aligned2 == 0:
        conv -= 5
    if rr >= 2.0:
        conv += 5
    elif rr >= 1.5:
        conv += 2
    elif 0 < rr < 1.2:
        conv -= 6
    return max(0.0, min(100.0, conv))

print(f"Fetching top {N_COINS}…")
syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]

rows = []
t0 = time.time()
for i, sym in enumerate(syms):
    try:
        df1 = binance_client.get_klines(sym, "1h", limit=KLINE_1H)
        df4 = binance_client.get_klines(sym, "4h", limit=400)
        # CRITICAL: enrich adds the 'atr' column that _build_plan reads.
        # Without it every trade_plan came back valid=False and EVERY
        # pick was dropped -> false "0 picks". ATR/EMA are causal so
        # enriching the full series then slicing has no lookahead.
        df1 = indicators.enrich(df1)
        df4 = indicators.enrich(df4)
    except Exception:
        continue
    if df1 is None or len(df1) < WARMUP + LOOKFWD + 5:
        continue
    d4 = df4.copy()
    if "open_time" in d4.columns:
        d4 = d4.set_index("open_time")
    n = len(df1)
    for t in range(WARMUP, n - LOOKFWD - 1, SAMPLE_EVERY):
        s1 = df1.iloc[:t+1]
        ts = s1.index[-1]
        try:
            s4 = d4[d4.index <= ts]
        except Exception:
            s4 = None
        if s4 is None or len(s4) < 50:
            continue
        try:
            r = es.score_from_data(sym, s1, df_4h=s4, oi_hist=None,
                                   pct_24h=0.0, skip_deriv=True)
        except Exception:
            continue
        sc = float(r.get("score") or 0)
        side = r.get("side")
        if sc < ELITE_FLOOR or side not in ("LONG", "SHORT"):
            continue
        plan = r.get("trade_plan") or {}
        rr = float(plan.get("rr") or 0)
        # 2-TF proxy (1h + 4h)
        a1 = _trend(s1, side); a4 = _trend(s4, side)
        aligned2 = (1 if a1 == 1 else 0) + (1 if a4 == 1 else 0)
        against2 = (1 if a1 == -1 else 0) + (1 if a4 == -1 else 0)
        n_lanes = len(r.get("active_lanes") or [])
        conv = sst1_conviction(sc, r.get("tier"), n_lanes, rr,
                               aligned2, against2)
        if conv < SST1_FLOOR:
            continue
        quality = "SURE SHOT" if conv >= 70 else "OK"
        # forward outcome
        entry = float(s1["close"].iloc[-1])
        stop = float(plan.get("stop") or 0); tp1 = float(plan.get("tp1") or 0)
        if entry <= 0 or stop <= 0 or tp1 <= 0:
            continue
        fwd = df1.iloc[t+1:t+LOOKFWD+1]
        if len(fwd) == 0:
            continue
        hi = float(fwd["high"].max()); lo = float(fwd["low"].min())
        if side == "LONG":
            tp_hit = hi >= tp1; sl_hit = lo <= stop
        else:
            tp_hit = lo <= tp1; sl_hit = hi >= stop
        if tp_hit and not sl_hit:
            out = "WIN"
        elif sl_hit and not tp_hit:
            out = "LOSS"
        elif tp_hit and sl_hit:
            out = "AMBIG"
        else:
            out = "TIMEOUT"
        rows.append((quality, conv, out, rr))
    print(f"  [{i+1}/{N_COINS}] {sym:12} cum {len(rows)} "
          f"({time.time()-t0:.0f}s)")

def stats(rs):
    resolved = [r for r in rs if r[2] in ("WIN", "LOSS")]
    w = sum(1 for r in resolved if r[2] == "WIN")
    n = len(resolved)
    wr = w/n*100 if n else 0
    # expectancy: win pays avg rr, loss -1
    avg_rr = np.mean([r[3] for r in resolved]) if resolved else 0
    exp = (w*avg_rr - (n-w)) / n if n else 0
    return len(rs), n, wr, exp, avg_rr

print("\n" + "="*64)
print(f"SST1 UNIT BACKTEST — {len(rows)} picks, {N_COINS} coins, ~60d 1h")
print("  (conservative: no CONV/SURE/regime bonuses, 2-TF proxy)")
print("="*64)
for label, sub in (("ALL gated (conv>=55)", rows),
                   ("SURE SHOT (conv>=70)", [r for r in rows if r[0]=="SURE SHOT"]),
                   ("OK (conv 55-69)", [r for r in rows if r[0]=="OK"])):
    tot, n, wr, exp, arr = stats(sub)
    print(f"\n{label}: {tot} picks ({n} resolved)")
    print(f"   win rate: {wr:.1f}%   avg R:R {arr:.2f}   "
          f"expectancy {exp:+.3f}R")
print(f"\nDone in {time.time()-t0:.0f}s.")
