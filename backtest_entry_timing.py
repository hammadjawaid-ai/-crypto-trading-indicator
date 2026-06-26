"""Entry-timing test (user idea 2026-06-18, research-backed).

For a still-alive MAX/HIGH ELITE setup, is the WIN RATE higher if you
wait for a PULLBACK + CONFIRMATION candle instead of entering at the
fire? (Research: pullback to EMA + RSI holding + rejection/bullish candle
+ volume uptick = the highest-quality entry.)

Compares, per MAX/HIGH fire (score>=80, tier MAX/HIGH):
  A) BASELINE     — enter at the fire bar; TP1-before-SL over the window.
  B) PULLBACK+CONF— within the alive window (before SL), wait for the
     first CONFIRMATION bar AFTER price has pulled back to the entry:
       LONG: low<=entry seen, then a bar with close>open, close>prev
       close, close>EMA20, volume>1.2x avg -> enter at that close.
     measure TP1-before-SL from there (same stop/target). Also report how
     OFTEN a confirmation appears (frequency) — selectivity matters.

Chunked + checkpointed + threaded (score_from_data is the slow part).
Re-run to add MAX_NEW coins per pass.
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
MAX_NEW = int(os.environ.get("ET_MAX_NEW", "10"))
BARS = 1500
WARMUP = 220
K = 4              # sample for fires every 4h
ALIVE = 48         # window to find a confirmation (2 days)
FWD = 24           # outcome window from the (chosen) entry
SCORE_FLOOR = 80.0
VOL_MULT = 1.2
ROWS_FILE = ".entry_rows.jsonl"


def _tp_before_sl(side, entry, stop, tp1, hi, lo, a, b, n):
    for fb in range(a, min(b, n)):
        h, l = hi[fb], lo[fb]
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
    if d1 is None or len(d1) < WARMUP + ALIVE + FWD + 5:
        return []
    d4i = d4.copy()
    o = d1["open"].to_numpy(); h = d1["high"].to_numpy()
    l = d1["low"].to_numpy(); c = d1["close"].to_numpy()
    v = d1["volume"].to_numpy()
    ema20 = d1["close"].ewm(span=20, adjust=False).mean().to_numpy()
    vma = pd.Series(v).rolling(20).mean().to_numpy()
    n = len(d1); rows = []
    for t in range(WARMUP, n - ALIVE - FWD - 1, K):
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
        tier = (r.get("tier") or "")
        if sc < SCORE_FLOOR or side not in ("LONG", "SHORT"):
            continue
        if tier not in ("MAX", "HIGH"):
            continue
        plan = r.get("trade_plan") or {}
        entry = float(plan.get("entry") or 0)
        stop = float(plan.get("stop") or 0); tp1 = float(plan.get("tp1") or 0)
        if entry <= 0 or stop <= 0 or tp1 <= 0:
            continue
        # A) baseline — enter at fire
        base = _tp_before_sl(side, entry, stop, tp1, h, l, t+1, t+1+FWD, n)
        # B) pullback + confirmation entry
        pulled = False; conf_i = None
        for i in range(t+1, t+1+ALIVE):
            if i >= n:
                break
            # dead if SL hit before any confirmation
            if side == "LONG" and l[i] <= stop:
                break
            if side == "SHORT" and h[i] >= stop:
                break
            if side == "LONG":
                if l[i] <= entry:
                    pulled = True
                is_conf = (pulled and c[i] > o[i] and c[i] > c[i-1]
                           and c[i] > ema20[i]
                           and vma[i] > 0 and v[i] > VOL_MULT*vma[i])
            else:
                if h[i] >= entry:
                    pulled = True
                is_conf = (pulled and c[i] < o[i] and c[i] < c[i-1]
                           and c[i] < ema20[i]
                           and vma[i] > 0 and v[i] > VOL_MULT*vma[i])
            if is_conf:
                conf_i = i
                break
        if conf_i is None:
            pb = "NOCONF"
        else:
            pb = _tp_before_sl(side, c[conf_i], stop, tp1, h, l,
                               conf_i+1, conf_i+1+FWD, n)
        rows.append((tier, base, pb))
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
            rows.append((ob["tier"], ob["base"], ob["pb"]))
    return rows, done


def _append(sym, rows):
    with open(ROWS_FILE, "a", encoding="utf-8") as f:
        for (tier, base, pb) in rows:
            f.write(json.dumps({"tier": tier, "base": base, "pb": pb,
                                "sym": sym}) + "\n")
        f.write(json.dumps({"done_coin": sym}) + "\n")


syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]
rows, done = _load()
todo = [s for s in syms if s not in done][:MAX_NEW]
print(f"Resume: {len(done)} done ({len(rows)} fires). This run: {todo}")
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
def wr(vals):
    res = [x for x in vals if x in ("WIN", "LOSS")]
    w = sum(1 for x in res if x == "WIN")
    return len(res), (w/len(res)*100 if res else 0)

base_n, base_w = wr([r[1] for r in rows])
conf_vals = [r[2] for r in rows]
conf_n, conf_w = wr(conf_vals)
n_conf = sum(1 for x in conf_vals if x in ("WIN", "LOSS"))
n_noconf = sum(1 for x in conf_vals if x == "NOCONF")
tot = len(rows)
print("\n" + "="*66)
_tag = "COMPLETE" if len(done2) >= N_COINS else f"PARTIAL {len(done2)}/{N_COINS}"
print(f"ENTRY-TIMING [{_tag}] — {tot} MAX/HIGH fires")
print("="*66)
print(f"A) BASELINE (enter at fire):       n={base_n:4}  win {base_w:.1f}%")
print(f"B) PULLBACK+CONFIRMATION entry:     n={conf_n:4}  win {conf_w:.1f}%")
print(f"   confirmation appeared in {n_conf}/{tot} fires "
      f"({n_conf/max(1,tot)*100:.0f}%); {n_noconf} never confirmed (skip)")
if len(done2) < N_COINS:
    print(f"\n>> Re-run to add {min(MAX_NEW, N_COINS-len(done2))} more coins.")
print(f"\nDone in {time.time()-t0:.0f}s.")
