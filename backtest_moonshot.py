"""🚀 MOONSHOT VALIDATION — the backtestable core of the big-move desk.

Live fire = TRIGGER + 2 of (HEAT, FUEL, BASE). Social HEAT has no
replayable history (LunarCrush hourly per-coin backfill is not wired),
so this harness validates the STRICTEST backtestable subset:
    TRIGGER (1h close breaks 12h high on >=1.5x vol)
  + FUEL    (OI build >=5%/24h OR crowd-lean short <=-0.05, from real
             Coinalyze hourly history)
  + BASE    (|24h|<12%, upper half of ~8d range or coiled)
Two exits measured per fire, fees in:
  rA — bank 100% at +1R (win-rate view)
  rT — the LIVE plan: bank HALF at +1R, rest rides a 3xATR chandelier
       trail (cap 96h) — the big-move view.
Checkpointed .moonbt_rows.jsonl (MB_MAX_NEW coins/run). Research only.
Bar: positive after-fee expectancy on BOTH exits, or the desk's buzz
stays honest-labeled UNPROVEN until the forward record speaks.
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
import coinalyze_client as cz

N_COINS = int(os.environ.get("MB_N", "30"))
MAX_NEW = int(os.environ.get("MB_MAX_NEW", "5"))
FEE = 0.00055
ROWS_FILE = ".moonbt_rows.jsonl"
BARS = 750
EXT_MAX = 12.0
FUEL_OI = 5.0
FUEL_LS = -0.05
VOL_X = 1.5
TRAIL_ATR = 3.0
TRAIL_CAP = 96


def _one(sym):
    try:
        d = binance_client.get_klines(sym, "1h", limit=BARS)
        mkt = cz.resolve_perp(sym)
        oi = cz.oi_history(mkt, "1hour", days=31) if mkt else None
        ls = cz.long_short_history(mkt, "1hour", days=31) if mkt else None
    except Exception as exc:
        print(f"  {sym}: fetch error {exc}", flush=True)
        return []
    if d is None or len(d) < 300:
        return []
    o = d["open"].astype(float).to_numpy()
    h = d["high"].astype(float).to_numpy()
    l = d["low"].astype(float).to_numpy()
    c = d["close"].astype(float).to_numpy()
    v = d["volume"].astype(float).to_numpy()
    idx = pd.to_datetime(d.index)
    n = len(c)
    vma = pd.Series(v).rolling(20).mean().to_numpy()
    tr = np.maximum(h[1:] - l[1:],
                    np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    atr = pd.Series(np.concatenate([[tr[0]], tr])).rolling(
        14, min_periods=1).mean().to_numpy()
    # align positioning frames to kline timestamps
    oi_v = ls_v = None
    if oi is not None and len(oi) and len(oi.columns):
        oi_s = oi[oi.columns[0]].astype(float)
        oi_v = oi_s.reindex(idx, method="ffill").to_numpy()
    if ls is not None and len(ls) and len(ls.columns):
        ls_s = ls[ls.columns[0]].astype(float)
        ls_v = ls_s.reindex(idx, method="ffill").to_numpy()
    rows = []
    last_fire = -999
    for t in range(200, n - 3):
        if t - last_fire <= 24:
            continue
        chg24 = (c[t] / c[t - 24] - 1) * 100
        if abs(chg24) >= EXT_MAX:
            continue
        # TRIGGER
        hi12 = h[t - 12:t].max()
        if not (c[t] > hi12 and vma[t] > 0
                and v[t] >= VOL_X * vma[t]):
            continue
        # BASE
        lo_r = l[max(0, t - 192):t].min()
        hi_r = h[max(0, t - 192):t].max()
        pos_r = (c[t] - lo_r) / (hi_r - lo_r) * 100 if hi_r > lo_r \
            else 50.0
        rng24 = (h[t - 24:t].max() - l[t - 24:t].min()) / c[t] * 100
        rng72 = (h[t - 72:t].max() - l[t - 72:t].min()) / c[t] * 100 / 3
        coiled = rng72 > 0 and rng24 / rng72 < 1.2
        if not (pos_r >= 50 or coiled):
            continue
        # FUEL (from real positioning history, values at t-1 vs t-25)
        fuel = False
        d_oi = d_ls = None
        if oi_v is not None and t >= 25 and oi_v[t - 25] and \
                oi_v[t - 25] > 0 and not np.isnan(oi_v[t - 1]):
            d_oi = (oi_v[t - 1] / oi_v[t - 25] - 1) * 100
            if d_oi >= FUEL_OI:
                fuel = True
        if ls_v is not None and t >= 25 and not np.isnan(ls_v[t - 1]) \
                and not np.isnan(ls_v[t - 25]):
            d_ls = ls_v[t - 1] - ls_v[t - 25]
            if d_ls <= FUEL_LS:
                fuel = True
        if not fuel:
            continue
        last_fire = t
        epx = float(c[t])
        stop = l[t] - 0.25 * atr[t]
        risk = epx - stop
        if risk <= 0 or risk > 4 * atr[t]:
            stop = epx - 1.5 * atr[t]
            risk = epx - stop
        tp1 = epx + risk
        fee_r = 2 * FEE * epx / risk
        # rA: bank all at 1R
        rA = None
        for j in range(t + 1, min(t + 1 + 48, n)):
            if l[j] <= stop:
                rA = -1.0 - fee_r
                break
            if h[j] >= tp1:
                rA = 1.0 - fee_r
                break
        if rA is None:
            rA = (c[min(t + 48, n - 1)] - epx) / risk - fee_r
        # rT: half at 1R, rest 3xATR trail
        rT = None
        half_done = False
        trail = stop
        hi_seen = epx
        for j in range(t + 1, min(t + 1 + TRAIL_CAP, n)):
            if not half_done:
                if l[j] <= stop:
                    rT = -1.0 - fee_r
                    break
                if h[j] >= tp1:
                    half_done = True
                    trail = epx        # BE for the runner
            if half_done:
                hi_seen = max(hi_seen, h[j])
                trail = max(trail, hi_seen - TRAIL_ATR * atr[j])
                if l[j] <= trail:
                    run_r = (trail - epx) / risk
                    rT = 0.5 * (1.0) + 0.5 * run_r - fee_r
                    break
        if rT is None:
            endc = c[min(t + TRAIL_CAP, n - 1)]
            if half_done:
                rT = 0.5 + 0.5 * (endc - epx) / risk - fee_r
            else:
                rT = (endc - epx) / risk - fee_r
        rows.append({"sym": sym, "t": str(idx[t]),
                     "d_oi": None if d_oi is None else round(d_oi, 1),
                     "d_ls": None if d_ls is None else round(d_ls, 3),
                     "pos_r": round(pos_r), "coiled": bool(coiled),
                     "vx": round(float(v[t] / vma[t]), 1),
                     "rA": round(float(rA), 3),
                     "rT": round(float(rT), 3)})
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


def _seg(df, col, name):
    s = df.dropna(subset=[col])
    if len(s) < 8:
        print(f"  {name:<28} n={len(s):3}  (too small)")
        return
    w = (s[col] > 0).mean() * 100
    print(f"  {name:<28} n={len(s):3} win {w:5.1f}% "
          f"exp {s[col].mean():+.3f}R net {s[col].sum():+.1f}R")


def _report(rows, done_n):
    print("\n" + "=" * 70)
    tag = "COMPLETE" if done_n >= N_COINS else f"PARTIAL {done_n}/{N_COINS}"
    print(f"🚀 MOONSHOT CORE [{tag}] — {len(rows)} fires · fees in")
    print("=" * 70)
    df = pd.DataFrame(rows)
    if df.empty:
        print("no rows")
        return
    _seg(df, "rA", "bank 100% at 1R")
    _seg(df, "rT", "LIVE plan (half + trail)")
    _seg(df[df.coiled], "rT", "coiled bases")
    _seg(df[df.pos_r >= 70], "rT", "upper-range breaks")
    _seg(df[df.vx >= 2.5], "rT", "big-volume breaks 2.5x+")
    d_oi_ok = df.d_oi.notna() & (df.d_oi >= 10)
    _seg(df[d_oi_ok], "rT", "heavy OI build 10%+")
    print("=" * 70)


if __name__ == "__main__":
    syms = binance_client.get_top_symbols(N_COINS + 5)["symbol"].tolist()
    syms = syms[:N_COINS]
    rows, done = _load()
    todo = [s for s in syms if s not in done][:MAX_NEW]
    print(f"Resume: {len(done)} done ({len(rows)} fires). Run: {todo}",
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
        print(f"  done {s:12} +{len(rs):3} (cum {len(rows)}, "
              f"{time.time() - t0:.0f}s)", flush=True)
    _report(rows, len(done) + len(todo))
    print(f"Done in {time.time() - t0:.0f}s.", flush=True)
