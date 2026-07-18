"""POSITIONING VALIDATION — 1h intraday track (Coinalyze, ~60 days).

The daily track (backtest_positioning.py) found the falling-OI breakout
edge. This tests the INTRADAY pre-move hypotheses — the "act prior at
the hours scale" vein — walk-forward, Bybit taker fees included:

  A. SQUEEZE (OI compression -> expansion): 24h price range AND 24h OI
     range both in the bottom quintile of their trailing 14d (coiled +
     positioned), then the first 1h bar where OI jumps (top-decile 1h
     OI change) -> enter in that bar's direction.
  B. OI DIVERGENCE 1h: 12h price down >1.5% while OI up >2% -> LONG
     (shorts crowding into weakness). Mirror: price up + OI up -> SHORT.
  C. LIQ FLUSH 1h: long-liquidation 1h spike >= trailing 14d p99 ->
     LONG next bar (post-cascade snapback). Mirror for shorts.
  D. BREAKOUT x OI 1h: close > prior 24h high, bucketed by 6h OI change
     (intraday analog of the validated daily falling-OI cell).

Construct: enter next 1h open, stop/TP symmetric 1.5x ATR(14h) (1:1),
walk 24h, else close. BASELINE: same construct every 24th bar.
Honest caveat up front: only ~60 days of 1h OI history exists on the
free tier — findings are PROVISIONAL vs the 8-month/4-year standards.
Checkpointed to .pos1h_rows.jsonl (P1_N coins / P1_MAX_NEW per run).
Research-only: deploys nothing.
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

N_COINS = int(os.environ.get("P1_N", "40"))
MAX_NEW = int(os.environ.get("P1_MAX_NEW", "40"))
FEE = 0.00055
HOLD = 24                  # bars (1h)
ROWS_FILE = ".pos1h_rows.jsonl"


def _atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(),
                    (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _play(df, i, side, hold=HOLD, stop_mult=1.5, tgt_r=1.0):
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
    stop = e - risk if side == "LONG" else e + risk
    tgt = e + tgt_r * risk if side == "LONG" else e - tgt_r * risk
    fee_r = 2 * FEE * e / risk
    last = min(i + 1 + hold, n - 1)
    for j in range(i + 1, last + 1):
        if side == "LONG":
            if l[j] <= stop:
                return -1.0 - fee_r
            if h[j] >= tgt:
                return tgt_r - fee_r
        else:
            if h[j] >= stop:
                return -1.0 - fee_r
            if l[j] <= tgt:
                return tgt_r - fee_r
    ex = float(c[last])
    r = (ex - e) / risk if side == "LONG" else (e - ex) / risk
    return r - fee_r


def _one(sym):
    mkt = cz.resolve_perp(sym)
    if not mkt:
        return []
    oi = cz.oi_history(mkt, "1hour", days=70)
    lq = cz.liquidation_history(mkt, "1hour", days=70)
    try:
        px = binance_client.get_klines(sym, "1h", limit=1700)
    except Exception:
        return []
    if px is None or len(px) < 500 or oi is None or len(oi) < 500:
        return []
    df = px[["open", "high", "low", "close", "volume"]].copy()
    df.index = pd.to_datetime(df.index, utc=True)
    df = df[~df.index.duplicated(keep="last")]
    df["oi"] = oi["oi_c"].reindex(df.index)
    if lq is not None:
        df["liq_l"] = lq["liq_long"].reindex(df.index).fillna(0)
        df["liq_s"] = lq["liq_short"].reindex(df.index).fillna(0)
    else:
        df["liq_l"] = 0.0
        df["liq_s"] = 0.0
    df = df[df["oi"].notna()]
    if len(df) < 500:
        return []
    df["atr"] = _atr(df)
    c = df["close"]
    oi_s = df["oi"]
    df["oi1"] = oi_s.pct_change(1)
    df["oi6"] = oi_s.pct_change(6)
    df["ret12"] = c.pct_change(12)
    df["oi12"] = oi_s.pct_change(12)
    # 24h ranges for the squeeze test
    df["prng24"] = (df["high"].rolling(24).max()
                    - df["low"].rolling(24).min()) / c
    df["orng24"] = (oi_s.rolling(24).max()
                    - oi_s.rolling(24).min()) / oi_s
    W = 14 * 24
    df["prng_q20"] = df["prng24"].rolling(W, min_periods=200) \
        .quantile(.20).shift(1)
    df["orng_q20"] = df["orng24"].rolling(W, min_periods=200) \
        .quantile(.20).shift(1)
    df["oi1_q90"] = df["oi1"].rolling(W, min_periods=200) \
        .quantile(.90).shift(1)
    df["ll_p99"] = df["liq_l"].rolling(W, min_periods=200) \
        .quantile(.99).shift(1)
    df["ls_p99"] = df["liq_s"].rolling(W, min_periods=200) \
        .quantile(.99).shift(1)
    df["hi24"] = df["high"].rolling(24).max().shift(1)

    rows = []
    o = df["open"].to_numpy(); cl = df["close"].to_numpy()
    n = len(df)
    for i in range(360, n - 26):
        r = df.iloc[i]

        def _rec(test, side, extra=None):
            net = _play(df, i, side)
            if net is None:
                return
            ob = {"sym": sym, "test": test, "side": side, "net": net,
                  "t": str(df.index[i])}
            if extra:
                ob.update(extra)
            rows.append(ob)

        if i % 24 == 0:
            _rec("BASE", "LONG")
            _rec("BASE", "SHORT")
        # A. squeeze: coiled price + coiled OI, then OI expansion bar
        if (np.isfinite(r["prng_q20"]) and np.isfinite(r["orng_q20"])
                and np.isfinite(r["oi1_q90"])
                and df["prng24"].iloc[i - 1] <= r["prng_q20"]
                and df["orng24"].iloc[i - 1] <= r["orng_q20"]
                and r["oi1"] >= r["oi1_q90"] and r["oi1"] > 0.002):
            _rec("A_SQUEEZE", "LONG" if cl[i] > o[i] else "SHORT")
        # B. OI divergence 12h
        if np.isfinite(r["ret12"]) and np.isfinite(r["oi12"]):
            if r["ret12"] < -0.015 and r["oi12"] > 0.02:
                _rec("B_OIDIV_DOWN", "LONG")
            if r["ret12"] > 0.015 and r["oi12"] > 0.02:
                _rec("B_OIDIV_UP", "SHORT")
        # C. liquidation flush 1h
        if (np.isfinite(r["ll_p99"]) and r["ll_p99"] > 0
                and r["liq_l"] >= r["ll_p99"]):
            _rec("C_LIQ_LONGFLUSH", "LONG")
        if (np.isfinite(r["ls_p99"]) and r["ls_p99"] > 0
                and r["liq_s"] >= r["ls_p99"]):
            _rec("C_LIQ_SHORTFLUSH", "SHORT")
        # D. 24h breakout bucketed by 6h OI change
        if (np.isfinite(r["hi24"]) and cl[i] > r["hi24"]
                and np.isfinite(r["oi6"])):
            b = ("oi_dn" if r["oi6"] < 0 else
                 "oi_up_sm" if r["oi6"] <= 0.03 else "oi_up_big")
            _rec("D_BREAK24", "LONG", {"bucket": b})
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
    print("\n" + "=" * 74)
    tag = "COMPLETE" if done_n >= N_COINS else f"PARTIAL {done_n}/{N_COINS}"
    print(f"1H POSITIONING [{tag}] — {len(rows)} plays · walk-forward · "
          f"fees in · ~60d window (PROVISIONAL)")
    print("=" * 74)
    df = pd.DataFrame(rows)
    if df.empty:
        print("no rows")
        return
    for side in ("LONG", "SHORT"):
        b = df[(df.test == "BASE") & (df.side == side)]
        if len(b):
            print(f"  BASELINE {side:5} n={len(b):5} "
                  f"win {(b.net > 0).mean() * 100:5.1f}% "
                  f"exp {b.net.mean():+.3f}R")
    print("-" * 74)
    for test in sorted(df.test.unique()):
        if test == "BASE":
            continue
        seg = df[df.test == test]
        if test == "D_BREAK24":
            for bk in ("oi_dn", "oi_up_sm", "oi_up_big"):
                s2 = seg[seg.get("bucket") == bk]
                if not len(s2):
                    continue
                print(f"  {test:16} [{bk:9}] n={len(s2):5} "
                      f"win {(s2.net > 0).mean() * 100:5.1f}% "
                      f"exp {s2.net.mean():+.3f}R")
        else:
            print(f"  {test:16} {'':11} n={len(seg):5} "
                  f"win {(seg.net > 0).mean() * 100:5.1f}% "
                  f"exp {seg.net.mean():+.3f}R")
    print("=" * 74)


if __name__ == "__main__":
    syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]
    rows, done = _load()
    todo = [s for s in syms if s not in done][:MAX_NEW]
    print(f"Resume: {len(done)} done ({len(rows)} plays). This run: {todo}")
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
