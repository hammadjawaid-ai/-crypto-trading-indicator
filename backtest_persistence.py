"""SIGNAL-PERSISTENCE edge test (user idea 2026-06-18, refined).

The real question: a STRONG/MAX ELITE setup that KEEPS FIRING (re-
confirms the same coin+side) over many hours — does its win rate rise
the longer it stays alive AND firing? (fresh -> 6h -> 24h -> 48h+)

This is DIFFERENT from the earlier 'price-idle' test. Here we track how
long the SIGNAL itself persists, then measure the forward win rate as a
function of that persistence.

Method (walk-forward, no lookahead, chunked + threaded):
  - Sample ELITE score_from_data every K=4 bars (4h).
  - A bar 'fires' if score>=80 and side in LONG/SHORT (STRONG+).
  - persistence = # of consecutive prior sample-bars that fired the SAME
    side. persistence_hours = persistence * 4.
  - Forward outcome = TP1 before SL over the next FWD bars, using the
    plan (stop/tp1) at that bar.
  - Bucket win rate by persistence so we see if 'still firing 24h+/48h+'
    wins more.
Re-run to add MAX_NEW coins per pass (checkpointed).
"""
from __future__ import annotations
import sys, io, time, os, json
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client, indicators
import experimental_signals as es

N_COINS = 40
MAX_NEW = int(os.environ.get("PER_MAX_NEW", "10"))
BARS = 1500
WARMUP = 220
K = 4            # sample every 4 bars = 4h
FWD = 24         # measure outcome over next 24h from the entry bar
SCORE_FLOOR = 80.0
ROWS_FILE = ".persist_rows.jsonl"

def _outcome(side, stop, tp1, hi, lo, t, n):
    for fb in range(t + 1, min(t + FWD + 1, n)):
        h = hi[fb]; l = lo[fb]
        if side == "LONG":
            if l <= stop:
                return "LOSS"
            if h >= tp1:
                return "WIN"
        else:
            if h >= stop:
                return "LOSS"
            if l <= tp1:
                return "WIN"
    return "NONE"

def _one(sym):
    try:
        d1 = indicators.enrich(binance_client.get_klines(sym, "1h", limit=BARS))
        d4 = indicators.enrich(binance_client.get_klines(sym, "4h", limit=400))
    except Exception:
        return []
    if d1 is None or len(d1) < WARMUP + FWD + 5:
        return []
    d4i = d4.copy()
    hi = d1["high"].to_numpy(); lo = d1["low"].to_numpy()
    n = len(d1)
    samples = list(range(WARMUP, n - FWD - 1, K))
    # pass 1: score each sample bar
    fired = {}   # idx -> (side, tier, stop, tp1)
    for t in samples:
        s1 = d1.iloc[:t+1]; ts = s1.index[-1]
        try:
            s4 = d4i[d4i.index <= ts]
        except Exception:
            continue
        if len(s4) < 50:
            continue
        try:
            r = es.score_from_data(sym, s1, df_4h=s4, oi_hist=None,
                                   pct_24h=0.0, skip_deriv=True)
        except Exception:
            continue
        sc = float(r.get("score") or 0); side = r.get("side")
        if sc < SCORE_FLOOR or side not in ("LONG", "SHORT"):
            continue
        plan = r.get("trade_plan") or {}
        stop = float(plan.get("stop") or 0); tp1 = float(plan.get("tp1") or 0)
        if stop <= 0 or tp1 <= 0:
            continue
        fired[t] = (side, r.get("tier"), stop, tp1)
    # pass 2: persistence + forward outcome
    rows = []
    for ti, t in enumerate(samples):
        if t not in fired:
            continue
        side, tier, stop, tp1 = fired[t]
        # consecutive prior sample bars firing SAME side
        persist = 0
        j = ti - 1
        while j >= 0:
            pt = samples[j]
            if pt in fired and fired[pt][0] == side:
                persist += 1; j -= 1
            else:
                break
        out = _outcome(side, stop, tp1, hi, lo, t, n)
        rows.append((tier, persist * K, out))   # persist in HOURS
    return rows

def _load():
    rows, done = [], set()
    if not os.path.exists(ROWS_FILE):
        return rows, done
    for line in open(ROWS_FILE, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        if "done_coin" in o:
            done.add(o["done_coin"])
        else:
            rows.append((o["tier"], o["ph"], o["out"]))
    return rows, done

def _append(sym, rows):
    with open(ROWS_FILE, "a", encoding="utf-8") as f:
        for (tier, ph, out) in rows:
            f.write(json.dumps({"tier": tier, "ph": ph, "out": out,
                                "sym": sym}) + "\n")
        f.write(json.dumps({"done_coin": sym}) + "\n")

syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]
rows, done = _load()
todo = [s for s in syms if s not in done][:MAX_NEW]
print(f"Resume: {len(done)} coins done ({len(rows)} fires). This run: {todo}")
t0 = time.time()
with ThreadPoolExecutor(max_workers=min(4, len(todo) or 1)) as pool:
    futs = {pool.submit(_one, s): s for s in todo}
    for f in as_completed(futs):
        s = futs[f]
        try:
            rr = f.result()
        except Exception:
            rr = []
        _append(s, rr)
        rows.extend(rr)
        print(f"  done {s:12} +{len(rr)} (cum {len(rows)}, "
              f"{time.time()-t0:.0f}s)", flush=True)

done2 = done | set(todo)
def wr(rs):
    res = [r for r in rs if r[2] in ("WIN", "LOSS")]
    n = len(res); w = sum(1 for r in res if r[2] == "WIN")
    return n, (w/n*100 if n else 0)

BUCKETS = [("just fired (0h)", lambda h: h == 0),
           ("firing 4-20h", lambda h: 4 <= h <= 20),
           ("firing 24-44h", lambda h: 24 <= h <= 44),
           ("firing 48h+", lambda h: h >= 48)]
_tag = "COMPLETE" if len(done2) >= N_COINS else f"PARTIAL {len(done2)}/{N_COINS}"
print("\n" + "="*64)
print(f"PERSISTENCE [{_tag}] — {len(rows)} STRONG+ fires "
      f"(does win rate rise the longer it keeps firing?)")
print("="*64)
print(f"{'persistence':>18} {'n':>5} {'win%':>7}")
for label, fn in BUCKETS:
    sub = [r for r in rows if fn(r[1])]
    nn, ww = wr(sub)
    print(f"{label:>18} {nn:>5} {ww:>6.1f}%")
print("\n-- 48h+ by tier --")
for tier in ("MAX", "HIGH", "STRONG"):
    sub = [r for r in rows if r[1] >= 48 and r[0] == tier]
    nn, ww = wr(sub)
    if nn:
        print(f"   {tier:7}: n={nn:3} win {ww:.1f}%")
if len(done2) < N_COINS:
    print(f"\n>> Re-run to add {min(MAX_NEW, N_COINS-len(done2))} more coins.")
print(f"\nDone in {time.time()-t0:.0f}s.")
