"""ORDER-FLOW IMBALANCE validation — the deep-research top recommendation.

The only after-fee edge the 102-agent research sweep confirmed at our
horizon (JFM 2026, peer-reviewed): daily order flow ORTHOGONALIZED
against returns predicts next-day/next-week crypto returns; long-only
survives fees. Its open question — does it survive post-June-2022, and
does a single-venue taker-flow version work — is answered HERE on our
own deep history (walk-forward, no lookahead, Bybit taker fees).

Signal per coin-day: fi = 2*(taker_buy/volume) - 1  (signed taker share)
Orthogonalized: resid_t = fi_t - (a + b*ret_t), with a,b estimated on
the trailing 90d ending t-1 (strictly past-only).

Tests:
  FLOW_NEXTDAY  — next-day close-to-close return spread: for each day,
                  top-third resid coins vs bottom-third (cross-section).
                  Reported pre-fee; daily-rebalance fee bar = 0.11%.
  FLOW_FILTER   — our proven construct: 20d-breakout LONG entries
                  (close > prior 20d high & > EMA50) bucketed by
                  prior-day resid sign. 2.5xATR stop / +2R / 30d — the
                  same construct as the validated OI-context test, so
                  the two filters are directly comparable.

Time-split 22-23 / 24 / 25-26 + per-coin spread in the analysis pass.
Checkpointed .flow_rows.jsonl. Research-only: deploys nothing.
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

N_COINS = int(os.environ.get("FL_N", "40"))
MAX_NEW = int(os.environ.get("FL_MAX_NEW", "40"))
BARS = 1600
FEE = 0.00055
ROWS_FILE = ".flow_rows.jsonl"


def _atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(),
                    (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _play(df, i, side="LONG", stop_mult=2.5, tgt_r=2.0, hold=30):
    o = df["open"].to_numpy(); h = df["high"].to_numpy()
    l = df["low"].to_numpy(); c = df["close"].to_numpy()
    atr = df["atr"].to_numpy()
    n = len(df)
    if i + 2 >= n or not np.isfinite(atr[i]) or atr[i] <= 0:
        return None
    e = float(o[i + 1])
    risk = stop_mult * float(atr[i])
    if risk <= 0 or e <= 0:
        return None
    stop = e - risk
    tgt = e + tgt_r * risk
    fee_r = 2 * FEE * e / risk
    last = min(i + 1 + hold, n - 1)
    for j in range(i + 1, last + 1):
        if l[j] <= stop:
            return -1.0 - fee_r
        if h[j] >= tgt:
            return tgt_r - fee_r
    return (float(c[last]) - e) / risk - fee_r


def _one(sym):
    try:
        px = deep_history.get_klines_deep(sym, "1d", bars=BARS)
    except Exception:
        return []
    if px is None or len(px) < 300 or "taker_base" not in px.columns:
        return []
    df = px[["open", "high", "low", "close", "volume",
             "taker_base"]].copy()
    df.index = pd.to_datetime(df.index, utc=True).normalize()
    df = df[~df.index.duplicated(keep="last")]
    v = df["volume"].replace(0, np.nan)
    df["fi"] = (2 * df["taker_base"] / v - 1).clip(-1, 1)
    # drop coins where taker_base is the 0.5*volume approximation
    if df["fi"].abs().max() < 1e-9:
        return []
    df["ret"] = df["close"].pct_change()
    # strictly-past rolling orthogonalization: a,b from window ending t-1
    W = 90
    cov = df["fi"].rolling(W).cov(df["ret"]).shift(1)
    var = df["ret"].rolling(W).var().shift(1)
    mfi = df["fi"].rolling(W).mean().shift(1)
    mret = df["ret"].rolling(W).mean().shift(1)
    b = cov / var.replace(0, np.nan)
    a = mfi - b * mret
    df["resid"] = df["fi"] - (a + b * df["ret"])
    df["atr"] = _atr(df)
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["hi20"] = df["high"].rolling(20).max().shift(1)
    df["fwd1"] = df["close"].pct_change().shift(-1)

    rows = []
    n = len(df)
    for i in range(120, n - 2):
        r = df.iloc[i]
        if not np.isfinite(r["resid"]):
            continue
        t = str(df.index[i].date())
        # next-day return sample for the cross-sectional spread analysis
        if np.isfinite(r["fwd1"]):
            rows.append({"sym": sym, "test": "FLOW_NEXTDAY", "t": t,
                         "resid": round(float(r["resid"]), 5),
                         "fwd1": round(float(r["fwd1"]), 5)})
        # breakout entries bucketed by prior-day resid sign
        if (np.isfinite(r["hi20"]) and r["close"] > r["hi20"]
                and r["close"] > r["ema50"]
                and np.isfinite(df["resid"].iloc[i - 1])):
            net = _play(df, i)
            if net is not None:
                rows.append({
                    "sym": sym, "test": "FLOW_FILTER", "t": t,
                    "bucket": ("flow_pos"
                               if df["resid"].iloc[i - 1] > 0
                               else "flow_neg"),
                    "net": net})
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


def _era(t):
    y = int(t[:4])
    return "22-23" if y <= 2023 else ("24" if y == 2024 else "25-26")


def _report(rows, done_n):
    print("\n" + "=" * 76)
    tag = "COMPLETE" if done_n >= N_COINS else f"PARTIAL {done_n}/{N_COINS}"
    print(f"FLOW-IMBALANCE VALIDATION [{tag}] — {len(rows)} rows")
    print("=" * 76)
    df = pd.DataFrame(rows)
    if df.empty:
        print("no rows")
        return
    # cross-sectional next-day spread: per-day terciles of resid
    nx = df[df.test == "FLOW_NEXTDAY"].copy()
    if len(nx):
        nx["era"] = nx["t"].map(_era)
        print("FLOW_NEXTDAY — per-day resid terciles, next-day return "
              "(PRE-fee; daily-trade fee bar 0.11%):")
        for era in ("22-23", "24", "25-26", "ALL"):
            seg = nx if era == "ALL" else nx[nx.era == era]
            if len(seg) < 500:
                continue
            days = []
            for t, g in seg.groupby("t"):
                if len(g) < 9:
                    continue
                q1, q2 = g["resid"].quantile([1 / 3, 2 / 3])
                top = g[g.resid >= q2]["fwd1"].mean()
                bot = g[g.resid <= q1]["fwd1"].mean()
                allm = g["fwd1"].mean()
                days.append((top, bot, allm))
            if not days:
                continue
            d = np.array(days)
            spread = (d[:, 0] - d[:, 1]).mean() * 100
            longonly = (d[:, 0] - d[:, 2]).mean() * 100
            tstat = ((d[:, 0] - d[:, 1]).mean()
                     / ((d[:, 0] - d[:, 1]).std()
                        / np.sqrt(len(d)) + 1e-12))
            print(f"  {era:5} days={len(d):4} · top-bot spread "
                  f"{spread:+.3f}%/day (t={tstat:+.2f}) · "
                  f"top-vs-universe {longonly:+.3f}%/day")
    # breakout filter
    fl = df[df.test == "FLOW_FILTER"].copy()
    if len(fl):
        fl["era"] = fl["t"].map(_era)
        print("-" * 76)
        print("FLOW_FILTER — 20d-breakout LONGs by prior-day flow resid "
              "(2.5xATR/+2R/30d, fees in):")
        for era in ("22-23", "24", "25-26", "ALL"):
            seg = fl if era == "ALL" else fl[fl.era == era]
            for bk in ("flow_pos", "flow_neg"):
                s2 = seg[seg.bucket == bk]
                if len(s2) < 15:
                    continue
                print(f"  {era:5} [{bk}] n={len(s2):5} "
                      f"win {(s2.net > 0).mean() * 100:5.1f}% "
                      f"exp {s2.net.mean():+.3f}R")
    print("=" * 76)


if __name__ == "__main__":
    syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]
    rows, done = _load()
    todo = [s for s in syms if s not in done][:MAX_NEW]
    print(f"Resume: {len(done)} done ({len(rows)} rows). This run: {todo}")
    t0 = time.time()
    for s in todo:
        try:
            rs = _one(s)
        except Exception as exc:
            print(f"  {s}: ERROR {exc}", flush=True)
            rs = []
        _append(s, rs)
        rows.extend(rs)
        print(f"  done {s:12} +{len(rs):5} (cum {len(rows)}, "
              f"{time.time() - t0:.0f}s)", flush=True)
    _report(rows, len(done) + len(todo))
    print(f"Done in {time.time() - t0:.0f}s.")
