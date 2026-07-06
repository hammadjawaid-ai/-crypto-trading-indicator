"""SST1 CONVICTION CALIBRATION — is the conviction score effective, i.e.
does a HIGHER conviction actually mean a HIGHER win rate?

Key fact: SST1's conviction is DETERMINISTIC (sureshot_agents.
_deterministic_conviction) = base_score×0.6 + edge bonuses (ELITE, R:R,
multi-TF, regime). The LLM only writes a verdict on top. So we can backtest
the conviction faithfully, no API calls.

Per MAX/HIGH/STRONG confirmation entry we reconstruct the candidate
(score, ELITE flag for MAX/HIGH, plan R:R, 1h+4h alignment) and compute the
REAL conviction via the shipped function, then record forward outcome.
Report win% + exp by conviction band, and compare vs sorting by raw score.
Honest caveat: CONVERGENCE / SURE SHOT / regime bonuses are rare / not
reconstructed here, so this covers the DOMINANT conviction terms (base +
ELITE + R:R + MTF) — enough to answer "does conviction sort outcomes".
Measurement only. Chunked + checkpointed (SC_MAX_NEW).
"""
from __future__ import annotations
import sys, io, time, os, json
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client, indicators
import experimental_signals as es
from sureshot_agents import _deterministic_conviction

N_COINS = 40
MAX_NEW = int(os.environ.get("SC_MAX_NEW", "14"))
BARS = 1500
WARMUP = 220
K = 4
ALIVE = 48
FWD = 24
SCORE_FLOOR = 80.0
VOL_MULT = 1.2
ROWS_FILE = ".sst1cal_rows.jsonl"


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
    e4_20 = d4["close"].ewm(span=20, adjust=False).mean()
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
        # reconstruct candidate for the REAL conviction function
        rr = abs(tp1 - float(c[ci])) / abs(float(c[ci]) - stop) \
            if abs(float(c[ci]) - stop) > 0 else 0.0
        try:
            e4v = float(e4_20[e4_20.index <= ts].iloc[-1])
            c4v = float(s4["close"].iloc[-1])
        except Exception:
            e4v = c4v = 0.0
        mtf = 1
        if c4v and e4v:
            if (side == "LONG" and c4v > e4v) or (side == "SHORT" and c4v < e4v):
                mtf = 2
        proven = ["ELITE"] if tier in ("MAX", "HIGH") else []
        cand = {
            "symbol": sym, "side": side, "score": sc,
            "proven_systems": proven, "proven_count": len(proven),
            "_mtf_aligned": mtf, "_mtf_against": 0,
            "trade_plan": {"rr": rr}, "rr": rr,
        }
        conv, _ = _deterministic_conviction(cand, {})
        out = _tp_before_sl(side, float(c[ci]), stop, tp1, h, l,
                            ci+1, ci+1+FWD, n)
        rows.append({"conv": round(float(conv), 1), "score": round(sc, 1),
                     "tier": tier, "rr": round(rr, 2), "o": out})
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
    # exp assumes avg RR from the plan; use rr per row (WIN=+rr, LOSS=-1)
    exp = sum((r["rr"] if r["o"] == "WIN" else -1.0) for r in dec) \
        / max(1, len(rs))
    return (w/len(dec)*100 if dec else 0.0), len(dec), exp


def band(label, rows, key, edges):
    print(f"--- sorted by {label} ---")
    prev = -1e9
    for e in edges + [1e9]:
        seg = [r for r in rows if prev <= r.get(key, 0) < e]
        wr, nd, exp = _wr(seg)
        lo = "-inf" if prev == -1e9 else f"{prev:g}"
        hi = "inf" if e == 1e9 else f"{e:g}"
        print(f"  {key} {lo:>4}..{hi:<4} | n={nd:4} | win {wr:5.1f}% | "
              f"exp/signal {exp:+.3f}R")
        prev = e


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
print(f"SST1 CONVICTION CALIBRATION [{_tag}] — {len(rows)} entries")
print("=" * 62)
wr, nd, exp = _wr(rows)
print(f"OVERALL: win {wr:.1f}% · exp/signal {exp:+.3f}R (n={nd})")
print("-" * 62)
band("SST1 CONVICTION", rows, "conv", [72, 75, 78, 82])
band("RAW SCORE (does conviction beat it?)", rows, "score", [82, 85, 88])
print("=" * 62)
print("SST1 conviction is EFFECTIVE only if win% RISES with conviction — and "
      "sorts outcomes better than raw score. Flat = it adds nothing.")
if len(done2) < N_COINS:
    print(f">> Re-run to add {min(MAX_NEW, N_COINS-len(done2))} more coins.")
print(f"Done in {time.time()-t0:.0f}s.")
