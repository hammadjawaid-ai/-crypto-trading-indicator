"""BTC GATE study — the user's exact complaint, tested on 8 months:
"when market goes up everything is green, 3-4h later everything is red —
how do we make decisions?"

Hypothesis: alt setups are hostage to BTC. The SAME textbook-green alt
moment (uptrend + fresh high) resolves completely differently depending on
BTC's state AT THAT MOMENT. If true, the decision layer isn't a better alt
signal — it's a RISK-ON/RISK-OFF gate: stand down when BTC is hostile.

Method (pure price, deep 8-month history, no signal engine → fast):
  - For each alt bar where a cheap TAKE-NOW proxy is true
    (close > EMA20 > EMA50 and close within 1 ATR of the 24h high):
    outcome = +1.5 ATR before −1.0 ATR within 24 bars (first touch).
  - Split by BTC state at that bar:
      RISK-ON   : BTC close > BTC EMA50(1h) and EMA20 rising
      NEUTRAL   : mixed
      RISK-OFF  : BTC close < BTC EMA50(1h) and EMA20 falling
  - Mirror for downtrend-short proxies.
Evidence = a big win% spread between BTC states on identical alt setups.
"""
from __future__ import annotations
import io, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client, indicators
import deep_history as dh

N_COINS = 40
BARS = 5800
K = 2
FWD = 24
ROWS_FILE = ".btcgate_rows.jsonl"


def _atr(h, l, c, n=14):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(n).mean().to_numpy()


print("loading BTC deep history (the gate)...")
_btc = indicators.enrich(dh.get_klines_deep("BTCUSDT", "1h", BARS))
_bc = _btc["close"].to_numpy()
_be20 = _btc["close"].ewm(span=20, adjust=False).mean().to_numpy()
_be50 = _btc["close"].ewm(span=50, adjust=False).mean().to_numpy()
_bslope = np.concatenate([[0.0], np.diff(_be20)])
_btc_ts = _btc.index.values.astype("datetime64[s]").astype("int64")


def _btc_state(ts_s: int) -> str:
    i = int(np.searchsorted(_btc_ts, ts_s, side="right")) - 1
    if i < 1:
        return "NEUTRAL"
    up = _bc[i] > _be50[i] and _bslope[i] > 0
    dn = _bc[i] < _be50[i] and _bslope[i] < 0
    return "RISK_ON" if up else ("RISK_OFF" if dn else "NEUTRAL")


def _first_touch(side, entry, stop, target, hi, lo, a, b, n):
    for fb in range(a, min(b, n)):
        if side == "LONG":
            if lo[fb] <= stop:
                return "LOSS"
            if hi[fb] >= target:
                return "WIN"
        else:
            if hi[fb] >= stop:
                return "LOSS"
            if lo[fb] <= target:
                return "WIN"
    return "NONE"


def _one(sym):
    if sym == "BTCUSDT":
        return []
    try:
        d = indicators.enrich(dh.get_klines_deep(sym, "1h", BARS))
    except Exception:
        return []
    if d is None or len(d) < 300:
        return []
    h = d["high"].to_numpy(); l = d["low"].to_numpy()
    c = d["close"].to_numpy()
    e20 = d["close"].ewm(span=20, adjust=False).mean().to_numpy()
    e50 = d["close"].ewm(span=50, adjust=False).mean().to_numpy()
    atr = _atr(h, l, c, 14)
    ts_s = d.index.values.astype("datetime64[s]").astype("int64")
    n = len(d); rows = []
    for t in range(120, n - FWD - 1, K):
        a = float(atr[t])
        if not (a > 0):
            continue
        hi24 = float(np.max(h[max(0, t-24):t+1]))
        lo24 = float(np.min(l[max(0, t-24):t+1]))
        long_sig = (c[t] > e20[t] > e50[t]) and (hi24 - c[t]) <= 1.0 * a
        short_sig = (c[t] < e20[t] < e50[t]) and (c[t] - lo24) <= 1.0 * a
        if not (long_sig or short_sig):
            continue
        side = "LONG" if long_sig else "SHORT"
        tgt = c[t] + 1.5 * a if side == "LONG" else c[t] - 1.5 * a
        stp = c[t] - 1.0 * a if side == "LONG" else c[t] + 1.0 * a
        out = _first_touch(side, c[t], stp, tgt, h, l, t+1, t+1+FWD, n)
        rows.append({"side": side, "btc": _btc_state(int(ts_s[t])),
                     "o": out})
    return rows


syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]
rows = []
t0 = time.time()
with ThreadPoolExecutor(max_workers=5) as pool:
    futs = {pool.submit(_one, s): s for s in syms}
    for fut in as_completed(futs):
        try:
            rows.extend(fut.result())
        except Exception:
            pass
print(f"samples: {len(rows)} in {time.time()-t0:.0f}s")
with open(ROWS_FILE, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")

print("=" * 66)
print("BTC GATE — identical alt setups, split by BTC state at that moment")
print("=" * 66)
for side in ("LONG", "SHORT"):
    print(f"--- alt {side} setups (uptrend+breakout proxy, 1.5:1 target) ---")
    for st in ("RISK_ON", "NEUTRAL", "RISK_OFF"):
        seg = [r for r in rows if r["side"] == side and r["btc"] == st]
        dec = [r for r in seg if r["o"] in ("WIN", "LOSS")]
        w = sum(1 for r in dec if r["o"] == "WIN")
        wr = w / len(dec) * 100 if dec else 0.0
        exp = (w * 1.5 - (len(dec) - w)) / max(1, len(dec))
        print(f"   BTC {st:9} | n={len(dec):6} | win {wr:5.1f}% | "
              f"exp {exp:+.3f}R")
print("=" * 66)
print("Big spread = the missing decision layer is a BTC risk gate.")
