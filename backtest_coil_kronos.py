"""🌋 COIL + KRONOS PRE-BURST VALIDATION — can the model smell the move?

User 2026-08-03 (PORTAL +21% case): "predict trades BEFORE they burst —
the setup forms at the quiet base, that's where the money is."

Construct under test: find QUIET COILS (the PORTAL-base signature:
tight 24h range, volatility compressed vs its own history, price going
nowhere) and ask Kronos to forecast the next 24h from each. If its
big-|exp| calls at coils precede real bursts at a rate baseline coils
don't, the radar is real. Also sims the tradeable version (enter on
Kronos direction, structural stop, TP1 1:1, fees) so "predicts bursts"
must also mean "makes money". Complements backtest_preburst.py (the
pre-Kronos 8-condition precursor study).

Walk-forward, no lookahead. Checkpointed to .coilkr_rows.jsonl
(CK_MAX_NEW coins/run). Research-only: deploys nothing.
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
import kronos_forecast as kf

N_COINS = int(os.environ.get("CK_N", "30"))
MAX_NEW = int(os.environ.get("CK_MAX_NEW", "3"))
FEE = 0.00055
ROWS_FILE = ".coilkr_rows.jsonl"
BARS = 1000
LOOKBACK = 400
STEP = 6                     # check coil conditions every 6h
RANGE_MAX = 0.06             # 24h high-low range < 6% of price
ATR_PCT_MAX = 35.0           # ATR14 in bottom 35% of trailing 100
MOVE_MAX = 4.0               # |24h change| < 4% (going nowhere)
BURST_PCT = 5.0              # >=5% excursion within horizon = burst
HORIZON = 48                 # hours forward to look for the burst


def _one(sym):
    try:
        d = binance_client.get_klines(sym, "1h", limit=BARS)
    except Exception as exc:
        print(f"  {sym}: fetch error {exc}", flush=True)
        return []
    if d is None or len(d) < LOOKBACK + HORIZON + 30:
        return []
    o = d["open"].astype(float).to_numpy()
    h = d["high"].astype(float).to_numpy()
    l = d["low"].astype(float).to_numpy()
    c = d["close"].astype(float).to_numpy()
    v = d["volume"].astype(float).to_numpy()
    qv = d["quote_volume"].astype(float).to_numpy()
    ts = pd.Series(pd.to_datetime(d.index))
    n = len(c)
    tr = np.maximum(h[1:] - l[1:],
                    np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    atr = pd.Series(np.concatenate([[tr[0]], tr])).rolling(
        14, min_periods=1).mean().to_numpy()
    rows = []
    for t in range(LOOKBACK, n - HORIZON, STEP):
        px = c[t - 1]
        if px <= 0:
            continue
        rng24 = (h[t - 24:t].max() - l[t - 24:t].min()) / px
        chg24 = abs(px / c[t - 25] - 1) * 100 if c[t - 25] else 99
        atr_win = atr[max(0, t - 100):t]
        atr_pct = float((atr_win <= atr[t - 1]).mean() * 100)
        if rng24 >= RANGE_MAX or chg24 >= MOVE_MAX \
                or atr_pct >= ATR_PCT_MAX:
            continue                       # not a quiet coil
        x_df = pd.DataFrame({
            "open": o[t - LOOKBACK:t], "high": h[t - LOOKBACK:t],
            "low": l[t - LOOKBACK:t], "close": c[t - LOOKBACK:t],
            "volume": v[t - LOOKBACK:t], "amount": qv[t - LOOKBACK:t]})
        x_ts = ts.iloc[t - LOOKBACK:t]
        try:
            pred = kf.forecast_window(x_df, x_ts, horizon=24)
            s = kf.summarize(px, pred)
        except Exception as exc:
            print(f"  {sym}@{t}: kronos error {exc}", flush=True)
            continue
        hi_exc = (h[t:t + HORIZON].max() / px - 1) * 100
        lo_exc = (l[t:t + HORIZON].min() / px - 1) * 100
        burst_up = hi_exc >= BURST_PCT
        burst_dn = lo_exc <= -BURST_PCT
        end24 = (c[min(t + 23, n - 1)] / px - 1) * 100
        row = {"sym": sym, "t": str(ts.iloc[t]),
               "kr_dir": s["direction"], "kr_exp": s["exp_move_pct"],
               "kr_hi": s["path_high_pct"], "kr_lo": s["path_low_pct"],
               "rng24": round(rng24 * 100, 2),
               "atr_pct": round(atr_pct, 0),
               "hi48": round(hi_exc, 2), "lo48": round(lo_exc, 2),
               "end24": round(end24, 2),
               "burst": bool(burst_up or burst_dn)}
        # tradeable sim: enter on Kronos direction at coil close,
        # structural stop (swing-10 -/+ 0.25*ATR), TP1 1:1
        if s["direction"] in ("UP", "DOWN"):
            long = s["direction"] == "UP"
            if long:
                ps = float(np.min(l[t - 10:t])) - 0.25 * atr[t - 1]
                if not (0 < px - ps <= 4 * atr[t - 1]):
                    ps = px - 1.5 * atr[t - 1]
                tp1 = px + (px - ps)
            else:
                ps = float(np.max(h[t - 10:t])) + 0.25 * atr[t - 1]
                if not (0 < ps - px <= 4 * atr[t - 1]):
                    ps = px + 1.5 * atr[t - 1]
                tp1 = px - (ps - px)
            risk = abs(px - ps)
            if risk > 0:
                fee_r = 2 * FEE * px / risk
                res = None
                for j in range(t, min(t + HORIZON, n)):
                    hit_sl = l[j] <= ps if long else h[j] >= ps
                    hit_tp = h[j] >= tp1 if long else l[j] <= tp1
                    if hit_sl:
                        res = -1.0 - fee_r
                        break
                    if hit_tp:
                        res = abs(tp1 - px) / risk - fee_r
                        break
                if res is None:
                    endc = c[min(t + HORIZON - 1, n - 1)]
                    res = ((endc - px) if long else
                           (px - endc)) / risk - fee_r
                row["r"] = round(float(res), 3)
        rows.append(row)
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


def _report(rows, done_n):
    print("\n" + "=" * 72)
    tag = "COMPLETE" if done_n >= N_COINS else f"PARTIAL {done_n}/{N_COINS}"
    print(f"🌋 COIL+KRONOS PRE-BURST [{tag}] — {len(rows)} quiet coils")
    print("=" * 72)
    df = pd.DataFrame(rows)
    if df.empty:
        print("no rows")
        return
    base_burst = df.burst.mean() * 100
    print(f"  baseline: {len(df)} coils · burst rate {base_burst:.1f}%")
    for thr in (1.0, 2.0, 3.0):
        seg = df[df.kr_exp.abs() >= thr]
        if len(seg) < 5:
            continue
        br = seg.burst.mean() * 100
        b = seg[seg.burst]
        if len(b):
            dir_ok = (((b.kr_dir == "UP") & (b.hi48 >= BURST_PCT)) |
                      ((b.kr_dir == "DOWN") & (b.lo48 <= -BURST_PCT))
                      ).mean() * 100
        else:
            dir_ok = 0
        print(f"  kronos |exp|>={thr:.0f}%: n={len(seg):4} · burst rate "
              f"{br:.1f}% · direction-on-burst {dir_ok:.0f}%")
    tr = df.dropna(subset=["r"]) if "r" in df.columns else pd.DataFrame()
    if len(tr):
        for thr in (0.0, 1.0, 2.0):
            seg = tr[tr.kr_exp.abs() >= thr]
            if len(seg) < 5:
                continue
            w = (seg.r > 0).mean() * 100
            print(f"  SIM |exp|>={thr:.0f}%: n={len(seg):4} win {w:5.1f}% "
                  f"exp {seg.r.mean():+.3f}R net {seg.r.sum():+.1f}R")
    print("=" * 72)


if __name__ == "__main__":
    if not kf.available():
        print("KRONOS UNAVAILABLE:", kf._import_err, flush=True)
        sys.exit(1)
    kf._get_predictor()
    syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()
    syms = syms[:N_COINS]
    rows, done = _load()
    todo = [s for s in syms if s not in done][:MAX_NEW]
    print(f"Resume: {len(done)} done ({len(rows)} coils). Run: {todo}",
          flush=True)
    t0 = time.time()
    for s in todo:
        try:
            rs = _one(s)
        except Exception as exc:
            print(f"  {s}: ERROR {exc}", flush=True)
            rs = []
        with open(ROWS_FILE, "a", encoding="utf-8") as f:
            for rec in rs:
                f.write(json.dumps(rec) + "\n")
            f.write(json.dumps({"done_coin": s}) + "\n")
        rows.extend(rs)
        print(f"  done {s:12} +{len(rs):4} (cum {len(rows)}, "
              f"{time.time() - t0:.0f}s)", flush=True)
    _report(rows, len(done) + len(todo))
    print(f"Done in {time.time() - t0:.0f}s.", flush=True)
