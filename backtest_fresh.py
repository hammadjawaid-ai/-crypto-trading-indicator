"""FRESHNESS test — do TAKE_NOW entries on YOUNG moves win more?

User case (ALLO): the best movers' first valid entry comes while the move is
young. Hypothesis (pre-registered, 2 splits only — no p-hacking):
  H1 trend age  : entries where the 1h trend is YOUNG (price crossed to the
                  right side of EMA20 <= 24 bars ago) beat OLD-trend entries.
  H2 fresh fire : the FIRST MAX/HIGH fire in 72h (per symbol+side) beats
                  re-fires on an already-running setup.
Both measured AT the confirmation bar, no lookahead. Outcomes: TP1-before-SL
win + MFE in R over 24 bars (same as every prior harness).

Chunked + checkpointed + threaded. Re-run to add FR_MAX_NEW coins per pass.
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
MAX_NEW = int(os.environ.get("FR_MAX_NEW", "14"))
BARS = 1500
WARMUP = 220
K = 4
ALIVE = 48
FWD = 24
SCORE_FLOOR = 80.0
VOL_MULT = 1.2
YOUNG_BARS = 24          # trend age <= 24h = young
FRESH_GAP_H = 72         # no same-side fire in 72h = fresh
ROWS_FILE = ".fresh_rows.jsonl"


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
    n = len(d1); rows = []
    last_fire: dict = {}    # side -> bar index of previous MAX/HIGH fire
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
        prev_fire = last_fire.get(side)
        last_fire[side] = t
        fresh = prev_fire is None or (t - prev_fire) > FRESH_GAP_H
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
        # H1: trend age at the confirmation bar — bars since price was last
        # on the WRONG side of EMA20 for this side.
        age = 0
        for b in range(ci, max(0, ci - 200), -1):
            wrong = (c[b] < ema20[b]) if side == "LONG" else (c[b] > ema20[b])
            if wrong:
                break
            age += 1
        ent = float(c[ci]); risk = abs(ent - stop)
        if risk <= 0:
            continue
        out = _tp_before_sl(side, stop, tp1, h, l, ci+1, ci+1+FWD, n)
        fh = h[ci+1:ci+1+FWD]; fl = l[ci+1:ci+1+FWD]
        if len(fh) == 0:
            continue
        mfe_r = ((float(np.max(fh)) - ent) / risk if side == "LONG"
                 else (ent - float(np.min(fl))) / risk)
        rows.append((int(age), bool(fresh), out, float(mfe_r)))
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
            rows.append((ob["age"], ob["fresh"], ob["out"], ob["mfe_r"]))
    return rows, done


def _append(sym, rs):
    with open(ROWS_FILE, "a", encoding="utf-8") as f:
        for (age, fresh, out, m) in rs:
            f.write(json.dumps({"age": age, "fresh": fresh, "out": out,
                                "mfe_r": m, "sym": sym}) + "\n")
        f.write(json.dumps({"done_coin": sym}) + "\n")


def report(label, rs):
    dec = [r for r in rs if r[2] in ("WIN", "LOSS")]
    w = sum(1 for r in dec if r[2] == "WIN")
    mfe = [r[3] for r in rs]
    print(f"{label:26} | n={len(rs):4} decided={len(dec):4} | "
          f"win {(w/len(dec)*100 if dec else 0):5.1f}% | MFE-R med "
          f"{(statistics.median(mfe) if mfe else 0):4.2f}")


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
print(f"FRESHNESS [{_tag}] — {len(rows)} TAKE_NOW entries")
print("=" * 66)
report("H1 YOUNG trend (<=24h)", [r for r in rows if r[0] <= YOUNG_BARS])
report("H1 OLD trend (>24h)", [r for r in rows if r[0] > YOUNG_BARS])
report("H2 FRESH fire (>72h gap)", [r for r in rows if r[1]])
report("H2 RE-FIRE (<72h)", [r for r in rows if not r[1]])
report("BOTH young+fresh", [r for r in rows if r[0] <= YOUNG_BARS and r[1]])
report("ALL", rows)
print("=" * 66)
print("Ship 🌱 FRESH only if young/fresh clearly beats old/re-fire on BOTH "
      "win% and MFE-R.")
if len(done2) < N_COINS:
    print(f">> Re-run to add {min(MAX_NEW, N_COINS-len(done2))} more coins.")
print(f"Done in {time.time()-t0:.0f}s.")
