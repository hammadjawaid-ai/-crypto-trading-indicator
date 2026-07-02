"""Frontier test — the two research-backed derivatives early-warning lanes.

A) FUNDING-VELOCITY FADE (BIS WP 1087 direction): when funding is EXTREME and
   ACCELERATING, does price mean-revert against the crowded side over the next
   8/24/48h? Event: funding print in the top decile of its trailing 90 prints
   AND above its recent average (accelerating). Mirror for extreme-negative.
   Metric: signed forward return FADING the crowd (short when funding extreme+,
   long when extreme−) vs the unconditional baseline.

B) OI-DELTA CONFIRMATION: a >=2% 4h price move — does it CONTINUE when open
   interest ROSE over the same window (new money) and FADE when OI fell
   (short-covering/liquidation)? Metric: forward 24h return in the move's
   direction, split by OI-delta sign. OI history is capped ~20d by Binance,
   so B runs on a shorter window (honest scope).

Pure event studies on free data — no lookahead (all features from bars <= t,
outcomes from bars > t). ~30 coins, threaded.
"""
from __future__ import annotations
import sys, io, time, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import requests
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import binance_client, config

N_COINS = 30
FAPI = getattr(config, "BINANCE_FAPI_BASE", "https://fapi.binance.com")
_S = requests.Session()


def _fapi(path, params):
    r = _S.get(FAPI + path, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def _funding(sym, limit=1000):
    data = _fapi("/fapi/v1/fundingRate", {"symbol": sym, "limit": limit})
    return [(int(d["fundingTime"]), float(d["fundingRate"])) for d in data]


def _oi_hist(sym, limit=500):
    data = _fapi("/futures/data/openInterestHist",
                 {"symbol": sym, "period": "1h", "limit": limit})
    return [(int(d["timestamp"]), float(d["sumOpenInterest"])) for d in data]


def _kl(sym, limit=1500):
    df = binance_client.get_klines(sym, "1h", limit=limit)
    ts = (df.index.values.astype("datetime64[ms]").astype("int64"))
    return ts, df["close"].to_numpy()


def _fwd(ts, close, t_ms, hours):
    i = int(np.searchsorted(ts, t_ms, side="right")) - 1
    j = i + hours
    if i < 0 or j >= len(close) or close[i] <= 0:
        return None
    return float(np.log(close[j] / close[i]))


def one_funding(sym):
    """Return (fade_events, baseline) lists of (fwd8, fwd24, fwd48) signed
    so + = the fade direction was right."""
    try:
        fr = _funding(sym)
        ts, close = _kl(sym)
    except Exception:
        return [], []
    events, base = [], []
    rates = [r for _, r in fr]
    for k in range(90, len(fr)):
        t_ms, rate = fr[k]
        if t_ms < ts[0] or t_ms > ts[-1] - 49 * 3600_000:
            continue
        trail = rates[k - 90:k]
        hi = float(np.percentile(trail, 90))
        lo = float(np.percentile(trail, 10))
        recent = float(np.mean(rates[max(0, k - 3):k]))
        f8 = _fwd(ts, close, t_ms, 8)
        f24 = _fwd(ts, close, t_ms, 24)
        f48 = _fwd(ts, close, t_ms, 48)
        if f8 is None or f24 is None or f48 is None:
            continue
        base.append((abs(f8), abs(f24), abs(f48), f8, f24, f48))
        if rate >= hi and rate > recent and rate > 0:
            # crowded long -> fade = SHORT -> profit when fwd return NEGATIVE
            events.append((-f8, -f24, -f48))
        elif rate <= lo and rate < recent and rate < 0:
            # crowded short -> fade = LONG
            events.append((f8, f24, f48))
    return events, base


def one_oi(sym):
    """Return (rising_events, falling_events): forward 24h log return in the
    DIRECTION of a >=2% 4h move, split by OI delta sign over the same 4h."""
    try:
        oi = _oi_hist(sym)
        ts, close = _kl(sym, limit=700)
    except Exception:
        return [], []
    if len(oi) < 30:
        return [], []
    oi_ts = np.array([t for t, _ in oi], dtype="int64")
    oi_v = np.array([v for _, v in oi])
    rising, falling = [], []
    for k in range(4, len(oi) - 25):
        t_ms = int(oi_ts[k])
        i = int(np.searchsorted(ts, t_ms, side="right")) - 1
        if i < 4 or i + 24 >= len(close):
            continue
        mv = float(np.log(close[i] / close[i - 4]))
        if abs(mv) < 0.02:
            continue
        if oi_v[k - 4] <= 0:
            continue
        d_oi = (oi_v[k] - oi_v[k - 4]) / oi_v[k - 4]
        fwd = float(np.log(close[i + 24] / close[i]))
        signed = fwd if mv > 0 else -fwd   # + = continuation
        if d_oi > 0.01:
            rising.append(signed)
        elif d_oi < -0.01:
            falling.append(signed)
    return rising, falling


def _stats(v):
    if not v:
        return "n=0"
    pos = sum(1 for x in v if x > 0) / len(v) * 100
    return (f"n={len(v):4} · mean {np.mean(v) * 100:+.2f}% · med "
            f"{statistics.median(v) * 100:+.2f}% · win {pos:.0f}%")


syms = binance_client.get_top_symbols(N_COINS)["symbol"].tolist()[:N_COINS]
print(f"Deriv frontier — {len(syms)} coins")
t0 = time.time()
fe, fb, oir, oif = [], [], [], []
with ThreadPoolExecutor(max_workers=6) as pool:
    futs = {pool.submit(one_funding, s): ("F", s) for s in syms}
    futs.update({pool.submit(one_oi, s): ("O", s) for s in syms})
    for fut in as_completed(futs):
        kind, s = futs[fut]
        try:
            a, b = fut.result()
        except Exception:
            a, b = [], []
        if kind == "F":
            fe.extend(a); fb.extend(b)
        else:
            oir.extend(a); oif.extend(b)

print(f"\ndone in {time.time()-t0:.0f}s")
print("=" * 70)
print("A) FUNDING-VELOCITY FADE (signed: + = fade direction was right)")
for i, h in enumerate(["8h", "24h", "48h"]):
    print(f"   fade fwd {h:>3}: " + _stats([e[i] for e in fe]))
base24 = [b[4] for b in fb]
print(f"   baseline raw fwd 24h (all prints): " + _stats(base24))
print("-" * 70)
print("B) OI-DELTA CONFIRMATION (signed: + = 4h move CONTINUED over next 24h)")
print(f"   move + OI RISING : " + _stats(oir))
print(f"   move + OI FALLING: " + _stats(oif))
print("=" * 70)
print("Edge if: (A) fade means clearly > 0 and beats baseline noise;")
print("         (B) rising-OI continuation clearly > falling-OI.")
