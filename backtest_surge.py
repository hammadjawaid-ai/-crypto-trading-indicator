"""📡 SURGE RADAR validation — the user's intuition, tested.

Hypothesis (user 2026-07-26, LPT case): a FRESH pump — +5..14% off an
8-bar low within the last 2h, run volume >= 2.5x pre-run average,
price above EMA20(15m) — continues, so entering LONG with the stop at
the surge low (capped 2xATR) and TP1 at +1R is profitable after fees.

Walk-forward on 15m deep history (~40 days), Bybit taker fees, exact
same detection code path as surge_radar.py. BASELINE: same construct
every 96th bar (daily), same coins. Outcome: TP1-before-SL within 96
bars (24h), else close-at-end. Time-split halves + per-coin spread in
the report.

HONEST CAVEAT: the universe is TODAY'S top-N by volume — coins that
pumped and died may have fallen out of it (survivorship tilts the
result kindly). Read the number as an upper bound.
Checkpointed .surge_rows.jsonl (SG_N / SG_MAX_NEW).
"""
from __future__ import annotations
import io
import json
import os
import sys
import time

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import binance_client
import deep_history

N_COINS = int(os.environ.get("SG_N", "80"))
MAX_NEW = int(os.environ.get("SG_MAX_NEW", "80"))
BARS = 4000                # 15m bars ≈ 41 days
FEE = 0.00055
RUN_MIN, RUN_MAX = 0.05, 0.14
FRESH_BARS = 8
VOL_MULT = 2.5
HOLD = 96                  # 24h in 15m bars
ROWS_FILE = ".surge_rows.jsonl"


def _one(sym):
    try:
        d = deep_history.get_klines_deep(sym, "15m", bars=BARS)
    except Exception:
        return []
    if d is None or len(d) < 600:
        return []
    h = d["high"].to_numpy(); l = d["low"].to_numpy()
    c = d["close"].to_numpy(); v = d["volume"].to_numpy()
    ema20 = d["close"].ewm(span=20, adjust=False).mean().to_numpy()
    tr = np.maximum(h[1:] - l[1:],
                    np.maximum(np.abs(h[1:] - c[:-1]),
                               np.abs(l[1:] - c[:-1])))
    atr = pd.Series(tr).rolling(14).mean().to_numpy()
    n = len(d)
    rows = []
    last_fire = -999
    for i in range(60, n - HOLD - 2):
        px = float(c[i])

        def _outcome(stop):
            risk = px - stop
            if risk <= 0:
                return None
            fee_r = 2 * FEE * px / risk
            tp1 = px + risk
            for j in range(i + 1, min(i + 1 + HOLD, n)):
                if l[j] <= stop:
                    return -1.0 - fee_r
                if h[j] >= tp1:
                    return 1.0 - fee_r
            return (float(c[min(i + HOLD, n - 1)]) - px) / risk - fee_r

        # baseline — every 96th bar, generic 2xATR stop
        if i % 96 == 0 and np.isfinite(atr[i - 1]) and atr[i - 1] > 0:
            net = _outcome(px - 2 * float(atr[i - 1]))
            if net is not None:
                rows.append({"sym": sym, "test": "BASE", "net": net,
                             "t": str(d.index[i])})
        # surge detection — identical to surge_radar.scan
        look = l[i - FRESH_BARS:i + 1]
        lo_rel = int(np.argmin(look))
        lo = float(look[lo_rel])
        lo_i = i - FRESH_BARS + lo_rel
        if lo <= 0 or px <= ema20[i]:
            continue
        run = px / lo - 1.0
        if not (RUN_MIN <= run <= RUN_MAX):
            continue
        pre = v[max(0, lo_i - 16):lo_i]
        if len(pre) < 6 or float(np.mean(pre)) <= 0:
            continue
        if float(np.mean(v[lo_i:i + 1])) < VOL_MULT * float(np.mean(pre)):
            continue
        if i - last_fire < 8:
            continue                     # one fire per surge, not per bar
        last_fire = i
        _a = float(atr[i - 1]) if np.isfinite(atr[i - 1]) else 0.0
        stop = max(lo, px - 2 * _a) if _a > 0 else lo
        net = _outcome(stop)
        if net is None:
            continue
        rows.append({"sym": sym, "test": "SURGE", "net": net,
                     "run": round(run * 100, 1), "t": str(d.index[i])})
    return rows


def _load():
    rows, done = [], set()
    if not os.path.exists(ROWS_FILE):
        return rows, done
    for ln in open(ROWS_FILE, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        ob = json.loads(ln)
        if "done_coin" in ob:
            done.add(ob["done_coin"])
        else:
            rows.append(ob)
    return rows, done


def _append(sym, rs):
    with open(ROWS_FILE, "a", encoding="utf-8") as f:
        for rec in rs:
            f.write(json.dumps(rec) + "\n")
        f.write(json.dumps({"done_coin": sym}) + "\n")


def _report(rows, done_n):
    print("\n" + "=" * 72)
    tag = "COMPLETE" if done_n >= N_COINS else f"PARTIAL {done_n}/{N_COINS}"
    print(f"📡 SURGE VALIDATION [{tag}] — {len(rows)} rows · 15m · "
          f"~41d · fees in · survivorship caveat applies")
    print("=" * 72)
    df = pd.DataFrame(rows)
    if df.empty:
        print("no rows")
        return
    for test in ("BASE", "SURGE"):
        seg = df[df.test == test]
        if not len(seg):
            continue
        w = (seg.net > 0).mean() * 100
        print(f"  {test:6} n={len(seg):5} win {w:5.1f}% "
              f"exp {seg.net.mean():+.3f}R")
    sg = df[df.test == "SURGE"].copy()
    if len(sg) > 40:
        sg["t"] = pd.to_datetime(sg["t"], utc=True)
        mid = sg["t"].median()
        for lbl, s in (("H1", sg[sg.t <= mid]), ("H2", sg[sg.t > mid])):
            print(f"    {lbl}: n={len(s):4} win "
                  f"{(s.net > 0).mean() * 100:5.1f}% "
                  f"exp {s.net.mean():+.3f}R")
        pc = sg.groupby("sym")["net"].agg(["count", "mean"])
        pc = pc[pc["count"] >= 3]
        print(f"    coins n>=3: {len(pc)} · positive-exp: "
              f"{(pc['mean'] > 0).sum()}")
    print("=" * 72)


if __name__ == "__main__":
    syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]
    rows, done = _load()
    todo = [s for s in syms if s not in done][:MAX_NEW]
    print(f"Resume: {len(done)} done ({len(rows)} rows). Run: {todo}")
    t0 = time.time()
    for s in todo:
        try:
            rs = _one(s)
        except Exception as exc:
            print(f"  {s}: ERROR {exc}", flush=True)
            rs = []
        _append(s, rs)
        rows.extend(rs)
        print(f"  done {s:12} +{len(rs):4} (cum {len(rows)}, "
              f"{time.time() - t0:.0f}s)", flush=True)
    _report(rows, len(done) + len(todo))
    print(f"Done in {time.time() - t0:.0f}s.")
