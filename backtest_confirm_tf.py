"""CONFIRMATION SPEED HEAD-TO-HEAD — at-fire vs 15m vs 30m vs 1h.

User 2026-07-28: "confirm ignition on 15m so it gives the best trades
early" + "full 1h confirmation to be 30m — see which is more
effective." One harness answers both: the SAME at-fire ELITE MAX/HIGH
signals (same engine as the boards), the SAME structural plan from 1h
data, and FOUR entry arms per signal:

  atfire : enter at the signal close, immediately (earliest)
  c15    : pullback to plan entry, then a confirming 15m candle
  c30    : same construct on 30m candles (resampled from 15m)
  c60    : same construct on 1h candles (the current proven confirm)

All arms share a 6h wall-clock confirm window; outcomes are walked on
15m bars (precise first-touch), TP1 1:1, conservative same-bar rule,
Bybit taker fees. Entry delay (signal->entry, minutes) is recorded so
earliness is measured, not argued.

Checkpointed to .ctf_rows.jsonl (CTF_MAX_NEW coins/run — rerun to
resume). Research-only: deploys nothing.
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

N_COINS = int(os.environ.get("CTF_N", "20"))
MAX_NEW = int(os.environ.get("CTF_MAX_NEW", "4"))
FEE = 0.00055
SCORE_FLOOR = 80.0
VOL_MULT = 1.2
ROWS_FILE = ".ctf_rows.jsonl"
H1_BARS = 800
M15_BARS = 3300           # ~34 days of 15m, covers the 1h span
WARMUP = 220
STEP = 4
WINDOW_H = 6              # confirm window, wall-clock hours (all arms)
FWD_H = 24                # outcome horizon after entry


def _prep(df):
    o = df["open"].astype(float).to_numpy()
    h = df["high"].astype(float).to_numpy()
    l = df["low"].astype(float).to_numpy()
    c = df["close"].astype(float).to_numpy()
    v = df["volume"].astype(float).to_numpy()
    ema = df["close"].astype(float).ewm(span=20, adjust=False).mean()
    vma = pd.Series(v).rolling(20).mean().to_numpy()
    return o, h, l, c, v, ema.to_numpy(), vma, df.index


def _confirm_entry(side, pe, ps, arr, start_i, win_bars):
    """fast_confirm construct on one TF: pullback to plan entry, then a
    confirming candle (close>open, >prev close, >EMA20, vol>1.2x vma).
    Returns (entry_px, entry_time) or None. Stop touch first -> None."""
    o, h, l, c, v, ema, vma, idx = arr
    n = len(c)
    pulled = False
    for i in range(start_i, min(start_i + win_bars, n)):
        if side == "LONG" and l[i] <= ps:
            return None
        if side == "SHORT" and h[i] >= ps:
            return None
        if side == "LONG":
            if l[i] <= pe:
                pulled = True
            ok = (pulled and c[i] > o[i] and c[i] > c[i - 1]
                  and c[i] > ema[i] and vma[i] > 0
                  and v[i] > VOL_MULT * vma[i])
        else:
            if h[i] >= pe:
                pulled = True
            ok = (pulled and c[i] < o[i] and c[i] < c[i - 1]
                  and c[i] < ema[i] and vma[i] > 0
                  and v[i] > VOL_MULT * vma[i])
        if ok:
            return (float(c[i]), idx[i])
    return None


def _outcome_15m(side, entry, stop, tp1, m15, from_ts):
    o, h, l, c, v, ema, vma, idx = m15
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    rr = abs(tp1 - entry) / risk
    fee_r = 2 * FEE * entry / risk
    start = int(np.searchsorted(idx, from_ts, side="right"))
    end = min(start + FWD_H * 4, len(c))
    if start >= len(c):
        return None
    for j in range(start, end):
        if side == "LONG":
            if l[j] <= stop:
                return ("LOSS", -1.0 - fee_r)
            if h[j] >= tp1:
                return ("WIN", rr - fee_r)
        else:
            if h[j] >= stop:
                return ("LOSS", -1.0 - fee_r)
            if l[j] <= tp1:
                return ("WIN", rr - fee_r)
    endc = c[min(end - 1, len(c) - 1)]
    mtm = ((endc - entry) if side == "LONG" else (entry - endc)) / risk
    return ("TIME", round(mtm - fee_r, 4))


def _one(sym):
    try:
        d4 = binance_client.get_klines(sym, "4h", limit=400)
        d1 = binance_client.get_klines(sym, "1h", limit=H1_BARS)
        d15 = deep_history.get_klines_deep(sym, "15m", bars=M15_BARS)
    except Exception as exc:
        print(f"  {sym}: fetch error {exc}", flush=True)
        return []
    if (d4 is None or len(d4) < 60 or d1 is None
            or len(d1) < WARMUP + 40 or d15 is None or len(d15) < 400):
        return []
    d30 = d15.resample("30min").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last",
         "volume": "sum"}).dropna()
    a1 = _prep(d1)
    a15 = _prep(d15)
    a30 = _prep(d30)
    o1, h1, l1, c1 = a1[0], a1[1], a1[2], a1[3]
    idx1 = a1[7]
    n1 = len(c1)
    rows = []
    for t in range(WARMUP, n1 - 2, STEP):
        s1 = d1.iloc[:t + 1]
        ts = s1.index[-1]
        try:
            s4 = d4[d4.index <= ts]
        except Exception:
            continue
        if len(s4) < 50:
            continue
        try:
            r = es.score_from_data(sym, s1, df_4h=s4, oi_hist=None,
                                   pct_24h=0.0, skip_deriv=True)
        except Exception:
            continue
        sc = float(r.get("score") or 0)
        side = r.get("side")
        tier = (r.get("tier") or "")
        # at-fire ELITE construct: MAX/HIGH the moment it fires
        if sc < SCORE_FLOOR or side not in ("LONG", "SHORT") \
                or tier not in ("MAX", "HIGH"):
            continue
        _hh = h1[max(0, t - 13):t + 1]
        _ll = l1[max(0, t - 13):t + 1]
        _atr = float(np.mean(np.maximum(_hh - _ll, 0)))
        pe = float(c1[t])
        if _atr <= 0 or pe <= 0:
            continue
        if side == "LONG":
            ps = float(np.min(l1[max(0, t - 9):t + 1])) - 0.25 * _atr
            if not (0 < pe - ps <= 4 * _atr):
                ps = pe - 1.5 * _atr
            tp1 = pe + (pe - ps)
        else:
            ps = float(np.max(h1[max(0, t - 9):t + 1])) + 0.25 * _atr
            if not (0 < ps - pe <= 4 * _atr):
                ps = pe + 1.5 * _atr
            tp1 = pe - (ps - pe)
        sig_ts = idx1[t]
        arms = {}
        arms["atfire"] = (pe, sig_ts)
        for name, arr, per_h in (("c15", a15, 4), ("c30", a30, 2),
                                 ("c60", a1, 1)):
            start_i = int(np.searchsorted(arr[7], sig_ts, side="right"))
            got = _confirm_entry(side, pe, ps, arr, start_i,
                                 WINDOW_H * per_h)
            if got:
                arms[name] = got
        for arm, (ent, ent_ts) in arms.items():
            okp = (ps < ent < tp1) if side == "LONG" else \
                (ps > ent > tp1)
            if not okp:
                continue
            out = _outcome_15m(side, ent, ps, tp1, a15, ent_ts)
            if out is None:
                continue
            delay = (pd.Timestamp(ent_ts) - pd.Timestamp(sig_ts)
                     ).total_seconds() / 60
            rows.append({"sym": sym, "t": str(sig_ts), "arm": arm,
                         "side": side, "tier": tier, "o": out[0],
                         "net": round(float(out[1]), 4),
                         "delay_m": int(delay)})
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
    print(f"⏱ CONFIRMATION SPEED HEAD-TO-HEAD [{tag}] — "
          f"{len(rows)} arm-entries · fees in · outcomes on 15m bars")
    print("=" * 72)
    df = pd.DataFrame(rows)
    if df.empty:
        print("no rows")
        return
    for arm in ("atfire", "c15", "c30", "c60"):
        seg = df[df.arm == arm]
        if not len(seg):
            continue
        w = (seg.o == "WIN").mean() * 100
        print(f"  {arm:7} n={len(seg):5} win {w:5.1f}% "
              f"exp {seg.net.mean():+.3f}R net {seg.net.sum():+.1f}R "
              f"avg delay {seg.delay_m.mean():5.0f}m")
        for sd in ("LONG", "SHORT"):
            s2 = seg[seg.side == sd]
            if len(s2) >= 10:
                w2 = (s2.o == "WIN").mean() * 100
                print(f"     {sd:5} n={len(s2):5} win {w2:5.1f}% "
                      f"exp {s2.net.mean():+.3f}R")
    print("=" * 72)
    print("Same signals, same plans — the ONLY variable is how long "
          "we wait to confirm.")


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
        _append(s, rs)
        rows.extend(rs)
        print(f"  done {s:12} +{len(rs):4} (cum {len(rows)}, "
              f"{time.time() - t0:.0f}s)", flush=True)
    _report(rows, len(done) + len(todo))
    print(f"Done in {time.time() - t0:.0f}s.", flush=True)
