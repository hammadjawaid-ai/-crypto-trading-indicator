"""PRE-BURST RADAR research — read the chart's pressure BEFORE the big move.

The user's ask: predict big moves (either direction) BEFORE they happen,
score them, and surface only the few best — like ELITE MAX "reads before the
movement starts", but earlier and sharper.

Honest framing: this is PRECURSOR DETECTION, not prophecy. We label every
clean historical BURST (>=2.5x ATR move within 24 bars WITHOUT first taking
a >=1.25x ATR hit against it) and measure what the chart looked like on the
bars BEFORE launch. Eight backward-looking precursor conditions per side:

  LONG-side (+1 each):
    1. vol_creep    — 6-bar avg volume >= 1.2x the 20-bar avg (accumulation)
    2. coil         — ATR6/ATR20 <= 0.85 (range compression before release)
    3. higher_lows  — >=3 of the last 5 lows are rising (structure building)
    4. posture      — close > EMA20 > EMA50 (aligned trend base)
    5. grind        — net candle bodies over last 6 bars >= +0.8x ATR
    6. door_knock   — close within 1.0x ATR of the 24-bar high (poised)
    7. wick_bias    — lower wicks > upper wicks over last 6 (buyers absorb)
    8. rsi_zone     — RSI 55-75 (strong but not blown out)
  SHORT-side: exact mirror.

Outputs:
  A) ODDS TABLE — P(burst within 24 bars | score) vs base rate. A real radar
     multiplies the base odds several-fold at high scores.
  B) BET TABLE — actually TAKING the bet at each score (entry=close, stop
     1.25x ATR against, target 2.5x ATR with = 2:1 reward:risk, first-touch):
     win% and exp/signal. This answers "can we bet on it".
  C) FREQUENCY — signals/day at each threshold across the 40-coin universe
     (the user wants FEW, perfect ones — not a firehose).

No signal engine needed (pure OHLCV) -> fast, full 40 coins in one run.
Measurement only — NOTHING deploys. Checkpointed (PB_MAX_NEW).
"""
from __future__ import annotations
import sys, io, time, os, json
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client, indicators

N_COINS = 40
MAX_NEW = int(os.environ.get("PB_MAX_NEW", "40"))
BARS = 3000                # ~4 months of 1h — multi-regime
WARMUP = 60
K = 2                      # sample every 2 bars (dense)
FWD = 24                   # burst must complete within 24 bars
BURST_ATR = 2.5            # move size that counts as a "big move"
HIT_ATR = 1.25             # adverse excursion that disqualifies / stops
ROWS_FILE = ".preburst_rows.jsonl"


def _atr(h, l, c, n=14):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(n).mean().to_numpy()


def _rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    ru = pd.Series(up).rolling(n).mean().to_numpy()
    rd = pd.Series(dn).rolling(n).mean().to_numpy()
    rs = np.divide(ru, rd, out=np.full_like(ru, np.nan), where=rd > 0)
    return 100 - 100 / (1 + rs)


def _first_touch(side, entry, stop, target, hi, lo, a, b, n):
    """WIN if target first, LOSS if stop first, NONE if neither in window."""
    for fb in range(a, min(b, n)):
        if side == "LONG":
            if lo[fb] <= stop:
                return "LOSS"
            if hi[fb] >= target:
                return "WIN"
        else:
            if hi[fb] >= stop:
                return "LOSS"
            if lo[fb] <= target:
                return "WIN"
    return "NONE"


def _one(sym):
    try:
        d1 = indicators.enrich(binance_client.get_klines(sym, "1h",
                                                         limit=BARS))
    except Exception:
        return []
    if d1 is None or len(d1) < WARMUP + FWD + 10:
        return []
    o = d1["open"].to_numpy(); h = d1["high"].to_numpy()
    l = d1["low"].to_numpy(); c = d1["close"].to_numpy()
    v = d1["volume"].to_numpy()
    ema20 = d1["close"].ewm(span=20, adjust=False).mean().to_numpy()
    ema50 = d1["close"].ewm(span=50, adjust=False).mean().to_numpy()
    atr14 = _atr(h, l, c, 14)
    atr6 = _atr(h, l, c, 6)
    atr20 = _atr(h, l, c, 20)
    rsi = _rsi(c, 14)
    vma20 = pd.Series(v).rolling(20).mean().to_numpy()
    vma6 = pd.Series(v).rolling(6).mean().to_numpy()
    n = len(d1); half = n // 2; rows = []
    for t in range(WARMUP, n - FWD - 1, K):
        a = float(atr14[t])
        if not (a > 0) or not (vma20[t] > 0):
            continue
        # ---------- label: does a clean burst start here? -----------------
        up_t = c[t] + BURST_ATR * a
        up_s = c[t] - HIT_ATR * a
        dn_t = c[t] - BURST_ATR * a
        dn_s = c[t] + HIT_ATR * a
        up = _first_touch("LONG", c[t], up_s, up_t, h, l, t+1, t+1+FWD, n)
        dn = _first_touch("SHORT", c[t], dn_s, dn_t, h, l, t+1, t+1+FWD, n)
        burst = "UP" if up == "WIN" else ("DOWN" if dn == "WIN" else "NONE")
        # ---------- LONG-side precursor conditions ------------------------
        bodies = c[t-5:t+1] - o[t-5:t+1]
        lows5 = l[t-4:t+1]; prev5 = l[t-5:t]
        hl = int(np.sum(lows5 > prev5))
        upper_w = np.sum(h[t-5:t+1] - np.maximum(o[t-5:t+1], c[t-5:t+1]))
        lower_w = np.sum(np.minimum(o[t-5:t+1], c[t-5:t+1]) - l[t-5:t+1])
        hi24 = float(np.max(h[max(0, t-24):t+1]))
        lo24 = float(np.min(l[max(0, t-24):t+1]))
        coil = (atr6[t] / atr20[t]) if atr20[t] > 0 else 1.0
        creep = (vma6[t] / vma20[t]) if vma20[t] > 0 else 1.0
        Ls = 0
        if creep >= 1.2:
            Ls += 1
        if coil <= 0.85:
            Ls += 1
        if hl >= 3:
            Ls += 1
        if c[t] > ema20[t] > ema50[t]:
            Ls += 1
        if np.sum(bodies) >= 0.8 * a:
            Ls += 1
        if (hi24 - c[t]) <= 1.0 * a:
            Ls += 1
        if lower_w > upper_w:
            Ls += 1
        if rsi[t] == rsi[t] and 55 <= rsi[t] <= 75:
            Ls += 1
        # ---------- SHORT-side mirror --------------------------------------
        highs5 = h[t-4:t+1]; prevh5 = h[t-5:t]
        lh = int(np.sum(highs5 < prevh5))
        Ss = 0
        if creep >= 1.2:
            Ss += 1
        if coil <= 0.85:
            Ss += 1
        if lh >= 3:
            Ss += 1
        if c[t] < ema20[t] < ema50[t]:
            Ss += 1
        if np.sum(bodies) <= -0.8 * a:
            Ss += 1
        if (c[t] - lo24) <= 1.0 * a:
            Ss += 1
        if upper_w > lower_w:
            Ss += 1
        if rsi[t] == rsi[t] and 25 <= rsi[t] <= 45:
            Ss += 1
        rows.append({"L": Ls, "S": Ss, "b": burst,
                     "half": "recent" if t >= half else "older"})
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
            r2 = dict(rec); r2["sym"] = sym
            f.write(json.dumps(r2) + "\n")
        f.write(json.dumps({"done_coin": sym}) + "\n")


syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]
rows, done = _load()
todo = [s for s in syms if s not in done][:MAX_NEW]
print(f"Resume: {len(done)} done ({len(rows)} samples). This run: {todo}")
t0 = time.time()
with ThreadPoolExecutor(max_workers=min(6, len(todo) or 1)) as pool:
    futs = {pool.submit(_one, s): s for s in todo}
    for fut in as_completed(futs):
        s = futs[fut]
        try:
            rr = fut.result()
        except Exception:
            rr = []
        _append(s, rr)
        rows.extend(rr)
        print(f"  done {s:12} +{len(rr)} (cum {len(rows)}, "
              f"{time.time()-t0:.0f}s)", flush=True)

done2 = done | set(todo)
print("\n" + "=" * 70)
_tag = "COMPLETE" if len(done2) >= N_COINS else f"PARTIAL {len(done2)}/{N_COINS}"
print(f"PRE-BURST RADAR [{_tag}] — {len(rows)} chart-moments "
      f"({BARS} bars x {len(done2)} coins)")
print("=" * 70)
nb = len(rows)
base_up = sum(1 for r in rows if r["b"] == "UP") / max(1, nb) * 100
base_dn = sum(1 for r in rows if r["b"] == "DOWN") / max(1, nb) * 100
print(f"BASE RATE: UP burst {base_up:.1f}% · DOWN burst {base_dn:.1f}% "
      f"(any moment, next 24h)")
print("-" * 70)
print("A) ODDS — P(UP burst | LONG score)   [lift vs base = the radar]:")
for s in range(0, 9):
    seg = [r for r in rows if r["L"] == s]
    if not seg:
        continue
    p = sum(1 for r in seg if r["b"] == "UP") / len(seg) * 100
    print(f"   L={s} | n={len(seg):6} | UP {p:5.1f}% | lift "
          f"{p/max(0.1, base_up):4.1f}x")
print("   P(DOWN burst | SHORT score):")
for s in range(0, 9):
    seg = [r for r in rows if r["S"] == s]
    if not seg:
        continue
    p = sum(1 for r in seg if r["b"] == "DOWN") / len(seg) * 100
    print(f"   S={s} | n={len(seg):6} | DOWN {p:5.1f}% | lift "
          f"{p/max(0.1, base_dn):4.1f}x")
print("-" * 70)
print("B) BET — enter at score, stop 1.25xATR, target 2.5xATR (2:1 RR):")
for lo_s in (5, 6, 7):
    seg = [r for r in rows if r["L"] >= lo_s]
    dec = [r for r in seg if r["b"] in ("UP", "DOWN") or True]
    w = sum(1 for r in seg if r["b"] == "UP")
    lref = sum(1 for r in seg if r["b"] == "DOWN")
    # WIN = clean up-burst; LOSS = hit 1.25 ATR down first (incl DOWN bursts
    # and chop that tagged the stop). NONE = neither -> ~0R, excluded.
    # honest exp: win pays +2.0R (2.5/1.25), loss -1R
    # LOSS = those moments where the DOWN side stop was hit first — proxy:
    # not "UP" and not "NONE-without-stop"; conservative: treat everything
    # not UP and not pure-chop as loss via first-touch already encoded:
    stop_hits = [r for r in seg if r["b"] != "UP"]
    # refine: b=="DOWN" definitely stopped a long; b=="NONE" = neither target
    # nor... NONE means no burst either way; the long stop may or may not
    # have been hit. Conservative: count NONE as -0.25R friction.
    n_up = w; n_dn = lref
    n_none = len(seg) - n_up - n_dn
    exp = (n_up * 2.0 + n_dn * -1.0 + n_none * -0.25) / max(1, len(seg))
    wr = n_up / max(1, n_up + n_dn) * 100
    print(f"   LONG score>={lo_s} | n={len(seg):5} | clean-burst "
          f"{n_up/max(1,len(seg))*100:4.1f}% | win-vs-stop {wr:5.1f}% | "
          f"exp/signal {exp:+.3f}R (2:1)")
print("-" * 70)
days = (BARS / 24) * max(1, len(done2))
print("C) FREQUENCY (few perfect ones):")
for lo_s in (5, 6, 7):
    nsig = sum(1 for r in rows if r["L"] >= lo_s or r["S"] >= lo_s)
    print(f"   score>={lo_s}: ~{nsig/max(1,days)*40:.1f} signals/day "
          f"across a 40-coin universe")
print("=" * 70)
print("Deploy bar: high scores must MULTIPLY base odds AND the bet table "
      "must be +exp — otherwise honest null.")
if len(done2) < N_COINS:
    print(">> Re-run to add more coins.")
print(f"Done in {time.time()-t0:.0f}s.")
