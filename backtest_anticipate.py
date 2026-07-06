"""ANTICIPATE overnight test — "real bets, not chasing": enter at the
pullback-to-support (earlier, better price) with a STRUCTURAL stop below
support, vs the current confirmation entry.

Why this is NOT a repeat of the 7 failed earlier-entry tests: every one of
those changed only the ENTRY (entered earlier at the same-ish stop) and got
gutted by adverse selection. This changes ENTRY *and* STOP together — you buy
the pullback AT a real support level and risk only to just below it. The
geometry is different: smaller, structural risk for the same target. Even a
lower win rate can pay if the risk shrinks enough. That reconciliation is the
whole question.

Per MAX/HIGH/STRONG setup (score>=80):
  V0 CONFIRM (current)  — pullback + confirmation candle, entry=close,
                          plan stop, plan tp1.
  V1 ANTICIPATE         — at signal time define support = swing low of last
                          10 bars; place a LIMIT there; if price pulls back
                          and touches it (within the alive window, before the
                          plan stop), FILL at support with stop = support −
                          0.35×ATR (structural). Same tp1. This fills EARLIER
                          (before the confirmation candle) at a BETTER price.
Honest costs the test charges V1: setups that never pull back to support =
NO FILL (missed — counted as 0R over signals); pullbacks that knife through
support = filled then stopped. Decisive metric: exp/signal (no-fill = 0).

Also reports: fill%, bars EARLIER than confirmation, entry-price advantage.
Measurement only — NOTHING deploys. Chunked + checkpointed (AN_MAX_NEW).
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
MAX_NEW = int(os.environ.get("AN_MAX_NEW", "14"))
BARS = 1500
WARMUP = 220
K = 4
ALIVE = 48
FWD = 36
SCORE_FLOOR = 80.0
VOL_MULT = 1.2
STRUCT_LOOKBACK = 10
STRUCT_BUF = 0.35
ROWS_FILE = ".antic_rows.jsonl"


def _atr(h, l, c, n=14):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(n).mean().to_numpy()


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
        plan = r.get("trade_plan") or {}
        p_entry = float(plan.get("entry") or 0)
        p_stop = float(plan.get("stop") or 0); tp1 = float(plan.get("tp1") or 0)
        if p_entry <= 0 or p_stop <= 0 or tp1 <= 0:
            continue
        a_atr = float(atr[t])
        if a_atr <= 0:
            continue
        # ---- V1 ANTICIPATE: support = swing extreme at signal time --------
        if side == "LONG":
            support = float(np.min(l[max(0, t-STRUCT_LOOKBACK):t+1]))
            a_stop = support - STRUCT_BUF * a_atr
        else:
            support = float(np.max(h[max(0, t-STRUCT_LOOKBACK):t+1]))
            a_stop = support + STRUCT_BUF * a_atr
        antic_fill = None
        # ---- V0 CONFIRM: pullback + confirmation candle -------------------
        pulled = False; conf_i = None
        for i in range(t+1, t+1+ALIVE):
            if i >= n:
                break
            # anticipatory limit fills the first time support is touched,
            # provided the structural stop hasn't already been breached
            if antic_fill is None:
                touch = (l[i] <= support) if side == "LONG" else (h[i] >= support)
                broke = (l[i] <= a_stop) if side == "LONG" else (h[i] >= a_stop)
                if touch and not broke:
                    antic_fill = i
                elif broke:
                    antic_fill = -1        # knifed through before filling long
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
        rec = {"tier": tier}
        # V0 outcome
        if conf_i is not None:
            ent0 = float(c[conf_i])
            out0, rr0 = _tp_before_stop(side, ent0, p_stop, tp1, h, l,
                                        conf_i+1, conf_i+1+FWD, n)
            rec["v0"] = {"o": out0, "rr": rr0, "i": conf_i, "px": ent0}
        else:
            rec["v0"] = {"o": "NOENT"}
        # V1 outcome
        if antic_fill is not None and antic_fill >= 0:
            entA = support
            # guard: support must be a valid long/short entry vs stop & tp1
            good = ((side == "LONG" and a_stop < entA < tp1)
                    or (side == "SHORT" and a_stop > entA > tp1))
            if good:
                outA, rrA = _tp_before_stop(side, entA, a_stop, tp1, h, l,
                                            antic_fill+1, antic_fill+1+FWD, n)
                earlier = (conf_i - antic_fill) if conf_i is not None else None
                adv = None
                if conf_i is not None and c[conf_i] > 0:
                    d = (c[conf_i] - entA) / c[conf_i] * 100
                    adv = d if side == "LONG" else -d
                rec["v1"] = {"o": outA, "rr": rrA, "i": antic_fill,
                             "earlier": earlier, "adv": adv}
            else:
                rec["v1"] = {"o": "BADGEO"}
        elif antic_fill == -1:
            rec["v1"] = {"o": "KNIFE"}     # broke support before filling
        else:
            rec["v1"] = {"o": "NOFILL"}    # never pulled back to support
        if rec["v0"]["o"] != "NOENT" or rec["v1"]["o"] not in (
                "NOFILL", "NOENT"):
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
        for rec in rs:
            r2 = dict(rec); r2["sym"] = sym
            f.write(json.dumps(r2) + "\n")
        f.write(json.dumps({"done_coin": sym}) + "\n")


def rep(rows):
    # V0 over all setups that produced a confirmation entry
    v0 = [r["v0"] for r in rows if r.get("v0", {}).get("o") in ("WIN","LOSS","NONE")]
    v0d = [e for e in v0 if e["o"] in ("WIN", "LOSS")]
    w0 = sum(1 for e in v0d if e["o"] == "WIN")
    exp0 = sum((e["rr"] if e["o"] == "WIN" else -1.0) for e in v0d) \
        / max(1, len(v0))
    print(f"  V0 CONFIRM (current)  | signals {len(v0):4} | win "
          f"{(w0/len(v0d)*100 if v0d else 0):5.1f}% | exp/signal {exp0:+.3f}R")
    # V1 over the SAME opportunity set (all rows), no-fill = 0R
    v1all = [r["v1"] for r in rows]
    filled = [e for e in v1all if e["o"] in ("WIN", "LOSS", "NONE")]
    v1d = [e for e in filled if e["o"] in ("WIN", "LOSS")]
    w1 = sum(1 for e in v1d if e["o"] == "WIN")
    nofill = sum(1 for e in v1all if e["o"] == "NOFILL")
    knife = sum(1 for e in v1all if e["o"] == "KNIFE")
    exp1 = sum((e["rr"] if e["o"] == "WIN" else -1.0) for e in v1d) \
        / max(1, len(rows))
    earlier = [e["earlier"] for e in filled if e.get("earlier") is not None]
    adv = [e["adv"] for e in filled if e.get("adv") is not None]
    print(f"  V1 ANTICIPATE (support)| signals {len(rows):4} | win "
          f"{(w1/len(v1d)*100 if v1d else 0):5.1f}% | exp/signal {exp1:+.3f}R")
    print(f"     fill {len(filled)/max(1,len(rows))*100:4.0f}% · no-fill "
          f"{nofill/max(1,len(rows))*100:3.0f}% · knifed "
          f"{knife/max(1,len(rows))*100:3.0f}% · earlier med "
          f"{(statistics.median(earlier) if earlier else 0):+.0f} bars · "
          f"price adv med {(statistics.median(adv) if adv else 0):+.2f}%")


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
print("\n" + "=" * 74)
_tag = "COMPLETE" if len(done2) >= N_COINS else f"PARTIAL {len(done2)}/{N_COINS}"
print(f"ANTICIPATE [{_tag}] — {len(rows)} setups")
print("=" * 74)
rep(rows)
print("=" * 74)
print("Ship anticipation ONLY if V1 exp/signal beats V0 — earlier+cheaper "
      "must outweigh the runners it misses (no-fill) and knives it catches.")
if len(done2) < N_COINS:
    print(f">> Re-run to add {min(MAX_NEW, N_COINS-len(done2))} more coins.")
print(f"Done in {time.time()-t0:.0f}s.")
