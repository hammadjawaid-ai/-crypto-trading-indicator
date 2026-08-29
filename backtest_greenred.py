"""GREEN/RED study — the user's ask (2026-08-29): after the GREEN
light (the validated confirmed entry on elite HIGH/MAX + best-family
fires), is there a RED get-out signal that beats holding to the plan?

Same 387-fire universe as the entry-styles study (.elanes3_s*.jsonl),
same house plan, same confirmed-entry fill. Four exit policies race
on identical entries:

  plan — hold to SL/TP1 (the deployed baseline, bank at TP1)
  r1   — STRUCTURE red: exit on a 1h close beyond ema20 AGAINST the
         position while underwater (the double-clock signature's 1h
         proxy — the shape that went 5-for-5 in live watches)
  r2   — FADE red: two consecutive 1h closes against the position
         while underwater
  r3   — HALF-STOP red: exit on a close past halfway to the stop

Honest accounting: fees in, stop-priority intrabar, both history
halves. Research-only — deploys nothing. Ship the red buzz only if a
rule is green in BOTH halves vs plan.
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
ROWS_FILE = ".greenred_rows.jsonl"
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


def _walk(side, ent, ps, tp1, o, h, l, c, ema20, a, b, n, red):
    """Walk bars from a. Stop-priority intrabar; red rule checked on
    the CLOSE after the bar survives stop/tp. red(i, underwater) ->
    True to exit at c[i]. Returns (outcome, net_r)."""
    lng = side == "LONG"
    risk = abs(ent - ps)
    if risk <= 0:
        return None
    rr = abs(tp1 - ent) / risk
    fee_r = 2 * FEE * ent / risk
    for i in range(a, min(b, n)):
        if lng:
            if l[i] <= ps:
                return ("LOSS", -1.0 - fee_r)
            if h[i] >= tp1:
                return ("WIN", rr - fee_r)
        else:
            if h[i] >= ps:
                return ("LOSS", -1.0 - fee_r)
            if l[i] <= tp1:
                return ("WIN", rr - fee_r)
        if red is not None and red(i):
            net = ((c[i] - ent) if lng else (ent - c[i])) / risk - fee_r
            return ("RED", round(net, 4))
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
            tp1 = pe + (pe - ps)
        else:
            ps = float(np.max(h[max(0, t - SWIN + 1):t + 1])) \
                + 0.25 * _atr
            if not (0 < ps - pe <= 4 * _atr):
                ps = pe + 1.5 * _atr
            tp1 = pe - (ps - pe)
        if ps <= 0 or tp1 <= 0:
            continue
        # ── GREEN: the confirmed entry (validated house construct) ──
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

        def _uw(i):
            return (c[i] < ent) if lng else (c[i] > ent)

        def red1(i):
            bad = (c[i] < ema20[i]) if lng else (c[i] > ema20[i])
            return bad and _uw(i)

        def red2(i):
            if i < 2:
                return False
            f2 = ((c[i] < c[i - 1] and c[i - 1] < c[i - 2])
                  if lng else
                  (c[i] > c[i - 1] and c[i - 1] > c[i - 2]))
            return f2 and _uw(i)

        def red3(i):
            lvl = ent - 0.5 * risk if lng else ent + 0.5 * risk
            return (c[i] < lvl) if lng else (c[i] > lvl)

        rec = {"sym": sym, "tier": fr["tier"], "score": fr["score"],
               "half": fr["half"], "t": fr["t"], "side": side}
        for nm, rd in (("plan", None), ("r1", red1), ("r2", red2),
                       ("r3", red3)):
            out = _walk(side, ent, ps, tp1, o, h, l, c, ema20,
                        conf_i + 1, conf_i + 1 + FWD, n, rd)
            rec[nm] = {"o": out[0], "net": round(out[1], 4)} \
                if out else {"o": "OPEN", "net": 0.0}
        rows.append(rec)
    return rows


def _seg(d, pol, label):
    res = [r for r in d if r[pol]["o"] != "OPEN"]
    if not res:
        print(f"  {label:<26} n=0")
        return
    n = len(res)
    w = sum(1 for r in res if r[pol]["net"] > 0) / n * 100
    net = sum(r[pol]["net"] for r in res) / n
    tot = sum(r[pol]["net"] for r in res)
    reds = sum(1 for r in res if r[pol]["o"] == "RED")
    print(f"  {label:<26} n={n:4} win {w:5.1f}% · exp {net:+.3f}R · "
          f"net {tot:+.1f}R · red exits {reds}")


def _report(rows):
    print("\n" + "=" * 74)
    print(f"🟢🔴 GREEN/RED STUDY — {len(rows)} confirmed entries · "
          f"fees in")
    print("=" * 74)
    for pol, nm in (("plan", "PLAN hold to SL/TP1"),
                    ("r1", "RED r1 structure break"),
                    ("r2", "RED r2 two-close fade"),
                    ("r3", "RED r3 half-stop cut")):
        _seg(rows, pol, nm)
    for hf in ("older", "recent"):
        print(f"  --- {hf.upper()} half ---")
        for pol in ("plan", "r1", "r2", "r3"):
            _seg([r for r in rows if r["half"] == hf], pol, pol)
    print("  --- HIGH tier only ---")
    for pol in ("plan", "r1", "r2", "r3"):
        _seg([r for r in rows if r["tier"] == "HIGH"], pol, pol)
    print("  --- MAX tier only ---")
    for pol in ("plan", "r1", "r2", "r3"):
        _seg([r for r in rows if r["tier"] == "MAX"], pol, pol)
    print("=" * 74)


if __name__ == "__main__":
    fires = _load_fires()
    total = sum(len(v) for v in fires.values())
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
    print(f"{len(fires)} coins / {total} fires · resume {len(done)}",
          flush=True)
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
