"""🎯 CONFIDENCE TEARDOWN — which votes carry signal, and what beats them.

Same 1,413-confirm universe as backtest_pwconfirm.py, but instead of
scoring each fire it DUMPS the raw features to .pwfeat_rows.jsonl so the
analysis can be re-sliced without refetching 20 coins of history.

Question 1: do the three current edge-conf votes each carry signal on
            their own, or are they three views of one fact?
Question 2: is there anything NOT made of momentum-heat that separates
            winners better?

Features captured per fire (all computed on history <= i, no lookahead):

  current votes      atr_pct, roc_pct, burst      (raw percentiles /
                                                   score, not the
                                                   thresholded bools)
  NOT heat           ext_pct   — how far above the 24h low already
                     dist_ema  — stretch above ema20
                     body_pct  — confirm candle conviction
                     vol_mult  — volume vs its 20-bar mean
                     since_dip — bars since the last red/sub-ema close
                     rr        — the benchmark target in R
                     rs_btc    — 24h return minus BTC's
                     btc_align — BTC 24h direction agrees with LONG

Run: .venv/Scripts/python.exe backtest_conffeat.py
"""
import io
import json
import sys

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import numpy as np

import binance_client
import config
import smart_stop
import velocity_burst as vb

FEE = 0.00055
MAX_HOLD = 48
BARS = 1500
OUT = ".pwfeat_rows.jsonl"


def pct_below(hist, now):
    """Fraction of the trailing window below the current value."""
    return sum(1 for x in hist if x < now) / len(hist) if hist else 0.0


# ── BTC context, fetched once ─────────────────────────────────────────
btc = binance_client.get_klines("BTCUSDT", "1h", limit=BARS)
btc_c = btc["close"].to_numpy()
btc_idx = {str(ts): k for k, ts in enumerate(btc.index)}

rows = []
syms = list(getattr(config, "PERSONAL_WATCH", []))
print(f"scanning {len(syms)} coins x {BARS} 1h bars…", flush=True)

for sym in syms:
    try:
        d = binance_client.get_klines(sym, "1h", limit=BARS)
    except Exception:
        continue
    if d is None or len(d) < 200:
        continue
    o = d["open"].to_numpy()
    h = d["high"].to_numpy()
    lo = d["low"].to_numpy()
    c = d["close"].to_numpy()
    v = d["volume"].to_numpy()
    ema = d["close"].ewm(span=20, adjust=False).mean().to_numpy()
    tr = h - lo
    n = len(c)
    n_fires = 0

    for i in range(120, n - MAX_HOLD - 2):
        vma = float(v[i - 20:i].mean())
        if not (c[i] > o[i] and c[i] > c[i - 1] and c[i] > ema[i]
                and vma > 0 and v[i] > 1.2 * vma):
            continue
        if sum(1 for k in range(i - 5, i)
               if c[k] < o[k] or c[k] < ema[k]) < 2:
            continue

        entry = float(o[i + 1])
        atr = float(tr[i - 13:i + 1].mean())
        if entry <= 0 or atr <= 0:
            continue
        plan = entry - 1.5 * atr
        try:
            sl = float(smart_stop.structural_stop(
                d.iloc[:i + 1], "LONG", entry, plan,
                entry + (entry - plan)))
        except Exception:
            sl = plan
        r = entry - sl
        if r <= 0:
            continue

        # ── the three CURRENT votes, kept continuous ──────────────────
        atr_hist = [float(tr[j - 14:j].mean())
                    for j in range(max(15, i - 99), i + 1)]
        atr_pct = pct_below(atr_hist, float(tr[i - 13:i + 1].mean()))
        roc_now = float(c[i] / c[i - 6] - 1)
        roc_hist = [float(c[j] / c[j - 6] - 1)
                    for j in range(max(7, i - 99), i + 1)]
        roc_pct = pct_below(roc_hist, roc_now)
        try:
            bs, bd, _ = vb.lane_velocity_burst(d.iloc[:i + 1])
        except Exception:
            bs, bd = 0.0, ""
        long_burst = (bd or "").upper() == "LONG"
        burst = float(bs) if long_burst else 0.0

        votes = (int(atr_pct >= 0.6) + int(roc_pct >= 0.6)
                 + int(burst >= 78))
        conf = min(98, 25 + 20 * votes)

        # ── features that are NOT momentum-heat ───────────────────────
        low24 = float(lo[i - 23:i + 1].min())
        ext_pct = (entry - low24) / low24 * 100 if low24 > 0 else 0.0
        dist_ema = (entry - float(ema[i])) / entry * 100
        rng = float(h[i] - lo[i])
        body_pct = (float(c[i] - o[i]) / rng * 100) if rng > 0 else 0.0
        vol_mult = float(v[i] / vma)
        since_dip = 0
        for k in range(i, max(i - 20, 0), -1):
            if c[k] < o[k] or c[k] < ema[k]:
                break
            since_dip += 1

        strong = (atr_pct >= 0.6) or (burst >= 65)
        bench = float(h[i - 23:i + 1].max())
        br = (bench - entry) / r
        blo, bhi = (1.0, 2.5) if strong else (0.75, 1.25)
        clip = min(max(br, blo), bhi) if br > 0 else blo
        tp1 = entry + clip * r

        # BTC context at the same timestamp
        bi = btc_idx.get(str(d.index[i]))
        if bi is not None and bi >= 24:
            btc_ret = float(btc_c[bi] / btc_c[bi - 24] - 1) * 100
        else:
            btc_ret = 0.0
        coin_ret = float(c[i] / c[i - 24] - 1) * 100
        rs_btc = coin_ret - btc_ret

        # ── resolve ───────────────────────────────────────────────────
        fee_r = 2 * FEE * entry / r
        out, net = "OPEN", 0.0
        for j in range(i + 1, min(i + 1 + MAX_HOLD, n)):
            if lo[j] <= sl:
                out, net = "LOSS", -1.0 - fee_r
                break
            if h[j] >= tp1:
                out, net = "WIN", clip - fee_r
                break
        if out == "OPEN":
            px = float(c[min(i + MAX_HOLD, n - 1)])
            net = (px - entry) / r - fee_r
            out = "WIN" if net > 0 else "LOSS"

        rows.append({
            "sym": sym, "i": i, "out": out, "net": round(net, 4),
            "conf": conf, "votes": votes,
            "atr_pct": round(atr_pct, 3), "roc_pct": round(roc_pct, 3),
            "burst": round(burst, 1),
            "ext_pct": round(ext_pct, 3),
            "dist_ema": round(dist_ema, 3),
            "body_pct": round(body_pct, 1),
            "vol_mult": round(vol_mult, 3),
            "since_dip": since_dip,
            "rr": round(clip, 3),
            "rs_btc": round(rs_btc, 3),
            "btc_ret": round(btc_ret, 3),
        })
        n_fires += 1
    print(f"  {sym:12} {n_fires:4}", flush=True)

# half split within each coin's own history
by_sym = {}
for x in rows:
    by_sym.setdefault(x["sym"], []).append(x)
for xs in by_sym.values():
    xs.sort(key=lambda z: z["i"])
    mid = len(xs) // 2
    for k, x in enumerate(xs):
        x["half"] = "older" if k < mid else "recent"

with open(OUT, "w", encoding="utf-8") as f:
    for x in rows:
        f.write(json.dumps(x) + "\n")
print(f"\nwrote {len(rows)} rows -> {OUT}")
