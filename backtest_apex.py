"""APEX consensus validation — does EDGE STACKING raise the win rate?

The APEX board ranks setups by how many independent validated edges agree.
This measures that premise directly on history: for each MAX/HIGH fire that
produced a TAKE_NOW confirmation (the proven entry), count the extra edges
present AT the confirmation bar — computable without lookahead:
  - HOT   : ATR14 percentile rank in top 40% of last 100 bars
  - ROC   : |6-bar return| rank in top 40%
  - BURST : lane_velocity_burst score >= 78 on the 1h slice, same side
Then bucket outcomes (TP1-before-SL, MFE in R) by edge count 0/1/2/3.
APEX premise holds if win% and MFE-R rise with the edge count.

(Forecast/multi-TF edges can't be reconstructed historically without their
own harnesses — so this validates the stacking PRINCIPLE on the three
reconstructable edges. Honest scope.)

Chunked + checkpointed + threaded. Re-run to add APX_MAX_NEW coins per pass.
"""
from __future__ import annotations
import sys, io, time, os, json, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client, indicators
import experimental_signals as es
import velocity_burst as vb

N_COINS = 40
MAX_NEW = int(os.environ.get("APX_MAX_NEW", "14"))
BARS = 1500
WARMUP = 220
K = 4
ALIVE = 48
FWD = 24
SCORE_FLOOR = 80.0
VOL_MULT = 1.2
HOT_PCTILE = 60.0
ROWS_FILE = ".apex_rows.jsonl"


def _atr(h, l, c, n=14):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(n).mean().to_numpy()


def _pct_rank(arr, val):
    if len(arr) == 0:
        return 0.0
    return float((arr < val).mean() * 100.0)


def _tp_before_sl(side, stop, tp1, hi, lo, a, b, n):
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
    roc6 = np.abs(c / np.roll(c, 6) - 1.0); roc6[:6] = 0.0
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
        if tier not in ("MAX", "HIGH"):
            continue
        plan = r.get("trade_plan") or {}
        entry = float(plan.get("entry") or 0)
        stop = float(plan.get("stop") or 0); tp1 = float(plan.get("tp1") or 0)
        if entry <= 0 or stop <= 0 or tp1 <= 0:
            continue
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
        edges = 0
        if _pct_rank(atr[max(0, ci-100):ci], atr[ci]) >= HOT_PCTILE:
            edges += 1
        if _pct_rank(roc6[max(0, ci-100):ci], roc6[ci]) >= HOT_PCTILE:
            edges += 1
        try:
            bs, bside, _ = vb.lane_velocity_burst(d1.iloc[:ci+1])
            if bs >= 78 and (bside or "").upper() == side:
                edges += 1
        except Exception:
            pass
        ent = float(c[ci]); risk = abs(ent - stop)
        if risk <= 0:
            continue
        out = _tp_before_sl(side, stop, tp1, h, l, ci+1, ci+1+FWD, n)
        fh = h[ci+1:ci+1+FWD]; fl = l[ci+1:ci+1+FWD]
        if len(fh) == 0:
            continue
        mfe_r = ((float(np.max(fh)) - ent) / risk if side == "LONG"
                 else (ent - float(np.min(fl))) / risk)
        rows.append((edges, out, float(mfe_r)))
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
            rows.append((ob["edges"], ob["out"], ob["mfe_r"]))
    return rows, done


def _append(sym, rs):
    with open(ROWS_FILE, "a", encoding="utf-8") as f:
        for (e, out, m) in rs:
            f.write(json.dumps({"edges": e, "out": out, "mfe_r": m,
                                "sym": sym}) + "\n")
        f.write(json.dumps({"done_coin": sym}) + "\n")


syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]
rows, done = _load()
todo = [s for s in syms if s not in done][:MAX_NEW]
print(f"Resume: {len(done)} done ({len(rows)} TAKE_NOWs). This run: {todo}")
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
print(f"APEX EDGE-STACKING [{_tag}] — {len(rows)} TAKE_NOW entries")
print("=" * 66)
for lo, hi, lab in [(0, 0, "0 edges"), (1, 1, "1 edge"),
                    (2, 2, "2 edges"), (3, 9, "3+ edges")]:
    rs = [r for r in rows if lo <= r[0] <= hi]
    dec = [r for r in rs if r[1] in ("WIN", "LOSS")]
    w = sum(1 for r in dec if r[1] == "WIN")
    mfe = [r[2] for r in rs]
    print(f"TAKE_NOW + {lab:8} | n={len(rs):4} decided={len(dec):4} | "
          f"win {(w/len(dec)*100 if dec else 0):5.1f}% | MFE-R med "
          f"{(statistics.median(mfe) if mfe else 0):4.2f}")
print("=" * 66)
print("APEX premise holds if win% and MFE-R RISE with edge count.")
if len(done2) < N_COINS:
    print(f">> Re-run to add {min(MAX_NEW, N_COINS-len(done2))} more coins.")
print(f"Done in {time.time()-t0:.0f}s.")
