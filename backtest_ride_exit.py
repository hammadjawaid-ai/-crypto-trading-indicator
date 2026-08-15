"""RIDE-EXIT STUDY — the user's "no restriction" exit, measured.

User 2026-08-15: strong fires "can do 20% or 5% based on the candles
and signals — no restriction," with the SL driven by chart reads.
This measures FOUR exits on the SAME strong at-fire population
(score>=80 fires; cells split MAX/HIGH+approved and STRONG+burst>=85
— the two validated at-fire classes), entry at the fire close,
structural stop, 48h horizon:

  T10  : plan TP1 (the deployed baseline)
  T125 : TP1 x1.25 (the shelved backtest_tp option, now live on the
         STRONG stream)
  T20  : TP1 x2.0 (a true wide target)
  RIDE : NO target — hold until the 1h chart says the move is over:
         close crosses the EMA20 against the position, or the stop.
         The pattern-read exit the user asked for.

Every exit uses the same structural stop. Expectancy in R per fire,
win% over decided, older/recent halves. Ship rule: RIDE (or a wider
target) replaces the deployed plan on a stream ONLY if it beats the
baseline in BOTH halves. Measurement only.
Env: RX_N (40), RX_MAX_NEW (40), RX_BARS (3000), RX_K (4).
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
import smart_stop
import deep_history as dh

N_COINS = int(os.environ.get("RX_N", "40"))
MAX_NEW = int(os.environ.get("RX_MAX_NEW", "40"))
BARS = int(os.environ.get("RX_BARS", "3000"))
K = int(os.environ.get("RX_K", "4"))
WARMUP = 220
FWD = 48
ROW_GAP = 12
ROWS_FILE = f".ride_exit_rows_{BARS}.jsonl"


def _sim_target(side, ent, stop, tp, hi, lo, a, b, n):
    """First-touch target-vs-stop. Returns R (win rr / -1 / 0 flat)."""
    risk = abs(ent - stop)
    if risk <= 0:
        return 0.0, "NONE"
    rr = abs(tp - ent) / risk
    for i in range(a, min(b, n)):
        if side == "LONG":
            if lo[i] <= stop:
                return -1.0, "LOSS"
            if hi[i] >= tp:
                return rr, "WIN"
        else:
            if hi[i] >= stop:
                return -1.0, "LOSS"
            if lo[i] <= tp:
                return rr, "WIN"
    return 0.0, "NONE"


def _sim_ride(side, ent, stop, c, hi, lo, ema, a, b, n):
    """No target: exit at stop, or at the close that crosses the EMA20
    against the position (the 1h structure-break read), or at b."""
    risk = abs(ent - stop)
    if risk <= 0:
        return 0.0, "NONE"
    for i in range(a, min(b, n)):
        if side == "LONG":
            if lo[i] <= stop:
                return -1.0, "LOSS"
            if c[i] < ema[i]:
                return (c[i] - ent) / risk, "EXIT"
        else:
            if hi[i] >= stop:
                return -1.0, "LOSS"
            if c[i] > ema[i]:
                return (ent - c[i]) / risk, "EXIT"
    j = min(b, n) - 1
    px = c[j]
    return ((px - ent) if side == "LONG" else (ent - px)) / risk, "TIME"


def _one(sym):
    try:
        d1 = indicators.enrich(dh.get_klines_deep(sym, "1h", BARS))
        d4 = indicators.enrich(dh.get_klines_deep(sym, "4h",
                                                  BARS // 4 + 60))
    except Exception:
        return []
    if d1 is None or len(d1) < WARMUP + FWD + 5:
        return []
    h = d1["high"].to_numpy(); l = d1["low"].to_numpy()
    c = d1["close"].to_numpy()
    ema20 = d1["close"].ewm(span=20, adjust=False).mean().to_numpy()
    roc6 = np.abs(c / np.roll(c, 6) - 1.0); roc6[:6] = 0.0
    n = len(d1); half = n // 2; rows = []
    last_row: dict = {}
    for t in range(WARMUP, n - FWD - 1, K):
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
        if sc < 80 or side not in ("LONG", "SHORT"):
            continue
        if tier not in ("MAX", "HIGH", "STRONG"):
            continue
        prow = last_row.get(side)
        if prow is not None and (t - prow) < ROW_GAP:
            continue
        plan = r.get("trade_plan") or {}
        p_entry = float(plan.get("entry") or 0)
        p_stop = float(plan.get("stop") or 0)
        tp1 = float(plan.get("tp1") or 0)
        if p_entry <= 0 or p_stop <= 0 or tp1 <= 0:
            continue
        last_row[side] = t
        ref = roc6[max(0, t-100):t]
        roc_hot = len(ref) > 0 and float(
            (ref < roc6[t]).mean() * 100) >= 60
        try:
            bs, bside, _ = vb.lane_velocity_burst(s1)
        except Exception:
            bs, bside = 0.0, ""
        appr = bool(roc_hot or (bs >= 78
                                and (bside or "").upper() == side))
        b85 = bs >= 85 and (bside or "").upper() == side
        ent = float(c[t])
        s_st = smart_stop.structural_stop(s1, side, ent, p_stop, tp1)
        d_tp = tp1 - p_entry
        exits = {}
        for lbl, mul in (("t10", 1.0), ("t125", 1.25), ("t20", 2.0)):
            tp = ent + d_tp * mul
            rr, o = _sim_target(side, ent, s_st, tp, h, l,
                                t+1, t+1+FWD, n)
            exits[lbl] = rr
        rr, o = _sim_ride(side, ent, s_st, c, h, l, ema20,
                          t+1, t+1+FWD, n)
        exits["ride"] = rr
        rows.append({"tier": tier, "appr": appr, "b85": bool(b85),
                     "half": "recent" if t >= half else "older",
                     **{k: round(v, 3) for k, v in exits.items()}})
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


def cell(label, seg):
    if not seg:
        print(f"  {label:34} | n=0")
        return
    print(f"  {label:34} | n={len(seg):4}", end="")
    for k, tag in (("t10", "TP1"), ("t125", "x1.25"), ("t20", "x2.0"),
                   ("ride", "RIDE")):
        vals = [r[k] for r in seg]
        e = sum(vals) / len(vals)
        w = sum(1 for v in vals if v > 0) / max(
            1, sum(1 for v in vals if v != 0)) * 100
        print(f" | {tag} {e:+.3f}R/{w:.0f}%", end="")
    print()


def report(rows):
    print("=" * 110)
    print(f"RIDE-EXIT STUDY — {len(rows)} at-fire entries · exits: "
          f"plan TP1 / x1.25 / x2.0 / RIDE(structure-break) · 48h")
    print("=" * 110)
    mh = [r for r in rows if r["tier"] in ("MAX", "HIGH")
          and r["appr"]]
    st85 = [r for r in rows if r["tier"] == "STRONG" and r["b85"]]
    for half in (None, "older", "recent"):
        sub_mh = [r for r in mh if half is None or r["half"] == half]
        sub_st = [r for r in st85
                  if half is None or r["half"] == half]
        tag = half or "FULL"
        cell(f"[{tag}] MAX/HIGH + approved", sub_mh)
        cell(f"[{tag}] STRONG + burst>=85", sub_st)
    print("=" * 110)


if __name__ == "__main__":
    syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()
    syms = syms[:N_COINS]
    rows, done = _load()
    todo = [s for s in syms if s not in done][:MAX_NEW]
    print(f"Resume: {len(done)} done ({len(rows)} fires). Run: {todo}")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=min(4, len(todo) or 1)) as pool:
        futs = {pool.submit(_one, s): s for s in todo}
        for fut in as_completed(futs):
            s = futs[fut]
            try:
                rr = fut.result()
            except Exception as exc:
                print(f"  {s} failed: {exc}", flush=True)
                rr = []
            _append(s, rr)
            rows.extend(rr)
            print(f"  done {s:12} +{len(rr)} (cum {len(rows)}, "
                  f"{time.time()-t0:.0f}s)", flush=True)
    done2 = done | set(todo)
    print(f"\n[{'COMPLETE' if len(done2) >= N_COINS else 'PARTIAL'}]")
    report(rows)
    print(f"Done in {time.time()-t0:.0f}s.")
