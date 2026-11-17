"""🛡 THE STOP RULE (user 2026-11-17).

His words, after an MVLL star he took by hand was stopped by a one-minute wick and then ran to TP1 while the
desk and the demo kept the trade: "sligh liquidation wick can hit stop but if its going our direction of tp we are
out of the trade on real money so we need to fix it" · "for everything paper trading and things we are doing we
are changing the rule of stops to 4h rule not the ones we have today this goes to all paper trading and to our
telegram notificaion streams that we have · for stocks on telegram notificaitons and for paper trading page in
our systems we add the rule of 15m rule stops".

THE RULE. A signal's own stop (the PLAN stop) is no longer the stop the desk trades or the bell prints:
  coins            the 4h rule   a quarter of the 4h ATR beyond the nearest 4h swing low (pivot, two candles each
                                 side) at or under the plan stop, in the last 30 closed 4h candles
  tokenized stocks the 15m rule  the same on the last 96 closed 15m candles
(swing high at or over the plan stop for a short). With no such swing the look-back's extreme is used when it lies
past the plan stop, else the plan stop itself, and the quarter ATR is taken beyond that. Never tighter than the
plan stop, never further than 8% from the entry.

WHAT WAS MEASURED (7,082 closed desk trades to 16 Nov replayed on 15m candles, wicks counted, fees in, stop or TP1
in full, in-sample; R per 1R risked): the six coin bells 62% / +0.15R on the plan stop, 76% / +0.18R on the 4h
rule (a stop-out costs about 1.5x the plan's); every coin row 61% / −0.01R → 71% / 0.00R. The three stock bells
68% / +0.10R on the plan stop, 70% / +0.09R on the 15m rule, 71% / +0.01R on the 4h rule (so stocks get the 15m).
More trades survive; the money per dollar risked is about the same; a position must be smaller for the same risk.

WHERE IT ACTS. shadow_trader.open_from_signal (every desk seat, except the mirrored conviction v2 tier) and the
entry bells of the Telegram roster (tg_roster.rule_card). Gates, signals, the demo and the real-money executor
still read the plan stop: the rule is applied where a trade is taken or printed, never where it is judged.
RECORDS. Desk R is measured on the seat's own stop, so wins book smaller R and losses the same −1R from RULE_TS
on: records after it are not comparable with records before it. Every seat whose stop moved writes one row in the
signals stream "stop_rule" (plan stop, rule stop) for the forward replay.

No Streamlit. No network unless LIVE is set (the worker sets it at import): tests and pages never fetch candles.
Every function is fail-soft: on any miss the plan stop stays.
"""
from __future__ import annotations

import time

RULE_ON = True            # False = the plan stop everywhere, as before 17 Nov
LIVE = False              # set True by the worker at import; nothing here fetches candles otherwise
RULE_TS = 1794925200      # 17 Nov 2026 14:20 UTC: the build of the rule; records after it are on the rule's stops
CAP = 0.08                # never further than 8% from the entry
SPEC = {"coin": ("4h", 14400, 30, 45), "stock": ("15m", 900, 96, 115)}   # interval, seconds, look-back, fetch limit
EXEMPT_TIERS = frozenset({"conviction_v2_rev"})      # the mirrored plan keeps its own stop (it is the experiment)
FETCH = None              # callable(symbol, interval, limit) -> candle frame; default binance_client.get_klines
MEMO_S = 600.0
_MEMO: dict = {}          # (symbol, interval) -> (ts, bars)


def is_stock(symbol) -> bool:
    try:
        import tg_cells
        return bool(tg_cells.is_tokenized(symbol))
    except Exception:
        return False


def rule_of(symbol) -> str:
    return SPEC["stock" if is_stock(symbol) else "coin"][0]


def rule_stop(side, entry, stop, bars, look: int = 30):
    """bars = CLOSED candles of the rule's timeframe, oldest first, as (high, low, close).
    -> (price, mark, capped) or None when there is too little to read or the plan is malformed."""
    try:
        lng = str(side or "").upper() == "LONG"
        e, s0 = float(entry), float(stop)
        bars = [(float(h), float(l), float(c)) for h, l, c in bars][-int(look):]
        n = len(bars)
        if n < 20 or e <= 0 or s0 <= 0 or (e - s0) * (1 if lng else -1) <= 0:
            return None
        ext = [b[1] for b in bars] if lng else [b[0] for b in bars]
        if lng:
            piv = [ext[i] for i in range(2, n - 2) if ext[i] < min(ext[i - 1], ext[i - 2]) and ext[i] <= min(ext[i + 1], ext[i + 2])]
            c = [p for p in piv if p <= s0]
            mark = max(c) if c else (min(ext) if min(ext) <= s0 else s0)
        else:
            piv = [ext[i] for i in range(2, n - 2) if ext[i] > max(ext[i - 1], ext[i - 2]) and ext[i] >= max(ext[i + 1], ext[i + 2])]
            c = [p for p in piv if p >= s0]
            mark = min(c) if c else (max(ext) if max(ext) >= s0 else s0)
        trs = [max(bars[i][0] - bars[i][1], abs(bars[i][0] - bars[i - 1][2]), abs(bars[i][1] - bars[i - 1][2]))
               for i in range(max(1, n - 14), n)]
        buf = 0.25 * sum(trs) / len(trs)
        d0 = abs(e - s0)
        d = max(abs(e - (mark - buf if lng else mark + buf)), d0)
        capped = d > CAP * e and d0 <= CAP * e
        if capped:
            d = CAP * e
        return (e - d if lng else e + d), mark, capped
    except Exception:
        return None


def closed_bars(kl, now: float, tf_s: int) -> list:
    """(high, low, close) rows of a binance_client.get_klines frame, the still-forming last candle dropped."""
    rows = list(zip(kl["high"], kl["low"], kl["close"]))
    try:
        forming = float(kl.index[-1].timestamp()) + float(tf_s) > float(now)
    except Exception:
        forming = True
    return rows[:-1] if forming else rows


def bars_for(symbol, now=None, live=None):
    """Closed candles of the symbol's rule timeframe (memo MEMO_S), or None. Fetches only when LIVE (or when the
    caller passes live=True: the Paper Trader page's own bot does, inside the app process)."""
    now = time.time() if now is None else float(now)
    interval, tf_s, _look, lim = SPEC["stock" if is_stock(symbol) else "coin"]
    hit = _MEMO.get((str(symbol), interval))
    if hit and now - hit[0] <= MEMO_S:
        return hit[1]
    if not (LIVE if live is None else live):
        return None
    fetch = FETCH
    if fetch is None:
        import binance_client
        fetch = binance_client.get_klines
    kl = fetch(str(symbol), interval, limit=lim)
    if kl is None or len(kl) < 22:
        return None
    bars = closed_bars(kl, now, tf_s)
    _MEMO[(str(symbol), interval)] = (now, bars)
    if len(_MEMO) > 600:
        for k in sorted(_MEMO, key=lambda k: _MEMO[k][0])[:200]:
            _MEMO.pop(k, None)
    return bars


def for_signal(symbol, side, entry, stop, now=None, bars=None, live=None):
    """-> {"stop", "plan", "rule", "mark", "capped"} for this plan, or None (rule off, no candles, malformed plan).
    "stop" equals "plan" when the rule finds nothing looser."""
    try:
        if not RULE_ON:
            return None
        if bars is None:
            bars = bars_for(symbol, now, live)
        if not bars:
            return None
        interval, _tf, look, _lim = SPEC["stock" if is_stock(symbol) else "coin"]
        rs = rule_stop(side, entry, stop, bars, look)
        if not rs:
            return None
        return {"stop": float(rs[0]), "plan": float(stop), "rule": interval, "mark": float(rs[1]), "capped": bool(rs[2])}
    except Exception:
        return None
