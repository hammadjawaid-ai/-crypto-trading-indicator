"""🩸 LIQ FLUSH — long-liquidation cascade snapback (PROVING tier).

Validated 2026-07-17 (backtest_positioning_1h, 38 coins, ~60d 1h data,
walk-forward, Bybit taker fees): a 1h bar whose LONG-liquidation volume
spikes to the trailing-14d p99 marks forced-seller exhaustion; entering
LONG on the next bar won 57.4% / +0.084R while the same-window long
baseline LOST -0.087R. Positive in BOTH halves of the window and on
19/30 coins. (Short-flush mirror, OI-divergence and squeeze variants
all failed robustness — killed.)

HONEST STATUS: provisional (60-day window — the free tier's full 1h
retention). Therefore this ships as a SILENT Decision Desk shadow tier
ONLY: no alerts, no 💎 votes, no live trading. If its live forward
record earns 🟢 GREEN LIGHT (>=20 closed, >=+2R after fees), it gets
promoted like everything else did.

Construct parity with the validation: entry at signal, stop 1.5x
ATR(14,1h) below, TP1 +1.5x ATR (1:1), TP2 +3x ATR waypoint; the desk
ladder manages from there. One fire per symbol per spike (the spike bar
must be one of the last 2 closed hours).

Data: Coinalyze 1h liquidation history (free key). p99 thresholds are
cached 6h per symbol; per cycle only a 2-day tail is fetched. Fail-soft
to no-signals when the key/API is unavailable.
"""
from __future__ import annotations

import time

import pandas as pd

import binance_client
import coinalyze_client as cz

TOP_N = 15               # most-liquid coins only — keeps API use tiny
P99_TTL = 6 * 3600.0
STOP_ATR = 1.5
TP2_ATR = 3.0

_thr_cache: dict = {}    # sym -> (ts, p99)
_mkt_cache: dict = {}    # sym -> coinalyze market code


def _market(sym: str):
    if sym not in _mkt_cache:
        try:
            _mkt_cache[sym] = cz.resolve_perp(sym)
        except Exception:
            _mkt_cache[sym] = None
    return _mkt_cache[sym]


def _p99(sym: str, mkt: str) -> float | None:
    now = time.time()
    hit = _thr_cache.get(sym)
    if hit and now - hit[0] < P99_TTL:
        return hit[1]
    try:
        h = cz.liquidation_history(mkt, "1hour", days=30)
        if h is None or len(h) < 200:
            return None
        v = float(h["liq_long"].iloc[:-1].tail(14 * 24).quantile(0.99))
        _thr_cache[sym] = (now, v)
        return v
    except Exception:
        return None


def scan(symbols: list[str]) -> list[dict]:
    """LONG snapback candidates among the top symbols. Fail-soft."""
    if not cz.is_configured():
        return []
    out: list[dict] = []
    now = pd.Timestamp.now(tz="UTC")
    for sym in symbols[:TOP_N]:
        mkt = _market(sym)
        if not mkt:
            continue
        thr = _p99(sym, mkt)
        if not thr or thr <= 0:
            continue
        try:
            tail = cz.liquidation_history(mkt, "1hour", days=2)
        except Exception:
            continue
        if tail is None or len(tail) < 3:
            continue
        # last fully-closed bar (the final row may be in progress)
        closed = tail.iloc[:-1]
        spike = closed[closed["liq_long"] >= thr]
        if spike.empty:
            continue
        last_spike = spike.index[-1]
        if (now - last_spike).total_seconds() > 2 * 3600:
            continue                      # stale — the snapback window past
        try:
            df = binance_client.get_klines(sym, "1h", limit=100)
        except Exception:
            continue
        if df is None or len(df) < 30:
            continue
        h, l, c = df["high"], df["low"], df["close"]
        tr = pd.concat([h - l, (h - c.shift()).abs(),
                        (l - c.shift()).abs()], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
        entry = float(c.iloc[-1])
        if not (atr > 0 and entry > 0):
            continue
        out.append({
            "symbol": sym,
            "base": sym.replace("USDT", ""),
            "side": "LONG",
            "tier": "LIQFLUSH",
            "score": 60.0,
            "entry": entry,
            "stop": entry - STOP_ATR * atr,
            "tp1": entry + STOP_ATR * atr,
            "tp2": entry + TP2_ATR * atr,
            "atr_pct": round(atr / entry * 100, 3),
            "liq_spike_at": str(last_spike),
        })
    return out
