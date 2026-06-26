"""Entry-timing TIMEFRAME test (user idea 2026-06-26): confirm the entry
on 15m / 30m instead of 1h so 'TAKE NOW' shows EARLIER and you keep more
of the move.

Same exact confirmation logic as entry_timing.py (pullback to entry, then
a candle with close>open, close>prev, close>EMA20, vol>1.2x avg) — only the
CANDLE TIMEFRAME changes. Fires are still detected on 1h (that's how the
live ACTIVE MAX/HIGH board fires); for each MAX/HIGH fire we look for the
confirmation on 1h, 30m AND 15m and compare:
  - WIN RATE (TP1 before SL, measured on 1h forward) — must hold, or the
    faster timeframe is just noise.
  - HOW MUCH EARLIER the faster TF confirms vs 1h (median hours).
  - HOW MUCH BETTER the entry PRICE is (cheaper LONG / higher SHORT) —
    i.e. the extra profit margin the user is asking for.

15m klines cover ~10 days, so only fires in the recent window are testable
-> smaller sample than the 1h study. Reported honestly. Chunked +
checkpointed + threaded; re-run to add ETF_MAX_NEW coins per pass.
"""
from __future__ import annotations
import sys, io, time, os, json, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client, indicators
import experimental_signals as es

N_COINS = 30
MAX_NEW = int(os.environ.get("ETF_MAX_NEW", "15"))
ALIVE_H = 48          # hours after the fire to find a confirmation
FWD_H = 24            # outcome window (1h bars) from the chosen entry
K = 4                 # sample fires every 4h
SCORE_FLOOR = 80.0
VOL_MULT = 1.2
TFS = ["1h", "30m", "15m"]
ROWS_FILE = ".entrytf_rows.jsonl"
NS_H = 3.6e12         # nanoseconds in an hour


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def _ns(index):
    # Force int64 NANOSECONDS regardless of the index's native resolution.
    # pandas 2.x can hand back datetime64[ms], whose raw int64 is in ms —
    # mixing that with an ns-based hour constant silently breaks the window.
    return index.values.astype("datetime64[ns]").astype("int64")


def _prep_tf(df):
    return dict(
        o=df["open"].to_numpy(), h=df["high"].to_numpy(),
        l=df["low"].to_numpy(), c=df["close"].to_numpy(),
        v=df["volume"].to_numpy(),
        ema20=_ema(df["close"], 20).to_numpy(),
        vma=pd.Series(df["volume"].to_numpy()).rolling(20).mean().to_numpy(),
        idx=_ns(df.index), n=len(df))


def _find_conf(tf, side, entry, stop, ts_ns, end_ns):
    """First pullback+confirmation bar strictly after ts_ns, within end_ns.
    Returns (conf_ts_ns, conf_close) or None (dead at stop / never confirms)."""
    idx = tf["idx"]
    lo = int(np.searchsorted(idx, ts_ns, side="right"))
    hi = int(np.searchsorted(idx, end_ns, side="right"))
    o, h, l, c = tf["o"], tf["h"], tf["l"], tf["c"]
    v, ema20, vma = tf["v"], tf["ema20"], tf["vma"]
    pulled = False
    for j in range(max(lo, 1), min(hi, tf["n"])):
        if side == "LONG":
            if l[j] <= stop:
                return None
            if l[j] <= entry:
                pulled = True
            is_conf = (pulled and c[j] > o[j] and c[j] > c[j-1]
                       and c[j] > ema20[j]
                       and vma[j] > 0 and v[j] > VOL_MULT * vma[j])
        else:
            if h[j] >= stop:
                return None
            if h[j] >= entry:
                pulled = True
            is_conf = (pulled and c[j] < o[j] and c[j] < c[j-1]
                       and c[j] < ema20[j]
                       and vma[j] > 0 and v[j] > VOL_MULT * vma[j])
        if is_conf:
            return (int(idx[j]), float(c[j]))
    return None


def _outcome_1h(side, stop, tp1, d1o, conf_ts_ns):
    idx, h, l = d1o["idx"], d1o["h"], d1o["l"]
    a = int(np.searchsorted(idx, conf_ts_ns, side="right"))
    for fb in range(a, min(a + FWD_H, d1o["n"])):
        if side == "LONG":
            if l[fb] <= stop:
                return "LOSS"
            if h[fb] >= tp1:
                return "WIN"
        else:
            if h[fb] >= stop:
                return "LOSS"
            if l[fb] <= tp1:
                return "WIN"
    return "NONE"


def _one(sym):
    try:
        d1 = indicators.enrich(binance_client.get_klines(sym, "1h", limit=1000))
        d4 = indicators.enrich(binance_client.get_klines(sym, "4h", limit=400))
        d30 = binance_client.get_klines(sym, "30m", limit=1000)
        d15 = binance_client.get_klines(sym, "15m", limit=1000)
    except Exception:
        return []
    if any(x is None or len(x) < 60 for x in (d1, d4, d30, d15)):
        return []
    conf = {"1h": _prep_tf(d1), "30m": _prep_tf(d30), "15m": _prep_tf(d15)}
    d1o = conf["1h"]
    d1_ns = d1o["idx"]
    t15_start = int(_ns(d15.index)[0])
    t_end = int(d1_ns[-1])
    cutoff = t_end - int((FWD_H + 2) * NS_H)
    n1 = len(d1)
    rows = []
    for t in range(0, n1, K):
        ts_ns = int(d1_ns[t])
        if ts_ns < t15_start or ts_ns > cutoff:
            continue
        ts = d1.index[t]
        s1 = d1.iloc[:t+1]
        s4 = d4[d4.index <= ts]
        if len(s1) < 60 or len(s4) < 50:
            continue
        try:
            r = es.score_from_data(sym, s1, df_4h=s4, oi_hist=None,
                                   pct_24h=0.0, skip_deriv=True)
        except Exception:
            continue
        sc = float(r.get("score") or 0)
        side = r.get("side")
        tier = r.get("tier") or ""
        if sc < SCORE_FLOOR or side not in ("LONG", "SHORT"):
            continue
        if tier not in ("MAX", "HIGH"):
            continue
        plan = r.get("trade_plan") or {}
        entry = float(plan.get("entry") or 0)
        stop = float(plan.get("stop") or 0)
        tp1 = float(plan.get("tp1") or 0)
        if entry <= 0 or stop <= 0 or tp1 <= 0:
            continue
        end_ns = ts_ns + int(ALIVE_H * NS_H)
        rec = {"tier": tier, "side": side}
        for tfn in TFS:
            cf = _find_conf(conf[tfn], side, entry, stop, ts_ns, end_ns)
            if cf is None:
                rec[tfn] = {"o": "NOCONF"}
            else:
                cts, cpx = cf
                rec[tfn] = {"o": _outcome_1h(side, stop, tp1, d1o, cts),
                            "ts": cts, "px": cpx}
        rows.append(rec)
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
        for r in rs:
            r2 = dict(r); r2["sym"] = sym
            f.write(json.dumps(r2) + "\n")
        f.write(json.dumps({"done_coin": sym}) + "\n")


def _wr(vals):
    res = [x for x in vals if x in ("WIN", "LOSS")]
    w = sum(1 for x in res if x == "WIN")
    return len(res), (w / len(res) * 100 if res else 0.0)


def _med(x):
    return statistics.median(x) if x else 0.0


syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]
rows, done = _load()
todo = [s for s in syms if s not in done][:MAX_NEW]
print(f"Resume: {len(done)} done ({len(rows)} fires). This run: {todo}")
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
tot = len(rows)
print("\n" + "=" * 70)
_tag = "COMPLETE" if len(done2) >= N_COINS else f"PARTIAL {len(done2)}/{N_COINS}"
print(f"ENTRY-TIMING-TF [{_tag}] — {tot} MAX/HIGH fires (recent ~10d window)")
print("=" * 70)
print(f"{'TF':>5} | {'entered':>8} | {'decided':>7} | {'WIN%':>6} | "
      f"{'confirm-freq':>12}")
print("-" * 70)
for tfn in TFS:
    outs = [r[tfn]["o"] for r in rows]
    n, winp = _wr(outs)
    entered = sum(1 for o in outs if o != "NOCONF")
    print(f"{tfn:>5} | {entered:>8} | {n:>7} | {winp:>5.1f}% | "
          f"{entered}/{tot} ({entered/max(1,tot)*100:>3.0f}%)")

print("\nEARLIER + BETTER ENTRY vs 1h (fires where BOTH confirmed):")
for tfn in ("30m", "15m"):
    earlier, cheaper = [], []
    for r in rows:
        a, b = r["1h"], r[tfn]
        if a.get("ts") and b.get("ts"):
            earlier.append((a["ts"] - b["ts"]) / NS_H)
            e1, e2 = a["px"], b["px"]
            if e1 > 0:
                cheaper.append(((e1 - e2) / e1 * 100) if r["side"] == "LONG"
                               else ((e2 - e1) / e1 * 100))
    print(f"  {tfn:>3}: median {_med(earlier):+.1f}h earlier · "
          f"median entry {_med(cheaper):+.2f}% better · n={len(earlier)}")

if len(done2) < N_COINS:
    print(f"\n>> Re-run to add {min(MAX_NEW, N_COINS-len(done2))} more coins.")
print(f"\nDone in {time.time()-t0:.0f}s.")
