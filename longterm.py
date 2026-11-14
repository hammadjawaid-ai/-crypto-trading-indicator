"""📈 Long Term Investment — the plan tracker's logic (user 2026-11-14). No Streamlit in here.

The plan is FROZEN in longterm_data/plan.json: for each of the ten names, four buy rungs, a stop one step under
the last rung, three take-profits (1.5x / 2x / 3x the plan-date price) and the add-up landmarks, all taken
from the 13 Nov 2026 close. This module walks the daily candles since the plan date to say which orders
the market has reached, and labels where the live price sits against those fixed levels.

The labels (STRONG BUY / BUY / HOLD / TAKE PROFIT / STOP) are plan states: they say which zone of the
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

RUNG_PRESETS = {
    "Equal: 25 / 25 / 25 / 25": (0.25, 0.25, 0.25, 0.25),
    "Heavier lower: 15 / 20 / 30 / 35": (0.15, 0.20, 0.30, 0.35),
    "Half now: 50 / 20 / 15 / 15": (0.50, 0.20, 0.15, 0.15),
}
TP_FRACS = (1.0 / 3.0, 0.5, 1.0)        # a third, a third, the rest (each of what is still held)
BUY_TOL = 0.02                           # BUY while price is within 2% above the first buy level, or lower

# key -> (label, chip background, chip text, meaning)
SIGNALS = {
    "STRONG_BUY": ("STRONG BUY", "#0b6b2e", "#ffffff", "price is at or under buy 3: the two deepest rungs of the ladder"),
    "BUY": ("BUY", "#1f9d55", "#ffffff", "price is at or under the first buy level, above buy 3"),
    "HOLD": ("HOLD", "#5b6472", "#ffffff", "price is above the buy levels and under the first take-profit"),
    "TP": ("TAKE PROFIT", "#2a78d6", "#ffffff", "price has reached a take-profit level"),
    "STOP": ("STOP HIT", "#b02a2a", "#ffffff", "price reached the stop: the plan for this name has ended"),
}
SIGNAL_ORDER = ("STRONG_BUY", "BUY", "HOLD", "TP", "STOP")

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


def walk(row: dict, bars, weights=(0.25, 0.25, 0.25, 0.25)) -> dict:
    """Replay the plan for one name over daily bars since the plan date.

    row: plan entry (rungs, stop, tps, addups). bars: iterable of (ts, high, low, close), oldest first,
    starting at the plan's start. weights: share of this name's money on each rung.
    Everything is per 1.0 of allocation. A rung fills at its own price when a bar's low reaches it; the
    stop sells everything at the stop price and ends the plan; a take-profit sells its share at its level
    when a bar's high reaches it. Inside one bar the order is: buys, then the stop, then take-profits.
    """
    rungs, stop, tps = row["rungs"], row["stop"], row["tps"]
    n = len(rungs)
    w = list(weights)[:n] + [0.0] * (n - len(weights))
    filled = [False] * n
    fill_ts = [None] * n
    filled[0], fill_ts[0] = True, None                 # rung 1 is bought at the plan-date price
    units = w[0] / rungs[0] if rungs[0] > 0 else 0.0
    bought_units, spent = units, w[0]
    cash = 1.0 - w[0]
    sold, sold_ts = [False] * len(tps), [None] * len(tps)
    adds = [False] * len(row.get("addups") or [])
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
                filled[k], fill_ts[k] = True, ts
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
        for j, a in enumerate(row.get("addups") or []):
            if not adds[j] and h >= a["price"]:
                adds[j] = True
    return {"filled": filled, "fill_ts": fill_ts, "sold": sold, "sold_ts": sold_ts, "stopped": stopped, "stop_ts": stop_ts,
            "adds": adds, "units": units, "cash": cash, "spent": spent, "weights": w,
            "avg_cost": (spent / bought_units) if bought_units > 0 else None, "hi": hi, "lo": lo, "last": last}


def value(state: dict, price: float) -> float:
    """Worth of 1.0 of allocation now: cash (unspent rungs + sale proceeds) + what is still held."""
    return state["cash"] + state["units"] * float(price)


def signal(row: dict, state: dict | None, price: float | None) -> dict:
    """Where the live price sits against the plan's fixed levels. Returns key, label, colours, detail."""
    if price is None:
        return {"key": None, "label": "no price", "bg": "#3a3f48", "fg": "#ffffff", "detail": "price feed unavailable"}
    rungs, stop, tps = row["rungs"], row["stop"], row["tps"]
    p = float(price)
    if (state and state.get("stopped")) or p <= stop:
        key, detail = "STOP", f"stop {fmt(stop)} reached"
    elif p >= tps[0]:
        j = max(i for i, t in enumerate(tps) if p >= t)
        key, detail = "TP", f"at or above take-profit {j + 1} ({fmt(tps[j])})"
    elif p <= rungs[2]:
        k = max(i for i, r in enumerate(rungs) if p <= r)
        key, detail = "STRONG_BUY", f"in the buy {k + 1} zone ({fmt(rungs[k])} or lower)"
    elif p <= rungs[0] * (1.0 + BUY_TOL):
        k = max([i for i, r in enumerate(rungs) if p <= r] or [0])
        key, detail = "BUY", (f"in the buy {k + 1} zone ({fmt(rungs[k])} or lower)" if k else f"at the first buy level ({fmt(rungs[0])})")
    else:
        key, detail = "HOLD", f"{(p / rungs[0] - 1) * 100:+.0f}% above the first buy level"
    lab, bg, fg, _ = SIGNALS[key]
    return {"key": key, "label": lab, "bg": bg, "fg": fg, "detail": detail}


def next_levels(row: dict, state: dict | None, price: float) -> tuple:
    """(next buy below, next level above) as (label, price) pairs or None."""
    p = float(price)
    filled = (state or {}).get("filled") or [True] + [False] * (len(row["rungs"]) - 1)
    sold = (state or {}).get("sold") or [False] * len(row["tps"])
    below = [(f"buy {k + 1}", r) for k, r in enumerate(row["rungs"]) if r < p and not filled[k]]
    below.append(("stop", row["stop"]))
    nb = max(below, key=lambda x: x[1])
    above = [(f"take-profit {j + 1}", t) for j, t in enumerate(row["tps"]) if t > p and not sold[j]]
    above += [(a["name"], a["price"]) for a in (row.get("addups") or []) if a["price"] > p]
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
    """The saved 'my three' choice: {'picks': [...], 'total': 10000, 'preset': name}. Fail-soft."""
    try:
        with open(os.path.join(_state_dir(), PICKS_FILE), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_picks(picks, total, preset) -> bool:
    """Atomic write of the choice beside the other durable state. Fail-soft."""
    try:
        path = os.path.join(_state_dir(), PICKS_FILE)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"picks": list(picks)[:3], "total": float(total), "preset": str(preset)}, f)
        os.replace(tmp, path)
        return True
    except Exception:
        return False
