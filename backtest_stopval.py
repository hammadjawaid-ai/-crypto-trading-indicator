"""STRUCTURAL-STOP RE-VALIDATION over a BROAD, multi-regime window.

The overnight test won but in a rough recent window (all methods negative).
This re-validates the ACTUAL deployable helper (smart_stop.structural_stop)
over a longer history (3000 bars ≈ 4 months, multiple regimes) and splits
the result OLDER-half vs RECENT-half — so we see whether structural beats the
plan stop in NORMAL conditions, not just "least-bad in a bad month".

Per MAX/HIGH/STRONG TAKE_NOW confirmation entry: outcome (TP1 before stop)
under PLAN stop vs STRUCTURAL stop (via the shipped helper). Reports win% +
exp/signal for each, overall and per window-half.
Measurement only. Chunked + checkpointed (SV_MAX_NEW).
"""
from __future__ import annotations
import sys, io, time, os, json
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client, indicators
import experimental_signals as es
import smart_stop

N_COINS = 40
MAX_NEW = int(os.environ.get("SV_MAX_NEW", "40"))
BARS = 3000
WARMUP = 220
K = 4
ALIVE = 48
FWD = 36
SCORE_FLOOR = 80.0
VOL_MULT = 1.2
ROWS_FILE = ".sst1_run2.txt".replace("sst1_run2.txt", "stopval_rows.jsonl")


def _tp_before_stop(side, entry, stop, tp1, hi, lo, a, b, n):
    risk = abs(entry - stop)
    if risk <= 0:
        return ("NONE", 0.0)
    rr = abs(tp1 - entry) / risk
    for fb in range(a, min(b, n)):
        if side == "LONG":
            if lo[fb] <= stop:
                return ("LOSS", rr)
            if hi[fb] >= tp1:
                return ("WIN", rr)
        else:
            if hi[fb] >= stop:
                return ("LOSS", rr)
            if lo[fb] <= tp1:
                return ("WIN", rr)
    return ("NONE", rr)


def _one(sym):
    try:
        d1 = indicators.enrich(binance_client.get_klines(sym, "1h", limit=BARS))
        d4 = indicators.enrich(binance_client.get_klines(sym, "4h", limit=700))
    except Exception:
        return []
    if d1 is None or len(d1) < WARMUP + ALIVE + FWD + 5:
        return []
    o = d1["open"].to_numpy(); h = d1["high"].to_numpy()
    l = d1["low"].to_numpy(); c = d1["close"].to_numpy()
    v = d1["volume"].to_numpy()
    ema20 = d1["close"].ewm(span=20, adjust=False).mean().to_numpy()
    vma = pd.Series(v).rolling(20).mean().to_numpy()
    n = len(d1); half = n // 2; rows = []
    for t in range(WARMUP, n - ALIVE - FWD - 1, K):
        s1 = d1.iloc[:t+1]; ts = s1.index[-1]
        try:
            s4 = d4[d4.index <= ts]
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
        if tier not in ("MAX", "HIGH", "STRONG"):
            continue
        plan = r.get("trade_plan") or {}
        p_entry = float(plan.get("entry") or 0)
        p_stop = float(plan.get("stop") or 0); tp1 = float(plan.get("tp1") or 0)
        if p_entry <= 0 or p_stop <= 0 or tp1 <= 0:
            continue
        pulled = False; conf_i = None
        for i in range(t+1, t+1+ALIVE):
            if i >= n:
                break
            if side == "LONG" and l[i] <= p_stop:
                break
            if side == "SHORT" and h[i] >= p_stop:
                break
            if side == "LONG":
                if l[i] <= p_entry:
                    pulled = True
                is_conf = (pulled and c[i] > o[i] and c[i] > c[i-1]
                           and c[i] > ema20[i]
                           and vma[i] > 0 and v[i] > VOL_MULT*vma[i])
            else:
                if h[i] >= p_entry:
                    pulled = True
                is_conf = (pulled and c[i] < o[i] and c[i] < c[i-1]
                           and c[i] < ema20[i]
                           and vma[i] > 0 and v[i] > VOL_MULT*vma[i])
            if is_conf:
                conf_i = i
                break
        if conf_i is None:
            continue
        ci = conf_i
        ent = float(c[ci])
        # structural stop via the SHIPPED helper (point-in-time df)
        s_struct = smart_stop.structural_stop(d1.iloc[:ci+1], side, ent,
                                              p_stop, tp1)
        out_p, rr_p = _tp_before_stop(side, ent, p_stop, tp1, h, l,
                                      ci+1, ci+1+FWD, n)
        out_s, rr_s = _tp_before_stop(side, ent, s_struct, tp1, h, l,
                                      ci+1, ci+1+FWD, n)
        rows.append({"half": "recent" if ci >= half else "older",
                     "p": {"o": out_p, "rr": rr_p},
                     "s": {"o": out_s, "rr": rr_s}})
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


def _stat(rows, key):
    dec = [r[key] for r in rows if r[key]["o"] in ("WIN", "LOSS")]
    w = sum(1 for e in dec if e["o"] == "WIN")
    exp = sum((e["rr"] if e["o"] == "WIN" else -1.0) for e in dec) \
        / max(1, len(rows))
    return (w/len(dec)*100 if dec else 0.0), exp, len(dec)


def rep(label, rows):
    pw, pe, pn = _stat(rows, "p")
    sw, se, sn = _stat(rows, "s")
    print(f"--- {label} (n={len(rows)}) ---")
    print(f"  PLAN stop       | win {pw:5.1f}% | exp/signal {pe:+.3f}R")
    print(f"  STRUCTURAL stop | win {sw:5.1f}% | exp/signal {se:+.3f}R  "
          f"({'BETTER' if se > pe else 'worse'} by {se-pe:+.3f}R)")


syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]
rows, done = _load()
todo = [s for s in syms if s not in done][:MAX_NEW]
print(f"Resume: {len(done)} done ({len(rows)} entries). This run: {todo}")
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
print("\n" + "=" * 62)
_tag = "COMPLETE" if len(done2) >= N_COINS else f"PARTIAL {len(done2)}/{N_COINS}"
print(f"STRUCTURAL-STOP RE-VALIDATION [{_tag}] — {len(rows)} entries "
      f"(BARS={BARS})")
print("=" * 62)
rep("ALL (full 4-month window)", rows)
rep("OLDER half (normal regime)", [r for r in rows if r["half"] == "older"])
rep("RECENT half (rough regime)", [r for r in rows if r["half"] == "recent"])
print("=" * 62)
print("DEPLOY if STRUCTURAL beats PLAN on exp/signal in the OLDER/normal "
      "half too (not just the rough recent one).")
if len(done2) < N_COINS:
    print(f">> Re-run to add more coins.")
print(f"Done in {time.time()-t0:.0f}s.")
