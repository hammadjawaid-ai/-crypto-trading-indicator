"""SST1 v2 — RE-GROUNDED CONVICTION on validated edges.

Tonight proved SST1's current conviction (base×0.6+bonuses) is compressed and
does NOT sort winners. This tests the fix: a conviction driven by the EDGES
we've independently validated (HOT, ROC-burst, velocity-burst, multi-TF,
freshness, tier). If win% rises cleanly with edge count, the re-grounded
conviction is a real ranker — unlike the old one.

Per MAX/HIGH/STRONG TAKE_NOW confirmation entry: count validated edges at the
entry bar, form new_conviction = 50 + 10×edges (spreads 50→100), record
outcome. Report win% by EDGE COUNT and by new-conviction band — the proof
that it sorts. Measurement only. Chunked + checkpointed (S2_MAX_NEW).
"""
from __future__ import annotations
import sys, io, time, os, json
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client, indicators
import experimental_signals as es
import velocity_burst as vb

N_COINS = 40
MAX_NEW = int(os.environ.get("S2_MAX_NEW", "40"))
BARS = 1500
WARMUP = 220
K = 4
ALIVE = 48
FWD = 24
SCORE_FLOOR = 80.0
VOL_MULT = 1.2
HOT_PCTILE = 60.0
FRESH_GAP_H = 72
ROWS_FILE = ".sst1_results.txt".replace("sst1_results.txt", "syn2_rows.jsonl")


def _atr(h, l, c, n=14):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(n).mean().to_numpy()


def _pr(arr, val):
    if len(arr) == 0:
        return 0.0
    return float((arr < val).mean() * 100.0)


def _tp_before_sl(side, entry, stop, tp1, hi, lo, a, b, n):
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
    e4_20 = d4["close"].ewm(span=20, adjust=False).mean()
    n = len(d1); rows = []
    last_fire: dict = {}
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
        prev = last_fire.get(side)
        last_fire[side] = t
        fresh = prev is None or (t - prev) > FRESH_GAP_H
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
        if _pr(atr[max(0, ci-100):ci], atr[ci]) >= HOT_PCTILE:
            edges += 1                                    # HOT
        if _pr(roc6[max(0, ci-100):ci], roc6[ci]) >= HOT_PCTILE:
            edges += 1                                    # ROC burst
        try:
            bs, bside, _ = vb.lane_velocity_burst(d1.iloc[:ci+1])
            if bs >= 78 and (bside or "").upper() == side:
                edges += 1                                # velocity burst
        except Exception:
            pass
        try:
            e4v = float(e4_20[e4_20.index <= ts].iloc[-1])
            c4v = float(s4["close"].iloc[-1])
            if (side == "LONG" and c4v > e4v) or (side == "SHORT" and c4v < e4v):
                edges += 1                                # multi-TF aligned
        except Exception:
            pass
        if fresh:
            edges += 1                                    # freshness
        if tier in ("MAX", "HIGH"):
            edges += 1                                    # premium tier
        new_conv = 50 + 10 * edges
        out = _tp_before_sl(side, float(c[ci]), stop, tp1, h, l,
                            ci+1, ci+1+FWD, n)
        rows.append({"edges": int(edges), "conv": int(new_conv),
                     "tier": tier, "o": out})
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


def _wr(rs):
    dec = [r for r in rs if r["o"] in ("WIN", "LOSS")]
    w = sum(1 for r in dec if r["o"] == "WIN")
    return (w/len(dec)*100 if dec else 0.0), len(dec)


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
print("\n" + "=" * 60)
_tag = "COMPLETE" if len(done2) >= N_COINS else f"PARTIAL {len(done2)}/{N_COINS}"
print(f"SST1 v2 RE-GROUNDED CONVICTION [{_tag}] — {len(rows)} entries")
print("=" * 60)
wr, nd = _wr(rows)
print(f"OVERALL win {wr:.1f}% (n={nd})")
print("-" * 60)
print("win% by EDGE COUNT (must RISE = it sorts, unlike old conviction):")
for e in range(0, 7):
    seg = [r for r in rows if r["edges"] == e]
    w, d = _wr(seg)
    if d > 0:
        print(f"  {e} edges (conv {50+10*e}) | n={len(seg):4} | win {w:5.1f}%")
print("=" * 60)
print("If win% climbs with edge count, the re-grounded conviction is a REAL "
      "ranker — the SST1 fix. Flat = even edges don't help here.")
if len(done2) < N_COINS:
    print(">> Re-run to add more coins.")
print(f"Done in {time.time()-t0:.0f}s.")
