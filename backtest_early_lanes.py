"""EARLY-LANES test — do the catch-it-early lanes flag movers SOONER at a
valid win rate?

User case (VANRY +67%/24h, shown mid-move): can ELITE fires whose ACTIVE
LANES include the early detectors (velocity_burst / early_trend /
early_momentum) provide an EARLIER heads-up — i.e. fire when LESS of the
move has already passed — without a win-rate collapse?

Per fire (tier MAX/HIGH/STRONG, score>=80) with a TAKE_NOW confirmation:
  - early_lane = any of the early lanes in active_lanes at the fire
  - move_passed = entry-bar close vs the 24h low (LONG; mirrored SHORT) —
    how much of the move had already happened at the FIRE
  - outcome from the confirmation close (TP1-before-SL + MFE-R), hot flag
Report EARLY-LANE vs OTHER fires: win%, MFE-R, median move-passed%.
Valid earlier heads-up = similar win% with LOWER move-passed.

Measurement only. Chunked + checkpointed (EL_MAX_NEW).
"""
from __future__ import annotations
import sys, io, time, os, json, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client, indicators
import experimental_signals as es

N_COINS = 40
MAX_NEW = int(os.environ.get("EL_MAX_NEW", "14"))
BARS = 1500
WARMUP = 220
K = 4
ALIVE = 48
FWD = 24
SCORE_FLOOR = 80.0
VOL_MULT = 1.2
HOT_PCTILE = 60.0
EARLY_LANES = {"velocity_burst", "early_trend", "early_momentum"}
ROWS_FILE = ".elanes_rows.jsonl"


def _atr(h, l, c, n=14):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(n).mean().to_numpy()


def _pct_rank(arr, val):
    if len(arr) == 0:
        return 0.0
    return float((arr < val).mean() * 100.0)


def _outcome(side, entry, stop, tp1, hi, lo, a, b, n):
    risk = abs(entry - stop)
    if risk <= 0:
        return "NONE"
    for fb in range(a, min(b, n)):
        if side == "LONG":
            if lo[fb] <= stop:
                return "LOSS"
            if hi[fb] >= tp1:
                return "WIN"
        else:
            if hi[fb] >= stop:
                return "LOSS"
            if lo[fb] <= tp1:
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
    o = d1["open"].to_numpy(); h = d1["high"].to_numpy()
    l = d1["low"].to_numpy(); c = d1["close"].to_numpy()
    v = d1["volume"].to_numpy()
    ema20 = d1["close"].ewm(span=20, adjust=False).mean().to_numpy()
    vma = pd.Series(v).rolling(20).mean().to_numpy()
    atr = _atr(h, l, c, 14)
    n = len(d1); rows = []
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
        lanes = set(r.get("active_lanes") or [])
        early = bool(lanes & EARLY_LANES)
        plan = r.get("trade_plan") or {}
        entry = float(plan.get("entry") or 0)
        stop = float(plan.get("stop") or 0); tp1 = float(plan.get("tp1") or 0)
        if entry <= 0 or stop <= 0 or tp1 <= 0:
            continue
        # move already passed at the FIRE bar (24h window)
        w0 = max(0, t - 24)
        if side == "LONG":
            base = float(np.min(l[w0:t+1]))
            passed = (c[t] / base - 1.0) * 100 if base > 0 else 0.0
        else:
            base = float(np.max(h[w0:t+1]))
            passed = (1.0 - c[t] / base) * 100 if base > 0 else 0.0
        pulled = False; conf_i = None
        for i in range(t+1, t+1+ALIVE):
            if i >= n:
                break
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
            continue
        ci = conf_i
        hot = _pct_rank(atr[max(0, ci-100):ci], atr[ci]) >= HOT_PCTILE
        ent = float(c[ci]); risk = abs(ent - stop)
        if risk <= 0:
            continue
        out = _outcome(side, ent, stop, tp1, h, l, ci+1, ci+1+FWD, n)
        fh = h[ci+1:ci+1+FWD]; fl = l[ci+1:ci+1+FWD]
        if len(fh) == 0:
            continue
        mfe_r = ((float(np.max(fh)) - ent) / risk if side == "LONG"
                 else (ent - float(np.min(fl))) / risk)
        rows.append({"early": early, "hot": bool(hot), "tier": tier,
                     "passed": round(float(passed), 2), "o": out,
                     "mfe": float(mfe_r)})
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


def rep(label, rs):
    dec = [r for r in rs if r["o"] in ("WIN", "LOSS")]
    w = sum(1 for r in dec if r["o"] == "WIN")
    mfe = [r["mfe"] for r in rs]
    psd = [r["passed"] for r in rs]
    print(f"  {label:26} | n={len(rs):4} dec={len(dec):4} | win "
          f"{(w/len(dec)*100 if dec else 0):5.1f}% | MFE-R med "
          f"{(statistics.median(mfe) if mfe else 0):4.2f} | move-passed med "
          f"{(statistics.median(psd) if psd else 0):5.1f}%")


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
print("\n" + "=" * 78)
_tag = "COMPLETE" if len(done2) >= N_COINS else f"PARTIAL {len(done2)}/{N_COINS}"
print(f"EARLY-LANES [{_tag}] — {len(rows)} TAKE_NOW entries")
print("=" * 78)
rep("EARLY-LANE fires (all)", [r for r in rows if r["early"]])
rep("OTHER fires (all)", [r for r in rows if not r["early"]])
rep("EARLY-LANE + HOT", [r for r in rows if r["early"] and r["hot"]])
rep("OTHER + HOT", [r for r in rows if not r["early"] and r["hot"]])
print("=" * 78)
print("Valid earlier heads-up = similar win% with LOWER move-passed.")
if len(done2) < N_COINS:
    print(f">> Re-run to add {min(MAX_NEW, N_COINS-len(done2))} more coins.")
print(f"Done in {time.time()-t0:.0f}s.")
