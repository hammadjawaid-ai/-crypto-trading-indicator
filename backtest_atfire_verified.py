"""AT-FIRE + VERIFIED test — enter BEFORE the move (at the ELITE fire bar),
verified by the validated stack. The user's ask: "when APEX/TAKE NOW show,
the move has started — I want in BEFORE, verified by HOT/ELITE MAX/HIGH/
fresh/etc."

Honest prior: raw at-fire entry tested 27-38% win (vs confirmation 60-75%).
UNTESTED cell: at-fire entry restricted to fires with the FULL verification
stack present AT THE FIRE BAR (no future info):
    V1 HOT        — ATR pct-rank >= 60 (firing with force)
    V2 ROC burst  — 6-bar ROC pct-rank >= 60
    V3 V-BURST    — lane_velocity_burst >= 78 same side
    V4 MTF        — 4h close on the same side of its EMA20
    V5 FRESH      — first fire on this coin+side in 72h

Per MAX/HIGH fire (score >= 80): enter AT THE FIRE CLOSE. Two stop variants:
plan stop and STRUCTURAL stop (the shipped smart_stop helper — point-in-time).
Outcome = TP1 before stop (first touch), FWD 36 bars. ALSO computes, for the
SAME fires, the confirmation-entry outcome (the current system) so the
comparison is apples-to-apples on identical setups.

Report: win% + exp/signal by verification count (0-5), for both stops, plus
how many bars EARLIER at-fire is vs confirmation and the entry-price diff.
Measurement only — NOTHING deploys. Chunked + checkpointed (AF_MAX_NEW).
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
import smart_stop

N_COINS = int(os.environ.get("AF_N", "40"))
SKIP = int(os.environ.get("AF_SKIP", "0"))     # skip top-N (out-of-sample)
MAX_NEW = int(os.environ.get("AF_MAX_NEW", "14"))
BARS = int(os.environ.get("AF_BARS", "1500"))
# DISJOINT-TIME mode: fetch deep paginated history (bypasses the silent
# 1000-bar API cap) and TRIM the most recent bars — the window every prior
# test already used — so all fires come from genuinely untested history.
TRIM = int(os.environ.get("AF_TRIM", "0"))
if TRIM > 0:
    import deep_history as _dh
WARMUP = 220
K = 4
ALIVE = 48
FWD = 36
SCORE_FLOOR = 80.0
VOL_MULT = 1.2
HOT_PCTILE = 60.0
FRESH_GAP_H = 72
if TRIM > 0:
    ROWS_FILE = f".atfire_disjoint_{BARS}_{TRIM}.jsonl"
elif SKIP == 0:
    ROWS_FILE = (f".atfire_rows_{BARS}.jsonl" if BARS != 1500
                 else ".atfire_rows.jsonl")
else:
    ROWS_FILE = f".atfire_oos_{SKIP}_{BARS}.jsonl"


def _atr(h, l, c, n=14):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(n).mean().to_numpy()


def _pr(arr, val):
    if len(arr) == 0:
        return 0.0
    return float((arr < val).mean() * 100.0)


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
        if TRIM > 0:
            d1 = indicators.enrich(
                _dh.get_klines_deep(sym, "1h", BARS + TRIM))
            d4 = indicators.enrich(
                _dh.get_klines_deep(sym, "4h", (BARS + TRIM) // 4 + 60))
            d1 = d1.iloc[:-TRIM]              # cut the already-used window
            d4 = d4[d4.index <= d1.index[-1]]
        else:
            d1 = indicators.enrich(binance_client.get_klines(sym, "1h",
                                                             limit=BARS))
            d4 = indicators.enrich(binance_client.get_klines(sym, "4h",
                                                             limit=400))
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
        if tier not in ("MAX", "HIGH"):        # ELITE MAX/HIGH only (user)
            continue
        prev = last_fire.get(side)
        last_fire[side] = t
        fresh = prev is None or (t - prev) > FRESH_GAP_H
        plan = r.get("trade_plan") or {}
        p_entry = float(plan.get("entry") or 0)
        p_stop = float(plan.get("stop") or 0)
        tp1 = float(plan.get("tp1") or 0)
        if p_entry <= 0 or p_stop <= 0 or tp1 <= 0:
            continue
        # ---------- verifications AT THE FIRE BAR (no future info) --------
        ver = 0
        hot = _pr(atr[max(0, t-100):t], atr[t]) >= HOT_PCTILE
        if hot:
            ver += 1
        if _pr(roc6[max(0, t-100):t], roc6[t]) >= HOT_PCTILE:
            ver += 1
        try:
            bs, bside, _ = vb.lane_velocity_burst(d1.iloc[:t+1])
            if bs >= 78 and (bside or "").upper() == side:
                ver += 1
        except Exception:
            pass
        try:
            e4v = float(e4_20[e4_20.index <= ts].iloc[-1])
            c4v = float(s4["close"].iloc[-1])
            if (side == "LONG" and c4v > e4v) or (side == "SHORT"
                                                  and c4v < e4v):
                ver += 1
        except Exception:
            pass
        if fresh:
            ver += 1
        # ---------- AT-FIRE entry (the user's ask) ------------------------
        ent_f = float(c[t])
        # guard: plan stop must be on the protective side of the fire close
        ok_plan = (p_stop < ent_f < tp1) if side == "LONG" \
            else (p_stop > ent_f > tp1)
        s_struct = smart_stop.structural_stop(d1.iloc[:t+1], side, ent_f,
                                              p_stop, tp1)
        ok_struct = (s_struct < ent_f) if side == "LONG" \
            else (s_struct > ent_f)
        rec = {"ver": int(ver), "hot": bool(hot), "tier": tier,
               "half": "recent" if t >= n // 2 else "older"}
        if ok_plan:
            out, rr = _tp_before_stop(side, ent_f, p_stop, tp1, h, l,
                                      t+1, t+1+FWD, n)
            rec["fp"] = {"o": out, "rr": rr}
        if ok_struct:
            out, rr = _tp_before_stop(side, ent_f, s_struct, tp1, h, l,
                                      t+1, t+1+FWD, n)
            rec["fs"] = {"o": out, "rr": rr}
        # ---------- confirmation entry on the SAME fire (baseline) --------
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
        if conf_i is not None:
            ci = conf_i
            ent_c = float(c[ci])
            out, rr = _tp_before_stop(side, ent_c, p_stop, tp1, h, l,
                                      ci+1, ci+1+FWD, n)
            adv = ((ent_c - ent_f) / ent_c * 100)
            rec["cf"] = {"o": out, "rr": rr, "earlier": int(ci - t),
                         "adv": adv if side == "LONG" else -adv}
        if "fp" in rec or "fs" in rec:
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


def _stat(entries, key, nsig=None):
    dec = [r[key] for r in entries if r.get(key, {}).get("o") in
           ("WIN", "LOSS")]
    w = sum(1 for e in dec if e["o"] == "WIN")
    base = nsig if nsig else len(entries)
    exp = sum((e["rr"] if e["o"] == "WIN" else -1.0) for e in dec) \
        / max(1, base)
    return (w/len(dec)*100 if dec else 0.0), exp, len(dec)


syms = binance_client.get_top_symbols(SKIP + N_COINS)["symbol"].tolist()
syms = syms[SKIP:SKIP + N_COINS]
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
print("\n" + "=" * 74)
_tag = "COMPLETE" if len(done2) >= N_COINS else f"PARTIAL {len(done2)}/{N_COINS}"
print(f"AT-FIRE + VERIFIED [{_tag}] — {len(rows)} ELITE MAX/HIGH fires")
print("=" * 74)
cw, ce, cn = _stat(rows, "cf")
earlier = [r["cf"]["earlier"] for r in rows if "cf" in r]
adv = [r["cf"]["adv"] for r in rows if "cf" in r]
print(f"BASELINE — confirmation entry (same fires): win {cw:.1f}% · "
      f"exp {ce:+.3f}R (n={cn})")
print(f"AT-FIRE is earlier by med "
      f"{statistics.median(earlier) if earlier else 0:.0f} bars · price adv "
      f"med {statistics.median(adv) if adv else 0:+.2f}%")
print("-" * 74)
print("AT-FIRE entry, PLAN stop — by verification count:")
for v0, v1, lbl in ((0, 1, "0 ver"), (1, 2, "1 ver"), (2, 3, "2 ver"),
                    (3, 9, "3+ ver (the user's cell)")):
    seg = [r for r in rows if v0 <= r["ver"] < v1]
    w, e, nn = _stat(seg, "fp")
    print(f"   {lbl:24} | n={len(seg):4} | win {w:5.1f}% | exp {e:+.3f}R")
print("AT-FIRE entry, STRUCTURAL stop — by verification count:")
for v0, v1, lbl in ((0, 1, "0 ver"), (1, 2, "1 ver"), (2, 3, "2 ver"),
                    (3, 9, "3+ ver (the user's cell)")):
    seg = [r for r in rows if v0 <= r["ver"] < v1]
    w, e, nn = _stat(seg, "fs")
    print(f"   {lbl:24} | n={len(seg):4} | win {w:5.1f}% | exp {e:+.3f}R")
print("-" * 74)
print("Confirmation entry on the SAME 3+ verified fires (the fair fight):")
seg = [r for r in rows if r["ver"] >= 3]
w, e, nn = _stat(seg, "cf")
print(f"   3+ ver, confirmation     | n={len(seg):4} | win {w:5.1f}% | "
      f"exp {e:+.3f}R")
print("-" * 74)
print("STRICT CELLS (the 'only the best' bar) — at-fire STRUCTURAL:")
for lbl, seg in (("ver=5 PERFECT", [r for r in rows if r["ver"] >= 5]),
                 ("ver>=4 + MAX", [r for r in rows if r["ver"] >= 4
                                   and r.get("tier") == "MAX"]),
                 ("ver>=4 (any)", [r for r in rows if r["ver"] >= 4])):
    w, e, nn = _stat(seg, "fs")
    print(f"   {lbl:16} | n={len(seg):4} | win {w:5.1f}% | exp {e:+.3f}R")
print("-" * 74)
print("REGIME SPLIT — 3+ ver, at-fire STRUCTURAL vs confirmation:")
for hlf in ("older", "recent"):
    seg = [r for r in rows if r["ver"] >= 3 and r.get("half") == hlf]
    w1, e1, _ = _stat(seg, "fs")
    w2, e2, _ = _stat(seg, "cf")
    print(f"   {hlf:6} half | n={len(seg):4} | at-fire {w1:5.1f}% "
          f"{e1:+.3f}R | confirm {w2:5.1f}% {e2:+.3f}R")
print("=" * 74)
print("The user's bet is real ONLY if at-fire 3+ ver beats (or ~matches) "
      "the confirmation entry on the same fires.")
if len(done2) < N_COINS:
    print(f">> Re-run to add {min(MAX_NEW, N_COINS-len(done2))} more coins.")
print(f"Done in {time.time()-t0:.0f}s.")
