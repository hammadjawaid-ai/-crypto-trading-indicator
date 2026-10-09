"""🌊⬆️ BOTTOM WATCH — one honest message at the first higher close after a BTC dump.

User 2026-10-09 (BTC -3.5% to 80.3k, alts bounced 7% median from 23:00 PKT,
"why are you not notifying me such trades … be more active with telegram
notifications regarding it, either it will range, dump more or rise"). The
13-month study (.bottom_study.py / .bottom_odds.py, 164 dumps >= 2% vs the 12h
high, 157 coins, 15m) found NO real-time confirmation that earns: the higher
close, RSI, MACD, EMA20, Bollinger, SAR and volume-climax entries all sit at the
random baseline (-0.1% a coin-trade, 41% win); only the true low pays (+0.41%)
and it is known afterwards. After the confirmation the median coin is FLAT at
8h; a broad bounce (median coin +3%) followed 7% of dumps, a +5% night 0.6%, a
further -2% leg 10%. So this is a FACTUAL READ, not an entry bell: when BTC
prints the first higher close after a >= BOTTOM_PCT dump it says what history
did from that print, which SHORT bells rang into the low (the first to pay if
this is a bounce night), and that no entry edge exists here. One message per
shock; nothing else.

Mechanics (closed 15m candles): a shock = close <= -BOTTOM_PCT vs the rolling
12h high (first crossing, one per 24h); the low = running minimum after it; the
print = first bar whose close exceeds the previous bar's high without a new
low, within 6h. State in config.state_path(".bottom_watch.json").
"""
from __future__ import annotations

import json
import time

import pandas as pd

import config

STATE_FILE = config.state_path(".bottom_watch.json")
BOTTOM_PCT = 0.02
MAX_PRINTS = 3          # per shock: the first print + up to two re-prints after new lows
PK = 5 * 3600
_LAST = {"shock": 0.0}

# measured odds from the exact print (164 dumps, 25 Aug 2025 -> 03 Oct 2026)
ODDS = {"window": "25 Aug 2025 → 03 Oct 2026", "n": 164, "median_8h": "+0.0%",
        "broad3": "7%", "night5": "0.6%", "leg2": "10%", "mfe_med": "+1.4%",
        "entry": "−0.10% a coin-trade (random −0.06%)", "hindsight": "+0.41%",
        "deep": "no better (54 dumps ≤ −3.5%: median +0.0%, 19% fell another 2%)",
        "star_short": "75% / +0.28R (16)",
        "second": "no better (57 second prints after a failed first bounce: median coin −0.1%)",
        "breadth": "did not sort it either (the share of coins printing with BTC, 157 coins)"}


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


def _closed(kl: pd.DataFrame, now: float) -> pd.DataFrame:
    idx = kl.index
    if getattr(idx, "tz", None) is None:
        idx = pd.to_datetime(idx, utc=True)
    d = kl.copy()
    d.index = idx
    d = d[(d.index + pd.Timedelta(minutes=15)) <= pd.Timestamp(now, unit="s", tz="UTC")]
    return d


def _hm(ts: float) -> str:
    return time.strftime("%H:%M", time.gmtime(ts + PK))


def message(shock: dict, shorts: list) -> str:
    o = ODDS
    sh = (", ".join(shorts[:8]) + (" …" if len(shorts) > 8 else "")) if shorts else "none"
    nth = int(shock.get("prints_n") or 1)
    tag = "first higher close" if nth == 1 else f"higher close again after a NEW low (print {nth})"
    return (f"🌊⬆️ *BTC BOTTOM CONFIRMED — {tag} after a "
            f"{shock['depth'] * 100:+.1f}% dump · {_hm(shock['print_at'])} PKT*\n"
            f"dump: `${shock['high']:,.0f}` ({_hm(shock['high_at'])} PKT) → low "
            f"`${shock['low']:,.0f}` ({_hm(shock['low_at'])} PKT) · now "
            f"`${shock['px']:,.0f}` ({(shock['px'] / shock['low'] - 1) * 100:+.1f}% off "
            f"the low) · RSI14 at the low {shock['rsi_low']:.0f}\n"
            f"what history did from this print ({o['n']} dumps ≥2%, {o['window']}): "
            f"the median coin was FLAT 8h later ({o['median_8h']}); a broad bounce "
            f"(median coin +3% or more) {o['broad3']} of the time; a +5% night like "
            f"08 Oct {o['night5']}; a further −2% leg {o['leg2']}. Best bounce by the "
            f"median coin within 8h: {o['mfe_med']}. Deep dumps {o['deep']}.\n"
            f"entering the bounce here measured {o['entry']}; only the true low pays "
            f"({o['hindsight']}) and it is known afterwards — no entry bell. A second "
            f"print after a failed first bounce measured {o['second']}; market breadth "
            f"{o['breadth']}.\n"
            f"shorts rung in the last 3h: {sh} — if this turns into a bounce night "
            f"they pay first; star shorts opened in these windows still ran "
            f"{o['star_short']} on the desk, so the stop keeps the risk, not a cut.\n"
            f"_a factual read, not a forecast — one message per dump._")


def run(get_klines, send, recent_shorts=None, now: float | None = None) -> dict | None:
    """One cycle. Returns the shock dict when the bell went out, else None."""
    now = time.time() if now is None else now
    d = _closed(get_klines("BTCUSDT", "15m", limit=400), now)
    if len(d) < 100:
        return None
    c = d["close"].astype(float).to_numpy()
    h = d["high"].astype(float).to_numpy()
    l = d["low"].astype(float).to_numpy()
    # unit-safe epoch seconds (the index may carry ms or ns resolution)
    t = d.index.map(lambda x: x.timestamp()).to_numpy(dtype=float)
    hi12 = pd.Series(h).rolling(48).max().to_numpy()
    dd = c / hi12 - 1.0
    s = _load()
    cur = s.get("shock")
    # new crossing?
    i = len(c) - 1
    if (cur is None or now - float(cur.get("shock_at") or 0) > 24 * 3600) and dd[i] <= -BOTTOM_PCT \
            and (i == 0 or dd[i - 1] > -BOTTOM_PCT) and now - _LAST["shock"] > 24 * 3600:
        j = int(pd.Series(h[max(0, i - 48):i + 1]).idxmax()) + max(0, i - 48)
        cur = {"shock_at": float(t[i]), "high": float(h[j]), "high_at": float(t[j]),
               "low": float(l[i]), "low_at": float(t[i]), "printed": False}
        _LAST["shock"] = now
        s["shock"] = cur
        _save(s)
        return None
    if not cur or now - float(cur.get("shock_at") or 0) > 6 * 3600 + 900:
        return None                      # no shock live, or its 6h window closed
    if int(cur.get("prints_n") or 0) >= MAX_PRINTS:
        return None
    # track the low; a print = first higher close after the CURRENT low that
    # has not been printed yet (a new low below the last print re-arms it —
    # 08 Oct: the 21:15 PKT print was a fake, the real low came at 22:15 and
    # the bounce printed again at 23:15; both are worth the read).
    k0 = int((t > cur["shock_at"]).argmax()) if (t > cur["shock_at"]).any() else len(t)
    low, low_at = float(cur["low"]), float(cur["low_at"])
    printed_low = cur.get("printed_low")
    print_at = None
    for k in range(k0, len(c)):
        if l[k] < low:
            low, low_at = float(l[k]), float(t[k])
        elif (k >= 1 and c[k] > h[k - 1] and l[k] >= low
              and (printed_low is None or low < float(printed_low))
              and float(t[k]) > float(cur.get("print_at") or 0)):
            print_at = float(t[k])
            break
    cur["low"], cur["low_at"] = low, low_at
    if print_at is None:
        s["shock"] = cur
        _save(s)
        return None
    # RSI14 at the low bar
    try:
        cs = pd.Series(c)
        dlt = cs.diff()
        up = dlt.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        dn = (-dlt.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        rsi = (100 - 100 / (1 + up / dn.replace(0, float("nan")))).fillna(50).to_numpy()
        kl_ = int((t == low_at).argmax())
        rsi_low = float(rsi[kl_])
    except Exception:
        rsi_low = float("nan")
    cur.update({"print_at": print_at, "px": float(c[-1]), "depth": low / cur["high"] - 1.0,
                "rsi_low": rsi_low, "printed": True, "printed_low": low,
                "prints_n": int(cur.get("prints_n") or 0) + 1})
    shorts = []
    try:
        shorts = list(recent_shorts(low_at - 3 * 3600) if recent_shorts else [])
    except Exception:
        shorts = []
    cur["shorts"] = shorts
    s["shock"] = cur
    s.setdefault("prints", []).append({k: cur[k] for k in ("shock_at", "low", "low_at", "print_at", "depth", "px")})
    s["prints"] = s["prints"][-200:]
    _save(s)
    send(message(cur, shorts))
    return cur
