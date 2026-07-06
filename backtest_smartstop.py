"""SMART-STOP overnight test — the GIGGLE problem: stopped in the noise,
then it runs to TP.

Grounded finding: GIGGLE ATR=2.91%, a 1.4% stop = 0.48x ATR = INSIDE the
noise band. Hypothesis: the plan's stop is sometimes placed too tight
RELATIVE TO THE COIN'S VOLATILITY, so ordinary wiggle hits it before the
real move — the user's exact pain. (Different from the flat wider-stop test,
which widened everything uniformly and washed out.)

Per historical MAX/HIGH/STRONG TAKE_NOW entry, measure:
  A) PLAN stop (baseline)          — the current stop
  B) ATR-FLOOR stop                — never tighter than 1.5x ATR (only
                                     widens the too-tight ones; keeps the
                                     rest as-is)
  C) STRUCTURAL stop               — below the recent swing low − 0.25x ATR
  D) ATR-2.0 stop                  — entry ± 2.0x ATR (pure volatility)
For each: win% (TP1 before that stop) + exp/signal in that stop's OWN R
(honest — wider stop = smaller R per win).

Plus the DIAGNOSTIC the user asked for:
  - STOPPED-THEN-RAN %: of PLAN-stop losses, how often does price reach TP1
    later in the window? (quantifies "SL hit, then it hit TP")
  - stop_dist / ATR segmentation: do too-tight (<1x ATR) plan stops get
    stopped disproportionately, and does the ATR-floor fix that subset?

Measurement only — NOTHING deploys. Chunked + checkpointed (SS_MAX_NEW).
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
MAX_NEW = int(os.environ.get("SS_MAX_NEW", "14"))
BARS = 1500
WARMUP = 220
K = 4
ALIVE = 48
FWD = 36                 # extended so the "then ran" can manifest
SCORE_FLOOR = 80.0
VOL_MULT = 1.2
ATR_FLOOR_MULT = 1.5     # variant B: never tighter than this × ATR
STRUCT_LOOKBACK = 10     # variant C: swing low/high window
STRUCT_BUF = 0.25        # variant C: ATR buffer beyond structure
ATR_WIDE_MULT = 2.0      # variant D
ROWS_FILE = ".smartstop_rows.jsonl"


def _atr(h, l, c, n=14):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(n).mean().to_numpy()


def _hit_tp_before_stop(side, stop, tp1, hi, lo, a, b, n):
    """First-touch: returns 'WIN' (tp1 first), 'LOSS' (stop first), 'NONE'."""
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


def _stopped_then_ran(side, stop, tp1, hi, lo, a, b, n):
    """Did the stop get hit AND price reach tp1 later in the window?"""
    stop_bar = None
    for fb in range(a, min(b, n)):
        hit_stop = (lo[fb] <= stop) if side == "LONG" else (hi[fb] >= stop)
        if hit_stop:
            stop_bar = fb
            break
    if stop_bar is None:
        return False
    for fb in range(stop_bar + 1, min(b, n)):
        hit_tp = (hi[fb] >= tp1) if side == "LONG" else (lo[fb] <= tp1)
        if hit_tp:
            return True
    return False


def _exp(side, entry, stop, tp1):
    risk = abs(entry - stop)
    return abs(tp1 - entry) / risk if risk > 0 else 0.0


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
        ent = float(c[ci]); a_atr = float(atr[ci])
        if a_atr <= 0 or tp1 == ent:
            continue
        plan_dist = abs(ent - p_stop)
        # stop variants (all on the LOSS-protection side of entry)
        if side == "LONG":
            s_plan = p_stop
            s_floor = ent - max(plan_dist, ATR_FLOOR_MULT * a_atr)
            swing = float(np.min(l[max(0, ci-STRUCT_LOOKBACK):ci+1]))
            s_struct = swing - STRUCT_BUF * a_atr
            s_atr2 = ent - ATR_WIDE_MULT * a_atr
        else:
            s_plan = p_stop
            s_floor = ent + max(plan_dist, ATR_FLOOR_MULT * a_atr)
            swing = float(np.max(h[max(0, ci-STRUCT_LOOKBACK):ci+1]))
            s_struct = swing + STRUCT_BUF * a_atr
            s_atr2 = ent + ATR_WIDE_MULT * a_atr
        rec = {"tier": tier, "sd_atr": round(plan_dist / a_atr, 3)}
        for tagname, sv in (("plan", s_plan), ("floor", s_floor),
                            ("struct", s_struct), ("atr2", s_atr2)):
            # guard: stop must be strictly protective & not beyond tp1
            bad = ((side == "LONG" and (sv >= ent or sv >= tp1))
                   or (side == "SHORT" and (sv <= ent or sv <= tp1)))
            if bad:
                rec[tagname] = {"o": "SKIP", "rr": 0.0}
                continue
            out = _hit_tp_before_stop(side, sv, tp1, h, l,
                                      ci+1, ci+1+FWD, n)
            rec[tagname] = {"o": out, "rr": _exp(side, ent, sv, tp1)}
        rec["ran"] = bool(_stopped_then_ran(side, s_plan, tp1, h, l,
                                            ci+1, ci+1+FWD, n))
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


def rep_stop(label, rs):
    print(f"--- {label} (n={len(rs)}) ---")
    for tag, nm in (("plan", "PLAN stop (current)"),
                    ("floor", "ATR-FLOOR (>=1.5xATR)"),
                    ("struct", "STRUCTURAL (swing)"),
                    ("atr2", "ATR-2.0x")):
        dec = [r[tag] for r in rs if r.get(tag, {}).get("o") in ("WIN", "LOSS")]
        w = sum(1 for e in dec if e["o"] == "WIN")
        exp = sum((e["rr"] if e["o"] == "WIN" else -1.0) for e in dec) \
            / max(1, len(rs))
        rrs = [e["rr"] for e in dec]
        print(f"  {nm:24} | dec {len(dec):4} | win "
              f"{(w/len(dec)*100 if dec else 0):5.1f}% | avg RR "
              f"{(np.mean(rrs) if rrs else 0):4.2f} | exp/signal {exp:+.3f}R")


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
print(f"SMART-STOP [{_tag}] — {len(rows)} TAKE_NOW entries")
print("=" * 74)
rep_stop("ALL", rows)
# stopped-then-ran diagnostic
plan_losses = [r for r in rows if r.get("plan", {}).get("o") == "LOSS"]
ran = [r for r in plan_losses if r.get("ran")]
print("-" * 74)
print(f"STOPPED-THEN-RAN: {len(ran)}/{len(plan_losses)} plan-stop losses "
      f"({(len(ran)/max(1,len(plan_losses))*100):.1f}%) hit TP1 AFTER the "
      f"stop — the GIGGLE scenario.")
# segmentation by plan stop tightness
def _seg(lo, hi):
    seg = [r for r in rows if lo <= r.get("sd_atr", 0) < hi]
    dec = [r["plan"] for r in seg if r.get("plan", {}).get("o") in ("WIN","LOSS")]
    w = sum(1 for e in dec if e["o"] == "WIN")
    fdec = [r["floor"] for r in seg
            if r.get("floor", {}).get("o") in ("WIN", "LOSS")]
    fw = sum(1 for e in fdec if e["o"] == "WIN")
    fexp = sum((e["rr"] if e["o"] == "WIN" else -1.0) for e in fdec) \
        / max(1, len(seg))
    pexp = sum((e["rr"] if e["o"] == "WIN" else -1.0)
               for e in dec) / max(1, len(seg))
    print(f"  stop {lo:.1f}-{hi:.1f}x ATR | n={len(seg):4} | PLAN win "
          f"{(w/len(dec)*100 if dec else 0):5.1f}% exp {pexp:+.3f}R | "
          f"FLOOR win {(fw/len(fdec)*100 if fdec else 0):5.1f}% exp "
          f"{fexp:+.3f}R")
print("-" * 74)
print("STOP-TIGHTNESS SEGMENTS (does fixing too-tight stops help?):")
_seg(0.0, 1.0); _seg(1.0, 2.0); _seg(2.0, 99.0)
print("=" * 74)
print("Ship a smarter stop ONLY if it beats PLAN on exp/signal. Wider raises "
      "win% mechanically — expectancy is the judge.")
if len(done2) < N_COINS:
    print(f">> Re-run to add {min(MAX_NEW, N_COINS-len(done2))} more coins.")
print(f"Done in {time.time()-t0:.0f}s.")
