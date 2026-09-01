"""🟢 CONFIRM-QUALITY study — which confirms should we SKIP?

Live weekend record on the personal-watch confirms was 36% / -0.31R
(n=11, all fired inside 90min of ONE market-wide wave). The MFE
diagnostic killed the exit-geometry hypothesis: the losers had a
median MFE of +0.14R — they died on arrival, so no target/partial/BE
rule could have saved them. The fix must be ENTRY SELECTION.

This tests candidate skip-filters on the 245-entry confirmed universe
where the confirm bar is known EXACTLY (no price-matching guesswork):

  crowd    — how many OTHER coins confirmed within +/-2h (the
             weekend lesson: correlated wave entries)
  volx     — confirm candle volume vs its 20-bar average
  closep   — where the confirm closed inside its own range
  ext4h    — how far above the 4h ema the confirm closed

Fees in, structural stop, 1R target, both history halves. Ship only a
filter that is green in BOTH halves AND beats the baseline.
"""
from __future__ import annotations

import glob
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

FEE = 0.00055
ROWS = ".pwfilter_rows.jsonl"
AWIN, SWIN, ALIVE, FWD, VOL_MULT = 14, 10, 48, 48, 1.2


def _load_fires():
    fires = {}
    for f in sorted(glob.glob(".elanes3_s*.jsonl")):
        for ln in open(f, encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            ob = json.loads(ln)
            if "done_coin" in ob:
                continue
            fires.setdefault(ob["sym"], []).append(ob)
    return fires


def _one(sym, coin_fires):
    try:
        df = binance_client.get_klines(sym, "1h", limit=1500)
    except Exception:
        return []
    if df is None or len(df) < 300:
        return []
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    v = df["volume"].to_numpy()
    ema20 = df["close"].ewm(span=20, adjust=False).mean().to_numpy()
    ema4h = df["close"].ewm(span=80, adjust=False).mean().to_numpy()
    vma = pd.Series(v).rolling(20).mean().to_numpy()
    tr = h - l
    idx = {str(ts): i for i, ts in enumerate(df.index)}
    n = len(df)
    out = []
    for fr in coin_fires:
        t = idx.get(fr["t"])
        if t is None or t + 2 >= n:
            continue
        side = fr["side"]
        lng = side == "LONG"
        hh = h[max(0, t - AWIN + 1):t + 1]
        ll = l[max(0, t - AWIN + 1):t + 1]
        atr = (float(np.mean(np.maximum(hh - ll, 0)))
               if len(hh) >= 5 else 0.0)
        pe = float(c[t])
        if atr <= 0 or pe <= 0:
            continue
        if lng:
            ps = float(np.min(l[max(0, t - SWIN + 1):t + 1])) - 0.25 * atr
            if not (0 < pe - ps <= 4 * atr):
                ps = pe - 1.5 * atr
        else:
            ps = float(np.max(h[max(0, t - SWIN + 1):t + 1])) + 0.25 * atr
            if not (0 < ps - pe <= 4 * atr):
                ps = pe + 1.5 * atr
        tp1f = pe + (pe - ps) if lng else pe - (ps - pe)
        pulled = False
        ci = None
        for i in range(t + 1, min(t + 1 + ALIVE, n)):
            if (lng and l[i] <= ps) or ((not lng) and h[i] >= ps):
                break
            if lng:
                if l[i] <= pe:
                    pulled = True
                ok = (pulled and c[i] > o[i] and c[i] > c[i - 1]
                      and c[i] > ema20[i] and vma[i] > 0
                      and v[i] > VOL_MULT * vma[i])
            else:
                if h[i] >= pe:
                    pulled = True
                ok = (pulled and c[i] < o[i] and c[i] < c[i - 1]
                      and c[i] < ema20[i] and vma[i] > 0
                      and v[i] > VOL_MULT * vma[i])
            if ok:
                ci = i
                break
        if ci is None:
            continue
        ent = float(c[ci])
        if not ((ps < ent < tp1f) if lng else (ps > ent > tp1f)):
            continue
        risk = abs(ent - ps)
        rr_t = ent + risk if lng else ent - risk
        fee_r = 2 * FEE * ent / risk
        res, net = "OPEN", 0.0
        for j in range(ci + 1, min(ci + 1 + FWD, n)):
            if lng:
                if l[j] <= ps:
                    res, net = "LOSS", -1.0 - fee_r
                    break
                if h[j] >= rr_t:
                    res, net = "WIN", 1.0 - fee_r
                    break
            else:
                if h[j] >= ps:
                    res, net = "LOSS", -1.0 - fee_r
                    break
                if l[j] <= rr_t:
                    res, net = "WIN", 1.0 - fee_r
                    break
        if res == "OPEN":
            continue
        rng = h[ci] - l[ci]
        out.append({
            "sym": sym, "half": fr["half"], "tier": fr["tier"],
            "o": res, "net": round(net, 4),
            "ts": float(df.index[ci].timestamp()),
            "volx": round(float(v[ci] / vma[ci]) if vma[ci] > 0 else 0, 2),
            "closep": (round(float((c[ci] - l[ci]) / rng * 100), 1)
                       if rng > 0 else 0.0),
            "ext4h": round(float((c[ci] / ema4h[ci] - 1) * 100), 2),
            "atrp": round(float(tr[max(0, ci - 13):ci + 1].mean()
                                / c[ci] * 100), 2),
        })
    return out


def _seg(rows, label):
    if not rows:
        print(f"  {label:<34} n=0")
        return
    n = len(rows)
    w = sum(1 for r in rows if r["o"] == "WIN")
    net = sum(r["net"] for r in rows)
    print(f"  {label:<34} n={n:4} win {w / n * 100:5.1f}% · "
          f"exp {net / n:+.3f}R")


def _both(rows, label, pred):
    sel = [r for r in rows if pred(r)]
    if len(sel) < 25:
        print(f"  {label:<34} n={len(sel)} (too thin to judge)")
        return
    _seg(sel, label)
    for hf in ("older", "recent"):
        _seg([r for r in sel if r["half"] == hf], f"    {hf}")


if __name__ == "__main__":
    fires = _load_fires()
    done = set()
    rows = []
    if os.path.exists(ROWS):
        for ln in open(ROWS, encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            ob = json.loads(ln)
            if "done_coin" in ob:
                done.add(ob["done_coin"])
            else:
                rows.append(ob)
    print(f"{len(fires)} coins · resume {len(done)}", flush=True)
    t0 = time.time()
    for sym, cf in fires.items():
        if sym in done:
            continue
        try:
            rs = _one(sym, cf)
        except Exception as exc:
            print(f"  {sym}: ERR {exc}", flush=True)
            rs = []
        with open(ROWS, "a", encoding="utf-8") as f:
            for r in rs:
                f.write(json.dumps(r) + "\n")
            f.write(json.dumps({"done_coin": sym}) + "\n")
        rows.extend(rs)
    # crowding: how many OTHER confirms landed within +/-2h
    ts = sorted(r["ts"] for r in rows)
    for r in rows:
        lo = np.searchsorted(ts, r["ts"] - 7200)
        hi = np.searchsorted(ts, r["ts"] + 7200)
        r["crowd"] = int(hi - lo - 1)
    print("\n" + "=" * 66)
    print(f"🟢 CONFIRM-QUALITY — {len(rows)} confirmed entries · fees in")
    print("=" * 66)
    _seg(rows, "BASELINE (all confirms)")
    for hf in ("older", "recent"):
        _seg([r for r in rows if r["half"] == hf], f"    {hf}")
    print("\n  --- CROWDING (the weekend lesson, measured) ---")
    _both(rows, "alone (<=2 others in +/-2h)", lambda r: r["crowd"] <= 2)
    _both(rows, "busy (3-7 others)", lambda r: 3 <= r["crowd"] <= 7)
    _both(rows, "WAVE (8+ others)", lambda r: r["crowd"] >= 8)
    print("\n  --- CONFIRM CANDLE VOLUME ---")
    _both(rows, "vol 1.2-1.6x", lambda r: 1.2 <= r["volx"] < 1.6)
    _both(rows, "vol 1.6-2.5x", lambda r: 1.6 <= r["volx"] < 2.5)
    _both(rows, "vol >=2.5x", lambda r: r["volx"] >= 2.5)
    print("\n  --- CLOSE POSITION IN ITS OWN RANGE ---")
    _both(rows, "closed <60% of range", lambda r: r["closep"] < 60)
    _both(rows, "closed 60-80%", lambda r: 60 <= r["closep"] < 80)
    _both(rows, "closed >=80% (near high)", lambda r: r["closep"] >= 80)
    print("\n  --- EXTENSION ABOVE THE 4h EMA ---")
    _both(rows, "ext < 1%", lambda r: r["ext4h"] < 1)
    _both(rows, "ext 1-3%", lambda r: 1 <= r["ext4h"] < 3)
    _both(rows, "ext >= 3% (stretched)", lambda r: r["ext4h"] >= 3)
    print("=" * 66)
    print(f"Done in {time.time() - t0:.0f}s.", flush=True)
