"""AT-FIRE RADIUS STUDY — the PIXEL gap (user 2026-08-14).

PIXEL fired STRONG 95 at +1.2% off its low, 47h before a +17% move —
and no stream could say so out loud: 🚨 IGNITION only takes MAX/HIGH,
and every STRONG stream waits for the pullback confirm that a grinder
never prints. ALICE's shape (MAX/HIGH at-fire + approval) is already
covered by IGNITION (measured 48.9%/+0.078R with approval).

This measures the missing cell: STRONG-tier AT-FIRE entries, gated by
the validated 🚀 approval (roc-hot or vburst>=78 same side) and by a
harder burst>=85 variant — against the MAX/HIGH baseline on the same
window. Entry at the fire close, plan TP1, structural stop, 24h
outcome — the same yardstick as every other study.

Ship rule: a STRONG at-fire stream exists ONLY if a cell here is
positive after fees in BOTH history halves. Measurement only.
Env: AF_N (40), AF_MAX_NEW (10), AF_BARS (3000), AF_K (4).
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

N_COINS = int(os.environ.get("AF_N", "40"))
MAX_NEW = int(os.environ.get("AF_MAX_NEW", "10"))
BARS = int(os.environ.get("AF_BARS", "3000"))
K = int(os.environ.get("AF_K", "4"))
WARMUP = 220
FWD = 24
ROW_GAP = 12
ROWS_FILE = f".atfire_strong_rows_{BARS}.jsonl"


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
        d1 = indicators.enrich(dh.get_klines_deep(sym, "1h", BARS))
        d4 = indicators.enrich(dh.get_klines_deep(sym, "4h",
                                                  BARS // 4 + 60))
    except Exception:
        return []
    if d1 is None or len(d1) < WARMUP + FWD + 5:
        return []
    h = d1["high"].to_numpy(); l = d1["low"].to_numpy()
    c = d1["close"].to_numpy()
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
        # the 🚀 approval gate + burst strength, at the fire bar
        ref = roc6[max(0, t-100):t]
        roc_hot = len(ref) > 0 and float(
            (ref < roc6[t]).mean() * 100) >= 60
        try:
            bs, bside, _ = vb.lane_velocity_burst(s1)
        except Exception:
            bs, bside = 0.0, ""
        vb_ok = bs >= 78 and (bside or "").upper() == side
        appr = bool(roc_hot or vb_ok)
        b85 = bs >= 85 and (bside or "").upper() == side
        # at-fire entry: fire close, plan TP, structural stop
        ent = float(c[t])
        s_st = smart_stop.structural_stop(s1, side, ent, p_stop, tp1)
        out, rr = _tp_before_stop(side, ent, s_st, tp1, h, l,
                                  t+1, t+1+FWD, n)
        rows.append({"tier": tier, "sc": round(sc, 1),
                     "appr": appr, "b85": bool(b85),
                     "half": "recent" if t >= half else "older",
                     "o": out, "rr": rr})
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


def _stat(seg):
    dec = [e for e in seg if e["o"] in ("WIN", "LOSS")]
    w = sum(1 for e in dec if e["o"] == "WIN")
    exp = sum((e["rr"] if e["o"] == "WIN" else -1.0) for e in dec) \
        / max(1, len(seg))
    return (w/len(dec)*100 if dec else 0.0), exp, len(seg)


def cell(label, seg):
    w, e, n = _stat(seg)
    so = [r for r in seg if r["half"] == "older"]
    sr = [r for r in seg if r["half"] == "recent"]
    wo, eo, no = _stat(so)
    wr, er, nr = _stat(sr)
    print(f"  {label:38} | n={n:4} | win {w:5.1f}% exp {e:+.3f}R | "
          f"older({no:4}) {wo:5.1f}%/{eo:+.3f} | "
          f"recent({nr:4}) {wr:5.1f}%/{er:+.3f}")


def report(rows):
    print("=" * 106)
    print(f"AT-FIRE RADIUS STUDY — {len(rows)} score-fires, entry AT "
          f"the fire close (no pullback wait), structural stop, 24h")
    print("=" * 106)
    mh = [r for r in rows if r["tier"] in ("MAX", "HIGH")]
    st = [r for r in rows if r["tier"] == "STRONG"]
    print("MAX/HIGH baseline (🚨 IGNITION's population):")
    cell("all at-fire", mh)
    cell("+ 🚀 approved", [r for r in mh if r["appr"]])
    cell("+ burst>=85", [r for r in mh if r["b85"]])
    print("STRONG — the PIXEL gap:")
    cell("all at-fire", st)
    cell("+ 🚀 approved", [r for r in st if r["appr"]])
    cell("+ 🚀 approved & sc>=90", [r for r in st
                                    if r["appr"] and r["sc"] >= 90])
    cell("+ burst>=85", [r for r in st if r["b85"]])
    cell("+ burst>=85 & sc>=90", [r for r in st
                                  if r["b85"] and r["sc"] >= 90])
    print("=" * 106)


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
    tag = ("COMPLETE" if len(done2) >= N_COINS
           else f"PARTIAL {len(done2)}/{N_COINS}")
    print(f"\n[{tag}]")
    report(rows)
    print(f"Done in {time.time()-t0:.0f}s.")
