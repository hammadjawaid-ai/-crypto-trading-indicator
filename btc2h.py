"""🧭 BTC 2H PULSE — lean, state and trading conditions every two hours.

User 2026-09-29: "after every 2 hrs you are going to predict and watch
every BTC movements and notify me on telegram ... lean up in next two
hours, lean down or remain sideways ... the point of this update is to
know the BTC movements and take trades accordingly" — no TP/SL, news
style; then "full pulse with lean, state and conditions".

1. THE LEAN (13-month test, .btc2h_bt.py, 4,703 calls on BTC 1h
   closes; outcome judged against an adaptive band = half the
   trailing-7-day median |2h move|):
     fade the last 2h (stretched up -> DOWN, stretched down -> UP,
     inside the band -> SIDEWAYS)   right 38.3% | direction 53.9%
     trend (1h EMA20/50 + 4h slope)  right 34.5% | direction 48.5%
     momentum (last 2h continues)    right 33.9% | direction 46.1%
     a random guess                  right 33.4% | direction 51.3%
   The fade is the most accurate reader, but the average BTC move in
   its called direction is ~0, and 4h/8h/24h windows were no better —
   so every lean prints its measured hit rate and is graded 2h later.
2. THE STATE: BTC's last 2h and 24h moves against their own normal
   size, and the 24h range. Seen, not predicted.
3. THE CONDITIONS (.btc_align.py, 23,409 clean desk trades over 83
   days): the BTC read that actually sorts the system's trades is the
   24h mood, not the 2h lean —
     BTC flat over 24h           48% win / +0.145R  (pre-rally +0.071R)
     trade AGAINST a 24h trend   45% win / +0.072R  (pre-rally +0.019R)
     trade WITH a 24h trend      43% win / +0.003R  (pre-rally -0.014R)
   Chasing BTC's visible trend is the weakest spot; setups work best
   while BTC is quiet. (Trading with vs against the 2h lean itself:
   +0.070R vs +0.072R — no difference, so the lean is never a filter.)
"""
import json
import time

import pandas as pd

import config

STATE_FILE = config.state_path(".btc2h.json")
BAND_K = 0.5            # band = BAND_K x median |move| over 7 days
BAND_LOOKBACK = 168     # hourly samples in 7 days
KEEP = 600              # leans kept in the state file
PKT = 5 * 3600          # Pakistan time, the user's clock
_LAST = {"t": 0.0}      # in-process backstop if the disk write fails
# quoted on every message: the LIVE module replayed over the same 13
# months (.btc2h_test.py, 4,657 leans) — a hair under the research
# backtest's 38.3% / 53.9%, so the smaller numbers are the ones shown.
BT_RIGHT, BT_RANDOM, BT_DIR = 37.8, 33.4, 52.7
ICON = {"UP": "⬆️", "DOWN": "⬇️", "SIDEWAYS": "↔️"}
HEAD = {"UP": "LEANS UP", "DOWN": "LEANS DOWN", "SIDEWAYS": "SIDEWAYS"}


def closed_closes(kl: pd.DataFrame, now: float) -> pd.Series:
    """1h closes indexed by CLOSE time, forming candle dropped."""
    c = kl["close"].astype(float).copy()
    c.index = c.index + pd.Timedelta(hours=1)
    return c[c.index <= pd.Timestamp(now, unit="s", tz="UTC")]


def _band(ret: pd.Series) -> float:
    return float(ret.abs().iloc[-BAND_LOOKBACK:].median() * BAND_K)


def read(c: pd.Series) -> dict:
    """Lean + state off closed 1h closes (oldest first, >= 200 bars)."""
    r2 = c / c.shift(2) - 1.0
    r24 = c / c.shift(24) - 1.0
    b2, b24 = _band(r2), _band(r24)
    p2, p24 = float(r2.iloc[-1]), float(r24.iloc[-1])
    lean = "UP" if p2 < -b2 else "DOWN" if p2 > b2 else "SIDEWAYS"
    x = abs(p2) / b2 if b2 > 0 else 0.0
    return {"t": float(c.index[-1].timestamp()), "px": float(c.iloc[-1]),
            "call": lean, "band": b2, "past": p2,
            "size2": ("wild" if x >= 4 else "big" if x >= 2 else
                      "normal" if x > 1 else "quiet"),
            "p24": p24, "b24": b24,
            "mood": ("UP" if p24 > b24 else "DOWN" if p24 < -b24
                     else "FLAT"),
            "lo24": float(c.iloc[-24:].min()),
            "hi24": float(c.iloc[-24:].max())}


def grade(calls: list, c: pd.Series) -> list:
    """Grade every ungraded lean whose 2h window has closed."""
    by_t = {float(ts.timestamp()): float(v) for ts, v in c.items()}
    for k in calls:
        if k.get("graded"):
            continue
        px2 = by_t.get(k["t"] + 2 * 3600)
        if px2 is None:
            if c.index[-1].timestamp() > k["t"] + 3 * 3600:
                k["graded"] = True       # window missed (worker down)
                k["right"] = None
            continue
        mv = px2 / k["px"] - 1.0
        out = ("UP" if mv > k["band"] else
               "DOWN" if mv < -k["band"] else "SIDEWAYS")
        k.update({"graded": True, "move": mv, "px2": px2,
                  "out": out, "right": out == k["call"]})
    return calls


def score(calls: list, now: float) -> dict:
    g = [k for k in calls
         if k.get("graded") and k.get("right") is not None]
    day = [k for k in g if now - k["t"] <= 26 * 3600]
    return {"n": len(g), "right": sum(k["right"] for k in g),
            "day_n": len(day), "day_right": sum(k["right"] for k in day)}


def conditions(r: dict) -> str:
    if r["mood"] == "FLAT":
        return ("🟢 BTC calm over 24h — your setups' best conditions "
                "(48% win, +0.15R a trade on 23k desk trades)")
    way, side = (("up", "longs") if r["mood"] == "UP"
                 else ("down", "shorts"))
    return (f"🟠 BTC trending {way} ({r['p24'] * 100:+.1f}% in 24h) — "
            f"setups run weaker while BTC trends, and {side} chasing "
            f"BTC's move were the weakest spot (43% win, ~0R). "
            f"Be pickier.")


def lean_why(r: dict) -> str:
    b = r["band"] * 100
    if r["call"] == "UP":
        return (f"BTC dropped {r['past'] * 100:+.2f}% in 2h, beyond the "
                f"±{b:.2f}% sideways band — after a push like that the "
                f"next 2h bounces a little more often than not")
    if r["call"] == "DOWN":
        return (f"BTC rose {r['past'] * 100:+.2f}% in 2h, beyond the "
                f"±{b:.2f}% sideways band — after a push like that the "
                f"next 2h gives a little back more often than not")
    return (f"BTC moved {r['past'] * 100:+.2f}% in 2h, inside the "
            f"±{b:.2f}% sideways band — no push to fade, so it leans "
            f"to a range")


def message(r: dict, last: dict | None, sc: dict) -> str:
    nxt = time.strftime("%H:%M", time.gmtime(r["t"] + 2 * 3600))
    nxt_pk = time.strftime("%H:%M", time.gmtime(r["t"] + 2 * 3600 + PKT))
    mood = {"FLAT": "flat", "UP": "trending up",
            "DOWN": "trending down"}[r["mood"]]
    lines = [
        f"🧭 *BTC 2H PULSE — {ICON[r['call']]} {HEAD[r['call']]}*",
        f"BTC `${r['px']:,.0f}` · next pulse ~{nxt} UTC "
        f"({nxt_pk} PKT)",
        f"📍 state: 2h {r['past'] * 100:+.2f}% ({r['size2']}) · "
        f"24h {r['p24'] * 100:+.2f}% ({mood}) · 24h range "
        f"${r['lo24']:,.0f}–${r['hi24']:,.0f}",
        f"🌡 conditions: {conditions(r)}",
        f"🧭 lean: {lean_why(r)}"]
    if last and last.get("right") is not None:
        s = (f"🕑 last lean: {ICON[last['call']]} {last['call']} @ "
             f"${last['px']:,.0f} → ${last['px2']:,.0f} "
             f"({last['move'] * 100:+.2f}%) "
             f"{'✅' if last['right'] else '❌'}")
    else:
        s = "🕑 last lean: none graded yet"
    if sc["n"]:
        s += (f" · score {sc['day_right']}/{sc['day_n']} in 24h, "
              f"{sc['right']}/{sc['n']} all-time "
              f"({sc['right'] / sc['n'] * 100:.0f}%)")
    lines.append(s)
    lines.append(f"_lean tested on 13 months: right {BT_RIGHT:.0f}% "
                 f"of the time vs {BT_RANDOM:.0f}% for a random guess "
                 f"(direction {BT_DIR:.0f}%) — context, not a trade "
                 f"signal._")
    return "\n".join(lines)


def _load() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            s = json.load(f)
        if isinstance(s, dict) and isinstance(s.get("calls"), list):
            return s
    except Exception:
        pass
    return {"calls": []}


def _save(s: dict) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f)
    except Exception:
        pass


def run(get_klines, send, now: float | None = None) -> dict | None:
    """One pulse: grade the open leans, read BTC, send. The caller
    decides WHEN (every even UTC hour)."""
    now = time.time() if now is None else now
    c = closed_closes(get_klines("BTCUSDT", "1h", limit=240), now)
    if len(c) < 200:
        return None
    s = _load()
    calls = grade(s["calls"], c)
    r = read(c)
    if (calls and calls[-1]["t"] >= r["t"]) or _LAST["t"] >= r["t"]:
        return None                      # this hour already sent
    _LAST["t"] = r["t"]
    last = next((k for k in reversed(calls)
                 if k.get("graded") and k.get("right") is not None
                 and r["t"] - k["t"] <= 2 * 3600), None)
    msg = message(r, last, score(calls, now))
    calls.append({"t": r["t"], "px": r["px"], "call": r["call"],
                  "band": r["band"], "graded": False})
    s["calls"] = calls[-KEEP:]
    _save(s)
    send(msg)
    return r
