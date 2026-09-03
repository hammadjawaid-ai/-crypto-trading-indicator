"""⚡ MY WATCH — WAKING (early): does the lane actually work?

The desk shows 7 closed / 100% / +11.82R. Seven straight wins is a real
update from two, but it is five days inside one regime on a board of
~25 tiers, so it needs measuring against history before anyone sizes up.

Replays the EXACT production rule from agent_worker.py:

    the 1h confirm candle has NOT printed, AND close > 1h ema20, AND
    on the 15m chart:  early_trend.detect  score >= 55 side LONG
                       lane_velocity_burst score >= 65 side LONG
    -> buzz, 6h cooldown per coin

Stop and target are the live ones: swing-low structural stop, benchmark
24h-high TP clipped by strength.

APPROXIMATION: production re-checks every 5 minutes and can fire mid-
hour; this evaluates on 1h boundaries and enters at the next 1h open.
That fires less often and slightly later than production, which is the
conservative direction.

1h bars come from .longkl/ (cached). 15m bars are fetched and cached to
.longkl15/ on first run.
"""
import io
import json
import os
import sys
import time

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import numpy as np
import pandas as pd

import binance_client as bc
import config
import early_trend
import smart_stop
import velocity_burst as vb

FEE = 0.00055
MAX_HOLD = 48
DAYS = int(os.environ.get("WAKE_DAYS", "75"))
CACHE1H = ".longkl"
CACHE15 = ".longkl15"
os.makedirs(CACHE15, exist_ok=True)


def klines15(sym, days=DAYS):
    path = os.path.join(CACHE15, f"{sym}_15m.csv")
    if os.path.exists(path):
        d = pd.read_csv(path, index_col=0, parse_dates=True)
        if len(d) >= days * 96 * 0.85:
            return d
    end = int(time.time() * 1000)
    cur = end - days * 96 * 15 * 60 * 1000
    frames = []
    while cur < end:
        try:
            raw = bc._get("/api/v3/klines",
                          {"symbol": sym, "interval": "15m",
                           "startTime": cur, "limit": 1000})
        except Exception:
            break
        if not raw:
            break
        cols = ["open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "trades", "taker_base",
                "taker_quote", "ignore"]
        df = pd.DataFrame(raw, columns=cols)
        num = ["open", "high", "low", "close", "volume"]
        df[num] = df[num].astype(float)
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms",
                                         utc=True)
        frames.append(df.set_index("open_time")[num])
        last = int(raw[-1][0])
        if last <= cur or len(raw) < 1000:
            break
        cur = last + 15 * 60 * 1000
    if not frames:
        return None
    d = pd.concat(frames)
    d = d[~d.index.duplicated(keep="first")].sort_index()
    d.to_csv(path)
    return d


rows = []
for sym in getattr(config, "PERSONAL_WATCH", []):
    p1 = os.path.join(CACHE1H, f"{sym}_1h.csv")
    if not os.path.exists(p1):
        continue
    d1 = pd.read_csv(p1, index_col=0, parse_dates=True)
    d15 = klines15(sym)
    if d15 is None or len(d15) < 400:
        print(f"  {sym:12} no 15m data", flush=True)
        continue
    # restrict the 1h frame to the span the 15m data covers
    d1 = d1[d1.index >= d15.index[0]]
    if len(d1) < 200:
        print(f"  {sym:12} 1h span too short", flush=True)
        continue

    o = d1["open"].to_numpy(); h = d1["high"].to_numpy()
    lo = d1["low"].to_numpy(); c = d1["close"].to_numpy()
    v = d1["volume"].to_numpy()
    ema = d1["close"].ewm(span=20, adjust=False).mean().to_numpy()
    tr = h - lo
    n = len(c)
    pos15 = d15.index.searchsorted(d1.index)      # 15m row per 1h bar
    last_fire = -10**9
    fires = 0

    for i in range(120, n - MAX_HOLD - 2):
        if c[i] <= ema[i]:
            continue
        # production only takes the early lane when the CONFIRM has not
        # printed — same rule, negated
        vma = float(v[i - 20:i].mean())
        confirmed = (c[i] > o[i] and c[i] > c[i - 1] and c[i] > ema[i]
                     and vma > 0 and v[i] > 1.2 * vma)
        if confirmed:
            continue
        if i - last_fire < 6:                     # 6h per-coin cooldown
            continue
        j = int(pos15[i])
        if j < 120:
            continue
        win15 = d15.iloc[max(0, j - 119):j + 1]   # production: limit=120
        if len(win15) < 60:
            continue
        try:
            t15, td15, _ = early_trend.detect(win15)
            b15, bd15, _ = vb.lane_velocity_burst(win15)
        except Exception:
            continue
        if not (t15 >= 55 and td15 == "LONG"
                and b15 >= 65 and (bd15 or "").upper() == "LONG"):
            continue

        entry = float(o[i + 1])
        atr = float(tr[i - 13:i + 1].mean())
        if entry <= 0 or atr <= 0:
            continue
        plan = entry - 1.5 * atr
        try:
            sl = float(smart_stop.structural_stop(
                d1.iloc[:i + 1], "LONG", entry, plan,
                entry + (entry - plan)))
        except Exception:
            sl = plan
        r = entry - sl
        if r <= 0:
            continue
        last_fire = i
        fires += 1

        atr_hist = [float(tr[k - 14:k].mean())
                    for k in range(max(15, i - 99), i + 1)]
        atr_now = float(tr[i - 13:i + 1].mean())
        strong = (sum(1 for x in atr_hist if x < atr_now)
                  / len(atr_hist) >= 0.6) if atr_hist else False
        bench = float(h[i - 23:i + 1].max())
        br = (bench - entry) / r
        blo, bhi = (1.0, 2.5) if strong else (0.75, 1.25)
        clip = min(max(br, blo), bhi) if br > 0 else blo
        tp1 = entry + clip * r

        fee_r = 2 * FEE * entry / r
        out, net = "OPEN", 0.0
        for k in range(i + 1, min(i + 1 + MAX_HOLD, n)):
            if lo[k] <= sl:
                out, net = "LOSS", -1.0 - fee_r
                break
            if h[k] >= tp1:
                out, net = "WIN", clip - fee_r
                break
        if out == "OPEN":
            px = float(c[min(i + MAX_HOLD, n - 1)])
            net = (px - entry) / r - fee_r
            out = "WIN" if net > 0 else "LOSS"
        rows.append({"sym": sym, "ts": str(d1.index[i]), "out": out,
                     "net": round(net, 4), "t15": round(float(t15)),
                     "b15": round(float(b15)), "strong": bool(strong)})
    print(f"  {sym:12} {fires:4} waking fires", flush=True)

rows.sort(key=lambda x: x["ts"])
t = len(rows) // 3
for k, x in enumerate(rows):
    x["third"] = "T1" if k < t else ("T2" if k < 2 * t else "T3")
with open(".waking_rows.jsonl", "w", encoding="utf-8") as f:
    for x in rows:
        f.write(json.dumps(x) + "\n")


def rep(sel, label):
    n = len(sel)
    if not n:
        print(f"  {label:<30} n=0")
        return
    w = sum(1 for x in sel if x["out"] == "WIN") / n * 100
    e = sum(x["net"] for x in sel) / n
    print(f"  {label:<30} n={n:4} · win {w:5.1f}% · {e:+.3f}R")


print("\n" + "=" * 62)
if rows:
    print(f"⚡ WAKING (early) — {len(rows)} fires, "
          f"{rows[0]['ts'][:10]} → {rows[-1]['ts'][:10]}")
    print("=" * 62)
    rep(rows, "ALL waking fires")
    for th in ("T1", "T2", "T3"):
        rep([x for x in rows if x["third"] == th], f"  {th}")
    rep([x for x in rows if x["strong"]], "STRONG entries")
    rep([x for x in rows if not x["strong"]], "quiet entries")
    rep([x for x in rows if x["b15"] >= 80], "15m burst >= 80")
    rep([x for x in rows if x["t15"] >= 70], "15m trend >= 70")
else:
    print("no fires")
print("=" * 62)
