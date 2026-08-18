"""SECOND-LEG STUDY — do recent elite winners' re-ignitions pay?
(user 2026-08-17, the ACE case: elite winner re-broke days after its
card expired and nothing was watching; "patterns are important too,
validate this as well".)

Population: every elite-class fire (score>=80, MAX/HIGH) in history.
For each, the window T+24h .. T+7d after the fire is scanned for the
LIVE watcher's construct: a break of the 24-bar consolidation high
(low for shorts) on expanding volume (>=1.5x the 20-bar average).
Entry at the break close with the watcher's exact ATR plan (stop
1.5*ATR behind the level, TP1 1R). Outcome: first-touch TP1-vs-stop
over 48h.

PATTERN CELLS (the user's ask): each break is tagged with the chart
state at that bar —
  EMA   : close > EMA20 > EMA50 (clean uptrend stack; mirrored short)
  COIL  : 24-bar range in the tightest 40% of its trailing 100 bars
  BURST : lane velocity burst >= 85 same side
so the report shows whether the patterns the user watches actually
separate paying second legs from fakeouts.

Ship rule: the live 🔥 watcher keeps buzzing regardless (watch-only);
a desk/money seat later requires the usual green-in-both-halves.
Env: SL_N (40), SL_MAX_NEW (40), SL_BARS (3000), SL_K (4).
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
import deep_history as dh

N_COINS = int(os.environ.get("SL_N", "40"))
MAX_NEW = int(os.environ.get("SL_MAX_NEW", "40"))
BARS = int(os.environ.get("SL_BARS", "3000"))
K = int(os.environ.get("SL_K", "4"))
WARMUP = 220
GAP_MIN_H = 24          # second-leg window starts 24h after the fire
GAP_MAX_H = 7 * 24      # ... and closes 7 days after (the live rule)
FWD = 48
BRK_VOL = 1.5
ROWS_FILE = f".secondleg_rows_{BARS}.jsonl"


def _one(sym):
    try:
        d1 = indicators.enrich(dh.get_klines_deep(sym, "1h", BARS))
        d4 = indicators.enrich(dh.get_klines_deep(sym, "4h",
                                                  BARS // 4 + 60))
    except Exception:
        return []
    if d1 is None or len(d1) < WARMUP + GAP_MAX_H + FWD + 5:
        return []
    o = d1["open"].to_numpy(); h = d1["high"].to_numpy()
    l = d1["low"].to_numpy(); c = d1["close"].to_numpy()
    v = d1["volume"].to_numpy()
    ema20 = d1["close"].ewm(span=20, adjust=False).mean().to_numpy()
    ema50 = d1["close"].ewm(span=50, adjust=False).mean().to_numpy()
    vma = pd.Series(v).rolling(20).mean().to_numpy()
    tr = np.maximum(h - l, np.maximum(
        np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    atr = pd.Series(tr).rolling(14).mean().to_numpy()
    rng24 = (pd.Series(h).rolling(24).max()
             - pd.Series(l).rolling(24).min()).to_numpy()
    n = len(d1); half = n // 2; rows = []
    last_fire: dict = {}
    for t in range(WARMUP, n - GAP_MAX_H - FWD - 1, K):
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
        if (r.get("tier") or "") not in ("MAX", "HIGH") or sc < 80 \
                or side not in ("LONG", "SHORT"):
            continue
        # one second-leg scan per fire EPISODE (dedup 24h per side)
        prev = last_fire.get(side)
        last_fire[side] = t
        if prev is not None and (t - prev) < 24:
            continue
        lng = side == "LONG"
        # scan the window T+24h..T+7d for the watcher's break
        for i in range(t + GAP_MIN_H, min(t + GAP_MAX_H, n - FWD - 1)):
            ref_hi = float(np.max(h[i-24:i]))
            ref_lo = float(np.min(l[i-24:i]))
            if lng:
                broke = (c[i] > ref_hi and c[i] > o[i]
                         and vma[i] > 0 and v[i] > BRK_VOL * vma[i])
            else:
                broke = (c[i] < ref_lo and c[i] < o[i]
                         and vma[i] > 0 and v[i] > BRK_VOL * vma[i])
            if not broke:
                continue
            a14 = atr[i]
            if not a14 or a14 != a14 or a14 <= 0:
                break
            ent = float(c[i])
            stop = ent - 1.5 * a14 if lng else ent + 1.5 * a14
            tp1 = ent + 1.5 * a14 if lng else ent - 1.5 * a14
            out, rr = "NONE", 1.0
            for fb in range(i + 1, min(i + 1 + FWD, n)):
                if lng:
                    if l[fb] <= stop:
                        out = "LOSS"; break
                    if h[fb] >= tp1:
                        out = "WIN"; break
                else:
                    if h[fb] >= stop:
                        out = "LOSS"; break
                    if l[fb] <= tp1:
                        out = "WIN"; break
            # pattern cells at the break bar
            ema_ok = ((c[i] > ema20[i] > ema50[i]) if lng
                      else (c[i] < ema20[i] < ema50[i]))
            ref_r = rng24[max(0, i-100):i]
            ref_r = ref_r[~np.isnan(ref_r)]
            coil = (len(ref_r) > 0 and rng24[i-1] == rng24[i-1]
                    and float((ref_r > rng24[i-1]).mean()) >= 0.6)
            b85 = False
            try:
                bs, bside, _ = vb.lane_velocity_burst(d1.iloc[:i+1])
                b85 = bs >= 85 and (bside or "").upper() == side
            except Exception:
                pass
            rows.append({"sc": round(sc, 1),
                         "gap_h": i - t,
                         "ema": bool(ema_ok), "coil": bool(coil),
                         "b85": bool(b85),
                         "half": "recent" if i >= half else "older",
                         "o": out, "rr": rr})
            break               # first break per fire episode only
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
    exp = sum((1.0 if e["o"] == "WIN" else -1.0) for e in dec) \
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
    print(f"SECOND-LEG STUDY — {len(rows)} consolidation breaks in "
          f"the 1-7d window after elite MAX/HIGH fires (1R ATR plan)")
    print("=" * 108)
    cell("all second-leg breaks", rows)
    cell("+ EMA stack aligned", [r for r in rows if r["ema"]])
    cell("+ COILED before break", [r for r in rows if r["coil"]])
    cell("+ burst>=85", [r for r in rows if r["b85"]])
    cell("EMA & coil", [r for r in rows if r["ema"] and r["coil"]])
    cell("EMA & burst>=85", [r for r in rows
                             if r["ema"] and r["b85"]])
    cell("early window (24-72h)", [r for r in rows
                                   if r["gap_h"] <= 72])
    cell("late window (72h-7d)", [r for r in rows
                                  if r["gap_h"] > 72])
    print("=" * 108)


if __name__ == "__main__":
    syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()
    syms = syms[:N_COINS]
    rows, done = _load()
    todo = [s for s in syms if s not in done][:MAX_NEW]
    print(f"Resume: {len(done)} done ({len(rows)} breaks). Run: {todo}")
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
