"""📈 Long Term Investment — the plan tracker's logic (user 2026-11-14). No Streamlit in here.

The plan is FROZEN in longterm_data/plan.json: for each of the ten names, three buy tranches, a stop one step
under the last one, and three take-profits (1.5x / 2x / 3x the plan-date price), all taken from the 13 Nov
2026 close. This module walks the daily candles since the plan date to say which orders the market has
reached, finds the "holds above" triggers for adding when price rises instead of dipping, labels where the
live price sits against the fixed levels, and works out what each sell level would return.

The labels (STRONG BUY / BUY / ADD / HOLD / TAKE PROFIT / STOP) are plan states: they say which zone of the
plan the price is in. They are not forecasts and not advice. Re-anchor the plan by re-running
research_meta/portfolio_1114/freeze_plan.py.
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN_PATH = os.path.join(HERE, "longterm_data", "plan.json")
WORKBOOK_HTML = os.path.join(HERE, "longterm_data", "workbook.html")
WORKBOOK_PDF = os.path.join(HERE, "longterm_data", "workbook.pdf")
PICKS_FILE = ".longterm_portfolio.json"

RUNG_PRESETS = {                         # three tranches (user 2026-11-14: "we are buying in 3 trenches not 4")
    "Equal thirds: 33 / 33 / 33": (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0),
    "Heavier lower: 20 / 30 / 50": (0.20, 0.30, 0.50),
    "Half now: 50 / 25 / 25": (0.50, 0.25, 0.25),
}
MAX_PICKS = 4                            # names held at once (user 2026-11-14: "can hold upto 4 instead of 3")
TP_FRACS = (1.0 / 3.0, 0.5, 1.0)        # a third, a third, the rest (each of what is still held)
BUY_TOL = 0.02                           # BUY while price is within 2% above the first buy level, or lower
HOLD_CLOSES = 2                          # "holds above" = this many daily closes in a row above the level
BREAKOUT_DAYS = 90                       # a close above the highest close of this many days is a breakout

# key -> (label, chip background, chip text, meaning)
SIGNALS = {
    "STRONG_BUY": ("STRONG BUY", "#0b6b2e", "#ffffff", "price is at or under the last buy: the deepest tranche"),
    "BUY": ("BUY", "#1f9d55", "#ffffff", "price is at or under the first buy level, above the last buy"),
    "ADD": ("ADD: HELD ABOVE", "#b7791f", "#ffffff", "price closed above a landmark two days running, or made a 90-day high, on the last full day"),
    "HOLD": ("HOLD", "#5b6472", "#ffffff", "price is above the buy levels and under the first take-profit"),
    "TP": ("TAKE PROFIT", "#2a78d6", "#ffffff", "price has reached a take-profit level"),
    "STOP": ("STOP HIT", "#b02a2a", "#ffffff", "price reached the stop: the plan for this name has ended"),
}
SIGNAL_ORDER = ("STRONG_BUY", "BUY", "ADD", "HOLD", "TP", "STOP")

_PLAN = {"mtime": None, "plan": None}


def load_plan(path: str = PLAN_PATH) -> dict:
    """The frozen plan (cached by file time). Raises if the file is missing or malformed."""
    mt = os.path.getmtime(path)
    if _PLAN["plan"] is None or _PLAN["mtime"] != mt:
        with open(path, encoding="utf-8") as f:
            plan = json.load(f)
        assert plan.get("names") and plan.get("start"), "plan.json needs 'names' and 'start'"
        _PLAN.update(mtime=mt, plan=plan)
    return _PLAN["plan"]


def addup_events(bars, start_ts: float) -> list:
    """The "price holds above" triggers since the plan start, oldest first.

    bars: COMPLETED daily bars (ts, high, low, close), oldest first, with history before the plan start.
    A reclaim: HOLD_CLOSES daily closes in a row above the 50-day (or 200-day) average, right after a close
    at or below it. A breakout: a close above the highest close of the BREAKOUT_DAYS before it (first day of
    the run). Each trigger is {"ts", "price" (that day's close), "label"}.
    """
    c = [float(b[3]) for b in bars]
    n = len(c)
    pre = [0.0]
    for x in c:
        pre.append(pre[-1] + x)
    sma = lambda k, i: (pre[i + 1] - pre[i + 1 - k]) / k          # mean of c[i-k+1 .. i]
    out = []
    m = HOLD_CLOSES
    for i in range(n):
        ts = bars[i][0]
        if ts < start_ts:
            continue
        for k in (50, 200):
            if i - m >= k - 1 and all(c[i - j] > sma(k, i - j) for j in range(m)) and c[i - m] <= sma(k, i - m):
                out.append({"ts": ts, "price": c[i], "label": f"held above the {k}-day average"})
        if i >= BREAKOUT_DAYS + 1 and c[i] > max(c[i - BREAKOUT_DAYS:i]) and not c[i - 1] > max(c[i - 1 - BREAKOUT_DAYS:i - 1]):
            out.append({"ts": ts, "price": c[i], "label": f"new {BREAKOUT_DAYS}-day high"})
    return out


def landmarks(bars, price: float | None = None) -> list:
    """Live levels above the price that a rise would have to hold above, nearest first:
    the 50-day and 200-day averages, the 90-day closing high and the 52-week closing high.
    bars: COMPLETED daily bars. Levels within 1% of the price or of each other are merged."""
    c = [float(b[3]) for b in bars]
    if not c:
        return []
    p = float(price) if price is not None else c[-1]
    cands = []
    if len(c) >= 50:
        cands.append(("50-day average", sum(c[-50:]) / 50.0))
    if len(c) >= 200:
        cands.append(("200-day average", sum(c[-200:]) / 200.0))
    if len(c) >= BREAKOUT_DAYS:
        cands.append((f"{BREAKOUT_DAYS}-day high", max(c[-BREAKOUT_DAYS:])))
    if len(c) >= 300:
        cands.append(("52-week high", max(c[-365:])))
    out = []
    for name, v in sorted([x for x in cands if x[1] > p * 1.01], key=lambda x: x[1]):
        if out and v < out[-1]["price"] * 1.01:
            out[-1]["name"] += " / " + name
            continue
        out.append({"name": name, "price": v})
    return out


def walk(row: dict, bars, weights=(1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0), events=None, addup: bool = False) -> dict:
    """Replay the plan for one name over daily bars since the plan date.

    row: plan entry (rungs, stop, tps). bars: iterable of (ts, high, low, close), oldest first, starting at
    the plan's start. weights: share of this name's money on each tranche. events: addup_events() output.
    Everything is per 1.0 of allocation. A tranche fills at its own price when a bar's low reaches it; the
    stop sells everything at the stop price and ends the plan; a take-profit sells its share at its level
    when a bar's high reaches it. With addup=True a "holds above" trigger buys the lowest unfilled tranche
    at that day's close. Inside one bar the order is: dip buys, the stop, take-profits, then the add.
    """
    rungs, stop, tps = row["rungs"], row["stop"], row["tps"]
    n = len(rungs)
    w = list(weights)[:n] + [0.0] * (n - len(weights))
    filled = [False] * n
    fill_ts, fill_px = [None] * n, [None] * n
    filled[0], fill_px[0] = True, rungs[0]             # tranche 1 is bought at the plan-date price
    units = w[0] / rungs[0] if rungs[0] > 0 else 0.0
    bought_units, spent = units, w[0]
    cash = 1.0 - w[0]
    sold, sold_ts = [False] * len(tps), [None] * len(tps)
    adds = []
    ev_by_ts = {}
    for e in (events or []):
        ev_by_ts.setdefault(e["ts"], []).append(e)
    stopped, stop_ts = False, None
    hi = lo = last = None
    for ts, h, l, c in bars:
        hi = h if hi is None else max(hi, h)
        lo = l if lo is None else min(lo, l)
        last = c
        if stopped:
            continue
        for k in range(1, n):
            if not filled[k] and w[k] > 0 and l <= rungs[k]:
                filled[k], fill_ts[k], fill_px[k] = True, ts, rungs[k]
                u = w[k] / rungs[k]
                units += u
                bought_units += u
                spent += w[k]
                cash -= w[k]
        if l <= stop:
            cash += units * stop
            units = 0.0
            stopped, stop_ts = True, ts
            continue
        for j, tp in enumerate(tps):
            if not sold[j] and h >= tp and units > 0:
                sold[j], sold_ts[j] = True, ts
                u = units * TP_FRACS[min(j, len(TP_FRACS) - 1)]
                units -= u
                cash += u * tp
        if addup:
            for e in ev_by_ts.get(ts, ()):
                k = next((x for x in range(n - 1, 0, -1) if not filled[x] and w[x] > 0), None)
                if k is None:
                    break
                filled[k], fill_ts[k], fill_px[k] = True, ts, float(e["price"])
                u = w[k] / float(e["price"])
                units += u
                bought_units += u
                spent += w[k]
                cash -= w[k]
                adds.append({"ts": ts, "price": float(e["price"]), "label": e["label"], "k": k})
    return {"filled": filled, "fill_ts": fill_ts, "fill_px": fill_px, "sold": sold, "sold_ts": sold_ts, "stopped": stopped,
            "stop_ts": stop_ts, "adds": adds, "units": units, "cash": cash, "spent": spent, "weights": w,
            "avg_cost": (spent / bought_units) if bought_units > 0 else None, "hi": hi, "lo": lo, "last": last}


def value(state: dict, price: float) -> float:
    """Worth of 1.0 of allocation now: cash (unspent tranches + sale proceeds) + what is still held."""
    return state["cash"] + state["units"] * float(price)


def _ladder_up(units: float, cash: float, sold, tps) -> list:
    """Worth of 1.0 of allocation as price climbs to each take-profit in turn (the rest marked at that level)."""
    out = []
    for j, tp in enumerate(tps):
        if not sold[j] and units > 0:
            u = units * TP_FRACS[min(j, len(TP_FRACS) - 1)]
            units -= u
            cash += u * tp
        out.append(cash + units * tp)
    return out


def outcomes(row: dict, state: dict) -> dict:
    """What each sell level is worth per 1.0 of allocation, two ways: 'now' = with what is held today and no
    further buys; 'full' = if every remaining tranche fills at its own level first. Plus the stop, both ways."""
    units, cash, sold = state["units"], state["cash"], list(state["sold"])
    fu, fc = units, cash
    if not state["stopped"]:
        for k, r in enumerate(row["rungs"]):
            if not state["filled"][k] and state["weights"][k] > 0:
                fu += state["weights"][k] / r
                fc -= state["weights"][k]
    return {"now": _ladder_up(units, cash, sold, row["tps"]), "full": _ladder_up(fu, fc, sold, row["tps"]),
            "stop_now": cash + units * row["stop"], "stop_full": fc + fu * row["stop"]}


def signal(row: dict, state: dict | None, price: float | None, fresh_add: dict | None = None) -> dict:
    """Where the live price sits against the plan's fixed levels. fresh_add: a "holds above" trigger from
    the last completed day, if there was one. Returns key, label, colours, detail."""
    if price is None:
        return {"key": None, "label": "no price", "bg": "#3a3f48", "fg": "#ffffff", "detail": "price feed unavailable"}
    rungs, stop, tps = row["rungs"], row["stop"], row["tps"]
    p = float(price)
    if (state and state.get("stopped")) or p <= stop:
        key, detail = "STOP", f"stop {fmt(stop)} reached"
    elif p >= tps[0]:
        j = max(i for i, t in enumerate(tps) if p >= t)
        key, detail = "TP", f"at or above take-profit {j + 1} ({fmt(tps[j])})"
    elif p <= rungs[-1]:
        key, detail = "STRONG_BUY", f"in the buy {len(rungs)} zone ({fmt(rungs[-1])} or lower)"
    elif p <= rungs[0] * (1.0 + BUY_TOL):
        k = max([i for i, r in enumerate(rungs) if p <= r] or [0])
        key, detail = "BUY", (f"in the buy {k + 1} zone ({fmt(rungs[k])} or lower)" if k else f"at the first buy level ({fmt(rungs[0])})")
    elif fresh_add:
        key, detail = "ADD", f"{fresh_add['label']}, closed at {fmt(fresh_add['price'])}"
    else:
        key, detail = "HOLD", f"{(p / rungs[0] - 1) * 100:+.0f}% above the first buy level"
    lab, bg, fg, _ = SIGNALS[key]
    return {"key": key, "label": lab, "bg": bg, "fg": fg, "detail": detail}


def next_levels(row: dict, state: dict | None, price: float, marks=None) -> tuple:
    """(next level below, next level above) as (label, price) pairs. Below: the highest unfilled buy under
    the price, else the stop. Above: the nearest of the unsold take-profits and the live landmarks."""
    p = float(price)
    filled = (state or {}).get("filled") or [True] + [False] * (len(row["rungs"]) - 1)
    sold = (state or {}).get("sold") or [False] * len(row["tps"])
    below = [(f"buy {k + 1}", r) for k, r in enumerate(row["rungs"]) if r < p and not filled[k]]
    below.append(("stop", row["stop"]))
    nb = max(below, key=lambda x: x[1])
    above = [(f"take-profit {j + 1}", t) for j, t in enumerate(row["tps"]) if t > p and not sold[j]]
    above += [(m["name"], m["price"]) for m in (marks or []) if m["price"] > p]
    na = min(above, key=lambda x: x[1]) if above else None
    return nb, na


def btc_read(closes, plan: dict, now_ts: float) -> dict:
    """Market strip from BTC daily closes (oldest first): price, gap to the 200-day average, fall from the
    cycle top and the day count since it. Missing pieces come back as None."""
    xs = [float(x) for x in closes if x is not None]
    out = {"price": xs[-1] if xs else None, "vs200": None, "from_top": None, "day": None}
    if len(xs) >= 200:
        sma = sum(xs[-200:]) / 200.0
        out["vs200"] = xs[-1] / sma - 1.0
    top = (plan.get("btc") or {})
    if xs and top.get("top"):
        out["from_top"] = xs[-1] / float(top["top"]) - 1.0
    if top.get("top_ts"):
        out["day"] = int((now_ts - float(top["top_ts"])) // 86400)
    return out


def fmt(v) -> str:
    """Price with sensible digits for anything from 0.07 to 100,000."""
    if v is None:
        return "—"
    v = float(v)
    if v >= 1000:
        return f"{v:,.0f}"
    if v >= 100:
        return f"{v:.1f}"
    if v >= 10:
        return f"{v:.2f}"
    if v >= 1:
        return f"{v:.3f}"
    return f"{v:.4f}"


def _state_dir() -> str:
    try:
        import config
        d = (getattr(config, "STATE_DIR", "") or "").strip()
    except Exception:
        d = (os.environ.get("STATE_DIR") or "").strip()
    return d if d and os.path.isdir(d) else HERE


def load_picks() -> dict:
    """The saved portfolio choice: {'picks': [...], 'total': 10000, 'preset': name, 'addup': bool}. Fail-soft."""
    try:
        with open(os.path.join(_state_dir(), PICKS_FILE), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_picks(picks, total, preset, addup: bool = True) -> bool:
    """Atomic write of the choice beside the other durable state. Fail-soft."""
    try:
        path = os.path.join(_state_dir(), PICKS_FILE)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"picks": list(picks)[:MAX_PICKS], "total": float(total), "preset": str(preset), "addup": bool(addup)}, f)
        os.replace(tmp, path)
        return True
    except Exception:
        return False
