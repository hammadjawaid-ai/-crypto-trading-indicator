"""CONTINUATION vs EXHAUSTION overnight test — once a coin has FLOWN to a
certain extent, does it keep running (ride / stay long) or reverse (pull
back / short it)? Both directions. The top-tier-trader question.

Honest prior (must be respected): extension alone is ambiguous — a strong
trend staying extended is momentum ("let winners run"), while extension +
exhaustion signals can mark a top. Which wins is exactly what we measure.
NO prediction of the future price — only: do measurable exhaustion features
(distance-from-mean, upper-wick rejection, volume climax, up-streak, ROC)
separate CONTINUATION from REVERSAL at an already-extended moment?

At each bar where the coin is EXTENDED up (close > EMA20 + 1.5×ATR, uptrend):
  features: ext=(c-ema20)/atr · ext50 · wick ratio · vol/vma · up-streak · roc6
  forward (24 bars) first-touch: +1×ATR new high (CONTINUATION) vs −1×ATR
  pullback (REVERSAL/short-profit) — which comes first.
Mirror for extended-down (short continuation vs bounce).

Report, per feature bucket, the CONTINUATION% — so we can see which signals,
if any, flip the odds toward "keep riding" or "expect a pullback/short".
A real edge = a bucket whose continuation% is clearly ≠ base rate.
Measurement only. Chunked + checkpointed (EX_MAX_NEW).
"""
from __future__ import annotations
import sys, io, time, os, json
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client, indicators

N_COINS = 40
MAX_NEW = int(os.environ.get("EX_MAX_NEW", "14"))
BARS = 1500
WARMUP = 120
K = 3
FWD = 24
EXT_MIN = 1.5            # "flown to a certain extent" = >=1.5 ATR from EMA20
CONT_ATR = 1.0          # new-extreme target that = continuation
REV_ATR = 1.0           # opposite move that = reversal/pullback
ROWS_FILE = ".exhaust_rows.jsonl"


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


def _one(sym):
    try:
        d1 = indicators.enrich(binance_client.get_klines(sym, "1h", limit=BARS))
    except Exception:
        return []
    if d1 is None or len(d1) < WARMUP + FWD + 5:
        return []
    o = d1["open"].to_numpy(); h = d1["high"].to_numpy()
    l = d1["low"].to_numpy(); c = d1["close"].to_numpy()
    v = d1["volume"].to_numpy()
    ema20 = d1["close"].ewm(span=20, adjust=False).mean().to_numpy()
    ema50 = d1["close"].ewm(span=50, adjust=False).mean().to_numpy()
    vma = pd.Series(v).rolling(20).mean().to_numpy()
    atr = _atr(h, l, c, 14)
    rsi = _rsi(c, 14)
    n = len(d1); rows = []
    for t in range(WARMUP, n - FWD - 1, K):
        a = float(atr[t])
        if a <= 0 or vma[t] <= 0:
            continue
        up_ext = (c[t] - ema20[t]) / a
        dn_ext = (ema20[t] - c[t]) / a
        # only extended moments, aligned with the prevailing trend
        long_case = up_ext >= EXT_MIN and c[t] > ema20[t] > ema50[t]
        short_case = dn_ext >= EXT_MIN and c[t] < ema20[t] < ema50[t]
        if not (long_case or short_case):
            continue
        side = "LONG" if long_case else "SHORT"
        rng = max(h[t] - l[t], 1e-9)
        if side == "LONG":
            wick = (h[t] - max(o[t], c[t])) / rng           # upper wick
            streak = 0
            for j in range(t, max(t-8, 0), -1):
                if c[j] > o[j]:
                    streak += 1
                else:
                    break
            ext = up_ext; ext50 = (c[t] - ema50[t]) / a
        else:
            wick = (min(o[t], c[t]) - l[t]) / rng           # lower wick
            streak = 0
            for j in range(t, max(t-8, 0), -1):
                if c[j] < o[j]:
                    streak += 1
                else:
                    break
            ext = dn_ext; ext50 = (ema50[t] - c[t]) / a
        volspike = v[t] / vma[t]
        roc6 = abs(c[t] / c[t-6] - 1.0) * 100 if t >= 6 else 0.0
        # forward first-touch: continuation (new extreme) vs reversal
        cont_lvl = (c[t] + CONT_ATR * a) if side == "LONG" \
            else (c[t] - CONT_ATR * a)
        rev_lvl = (c[t] - REV_ATR * a) if side == "LONG" \
            else (c[t] + REV_ATR * a)
        outcome = "CHOP"
        for fb in range(t+1, min(t+1+FWD, n)):
            if side == "LONG":
                hit_cont = h[fb] >= cont_lvl
                hit_rev = l[fb] <= rev_lvl
            else:
                hit_cont = l[fb] <= cont_lvl
                hit_rev = h[fb] >= rev_lvl
            if hit_cont and hit_rev:
                outcome = "CONT"      # same-bar tie → favor continuation
                break
            if hit_cont:
                outcome = "CONT"; break
            if hit_rev:
                outcome = "REV"; break
        rows.append({
            "side": side,
            "ext": round(float(ext), 2), "ext50": round(float(ext50), 2),
            "wick": round(float(wick), 3), "vol": round(float(volspike), 2),
            "streak": int(streak), "roc6": round(float(roc6), 2),
            "rsi": round(float(rsi[t]), 1) if rsi[t] == rsi[t] else None,
            "o": outcome})
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


def _cont_pct(rs):
    dec = [r for r in rs if r["o"] in ("CONT", "REV")]
    cont = sum(1 for r in dec if r["o"] == "CONT")
    return (cont / len(dec) * 100 if dec else 0.0), len(dec)


def bucket(label, rows, key, edges):
    print(f"--- {label} ---")
    prev = -1e9
    for e in edges + [1e9]:
        seg = [r for r in rows if prev <= r.get(key, 0) < e]
        pct, nd = _cont_pct(seg)
        lo = "-inf" if prev == -1e9 else f"{prev:g}"
        hi = "inf" if e == 1e9 else f"{e:g}"
        print(f"  {key} {lo:>5}..{hi:<5} | n={nd:5} | CONT {pct:5.1f}% "
              f"| REV {100-pct:5.1f}%")
        prev = e


syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]
rows, done = _load()
todo = [s for s in syms if s not in done][:MAX_NEW]
print(f"Resume: {len(done)} done ({len(rows)} extended moments). "
      f"This run: {todo}")
t0 = time.time()
with ThreadPoolExecutor(max_workers=min(4, len(todo) or 1)) as pool:
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
print("\n" + "=" * 66)
_tag = "COMPLETE" if len(done2) >= N_COINS else f"PARTIAL {len(done2)}/{N_COINS}"
print(f"CONTINUATION vs EXHAUSTION [{_tag}] — {len(rows)} extended moments")
print("=" * 66)
base, nd = _cont_pct(rows)
print(f"BASE RATE: {base:.1f}% continue / {100-base:.1f}% reverse "
      f"(n={nd}). An edge = a bucket clearly off this base.")
print("-" * 66)
bucket("EXTENSION from EMA20 (ATR)", rows, "ext", [2, 3, 4])
bucket("UPPER/LOWER WICK ratio (rejection)", rows, "wick", [0.2, 0.4, 0.6])
bucket("VOLUME climax (v/vma)", rows, "vol", [1.0, 2.0, 3.0])
bucket("UP/DOWN streak (candles)", rows, "streak", [2, 4, 6])
bucket("RSI", rows, "rsi", [50, 70, 80])
print("=" * 66)
print("Read: buckets with CONT% >> base → keep riding. CONT% << base → "
      "exhaustion, expect pullback/short. Flat → no edge (honest null).")
if len(done2) < N_COINS:
    print(f">> Re-run to add {min(MAX_NEW, N_COINS-len(done2))} more coins.")
print(f"Done in {time.time()-t0:.0f}s.")
