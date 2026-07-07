"""MASTER DEEP VALIDATION — every paper-trading board re-validated on 7-8
months of TRUE history (deep_history pagination; the old silent 1000-bar cap
made all prior windows ~41 days).

One engine pass produces every board's cell:
  ✅ TAKE NOW            — ELITE MAX/HIGH fire + confirmation entry
  ✅🔥 TAKE NOW + HOT     — + hot at the confirmation bar
  🏆 APEX proxy          — 2+/3+ corroborating edges at confirmation
  🌱 FRESH + HOT         — first fire on coin+side in 72h + hot
  ⚡ EARLY MOVERS        — STRONG tier + confirmation + hot
  🚀 EARLY-LANE          — EARLY MOVERS + early lanes (roc/vburst)
  💠 SST1 v2 ladder      — win% by corroborating-edge count (0/1/2/3+)
  🛡️ STRUCTURAL STOP     — plan stop vs structural stop on ALL entries
                           (the deployed change, re-validated deep)

Splits: FULL window · OLDER half · RECENT half (true multi-regime for the
first time). Outcomes: TP1-before-stop (first touch) + exp/signal.
Measurement only. Chunked + checkpointed (MD_MAX_NEW).
Env: MD_BARS (default 5800), MD_TRIM (default 0 = include recent).
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

N_COINS = int(os.environ.get("MD_N", "40"))
MAX_NEW = int(os.environ.get("MD_MAX_NEW", "10"))
BARS = int(os.environ.get("MD_BARS", "5800"))
TRIM = int(os.environ.get("MD_TRIM", "0"))
WARMUP = 220
K = 4
ALIVE = 48
FWD = 24
SCORE_FLOOR = 80.0
VOL_MULT = 1.2
HOT_PCTILE = 60.0
FRESH_GAP_H = 72
ROWS_FILE = f".master_rows_{BARS}_{TRIM}.jsonl"


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
        d1 = indicators.enrich(dh.get_klines_deep(sym, "1h", BARS + TRIM))
        d4 = indicators.enrich(dh.get_klines_deep(sym, "4h",
                                                  (BARS + TRIM) // 4 + 60))
        if TRIM > 0:
            d1 = d1.iloc[:-TRIM]
            d4 = d4[d4.index <= d1.index[-1]]
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
    n = len(d1); half = n // 2; rows = []
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
        p_entry = float(plan.get("entry") or 0)
        p_stop = float(plan.get("stop") or 0)
        tp1 = float(plan.get("tp1") or 0)
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
        hot = _pr(atr[max(0, ci-100):ci], atr[ci]) >= HOT_PCTILE
        rocb = _pr(roc6[max(0, ci-100):ci], roc6[ci]) >= HOT_PCTILE
        vburst = False
        try:
            bs, bside, _ = vb.lane_velocity_burst(d1.iloc[:ci+1])
            vburst = bs >= 78 and (bside or "").upper() == side
        except Exception:
            pass
        mtf = False
        try:
            e4v = float(e4_20[e4_20.index <= ts].iloc[-1])
            c4v = float(s4["close"].iloc[-1])
            mtf = ((side == "LONG" and c4v > e4v)
                   or (side == "SHORT" and c4v < e4v))
        except Exception:
            pass
        edges = sum([hot, rocb, vburst, mtf, fresh])
        ent = float(c[ci])
        s_struct = smart_stop.structural_stop(d1.iloc[:ci+1], side, ent,
                                              p_stop, tp1)
        out_p, rr_p = _tp_before_stop(side, ent, p_stop, tp1, h, l,
                                      ci+1, ci+1+FWD, n)
        out_s, rr_s = _tp_before_stop(side, ent, s_struct, tp1, h, l,
                                      ci+1, ci+1+FWD, n)
        rows.append({
            "tier": tier, "hot": bool(hot), "roc": bool(rocb),
            "vb": bool(vburst), "mtf": bool(mtf), "fresh": bool(fresh),
            "edges": int(edges),
            "half": "recent" if ci >= half else "older",
            "p": {"o": out_p, "rr": rr_p},
            "s": {"o": out_s, "rr": rr_s},
        })
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


def _stat(seg, key="s"):
    dec = [r[key] for r in seg if r.get(key, {}).get("o") in ("WIN", "LOSS")]
    w = sum(1 for e in dec if e["o"] == "WIN")
    exp = sum((e["rr"] if e["o"] == "WIN" else -1.0) for e in dec) \
        / max(1, len(seg))
    return (w/len(dec)*100 if dec else 0.0), exp


def board(label, seg):
    w, e = _stat(seg, "s")
    wo, eo = _stat([r for r in seg if r["half"] == "older"], "s")
    wr, er = _stat([r for r in seg if r["half"] == "recent"], "s")
    no = sum(1 for r in seg if r["half"] == "older")
    nr = len(seg) - no
    print(f"  {label:34} | n={len(seg):4} | win {w:5.1f}% exp {e:+.3f}R | "
          f"older({no:4}) {wo:5.1f}%/{eo:+.3f} | recent({nr:4}) "
          f"{wr:5.1f}%/{er:+.3f}")


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
print("\n" + "=" * 100)
_tag = "COMPLETE" if len(done2) >= N_COINS else f"PARTIAL {len(done2)}/{N_COINS}"
mh = [r for r in rows if r["tier"] in ("MAX", "HIGH")]
stg = [r for r in rows if r["tier"] == "STRONG"]
print(f"MASTER DEEP VALIDATION [{_tag}] — {len(rows)} confirmation entries "
      f"over ~{BARS//24} days x {len(done2)} coins (STRUCTURAL stop)")
print("=" * 100)
board("✅ TAKE NOW (MAX/HIGH)", mh)
board("✅🔥 TAKE NOW + HOT", [r for r in mh if r["hot"]])
board("🏆 APEX proxy (3+ edges, MAX/HIGH)", [r for r in mh
                                             if r["edges"] >= 3])
board("🏆 APEX proxy (2+ edges, MAX/HIGH)", [r for r in mh
                                             if r["edges"] >= 2])
board("🌱 FRESH + HOT (MAX/HIGH)", [r for r in mh if r["fresh"]
                                    and r["hot"]])
board("⚡ EARLY MOVERS (STRONG + HOT)", [r for r in stg if r["hot"]])
board("🚀 EARLY-LANE (EM + roc|vburst)", [r for r in stg if r["hot"]
                                          and (r["roc"] or r["vb"])])
print("-" * 100)
print("💠 SST1 v2 conviction ladder (all tiers, by corroborating edges):")
for e0, e1, lbl in ((0, 1, "0 edges"), (1, 2, "1 edge"), (2, 3, "2 edges"),
                    (3, 9, "3+ edges")):
    board(f"   {lbl}", [r for r in rows if e0 <= r["edges"] < e1])
print("-" * 100)
print("🛡️ STOP re-validation on ALL entries (deployed change):")
for key, lbl in (("p", "plan stop"), ("s", "STRUCTURAL stop")):
    w, e = _stat(rows, key)
    wo, eo = _stat([r for r in rows if r["half"] == "older"], key)
    wr, er = _stat([r for r in rows if r["half"] == "recent"], key)
    print(f"  {lbl:34} | win {w:5.1f}% exp {e:+.3f}R | older "
          f"{wo:5.1f}%/{eo:+.3f} | recent {wr:5.1f}%/{er:+.3f}")
print("=" * 100)
if len(done2) < N_COINS:
    print(">> Re-run to add more coins.")
print(f"Done in {time.time()-t0:.0f}s.")
