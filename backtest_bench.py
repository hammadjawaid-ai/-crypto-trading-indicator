"""🎯 BENCHMARK TARGET study — should TP race to the LEVEL, not the ratio?

User 2026-08-29: "SL and TP should be according to the benchmark and
race to it — it should not be 1:1, it should be according to its
strength." The SL side is done (structural smart_stop, validated).
This study answers the TP side: on the same confirmed entries the
green buzzes fire, does targeting the actual overhead STRUCTURE beat
the fixed 1:1?

Policies raced on identical confirmed entries (same 387-fire
universe, house structural stop, fees in, stop-priority, 48h):

  base    — TP at 1R (deployed baseline)
  s125    — TP at 1.25R when STRONG (hot ATR or 1.2x+ vol confirm),
            else 1R (the deployed strength-adaptive cell)
  bench   — TP at the nearest overhead structural level (max of the
            20-bar swing high and 24h high at confirm), clipped to
            [0.75R, 2.5R]
  benchst — strength-aware benchmark: STRONG -> clip [1R, 2.5R];
            quiet -> clip [0.75R, 1.25R]

Prior art honored: blind 2R measured dead (22% win) — bench targets
are LEVELS, clipped, never blind multiples. Ship only if green both
halves vs the deployed policy.
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
ROWS_FILE = ".bench_rows.jsonl"
AWIN, SWIN = 14, 10
ALIVE = 48
FWD = 48
VOL_MULT = 1.2


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


def _resolve(side, ent, ps, tp, h, l, a, b, n):
    lng = side == "LONG"
    risk = abs(ent - ps)
    if risk <= 0 or tp <= 0:
        return None
    rr = abs(tp - ent) / risk
    fee_r = 2 * FEE * ent / risk
    for i in range(a, min(b, n)):
        if lng:
            if l[i] <= ps:
                return ("LOSS", -1.0 - fee_r)
            if h[i] >= tp:
                return ("WIN", rr - fee_r)
        else:
            if h[i] >= ps:
                return ("LOSS", -1.0 - fee_r)
            if l[i] <= tp:
                return ("WIN", rr - fee_r)
    return None


def _one(sym, coin_fires):
    try:
        df = binance_client.get_klines(sym, "1h", limit=1500)
    except Exception:
        return []
    if df is None or len(df) < 300:
        return []
    o = df["open"].to_numpy(); h = df["high"].to_numpy()
    l = df["low"].to_numpy(); c = df["close"].to_numpy()
    v = df["volume"].to_numpy()
    ema20 = df["close"].ewm(span=20, adjust=False).mean().to_numpy()
    vma = pd.Series(v).rolling(20).mean().to_numpy()
    tr = h - l
    idx = {str(ts): i for i, ts in enumerate(df.index)}
    n = len(df)
    rows = []
    for fr in coin_fires:
        t = idx.get(fr["t"])
        if t is None or t + 2 >= n:
            continue
        side = fr["side"]
        lng = side == "LONG"
        _hh = h[max(0, t - AWIN + 1):t + 1]
        _ll = l[max(0, t - AWIN + 1):t + 1]
        _atr = float(np.mean(np.maximum(_hh - _ll, 0))) \
            if len(_hh) >= 5 else 0.0
        pe = float(c[t])
        if _atr <= 0 or pe <= 0:
            continue
        if lng:
            ps = float(np.min(l[max(0, t - SWIN + 1):t + 1])) \
                - 0.25 * _atr
            if not (0 < pe - ps <= 4 * _atr):
                ps = pe - 1.5 * _atr
        else:
            ps = float(np.max(h[max(0, t - SWIN + 1):t + 1])) \
                + 0.25 * _atr
            if not (0 < ps - pe <= 4 * _atr):
                ps = pe + 1.5 * _atr
        if ps <= 0:
            continue
        tp1 = pe + (pe - ps) if lng else pe - (ps - pe)
        # confirmed entry hunt (house construct)
        pulled = False
        conf_i = None
        for i in range(t + 1, min(t + 1 + ALIVE, n)):
            if lng and l[i] <= ps:
                break
            if not lng and h[i] >= ps:
                break
            if lng:
                if l[i] <= pe:
                    pulled = True
                ok = (pulled and c[i] > o[i] and c[i] > c[i - 1]
                      and c[i] > ema20[i]
                      and vma[i] > 0 and v[i] > VOL_MULT * vma[i])
            else:
                if h[i] >= pe:
                    pulled = True
                ok = (pulled and c[i] < o[i] and c[i] < c[i - 1]
                      and c[i] < ema20[i]
                      and vma[i] > 0 and v[i] > VOL_MULT * vma[i])
            if ok:
                conf_i = i
                break
        if conf_i is None:
            continue
        ent = float(c[conf_i])
        okp = (ps < ent < tp1) if lng else (ps > ent > tp1)
        if not okp:
            continue
        risk = abs(ent - ps)
        # strength at the confirm bar: hot ATR (top 40% of trailing
        # 100) or a 1.5x volume confirm candle
        _atr_now = float(tr[max(0, conf_i - 14):conf_i].mean())
        _histA = [float(tr[j - 14:j].mean())
                  for j in range(max(15, conf_i - 100), conf_i)]
        hot = (len(_histA) >= 30 and
               sum(1 for x in _histA if x < _atr_now)
               / len(_histA) >= 0.6)
        volx = float(v[conf_i] / vma[conf_i]) if vma[conf_i] > 0 else 0
        strong = hot or volx >= 1.5
        # the benchmark: nearest overhead structure at the confirm
        if lng:
            lv1 = float(np.max(h[max(0, conf_i - 20):conf_i]))
            lv2 = float(np.max(h[max(0, conf_i - 24):conf_i]))
            bench_raw = max(lv1, lv2)
            bench_r = (bench_raw - ent) / risk
        else:
            lv1 = float(np.min(l[max(0, conf_i - 20):conf_i]))
            lv2 = float(np.min(l[max(0, conf_i - 24):conf_i]))
            bench_raw = min(lv1, lv2)
            bench_r = (ent - bench_raw) / risk
        def _clip(rlo, rhi):
            br = min(max(bench_r, rlo), rhi) if bench_r > 0 else rlo
            return ent + br * risk if lng else ent - br * risk
        pol = {
            "base": ent + risk if lng else ent - risk,
            "s125": (ent + 1.25 * risk if lng else ent - 1.25 * risk)
                    if strong else (ent + risk if lng
                                    else ent - risk),
            "bench": _clip(0.75, 2.5),
            "benchst": _clip(1.0, 2.5) if strong
                       else _clip(0.75, 1.25),
        }
        rec = {"sym": sym, "tier": fr["tier"], "score": fr["score"],
               "half": fr["half"], "t": fr["t"], "strong": strong,
               "bench_r": round(bench_r, 2)}
        for nm, tp in pol.items():
            out = _resolve(side, ent, ps, tp, h, l, conf_i + 1,
                           conf_i + 1 + FWD, n)
            rec[nm] = {"o": out[0], "net": round(out[1], 4)} \
                if out else {"o": "OPEN", "net": 0.0}
        rows.append(rec)
    return rows


def _seg(rows, pol, label):
    res = [r for r in rows if r[pol]["o"] in ("WIN", "LOSS")]
    if not res:
        print(f"  {label:<30} n=0")
        return
    n = len(res)
    w = sum(1 for r in res if r[pol]["o"] == "WIN") / n * 100
    net = sum(r[pol]["net"] for r in res) / n
    print(f"  {label:<30} n={n:4} win {w:5.1f}% · exp {net:+.3f}R · "
          f"net {sum(r[pol]['net'] for r in res):+.1f}R")


def _report(rows):
    print("\n" + "=" * 74)
    print(f"🎯 BENCHMARK TARGET STUDY — {len(rows)} confirmed "
          f"entries · fees in")
    print("=" * 74)
    for pol, nm in (("base", "TP 1:1 (deployed)"),
                    ("s125", "strength x1.25 (deployed)"),
                    ("bench", "BENCH level [0.75-2.5R]"),
                    ("benchst", "BENCH + strength clips")):
        _seg(rows, pol, nm)
    for hf in ("older", "recent"):
        print(f"  --- {hf.upper()} half ---")
        for pol in ("base", "s125", "bench", "benchst"):
            _seg([r for r in rows if r["half"] == hf], pol, pol)
    print("  --- STRONG confirms only ---")
    for pol in ("base", "s125", "bench", "benchst"):
        _seg([r for r in rows if r["strong"]], pol, pol)
    print("  --- quiet confirms only ---")
    for pol in ("base", "s125", "bench", "benchst"):
        _seg([r for r in rows if not r["strong"]], pol, pol)
    print("=" * 74)


if __name__ == "__main__":
    fires = _load_fires()
    done = set()
    rows = []
    if os.path.exists(ROWS_FILE):
        for ln in open(ROWS_FILE, encoding="utf-8"):
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
    for sym, coin_fires in fires.items():
        if sym in done:
            continue
        try:
            rs = _one(sym, coin_fires)
        except Exception as exc:
            print(f"  {sym}: ERROR {exc}", flush=True)
            rs = []
        with open(ROWS_FILE, "a", encoding="utf-8") as f:
            for rec in rs:
                f.write(json.dumps(rec) + "\n")
            f.write(json.dumps({"done_coin": sym}) + "\n")
        rows.extend(rs)
    _report(rows)
    print(f"Done in {time.time() - t0:.0f}s.", flush=True)
