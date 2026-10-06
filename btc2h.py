"""🧭 BTC 2H PULSE — a factual BTC read every two hours (no forecast).

User 2026-09-29: "after every 2 hrs ... notify me on telegram ... up,
down or sideways ... the point is to know the BTC movements and take
trades accordingly" — no TP/SL, news style; then "full pulse with lean,
state and conditions". 2026-10-01, after 3/12 leans came in wrong:
"switch it" — the lean is replaced by a fact-based read.

WHY NO FORECAST (13-month test, .btc2h_bt.py / .pulse_fix.py, 4,692
pulses): no chart reader called BTC's next 2h better than ~54% on
direction with ~0 move captured — fade-the-push 53.8%, trend 48%,
regime switch 48%, dip-in-uptrend 53%, random 49%. So the pulse
reports what BTC IS doing, which the desk can act on:
  1. NOW: the last 2h move against BTC's own normal 2h size (band =
     half the trailing-7-day median |2h move|) -> RISING / FALLING /
     RANGING; plus the last closed 15m candle against its normal size
     -> ⚡ strong candle flag. A strong BTC 15m candle in the trade's
     direction was the one BTC cue that sorted elite-star re-entries
     (+0.7%/trade vs a random moment, .sc3.py).
  2. STATE: 2h / 24h moves and the 24h range.
  3. CONDITIONS (.btc_align.py, 23,409 desk trades): BTC flat over 24h
     48% win / +0.145R (best); trading WITH a 24h trend 43% / +0.003R
     (worst); against +0.072R.
  4. HOURS: the measured PKT trading windows (project_entry_timing_pkt).
"""
import json
import time

import pandas as pd

import config

STATE_FILE = config.state_path(".btc2h.json")
BAND_K = 0.5            # band = BAND_K x median |move| over 7 days
BAND_LOOKBACK = 168     # hourly samples in 7 days
BAND_LOOKBACK_15 = 672  # 15m samples in 7 days
STRONG_15 = 1.5         # a 15m candle >= this x its normal size is "strong"
KEEP = 600              # pulses kept in the state file
PKT = 5 * 3600          # Pakistan time, the user's clock
_LAST = {"t": 0.0}      # in-process backstop if the disk write fails
ICON = {"UP": "📈", "DOWN": "📉", "FLAT": "↔️"}
HEAD = {"UP": "RISING NOW", "DOWN": "FALLING NOW", "FLAT": "RANGING NOW"}
# 🧭⚡ BTC FLIP (user 2026-10-06: "for the 2h BTC pulse if it flips please have
# an additional notification when it flips, else keep it 2h; if the momentum
# flips within 2h have the notification accordingly"). Between pulses the same
# 2h read is re-taken at 15m cadence (8 closed 15m bars = 2h, same band); a
# bell rings when its label differs from the last SENT message (pulse or
# flip), confirmed on two closed 15m bars, never within FLIP_GAP of the last
# sent message. The 2h pulse keeps its clock.
FLIP_GAP = 30 * 60
_FLIP = {"t": 0.0}
# Reversals only (measured on 14 days of real BTC, 5-min cycles): every label
# change would ring ~10x/day, mostly in and out of the RANGING band; true
# RISING<->FALLING reversals ~2-3x/day. FLAT labels neither ring nor move the
# anchor, so RISING -> ranging -> FALLING still rings as FLIPPED DOWN.
FLIP_ONLY_REVERSALS = True
FLIP_HEAD = {("UP", "DOWN"): "📈→📉 FLIPPED DOWN",
             ("DOWN", "UP"): "📉→📈 FLIPPED UP",
             ("UP", "FLAT"): "📈→↔️ momentum faded",
             ("DOWN", "FLAT"): "📉→↔️ momentum faded",
             ("FLAT", "UP"): "↔️→📈 turned UP",
             ("FLAT", "DOWN"): "↔️→📉 turned DOWN"}


def closed_closes(kl: pd.DataFrame, now: float, minutes: int = 60
                  ) -> pd.Series:
    """Closes indexed by CLOSE time, forming candle dropped."""
    c = kl["close"].astype(float).copy()
    c.index = c.index + pd.Timedelta(minutes=minutes)
    return c[c.index <= pd.Timestamp(now, unit="s", tz="UTC")]


def _band(ret: pd.Series, n: int) -> float:
    return float(ret.abs().iloc[-n:].median() * BAND_K)


def read(c: pd.Series, c15: pd.Series | None = None) -> dict:
    """The factual read off closed 1h closes (>= 200 bars) and, when
    given, closed 15m closes (>= 300 bars)."""
    r2 = c / c.shift(2) - 1.0
    r24 = c / c.shift(24) - 1.0
    b2, b24 = _band(r2, BAND_LOOKBACK), _band(r24, BAND_LOOKBACK)
    p2, p24 = float(r2.iloc[-1]), float(r24.iloc[-1])
    now2 = "UP" if p2 > b2 else "DOWN" if p2 < -b2 else "FLAT"
    x = abs(p2) / b2 if b2 > 0 else 0.0
    out = {"t": float(c.index[-1].timestamp()), "px": float(c.iloc[-1]),
           "now": now2, "band": b2, "past": p2,
           "size2": ("wild" if x >= 4 else "big" if x >= 2 else
                     "normal" if x > 1 else "quiet"),
           "p24": p24, "b24": b24,
           "mood": ("UP" if p24 > b24 else "DOWN" if p24 < -b24
                    else "FLAT"),
           "lo24": float(c.iloc[-24:].min()),
           "hi24": float(c.iloc[-24:].max()),
           "m15": None, "z15": None, "strong15": None}
    if c15 is not None and len(c15) >= 300:
        r15 = c15 / c15.shift(1) - 1.0
        sd = float(r15.iloc[-BAND_LOOKBACK_15:].std())
        m15 = float(r15.iloc[-1])
        z = abs(m15) / sd if sd > 0 else 0.0
        out.update({"m15": m15, "z15": z,
                    "strong15": ("UP" if m15 > 0 else "DOWN")
                    if z >= STRONG_15 else None})
    return out


def window(t: float) -> str:
    """🕐 the trading-hours headline (user 2026-09-29: "the best trading
    times ... should have a btc headline accordingly"). The pulse covers
    the next 2h; this names the measured window those hours fall in.
    Numbers from .timing_pkt.py (live desk split before/after the Sep
    rally + the 79-day replays), in PKT:
      13-21  elite star 67-83% win / +0.30R, APEX and moonshot green in
             both regimes — the best hours for every stream
      05-13  APEX and moonshot fine; elite star only worked in the rally
      21-05  elite star and APEX lost money before the rally (replay
             -0.20..-0.30R); moonshot still fine
    Elite conviction had no good hour at all (see the star instead)."""
    h = int(time.gmtime(t + PKT).tm_hour)
    h2 = (h + 2) % 24
    span = f"{h:02d}:00–{h2:02d}:00 PKT"
    if 13 <= h < 21:
        return (f"🕐 {span} · 🟢 your best trading hours (13–21 PKT): "
                f"elite star, APEX and moonshot all measured green here")
    if 5 <= h < 13:
        return (f"🕐 {span} · 🟡 morning hours (05–13 PKT): APEX and "
                f"moonshot fine, elite star only paid in the rally — "
                f"take the star with care")
    return (f"🕐 {span} · 🔴 weak hours (21–05 PKT): elite star and APEX "
            f"lost money here before the rally; moonshot still fine — "
            f"be pickier, smaller")


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


def now_line(r: dict) -> str:
    b = r["band"] * 100
    if r["now"] == "UP":
        s = (f"BTC is up {r['past'] * 100:+.2f}% over the last 2h, beyond "
             f"its ±{b:.2f}% normal range")
    elif r["now"] == "DOWN":
        s = (f"BTC is down {r['past'] * 100:+.2f}% over the last 2h, beyond "
             f"its ±{b:.2f}% normal range")
    else:
        s = (f"BTC moved {r['past'] * 100:+.2f}% over the last 2h, inside "
             f"its ±{b:.2f}% normal range")
    if r.get("m15") is not None:
        if r.get("strong15"):
            s += (f" · ⚡ strong 15m candle {'up' if r['strong15'] == 'UP' else 'down'} "
                  f"({r['m15'] * 100:+.2f}%, {r['z15']:.1f}× normal) — the "
                  f"one BTC cue that helped star re-entries in its direction")
        else:
            s += f" · last 15m {r['m15'] * 100:+.2f}% (quiet)"
    return s


def message(r: dict) -> str:
    nxt = time.strftime("%H:%M", time.gmtime(r["t"] + 2 * 3600))
    nxt_pk = time.strftime("%H:%M", time.gmtime(r["t"] + 2 * 3600 + PKT))
    mood = {"FLAT": "flat", "UP": "trending up",
            "DOWN": "trending down"}[r["mood"]]
    lines = [
        f"🧭 *BTC 2H PULSE — {ICON[r['now']]} {HEAD[r['now']]}*",
        window(r["t"]),
        f"BTC `${r['px']:,.0f}` · next pulse ~{nxt} UTC "
        f"({nxt_pk} PKT)",
        f"📍 now: {now_line(r)}",
        f"📊 state: 2h {r['past'] * 100:+.2f}% ({r['size2']}) · "
        f"24h {r['p24'] * 100:+.2f}% ({mood}) · 24h range "
        f"${r['lo24']:,.0f}–${r['hi24']:,.0f}",
        f"🌡 conditions: {conditions(r)}",
        "_a factual read, not a forecast — no chart method called BTC's "
        "next 2h better than a coin flip over 13 months, so the pulse "
        "reports what BTC is doing and the conditions your setups "
        "measured best in._"]
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
    """One pulse. The caller decides WHEN (every even UTC hour)."""
    now = time.time() if now is None else now
    c = closed_closes(get_klines("BTCUSDT", "1h", limit=240), now)
    if len(c) < 200:
        return None
    c15 = None
    try:
        c15 = closed_closes(get_klines("BTCUSDT", "15m", limit=720), now,
                            minutes=15)
    except Exception:
        c15 = None
    s = _load()
    calls = s["calls"]
    r = read(c, c15)
    if (calls and calls[-1]["t"] >= r["t"]) or _LAST["t"] >= r["t"]:
        return None                      # this hour already sent
    _LAST["t"] = r["t"]
    msg = message(r)
    calls.append({"t": r["t"], "px": r["px"], "now": r["now"],
                  "band": r["band"]})
    s["calls"] = calls[-KEEP:]
    s["last_now"], s["last_now_t"] = r["now"], now   # the flip watch's anchor
    _save(s)
    send(msg)
    return r


def _size(x: float) -> str:
    return ("wild" if x >= 4 else "big" if x >= 2 else
            "normal" if x > 1 else "quiet")


def fine_labels(c15: pd.Series, band: float) -> tuple:
    """The 2h read at 15m cadence: (label at the last closed 15m bar, label
    at the bar before, the last 2h move). 8 closed 15m bars = 2h."""
    p_now = float(c15.iloc[-1] / c15.iloc[-9] - 1.0)
    p_prev = float(c15.iloc[-2] / c15.iloc[-10] - 1.0)

    def lab(p):
        return "UP" if p > band else "DOWN" if p < -band else "FLAT"
    return lab(p_now), lab(p_prev), p_now


def flip_message(prev: str, prev_t: float, r: dict) -> str:
    head = FLIP_HEAD.get((prev, r["now"]),
                         f"{ICON[prev]}→{ICON[r['now']]} changed")
    nxt = (r["t"] // 7200 + 1) * 7200          # the next even UTC hour

    def hm(t):
        return time.strftime("%H:%M", time.gmtime(t))
    mood = {"FLAT": "flat", "UP": "trending up",
            "DOWN": "trending down"}[r["mood"]]
    lines = [
        f"🧭⚡ *BTC FLIP — {head} · {HEAD[r['now']]}*",
        window(r["t"]),
        f"BTC `${r['px']:,.0f}` · the last pulse said {HEAD[prev]} at "
        f"{hm(prev_t)} UTC ({hm(prev_t + PKT)} PKT) · next pulse ~{hm(nxt)} "
        f"UTC ({hm(nxt + PKT)} PKT)",
        f"📍 now: {now_line(r)}",
        f"📊 state: 2h {r['past'] * 100:+.2f}% ({r['size2']}) · "
        f"24h {r['p24'] * 100:+.2f}% ({mood}) · 24h range "
        f"${r['lo24']:,.0f}–${r['hi24']:,.0f}",
        f"🌡 conditions: {conditions(r)}",
        "_rings only when the 2h read changes between pulses, confirmed on "
        "two closed 15m bars; the 2h pulse keeps its clock._"]
    return "\n".join(lines)


def run_flip(get_klines, send, now: float | None = None) -> dict | None:
    """🧭⚡ between pulses — the caller runs it every cycle. Rings when the
    2h read's label differs from the last sent message (pulse or flip),
    confirmed on two closed 15m bars, at most once per 15m close and never
    within FLIP_GAP of the last sent message."""
    now = time.time() if now is None else now
    s = _load()
    prev = s.get("last_now")
    if prev not in ICON:
        return None                      # no pulse sent on this code yet
    prev_t = float(s.get("last_now_t") or 0)
    if now - prev_t < FLIP_GAP:
        return None
    c = closed_closes(get_klines("BTCUSDT", "1h", limit=240), now)
    if len(c) < 200:
        return None
    c15 = closed_closes(get_klines("BTCUSDT", "15m", limit=720), now,
                        minutes=15)
    if len(c15) < 300:
        return None
    t15 = float(c15.index[-1].timestamp())
    if float(s.get("flip_t") or 0) >= t15 or _FLIP["t"] >= t15:
        return None                      # this 15m close already rang
    r = read(c, c15)
    f_now, f_prev, p_now = fine_labels(c15, r["band"])
    if f_now == prev or f_prev != f_now:
        return None                      # no change, or not yet confirmed
    if FLIP_ONLY_REVERSALS and not (prev in ("UP", "DOWN")
                                    and f_now in ("UP", "DOWN")):
        return None                      # a fade or a start, not a flip
    x = abs(p_now) / r["band"] if r["band"] > 0 else 0.0
    r = dict(r, now=f_now, past=p_now, size2=_size(x), t=t15,
             px=float(c15.iloc[-1]))
    msg = flip_message(prev, prev_t, r)
    s["last_now"], s["last_now_t"], s["flip_t"] = f_now, now, t15
    _FLIP["t"] = t15
    s.setdefault("flips", []).append({"t": t15, "from": prev, "to": f_now,
                                      "px": r["px"]})
    s["flips"] = s["flips"][-KEEP:]
    _save(s)
    send(msg)
    return r
