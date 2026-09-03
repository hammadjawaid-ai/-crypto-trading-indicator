"""🟢 PERSONAL WATCH — confirmed-entry win rate across the coin list.

Replays the EXACT production rule from agent_worker.py's personal-watch
block over every coin in config.PERSONAL_WATCH, walk-forward, no
lookahead:

  confirm bar i  = green (c>o) AND c[i] > c[i-1] AND c[i] > ema20[i]
                   AND volume[i] > 1.2 x mean(volume[i-20:i])
  dip filter     = 2+ of bars i-5..i-1 closed red or under ema20
  entry          = OPEN of bar i+1 (the honest stand-in for "live price
                   the moment the confirm bar closes")
  stop           = smart_stop.structural_stop on history <= i
  benchmark TP1  = 24h high (24 bars ending at i), clipped by strength:
                   STRONG (hot ATR or 1h burst>=65 LONG) -> [1.0R, 2.5R]
                   quiet                                 -> [0.75R, 1.25R]
  resolve        = walk forward up to 48 bars; stop checked BEFORE
                   target within the same bar (conservative)
  conf           = _conf_votes ladder (25 + 20 x votes) — production
                   buzzes the 🟢 confirm only at conf >= 65

Reports all confirms, the conf>=65 subset that actually reaches the
phone, and both history halves (nothing ships unless both are green).
"""
import io
import sys
from collections import defaultdict

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import numpy as np

import binance_client
import config
import smart_stop
import velocity_burst as vb

FEE = 0.00055          # taker, each way
MAX_HOLD = 48          # bars (48h time-stop, same as the desk)
BARS = 1500            # ~62 days of 1h history


def _pct_rank_hot(hist, now):
    return (len(hist) >= 30
            and sum(1 for x in hist if x < now) / len(hist) >= 0.6)


def conf_at(h, l, c, i):
    """_conf_votes replayed at bar i (history <= i only)."""
    if i < 40:
        return None
    tr = h - l
    atr_now = float(tr[i - 13:i + 1].mean())
    hist = [float(tr[j - 14:j].mean())
            for j in range(max(15, i - 99), i + 1)]
    hot = _pct_rank_hot(hist, atr_now)
    roc_now = float(c[i] / c[i - 6] - 1)
    rh = [float(c[j] / c[j - 6] - 1) for j in range(max(7, i - 99), i + 1)]
    hotroc = _pct_rank_hot(rh, roc_now)
    return hot, hotroc, atr_now, hist


rows = []
skipped = []
syms = list(getattr(config, "PERSONAL_WATCH", []))
print(f"scanning {len(syms)} coins x {BARS} 1h bars…", flush=True)

for sym in syms:
    try:
        d = binance_client.get_klines(sym, "1h", limit=BARS)
    except Exception as exc:
        skipped.append((sym, f"{type(exc).__name__}"))
        continue
    if d is None or len(d) < 200:
        skipped.append((sym, f"only {0 if d is None else len(d)} bars"))
        continue
    o = d["open"].to_numpy()
    h = d["high"].to_numpy()
    l = d["low"].to_numpy()
    c = d["close"].to_numpy()
    v = d["volume"].to_numpy()
    ema = d["close"].ewm(span=20, adjust=False).mean().to_numpy()
    n = len(c)
    n_fires = 0

    for i in range(120, n - MAX_HOLD - 2):
        vma = float(v[i - 20:i].mean())
        if not (c[i] > o[i] and c[i] > c[i - 1] and c[i] > ema[i]
                and vma > 0 and v[i] > 1.2 * vma):
            continue
        dip = sum(1 for k in range(i - 5, i)
                  if c[k] < o[k] or c[k] < ema[k]) >= 2
        if not dip:
            continue

        entry = float(o[i + 1])
        if entry <= 0:
            continue
        atr = float((h[i - 13:i + 1] - l[i - 13:i + 1]).mean())
        if atr <= 0:
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

        cv = conf_at(h, l, c, i)
        if cv is None:
            continue
        hot, hotroc, _atr_now, _hist = cv
        try:
            bs, bd, _ = vb.lane_velocity_burst(d.iloc[:i + 1])
        except Exception:
            bs, bd = 0.0, ""
        long_side = (bd or "").upper() == "LONG"
        votes = int(hot) + int(hotroc) + int(bs >= 78 and long_side)
        conf = min(98, 25 + 20 * votes)

        strong = hot or (bs >= 65 and long_side)
        bench = float(h[i - 23:i + 1].max())
        br = (bench - entry) / r
        lo, hi = (1.0, 2.5) if strong else (0.75, 1.25)
        clip = min(max(br, lo), hi) if br > 0 else lo
        tp1 = entry + clip * r

        fee_r = 2 * FEE * entry / r
        out, net = "OPEN", 0.0
        for j in range(i + 1, min(i + 1 + MAX_HOLD, n)):
            if l[j] <= sl:                       # stop first — conservative
                out, net = "LOSS", -1.0 - fee_r
                break
            if h[j] >= tp1:
                out, net = "WIN", clip - fee_r
                break
        if out == "OPEN":                        # 48h time-stop
            px = float(c[min(i + MAX_HOLD, n - 1)])
            net = (px - entry) / r - fee_r
            out = "WIN" if net > 0 else "LOSS"

        rows.append({"sym": sym, "i": i, "conf": conf, "out": out,
                     "net": net, "strong": strong, "clip": clip})
        n_fires += 1
    print(f"  {sym:12} {n_fires:4} confirms", flush=True)

if skipped:
    print("\n  skipped:", skipped)

# both-halves split by bar index within each coin's own history
by_sym = defaultdict(list)
for x in rows:
    by_sym[x["sym"]].append(x)
for s, xs in by_sym.items():
    xs.sort(key=lambda z: z["i"])
    mid = len(xs) // 2
    for k, x in enumerate(xs):
        x["half"] = "older" if k < mid else "recent"


def rep(sel, label, thin=20):
    n = len(sel)
    if n == 0:
        print(f"  {label:<34} n=0")
        return
    w = sum(1 for x in sel if x["out"] == "WIN") / n * 100
    e = sum(x["net"] for x in sel) / n
    flag = "  ⚠️ thin" if n < thin else ""
    print(f"  {label:<34} n={n:4} · win {w:5.1f}% · {e:+.3f}R{flag}")


print("\n" + "=" * 62)
print(f"🟢 CONFIRMED ENTRIES — {len(rows)} across {len(by_sym)} coins")
print("=" * 62)
rep(rows, "ALL confirms")
print("  ---  what actually buzzes (production gate conf >= 65)")
rep([x for x in rows if x["conf"] >= 65], "conf >= 65  ← THE BUZZ")
for hf in ("older", "recent"):
    rep([x for x in rows if x["conf"] >= 65 and x["half"] == hf],
        f"   conf>=65 {hf}")
print("  ---  the ones held back")
rep([x for x in rows if x["conf"] < 65], "conf < 65 (silent)")
print("  ---  by conf band")
for vt in (0, 1, 2, 3):
    rep([x for x in rows if x["conf"] == min(98, 25 + 20 * vt)],
        f"conf {min(98, 25 + 20 * vt)} ({vt} votes)")
print("  ---  by strength (TP clip band)")
rep([x for x in rows if x["strong"]], "STRONG (1.0-2.5R target)")
rep([x for x in rows if not x["strong"]], "quiet (0.75-1.25R target)")

print("\n  === per coin, conf>=65 only ===")
for s in syms:
    rep([x for x in rows if x["sym"] == s and x["conf"] >= 65],
        s.replace("USDT", ""), thin=10)
print("=" * 62)
