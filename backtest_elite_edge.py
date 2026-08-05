"""ELITE EDGE MINER — what separates EARLY ELITE winners from losers?

User 2026-08-04: "one board — fewer trades, but the ones that WIN.
Early elite is the best since the beginning; advance it one step."

Replays the elite family (MAX/HIGH at-fire + 30m confirmation — the
validated construct) across 30 coins and records the FULL feature
snapshot at every entry: score, ATR percentile, 24h/6h change, volume
ratio, hour (UTC), side, coil range. Then slices win rate / expectancy
by each feature and hunts intersections with n>=30 — the data-defined
"winning subset" that becomes the advanced board. Test-only.
Checkpointed .estrong_rows.jsonl (EE_MAX_NEW coins/run).
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
import experimental_signals as es

N_COINS = int(os.environ.get("EE_N", "30"))
MAX_NEW = int(os.environ.get("EE_MAX_NEW", "4"))
FEE = 0.00055
ROWS_FILE = ".ee3_rows.jsonl"   # confirmation pass — 3x history depth
# (.ee2 = the 37-day pass whose quiet-ATR thread needs confirming)
WARMUP = 220
STEP = 3
FWD = 48 * 2                # 48h on 30m bars


def _one(sym):
    try:
        d4 = binance_client.get_klines(sym, "4h", limit=750)
        d1 = deep_history.get_klines_deep(sym, "1h", bars=2600)
        d30 = deep_history.get_klines_deep(sym, "30m", bars=5300)
    except Exception as exc:
        print(f"  {sym}: fetch error {exc}", flush=True)
        return []
    if (d4 is None or d1 is None or d30 is None or len(d1) < 400
            or len(d30) < 600):
        return []
    o1 = d1["open"].astype(float).to_numpy()
    h1 = d1["high"].astype(float).to_numpy()
    l1 = d1["low"].astype(float).to_numpy()
    c1 = d1["close"].astype(float).to_numpy()
    v1 = d1["volume"].astype(float).to_numpy()
    vma = pd.Series(v1).rolling(20).mean().to_numpy()
    tr = np.maximum(h1[1:] - l1[1:],
                    np.maximum(abs(h1[1:] - c1[:-1]),
                               abs(l1[1:] - c1[:-1])))
    atr = pd.Series(np.concatenate([[tr[0]], tr])).rolling(
        14, min_periods=1).mean().to_numpy()
    idx1 = d1.index
    o30 = d30["open"].astype(float).to_numpy()
    h30 = d30["high"].astype(float).to_numpy()
    l30 = d30["low"].astype(float).to_numpy()
    c30 = d30["close"].astype(float).to_numpy()
    v30 = d30["volume"].astype(float).to_numpy()
    e30 = d30["close"].astype(float).ewm(
        span=20, adjust=False).mean().to_numpy()
    vm30 = pd.Series(v30).rolling(20).mean().to_numpy()
    idx30 = d30.index
    n1, n30 = len(c1), len(c30)
    rows = []
    for t in range(WARMUP, n1 - 50, STEP):
        s1 = d1.iloc[:t + 1]
        ts = s1.index[-1]
        try:
            s4 = d4[d4.index <= ts]
            r = es.score_from_data(sym, s1, df_4h=s4, oi_hist=None,
                                   pct_24h=0.0, skip_deriv=True)
        except Exception:
            continue
        sc = float(r.get("score") or 0)
        side = r.get("side")
        tier = (r.get("tier") or "")
        if sc < 80 or side not in ("LONG", "SHORT") \
                or tier not in ("MAX", "HIGH"):
            continue
        pe = float(c1[t])
        _a = atr[t - 1]
        if _a <= 0 or pe <= 0:
            continue
        if side == "LONG":
            ps = float(np.min(l1[max(0, t - 9):t + 1])) - 0.25 * _a
            if not (0 < pe - ps <= 4 * _a):
                ps = pe - 1.5 * _a
            tp1 = pe + (pe - ps)
        else:
            ps = float(np.max(h1[max(0, t - 9):t + 1])) + 0.25 * _a
            if not (0 < ps - pe <= 4 * _a):
                ps = pe + 1.5 * _a
            tp1 = pe - (ps - pe)
        # 30m confirmation within 6h (the validated middle path)
        st30 = int(np.searchsorted(idx30, ts, side="right"))
        ent = None
        pulled = False
        for j in range(st30, min(st30 + 12, n30)):
            if side == "LONG" and l30[j] <= ps:
                break
            if side == "SHORT" and h30[j] >= ps:
                break
            if side == "LONG":
                if l30[j] <= pe:
                    pulled = True
                ok = (pulled and c30[j] > o30[j] and c30[j] > c30[j - 1]
                      and c30[j] > e30[j] and vm30[j] > 0
                      and v30[j] > 1.2 * vm30[j])
            else:
                if h30[j] >= pe:
                    pulled = True
                ok = (pulled and c30[j] < o30[j] and c30[j] < c30[j - 1]
                      and c30[j] < e30[j] and vm30[j] > 0
                      and v30[j] < 1e18 and v30[j] > 1.2 * vm30[j])
            if ok:
                ent = (float(c30[j]), j)
                break
        if ent is None:
            continue
        epx, ei = ent
        okp = (ps < epx < tp1) if side == "LONG" else (ps > epx > tp1)
        if not okp:
            continue
        risk = abs(epx - ps)
        fee_r = 2 * FEE * epx / risk
        out = None
        for j in range(ei + 1, min(ei + 1 + FWD, n30)):
            hs = l30[j] <= ps if side == "LONG" else h30[j] >= ps
            ht = h30[j] >= tp1 if side == "LONG" else l30[j] <= tp1
            if hs:
                out = -1.0 - fee_r
                break
            if ht:
                out = abs(tp1 - epx) / risk - fee_r
                break
        if out is None:
            endc = c30[min(ei + FWD, n30 - 1)]
            out = ((endc - epx) if side == "LONG" else
                   (epx - endc)) / risk - fee_r
        # feature snapshot at signal time
        atr_pct = float((atr[max(0, t - 100):t] <= atr[t - 1]).mean()
                        * 100)
        rows.append({
            "sym": sym, "t": str(ts), "side": side, "tier": tier,
            "score": sc, "atr_pct": round(atr_pct),
            "c24": round((c1[t] / c1[t - 24] - 1) * 100, 1),
            "c6": round((c1[t] / c1[t - 6] - 1) * 100, 1),
            "vr": round(float(v1[t] / vma[t]) if vma[t] > 0 else 0, 2),
            "hour": int(pd.Timestamp(ts).hour),
            "r": round(float(out), 3)})
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


def _seg(df, name):
    if len(df) < 15:
        return
    w = (df.r > 0).mean() * 100
    print(f"  {name:<28} n={len(df):4} win {w:5.1f}% "
          f"exp {df.r.mean():+.3f}R", flush=True)


def _report(rows, done_n):
    print("\n" + "=" * 70)
    tag = "COMPLETE" if done_n >= N_COINS else f"PARTIAL {done_n}/{N_COINS}"
    print(f"🌟 ELITE EDGE MINER [{tag}] — {len(rows)} confirmed entries")
    print("=" * 70)
    df = pd.DataFrame(rows)
    if df.empty:
        print("no rows")
        return
    _seg(df, "ALL elite entries")
    _seg(df[df.tier == "MAX"], "tier MAX")
    _seg(df[df.tier == "HIGH"], "tier HIGH")
    _seg(df[df.score >= 90], "score>=90")
    _seg(df[df.score < 90], "score 80-90")
    _seg(df[df.atr_pct >= 80], "ATR blazing 80+")
    _seg(df[(df.atr_pct >= 40) & (df.atr_pct < 80)], "ATR mid 40-80")
    _seg(df[df.atr_pct < 40], "ATR quiet <40")
    _seg(df[df.vr >= 2], "vol surge 2x+")
    _seg(df[df.vr < 2], "vol normal <2x")
    _seg(df[df.side == "LONG"], "LONG")
    _seg(df[df.side == "SHORT"], "SHORT")
    _seg(df[df.c6.abs() < 3], "calm 6h (<3%)")
    _seg(df[df.c6.abs() >= 3], "moving 6h (>=3%)")
    print("  --- best intersections (n>=30) ---", flush=True)
    combos = [("MAX + vol2x", (df.tier == "MAX") & (df.vr >= 2)),
              ("score90 + calm6h", (df.score >= 90) & (df.c6.abs() < 3)),
              ("MAX + ATR mid", (df.tier == "MAX") & (df.atr_pct >= 40)
               & (df.atr_pct < 80)),
              ("score90 + vol2x", (df.score >= 90) & (df.vr >= 2)),
              ("calm6h + vol2x", (df.c6.abs() < 3) & (df.vr >= 2))]
    for nm, m in combos:
        s = df[m]
        if len(s) >= 30:
            _seg(s, nm)
    print("=" * 70)


if __name__ == "__main__":
    syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()
    syms = syms[:N_COINS]
    rows, done = _load()
    todo = [s for s in syms if s not in done][:MAX_NEW]
    print(f"Resume: {len(done)} done ({len(rows)} rows). Run: {todo}",
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
