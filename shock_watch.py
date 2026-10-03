"""🌊 SHOCK WATCH — the 24/7 measuring agent for post-shock re-ignition.

User 2026-10-03: after a BTC shock (a dump, or a pump that turns into a
dump) alts bleed for ~2h, then some "catch momentum again" — catch those
early, measure it 24/7, board it. The replay (.reignite.py, 406 shocks,
13 months) says the detector SORTS (re-ignition picks beat a random coin
at the same moment by 0.2-0.4%) but does NOT EARN (-0.2% a trade, ~40%
win) and post-shock momentum does not persist. So this module is a
RECORDS-ONLY instrument: no Telegram, no money. Every re-ignition is
shadow-taken under desk tier `shock_reignite` and the live ledger judges
it; the board shows the live leaderboard while a window is open.

Mechanics (all on closed 15m candles, PKT shown on the board):
  shock      BTC close <= -SHOCK_PCT vs its 12h high (dump), or BTC rose
             >= SHOCK_PCT within the last 6h and now sits >= SHOCK_PCT
             under that run's high (pump-then-dump). One shock per 24h.
  calm       after the shock low, 4 bars with no new low and a 1h range
             < 1.5% -> "calm_at".
  window     opens WAIT_H after calm_at, stays open WINDOW_H.
  re-ignite  during the window, a coin whose 1h return beats BTC's 1h
             return by >= REL_1H, 1h quote volume >= VOL_X its 7d hourly
             average, and whose close is a new high since calm_at.
             First time per coin per shock -> record + shadow open:
             stop = its post-shock low - 0.25 ATR(15m,24h), TP1 = 1.5R,
             TP2 = 2.5R (the desk ladder manages from there).
State: config.state_path(".shock_watch.json") — the board reads it.
Fail-soft everywhere; a cycle is ~1-2 min of klines only while a window
is open (rare: ~1 shock every 1-2 days).
"""
from __future__ import annotations

import json
import time

import pandas as pd

import config

STATE_FILE = config.state_path(".shock_watch.json")
SHOCK_PCT = 0.015
WAIT_H, WINDOW_H = 2.0, 6.0
REL_1H, VOL_X = 0.015, 1.5
MAX_COINS = 150
PK = 5 * 3600
TIER = "shock_reignite"


def _load() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            s = json.load(f)
        if isinstance(s, dict):
            return s
    except Exception:
        pass
    return {}


def _save(s: dict) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, default=str)
    except Exception:
        pass


def _epoch(idx):
    """Epoch seconds for a DatetimeIndex at any resolution (ns/us/ms/s)."""
    try:
        unit = {"ns": 10 ** 9, "us": 10 ** 6, "ms": 10 ** 3, "s": 1}[idx.unit]
    except Exception:
        unit = 10 ** 9
    return idx.asi8 // unit


def _closed(kl: pd.DataFrame, now: float) -> pd.DataFrame:
    """15m candles that have closed by `now` (open_time + 15m <= now)."""
    cut = pd.Timestamp(now - 900, unit="s", tz="UTC")
    return kl[kl.index <= cut]


def detect_shock(btc: pd.DataFrame, now: float) -> dict | None:
    """Current shock state from closed BTC 15m candles, or None."""
    d = _closed(btc, now)
    if len(d) < 60:
        return None
    c = d["close"].astype(float).to_numpy()
    h = d["high"].astype(float).to_numpy()
    l = d["low"].astype(float).to_numpy()
    t = _epoch(d.index) + 900   # close times
    i = len(c) - 1
    hi12 = c[max(0, i - 48):i + 1].max()
    kind = None
    # pump-then-dump is the more specific shape, so it is tested first
    w = c[max(0, i - 24):i + 1]
    k = int(w.argmax())
    if k > 2 and w[k] / w[:k].min() - 1 >= SHOCK_PCT \
            and c[i] / w[k] - 1 <= -SHOCK_PCT:
        kind = "pump-then-dump"
    elif c[i] / hi12 - 1 <= -SHOCK_PCT:
        kind = "dump"
    if kind is None:
        return None
    hi_i = i - 48 + int(c[max(0, i - 48):i + 1].argmax()) if kind == "dump" \
        else i - 24 + int(c[max(0, i - 24):i + 1].argmax())
    return {"kind": kind, "shock_at": float(t[i]), "high": float(c[hi_i]),
            "high_at": float(t[hi_i]), "low": float(l[i]),
            "low_at": float(t[i]), "px": float(c[i])}


def update_calm(st: dict, btc: pd.DataFrame, now: float) -> dict:
    """Track the running low after the shock; stamp calm_at when 4 closed
    bars show no new low and the 1h range is under 1.5%."""
    d = _closed(btc, now)
    d = d[(_epoch(d.index) + 900) > st["shock_at"]]
    if d.empty:
        return st
    h = d["high"].astype(float).to_numpy()
    l = d["low"].astype(float).to_numpy()
    c = d["close"].astype(float).to_numpy()
    t = _epoch(d.index) + 900
    low, low_at = st["low"], st["low_at"]
    for j in range(len(c)):
        if l[j] < low:
            low, low_at = float(l[j]), float(t[j])
        if st.get("calm_at") is None and t[j] - low_at >= 4 * 900 and j >= 3 \
                and (h[j - 3:j + 1].max() - l[j - 3:j + 1].min()) / c[j] < 0.015:
            st["calm_at"] = float(t[j])
            st["calm_px"] = float(c[j])
    st["low"], st["low_at"] = low, low_at
    st["px"] = float(c[-1])
    return st


def scan_coin(kl: pd.DataFrame, btc: pd.DataFrame, st: dict, now: float) -> dict | None:
    """Re-ignition test for one coin on closed 15m candles."""
    d = _closed(kl, now)
    b = _closed(btc, now)
    if len(d) < 700 or len(b) < 8:
        return None
    c = d["close"].astype(float); h = d["high"].astype(float)
    l = d["low"].astype(float); v = d["volume"].astype(float) * c
    bc = b["close"].astype(float)
    r1 = float(c.iloc[-1] / c.iloc[-5] - 1)
    br1 = float(bc.iloc[-1] / bc.iloc[-5] - 1)
    rel = r1 - br1
    vol1 = float(v.iloc[-4:].sum())
    base = float(v.iloc[-672:].sum() / 168.0) if len(v) >= 672 else float("nan")
    volx = vol1 / base if base and base > 0 else 0.0
    ts = _epoch(d.index) + 900
    since_calm = d[ts > st["calm_at"]]
    since_shock = d[ts > st["shock_at"]]
    if since_calm.empty or since_shock.empty:
        return None
    prior = since_calm.iloc[:-1]                     # bars since calm, excluding this one
    new_high = bool(prior.empty or float(c.iloc[-1]) >= float(prior["high"].astype(float).max()))
    atr = float((h - l).iloc[-96:].mean())
    plow = float(since_shock["low"].astype(float).min())
    e = float(c.iloc[-1])
    stop = plow - 0.25 * atr
    if stop >= e * 0.995:
        stop = e * 0.985
    rk = e - stop
    out = {"rel_1h": rel, "vol_x": volx, "new_high": bool(new_high),
           "px": e, "since_low": e / plow - 1.0, "stop": stop,
           "tp1": e + 1.5 * rk, "tp2": e + 2.5 * rk,
           "fires": bool(rel >= REL_1H and volx >= VOL_X and new_high)}
    return out


def run(get_klines, symbols, record=None, open_trade=None, now=None) -> dict:
    """One worker cycle. Returns the state (also written to STATE_FILE)."""
    now = time.time() if now is None else now
    st = _load()
    try:
        btc = get_klines("BTCUSDT", "15m", limit=200)
    except Exception:
        return st
    cur = st.get("shock")
    if cur and now - cur["shock_at"] > 24 * 3600:
        st["last_shock"] = cur
        cur = None
    if cur is None:
        sh = detect_shock(btc, now)
        if sh:
            sh["fired"] = {}
            cur = sh
    if cur is None:
        st["shock"] = None
        st["ts"] = now
        st["board"] = []
        _save(st)
        return st
    cur = update_calm(cur, btc, now)
    board = []
    phase = "bleeding"
    if cur.get("calm_at"):
        t_open = cur["calm_at"] + WAIT_H * 3600
        t_close = t_open + WINDOW_H * 3600
        if now < t_open:
            phase = "waiting"
        elif now <= t_close:
            phase = "window"
        else:
            phase = "closed"
    cur["phase"] = phase
    if phase in ("window", "waiting"):
        for sym in list(symbols)[:MAX_COINS]:
            if sym == "BTCUSDT":
                continue
            try:
                r = scan_coin(get_klines(sym, "15m", limit=720), btc, cur, now)
            except Exception:
                r = None
            if not r:
                continue
            if phase == "window" and r["fires"] and sym not in cur["fired"]:
                sig = {"symbol": sym, "base": sym.replace("USDT", ""),
                       "side": "LONG", "tier": "REIGNITE",
                       "entry": r["px"], "stop": r["stop"],
                       "tp1": r["tp1"], "tp2": r["tp2"],
                       "score": 60, "shock_kind": cur["kind"],
                       "rel_1h": r["rel_1h"], "vol_x": r["vol_x"],
                       "mins_after_calm": round((now - cur["calm_at"]) / 60)}
                cur["fired"][sym] = now
                try:
                    if record:
                        record(TIER, sig)
                    if open_trade:
                        open_trade(TIER, sig, r["px"])
                except Exception:
                    pass
            board.append({"symbol": sym, "rel_1h": round(r["rel_1h"] * 100, 2),
                          "vol_x": round(r["vol_x"], 1),
                          "since_low": round(r["since_low"] * 100, 2),
                          "new_high": r["new_high"],
                          "fired": sym in cur["fired"]})
        board.sort(key=lambda x: -x["rel_1h"])
    st["shock"] = cur
    st["board"] = board[:25]
    st["ts"] = now
    _save(st)
    return st


def describe(st: dict) -> str:
    """One-line status for logs / the board header (PKT times)."""
    cur = (st or {}).get("shock")
    if not cur:
        return "no BTC shock in the last 24h"
    f = lambda t: time.strftime("%H:%M", time.gmtime(float(t) + PK))
    s = (f"{cur['kind']} {((cur['low'] / cur['high']) - 1) * 100:+.1f}% "
         f"(high {cur['high']:,.0f} {f(cur['high_at'])} PKT → low "
         f"{cur['low']:,.0f} {f(cur['low_at'])})")
    if cur.get("calm_at"):
        s += f" · calm {f(cur['calm_at'])} PKT · {cur.get('phase', '')}"
    else:
        s += " · still bleeding"
    return s
