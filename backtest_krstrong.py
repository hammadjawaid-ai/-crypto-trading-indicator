"""KRONOS-ON-STRONG — the user's gate hypothesis, measured.

User 2026-08-15: "for strong elite convictions, if only kronos agrees
— maybe we should test that." Standing constraint: the existing elite
conviction / STRONG lane systems are NOT touched — this is
measurement only; a green verdict earns a SEPARATE stream/list.

Question: does 🔮 kronos agreement separate STRONG-tier winners the
way it does MAX/HIGH (+0.34R agree edge there)? Prior caution: the 🚀
approval gate does NOT transfer to STRONG (44.5%/+0.052R ≈ no gate),
so transfer cannot be assumed.

Method: STRONG-tier score fires (>=80), entry AT the fire close,
structural stop, plan TP1, 24h outcome — the same yardstick as the
at-fire radius study — plus a kronos read computed on the HISTORICAL
slice via kronos_forecast.forecast_window (backtest-safe, no
network). Cells: agree / conflict / flat, crossed with burst>=85 and
🚀 approval, split older/recent. Ship rule: a kronos-gated STRONG
stream exists only if the agree cell beats the ungated construct in
BOTH halves.
Env: KS_N (40), KS_MAX_NEW (40), KS_BARS (3000), KS_K (6).
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
import kronos_forecast as kf

N_COINS = int(os.environ.get("KS_N", "40"))
MAX_NEW = int(os.environ.get("KS_MAX_NEW", "40"))
BARS = int(os.environ.get("KS_BARS", "3000"))
K = int(os.environ.get("KS_K", "6"))
WARMUP = 420          # >= kronos LOOKBACK so every fire has context
FWD = 24
ROW_GAP = 24          # thinner sampling — each fire costs a forecast
FLAT_PCT = 0.5
ROWS_FILE = f".krstrong_rows_{BARS}.jsonl"


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


def _kr_verdict(d1, t):
    """Kronos read on the slice ending at bar t (no lookahead)."""
    try:
        look = min(getattr(kf, "LOOKBACK", 400), t + 1)
        sl = d1.iloc[t + 1 - look:t + 1]
        x_df = pd.DataFrame({
            "open": sl["open"].astype(float).to_numpy(),
            "high": sl["high"].astype(float).to_numpy(),
            "low": sl["low"].astype(float).to_numpy(),
            "close": sl["close"].astype(float).to_numpy(),
            "volume": sl["volume"].astype(float).to_numpy()})
        x_ts = pd.Series(sl.index)
        pred = kf.forecast_window(x_df, x_ts, horizon=24, freq="1h")
        last = float(sl["close"].iloc[-1])
        exp = (float(pred["close"].iloc[-1]) / last - 1.0) * 100.0
        d = ("UP" if exp >= FLAT_PCT
             else "DOWN" if exp <= -FLAT_PCT else "FLAT")
        return d, exp
    except Exception:
        return None, 0.0


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
        if (r.get("tier") or "") != "STRONG" or sc < 80 \
                or side not in ("LONG", "SHORT"):
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
        kd, kexp = _kr_verdict(d1, t)
        if kd is None:
            continue
        agree = ((kd == "UP" and side == "LONG")
                 or (kd == "DOWN" and side == "SHORT"))
        conflict = ((kd == "DOWN" and side == "LONG")
                    or (kd == "UP" and side == "SHORT"))
        ent = float(c[t])
        s_st = smart_stop.structural_stop(s1, side, ent, p_stop, tp1)
        out, rr = _tp_before_stop(side, ent, s_st, tp1, h, l,
                                  t+1, t+1+FWD, n)
        rows.append({"sc": round(sc, 1), "appr": appr,
                     "b85": bool(b85),
                     "kr": ("agree" if agree
                            else "conflict" if conflict else "flat"),
                     "kexp": round(kexp, 2),
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
    print(f"  {label:36} | n={n:4} | win {w:5.1f}% exp {e:+.3f}R | "
          f"older({no:4}) {wo:5.1f}%/{eo:+.3f} | "
          f"recent({nr:4}) {wr:5.1f}%/{er:+.3f}")


def report(rows):
    print("=" * 108)
    print(f"KRONOS-ON-STRONG — {len(rows)} STRONG at-fire entries "
          f"with slice-based kronos reads (no lookahead)")
    print("=" * 108)
    cell("all STRONG (ungated baseline)", rows)
    for kr in ("agree", "conflict", "flat"):
        cell(f"kronos {kr.upper()}", [r for r in rows
                                      if r["kr"] == kr])
    cell("AGREE & |exp|>=1%", [r for r in rows if r["kr"] == "agree"
                               and abs(r["kexp"]) >= 1.0])
    print("-" * 108)
    b85 = [r for r in rows if r["b85"]]
    cell("burst>=85 (the shipped gate)", b85)
    cell("burst>=85 & kronos AGREE", [r for r in b85
                                      if r["kr"] == "agree"])
    ap = [r for r in rows if r["appr"]]
    cell("approved & kronos AGREE", [r for r in ap
                                     if r["kr"] == "agree"])
    cell("sc>=90 & kronos AGREE", [r for r in rows
                                   if r["sc"] >= 90
                                   and r["kr"] == "agree"])
    print("=" * 108)


if __name__ == "__main__":
    if not kf.available():
        print("Kronos unavailable (torch missing?) — aborting.")
        sys.exit(1)
    syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()
    syms = syms[:N_COINS]
    rows, done = _load()
    todo = [s for s in syms if s not in done][:MAX_NEW]
    print(f"Resume: {len(done)} done ({len(rows)} fires). Run: {todo}")
    t0 = time.time()
    # 2 workers only — each fire pays a torch forecast; more threads
    # just fight over the same cores.
    with ThreadPoolExecutor(max_workers=min(2, len(todo) or 1)) as pool:
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
