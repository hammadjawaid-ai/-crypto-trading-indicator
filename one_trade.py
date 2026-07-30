"""👑 ONE TRADE — the single best clean candidate across every lane.

The user's standing ask (2026-07-28): "I just need one trade that is the
best one to take — it's ok if it's blank when there is no clear point,
but if it fires, tell me one, straight to Telegram."

This is the concierge ritual made permanent: every worker cycle, look at
every lane's candidates together and pick AT MOST ONE — the setup a
disciplined trader would actually take right now — or nothing at all.

Quality bar (each rule earned this session, with real money):
  - conf >= 70          — no conf-40 lottery tickets (ALLO / SNDKB)
  - in zone (<=25% of entry->TP1 gone, stop untouched) — no chasing
  - NOT extended: |24h| < 25% and |6h| < 18% — the LA/LPT rule; the
    surge backtest measured mid-vertical entries NEGATIVE (-0.087R)
  - R:R to TP1 >= 1.0 at LIVE price — a card that pays less than it
    risks is not "the best trade" (the AAVE-0.69 rejection)
Ranked by confidence first (system agreement), reward-to-risk second
(the UNI-2.1R geometry test). Silence when nothing clears the bar.
"""
from __future__ import annotations

import best_board
import binance_client

CONF_MIN = 70
ZONE_MAX = 0.25
EXT_24H = 25.0
EXT_6H = 18.0
RR_MIN = 1.0
MAX_EXT_CHECKS = 8   # klines calls per cycle, worst case


def _extension(sym):
    d = binance_client.get_klines(sym, "1h", limit=30)
    c = d["close"].to_numpy()
    if len(c) < 26 or not c[-25] or not c[-7]:
        return (0.0, 0.0)
    return ((c[-1] / c[-25] - 1) * 100, (c[-1] / c[-7] - 1) * 100)


def pick(streams) -> dict | None:
    """streams: ordered iterable of (label, [signal dicts]).

    Returns ONE augmented copy of the winning signal (adds _one_label,
    _one_conf, _one_rr, _one_live, _one_c24, _one_c6, _prog) or None.
    Every gate fails CLOSED — a data error disqualifies the candidate
    rather than letting an unverified card through.
    """
    seen: set = set()
    rows = []
    checks = 0
    for lbl, items in streams:
        for p in items or []:
            k = (p.get("symbol"), p.get("side"))
            if not k[0] or not k[1] or k in seen:
                continue
            seen.add(k)
            conf = best_board.confidence(p.get("symbol"), p.get("side"))
            if conf < CONF_MIN:
                continue
            try:
                e = float(p.get("entry") or 0)
                st = float(p.get("stop") or 0)
                t1 = float(p.get("tp1") or 0)
            except (TypeError, ValueError):
                continue
            if min(e, st, t1) <= 0 or t1 == e:
                continue
            try:
                live = float(binance_client.get_ticker_price(
                    p["symbol"]) or 0)
            except Exception:
                continue
            if live <= 0:
                continue
            is_long = p["side"] == "LONG"
            prog = ((live - e) / (t1 - e) if is_long
                    else (e - live) / (e - t1))
            dead = (live <= st if is_long else live >= st)
            if dead or prog > ZONE_MAX:
                continue
            risk = abs(live - st) / live * 100
            if risk <= 0:
                continue
            rr1 = (abs(t1 - live) / live * 100) / risk
            if rr1 < RR_MIN:
                continue
            if checks >= MAX_EXT_CHECKS:
                continue
            checks += 1
            try:
                c24, c6 = _extension(p["symbol"])
            except Exception:
                continue
            if abs(c24) >= EXT_24H or abs(c6) >= EXT_6H:
                continue
            rows.append((conf, rr1, lbl, p, live, c24, c6, prog))
    if not rows:
        return None
    rows.sort(key=lambda x: (x[0], x[1]), reverse=True)
    conf, rr1, lbl, p, live, c24, c6, prog = rows[0]
    out = dict(p)
    out["_one_label"] = lbl
    out["_one_conf"] = conf
    out["_one_rr"] = round(rr1, 2)
    out["_one_live"] = live
    out["_one_c24"] = round(c24, 1)
    out["_one_c6"] = round(c6, 1)
    out["_prog"] = prog
    return out
