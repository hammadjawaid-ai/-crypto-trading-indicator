"""📡 SURGE RADAR — whole-market fresh-pump ignition detector.

User 2026-07-26 (LPT +23% case): "we are not leveraging trades when
they are pumping — the boards show it when the move already happened."
Correct — and no existing stream hunts this shape: a VERTICAL pump in
any coin, market-wide, caught in its FIRST hour. This radar does
exactly that, and ONLY that:

  universe:  every USDT perp on the exchange (one 24h-ticker call),
             top movers by 24h change with >= $2M quote volume
  detection: 15m bars — a run whose LOW printed within the last 8 bars
             (<= 2h old), run size +5%..+14% (young — anything more
             extended, like LPT at +23%, is REFUSED as a chase),
             run volume >= 2.5x the pre-run average, price > EMA20(15m)
  plan:      entry at close · stop at the surge low (capped 2xATR15)
             · TP1 +1R · TP2 +2R

HONEST STATUS: UNPROVEN construct. Ships as a labeled Telegram stream
(the user's explicit early-risk appetite) + silent desk tier "surge"
that must earn its record forward. The LIVE EXECUTOR does not touch it
unless it ever goes green with an explicit user go. Fires are capped at
4/cycle; per-symbol cooldown comes from the alert ledger + the desk's
one-open-per-tier-symbol rule.
"""
from __future__ import annotations

import numpy as np

import binance_client

MIN_QVOL = 2_000_000.0     # $ liquidity floor
RUN_MIN = 0.05             # +5% minimum — it's really moving
RUN_MAX = 0.14             # +14% maximum — beyond this it's a chase
FRESH_BARS = 8             # surge low within the last 8 x 15m (2h)
VOL_MULT = 2.5
MAX_PICKS = 4


def scan() -> list[dict]:
    try:
        t = binance_client.get_top_symbols(150)
    except Exception:
        return []
    movers = t.sort_values("priceChangePercent", ascending=False)
    movers = movers[movers["quoteVolume"] >= MIN_QVOL].head(12)
    out: list[dict] = []
    for _, row in movers.iterrows():
        sym = row["symbol"]
        try:
            d = binance_client.get_klines(sym, "15m", limit=40)
        except Exception:
            continue
        if d is None or len(d) < 36:
            continue
        h = d["high"].to_numpy(); l = d["low"].to_numpy()
        c = d["close"].to_numpy(); v = d["volume"].to_numpy()
        ema20 = d["close"].ewm(span=20, adjust=False).mean().to_numpy()
        px = float(c[-1])
        look = l[-(FRESH_BARS + 1):]
        lo_i_rel = int(np.argmin(look))
        lo = float(look[lo_i_rel])
        lo_i = len(l) - (FRESH_BARS + 1) + lo_i_rel
        if lo <= 0 or px <= ema20[-1]:
            continue
        run = px / lo - 1.0
        if not (RUN_MIN <= run <= RUN_MAX):
            continue                      # too small or already a chase
        run_bars = max(1, len(c) - 1 - lo_i)
        pre = v[max(0, lo_i - 16):lo_i]
        if len(pre) < 6 or float(np.mean(pre)) <= 0:
            continue
        run_vol = float(np.mean(v[lo_i:]))
        if run_vol < VOL_MULT * float(np.mean(pre)):
            continue                      # no real volume behind it
        tr = np.maximum(h[1:] - l[1:],
                        np.maximum(np.abs(h[1:] - c[:-1]),
                                   np.abs(l[1:] - c[:-1])))
        atr = float(np.mean(tr[-14:]))
        stop = max(lo, px - 2 * atr)
        if not (0 < px - stop):
            continue
        risk = px - stop
        out.append({
            "symbol": sym,
            "base": sym.replace("USDT", ""),
            "side": "LONG",
            "tier": "SURGE",
            "score": round(min(99.0, 60 + run * 200), 1),
            "entry": px,
            "stop": stop,
            "tp1": px + risk,
            "tp2": px + 2 * risk,
            "atr_pct": round(atr / px * 100, 3),
            "surge_pct": round(run * 100, 1),
            "surge_age_bars": run_bars,
            "chg24": float(row["priceChangePercent"]),
        })
        if len(out) >= MAX_PICKS:
            break
    return out
