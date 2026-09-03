"""🎯 The ATR ladder on a LONG sample — is it an edge or a lucky regime?

The 62-day run (backtest_confladder) showed every gate negative in the
older half and strongly positive in the recent half — including the
do-nothing baseline. That is the signature of a regime split, not of a
filter, and 1500 bars is not enough to tell them apart.

This paginates Binance klines back as far as each coin goes (up to ~1
year of 1h), caches the frames under .longkl/, and reruns the same
extraction across THIRDS so a gate has to survive three different tapes,
not one lucky half.

DELIBERATE SIMPLIFICATION: lane_velocity_burst is skipped here (it is
the runtime bottleneck and it already failed the stability test —
older +0.160R / recent -0.182R). Strength for the TP clip is therefore
`atr_pct >= 0.6` alone rather than `hot ATR OR burst>=65`, so the clip
differs from production on a minority of quiet-but-bursting fires.
Everything about the ATR ladder itself is unaffected.
"""
import io
import json
import os
import sys
import time

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import pandas as pd

import binance_client as bc
import config
import smart_stop

FEE = 0.00055
MAX_HOLD = 48
CACHE = ".longkl"
TARGET_BARS = 8760          # ~1 year of 1h
OUT = ".pwlong_rows.jsonl"
os.makedirs(CACHE, exist_ok=True)


def long_klines(sym, want=TARGET_BARS):
    """Paginate /api/v3/klines backwards via startTime. Cached to disk."""
    path = os.path.join(CACHE, f"{sym}_1h.csv")
    if os.path.exists(path):
        d = pd.read_csv(path, index_col=0, parse_dates=True)
        if len(d) >= min(want, 2000) * 0.9:
            return d
    end = int(time.time() * 1000)
    start = end - want * 3600 * 1000
    frames, cur = [], start
    while cur < end:
        try:
            raw = bc._get("/api/v3/klines",
                          {"symbol": sym, "interval": "1h",
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
        cur = last + 3600 * 1000
    if not frames:
        return None
    d = pd.concat(frames)
    d = d[~d.index.duplicated(keep="first")].sort_index()
    d.to_csv(path)
    return d


def pct_below(hist, now):
    return sum(1 for x in hist if x < now) / len(hist) if hist else 0.0


rows = []
syms = list(getattr(config, "PERSONAL_WATCH", []))
for sym in syms:
    d = long_klines(sym)
    if d is None or len(d) < 300:
        print(f"  {sym:12} skipped ({0 if d is None else len(d)} bars)",
              flush=True)
        continue
    o = d["open"].to_numpy(); h = d["high"].to_numpy()
    lo = d["low"].to_numpy(); c = d["close"].to_numpy()
    v = d["volume"].to_numpy()
    ema = d["close"].ewm(span=20, adjust=False).mean().to_numpy()
    tr = h - lo
    n = len(c)
    fires = 0
    for i in range(120, n - MAX_HOLD - 2):
        vma = float(v[i - 20:i].mean())
        if not (c[i] > o[i] and c[i] > c[i - 1] and c[i] > ema[i]
                and vma > 0 and v[i] > 1.2 * vma):
            continue
        if sum(1 for k in range(i - 5, i)
               if c[k] < o[k] or c[k] < ema[k]) < 2:
            continue
        entry = float(o[i + 1])
        atr = float(tr[i - 13:i + 1].mean())
        if entry <= 0 or atr <= 0:
            continue
        plan = entry - 1.5 * atr
        try:
            sl = float(smart_stop.structural_stop(
                d.iloc[:i + 1], "LONG", entry, plan,
                entry + (entry - plan)))
        except Exception:
            sl = plan
        r = entry - sl
        if r <= 0:
            continue
        atr_hist = [float(tr[j - 14:j].mean())
                    for j in range(max(15, i - 99), i + 1)]
        atr_pct = pct_below(atr_hist, float(tr[i - 13:i + 1].mean()))
        roc_now = float(c[i] / c[i - 6] - 1)
        roc_hist = [float(c[j] / c[j - 6] - 1)
                    for j in range(max(7, i - 99), i + 1)]
        roc_pct = pct_below(roc_hist, roc_now)
        since_dip = 0
        for k in range(i, max(i - 20, 0), -1):
            if c[k] < o[k] or c[k] < ema[k]:
                break
            since_dip += 1
        strong = atr_pct >= 0.6
        bench = float(h[i - 23:i + 1].max())
        br = (bench - entry) / r
        blo, bhi = (1.0, 2.5) if strong else (0.75, 1.25)
        clip = min(max(br, blo), bhi) if br > 0 else blo
        tp1 = entry + clip * r
        fee_r = 2 * FEE * entry / r
        out, net = "OPEN", 0.0
        for j in range(i + 1, min(i + 1 + MAX_HOLD, n)):
            if lo[j] <= sl:
                out, net = "LOSS", -1.0 - fee_r
                break
            if h[j] >= tp1:
                out, net = "WIN", clip - fee_r
                break
        if out == "OPEN":
            px = float(c[min(i + MAX_HOLD, n - 1)])
            net = (px - entry) / r - fee_r
            out = "WIN" if net > 0 else "LOSS"
        rows.append({"sym": sym, "i": i, "ts": str(d.index[i]),
                     "out": out, "net": round(net, 4),
                     "atr_pct": round(atr_pct, 3),
                     "roc_pct": round(roc_pct, 3),
                     "dist_ema": round((entry - float(ema[i])) / entry * 100,
                                       3),
                     "since_dip": since_dip})
        fires += 1
    print(f"  {sym:12} {len(d):5} bars → {fires:4} confirms", flush=True)

# thirds by calendar time across the whole pooled sample
rows.sort(key=lambda r: r["ts"])
t = len(rows) // 3
for k, r in enumerate(rows):
    r["third"] = "T1" if k < t else ("T2" if k < 2 * t else "T3")
with open(OUT, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")


def stat(sel):
    n = len(sel)
    if not n:
        return 0, 0.0, 0.0
    w = sum(1 for r in sel if r["out"] == "WIN") / n * 100
    return n, w, sum(r["net"] for r in sel) / n


def show(pred, label):
    sel = [r for r in rows if pred(r)]
    n, w, e = stat(sel)
    if not n:
        print(f"  {label:<34} n=0")
        return
    parts, ok = [], True
    for th in ("T1", "T2", "T3"):
        tn, tw, te = stat([r for r in sel if r["third"] == th])
        parts.append(f"{th} {tw:4.1f}%/{te:+.3f}")
        if te <= 0:
            ok = False
    print(f"  {'✅' if ok else '  '} {label:<32} n={n:5} · win {w:5.1f}%"
          f" · {e:+.3f}R    {'  '.join(parts)}")


print("\n" + "=" * 78)
print(f"🎯 LONG SAMPLE — {len(rows)} confirms, {rows[0]['ts'][:10]} → "
      f"{rows[-1]['ts'][:10]}")
print("   ✅ = profitable in ALL THREE thirds")
print("=" * 78)
show(lambda r: True, "no gate — every confirm")
print()
for cut in (0.50, 0.60, 0.70, 0.80, 0.90):
    show(lambda r, c=cut: r["atr_pct"] >= c, f"HOT ATR pct >= {cut:.2f}")
print()
show(lambda r: r["atr_pct"] >= 0.6 and r["roc_pct"] >= 0.6,
     "ATR>=.60 AND ROC>=.60 (conf 65)")
show(lambda r: r["atr_pct"] >= 0.8 and r["since_dip"] <= 2,
     "ATR>=.80 AND fresh (dip<=2)")
show(lambda r: r["atr_pct"] >= 0.8 and r["dist_ema"] >= 1.0,
     "ATR>=.80 AND ema stretch>=1%")
print("=" * 78)
