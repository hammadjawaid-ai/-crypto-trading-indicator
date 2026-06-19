"""Delayed-trigger edge test (user idea 2026-06-18) — CHECKPOINTED.

Question: a strong ELITE setup (score>=80) often doesn't move
immediately. If it stays ALIVE (neither TP1 nor SL hit in the first
24h), does it still WIN when it finally resolves over the next few days?

The delayed bucket is RARE (~7% of strong fires), so we accumulate a
bigger sample across foreground chunks: each run processes MAX_NEW new
coins (threaded), checkpoints per coin to .delayed_rows.jsonl, and
resumes. Re-run until enough coins are in. Longer per-coin history
(1500 1h bars ~62d) harvests more fires per coin.

Buckets (walk-forward, no lookahead):
  IMMEDIATE       = TP1 or SL hit within first 24 bars
  STILL-ALIVE@24h = neither hit in 24 bars -> DELAYED outcome over 25..96
"""
from __future__ import annotations
import sys, io, time, os, json
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client, indicators
import experimental_signals as es

N_COINS = 40              # total universe to accumulate over chunks
MAX_NEW = int(os.environ.get("DLY_MAX_NEW", "4"))  # new coins per run
BARS = 1500
WARMUP = 220
SAMPLE = 5
SCORE_FLOOR = 80.0
IMMEDIATE = 24
FULL = 96
ROWS_FILE = ".delayed_rows.jsonl"

def _resolve(side, stop, tp1, hi, lo, t, n, a0, a1):
    for fb in range(t + a0, min(t + a1 + 1, n)):
        h = hi[fb]; l = lo[fb]
        if side == "LONG":
            hs = l <= stop; ht = h >= tp1
        else:
            hs = h >= stop; ht = l <= tp1
        if hs:
            return "LOSS"
        if ht:
            return "WIN"
    return "NONE"

def _one(sym):
    try:
        d1 = indicators.enrich(binance_client.get_klines(sym, "1h", limit=BARS))
        d4 = indicators.enrich(binance_client.get_klines(sym, "4h", limit=400))
    except Exception:
        return []
    if d1 is None or len(d1) < WARMUP + FULL + 5:
        return []
    d4i = d4.copy()
    hi = d1["high"].to_numpy(); lo = d1["low"].to_numpy()
    n = len(d1); rows = []
    for t in range(WARMUP, n - FULL - 1, SAMPLE):
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
        if float(plan.get("entry") or 0) <= 0 or stop <= 0 or tp1 <= 0:
            continue
        tier = r.get("tier")
        imm = _resolve(side, stop, tp1, hi, lo, t, n, 1, IMMEDIATE)
        if imm in ("WIN", "LOSS"):
            rows.append((tier, "IMMEDIATE", imm))
        else:
            dly = _resolve(side, stop, tp1, hi, lo, t, n, IMMEDIATE + 1, FULL)
            rows.append((tier, "DELAYED", dly))
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
            rows.append((o["tier"], o["bucket"], o["out"]))
    return rows, done

def _append(sym, rows):
    with open(ROWS_FILE, "a", encoding="utf-8") as f:
        for (tier, bucket, out) in rows:
            f.write(json.dumps({"tier": tier, "bucket": bucket,
                                "out": out, "sym": sym}) + "\n")
        f.write(json.dumps({"done_coin": sym}) + "\n")

syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]
rows, done = _load()
todo = [s for s in syms if s not in done][:MAX_NEW]
print(f"Resume: {len(done)} coins done ({len(rows)} fires). "
      f"This run: {todo}")
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
        print(f"  done {s:12} +{len(rr)} fires (cum {len(rows)}, "
              f"{time.time()-t0:.0f}s)", flush=True)

done2 = done | set(todo)
def wr(rs):
    res = [r for r in rs if r[2] in ("WIN", "LOSS")]
    n = len(res); w = sum(1 for r in res if r[2] == "WIN")
    return n, (w/n*100 if n else 0)

imm = [r for r in rows if r[1] == "IMMEDIATE"]
dly = [r for r in rows if r[1] == "DELAYED"]
ni, wi = wr(imm); nd, wd = wr(dly)
print("\n" + "="*64)
_tag = "COMPLETE" if len(done2) >= N_COINS else f"PARTIAL {len(done2)}/{N_COINS} coins"
print(f"DELAYED-TRIGGER [{_tag}] — {len(rows)} strong fires (score>=80)")
print("="*64)
print(f"IMMEDIATE (<=24h):  n={ni:4}  win {wi:.1f}%  "
      f"({len(imm)/max(1,len(rows))*100:.0f}% of fires)")
print(f"DELAYED (alive@24h, resolves 24-96h):  n={nd:4}  win {wd:.1f}%  "
      f"({len(dly)/max(1,len(rows))*100:.0f}% of fires)")
print("\n-- delayed win by tier --")
for tier in ("MAX", "HIGH", "STRONG"):
    sub = [r for r in dly if r[0] == tier]
    nn, ww = wr(sub)
    if nn:
        print(f"   {tier:7}: n={nn:3} win {ww:.1f}%")
if len(done2) < N_COINS:
    print(f"\n>> Re-run to add {min(MAX_NEW, N_COINS-len(done2))} more coins.")
print(f"\nDone in {time.time()-t0:.0f}s.")
