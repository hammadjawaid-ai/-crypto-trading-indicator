"""📈 Long Term Investment — the plan tracker's logic (user 2026-11-14). No Streamlit in here.

The plan is FROZEN in longterm_data/plan.json: for each name, three buy tranches, a stop one step under the
last one, and three take-profits (1.5x / 2x / 3x the plan-date price). The first ten names are frozen at the
13 Nov 2026 close; a name added later (2026-11-15: WLD, TAO, HYPE, ONDO, LINK, QNT) carries its own plan date.
This module walks the daily candles since each name's plan date to say which orders the market has reached,
finds the "holds above" triggers for adding when price rises instead of dipping, labels where the live price
sits against the fixed levels, and works out what each sell level would return. For names really held it
builds the position from the recorded fills; for names being weighed it prices them as if bought now.

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
MAX_PICKS = 10                           # names in the calculator at once (user 2026-11-15: three held, six more being weighed)
TOTAL_OPTIONS = {"Option A · $10,000": 10000.0, "Option B · $12,000": 12000.0}   # user 2026-11-15
PATHS = {"now": "With what is held now", "up": "Price goes up first: the adds trigger", "full": "Every buy fills on a dip first"}
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


def add_plan(row: dict, state: dict, marks) -> list:
    """When price goes up instead of dipping: which money goes in at which level. The nearest landmark above
    the price takes the LOWEST unfilled tranche's money, the next landmark the next one up. Each entry is
    {"name", "price", "k" (tranche index), "share" (of this name's money)}. Empty once every tranche is in."""
    if state.get("stopped"):
        return []
    open_k = [k for k in range(len(row["rungs"]) - 1, 0, -1) if not state["filled"][k] and state["weights"][k] > 0]
    return [{"name": m["name"], "price": float(m["price"]), "k": k, "share": state["weights"][k]} for m, k in zip(marks or [], open_k)]


def climb_steps(row: dict, units: float, cash: float, sold, adds=()) -> tuple:
    """(worth at each sell level, units sold at each sell level) per 1.0 of allocation as price climbs from
    here: it buys each (price, share) in `adds` as it passes it and sells at each take-profit it passes (what
    is left is marked at that level). A level already sold sells nothing."""
    steps = sorted([(float(p), 0, w) for p, w in adds] + [(float(tp), 1, j) for j, tp in enumerate(row["tps"])])
    sold = list(sold)
    out, sells = [None] * len(row["tps"]), [0.0] * len(row["tps"])
    for price, kind, x in steps:
        if kind == 0:
            units += x / price
            cash -= x
        else:
            if not sold[x] and units > 0:
                u = units * TP_FRACS[min(x, len(TP_FRACS) - 1)]
                units -= u
                cash += u * price
                sells[x] = u
            out[x] = cash + units * price
    return out, sells


def climb(row: dict, units: float, cash: float, sold, adds=()) -> list:
    """Worth of 1.0 of allocation at each sell level (see climb_steps)."""
    return climb_steps(row, units, cash, sold, adds)[0]


def outcomes(row: dict, state: dict, marks=None) -> dict:
    """What each sell level is worth per 1.0 of allocation, three ways: 'now' = with what is held today and no
    further buys; 'up' = price rises first and each add in add_plan() triggers at its level on the way;
    'full' = every remaining tranche fills at its own (lower) level first. Plus the stop, with and without
    the remaining buys."""
    units, cash, sold = state["units"], state["cash"], list(state["sold"])
    fu, fc = units, cash
    if not state["stopped"]:
        for k, r in enumerate(row["rungs"]):
            if not state["filled"][k] and state["weights"][k] > 0:
                fu += state["weights"][k] / r
                fc -= state["weights"][k]
    ups = [(a["price"], a["share"]) for a in add_plan(row, state, marks)]
    now, s_now = climb_steps(row, units, cash, sold)
    up, s_up = climb_steps(row, units, cash, sold, ups)
    full, s_full = climb_steps(row, fu, fc, sold)
    return {"now": now, "full": full, "up": up, "sells": {"now": s_now, "up": s_up, "full": s_full},
            "stop_now": cash + units * row["stop"], "stop_full": fc + fu * row["stop"], "units_full": fu}


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


def save_picks(picks, total, preset, addup: bool = True, custom=None) -> bool:
    """Atomic write of the choice beside the other durable state. custom: {name: dollars} when the amounts per
    name were set by hand, else None. Fail-soft."""
    try:
        path = os.path.join(_state_dir(), PICKS_FILE)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"picks": list(picks)[:MAX_PICKS], "total": float(total), "preset": str(preset), "addup": bool(addup),
                       "custom": {str(k): float(v) for k, v in (custom or {}).items()}}, f)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


# ───────────────────────── real fills: the buys and sells actually made ─────────────────────────
FILLS_FILE = ".longterm_fills.json"


def load_fills() -> list:
    """The recorded real buys and sells, oldest first: {"tk", "side", "price", "usd", "units", "ts"}.
    Kept on the state disk only, never in the code repository (which is public). [] when there is none."""
    try:
        with open(os.path.join(_state_dir(), FILLS_FILE), encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, list):
            return []
        return sorted([x for x in d if isinstance(x, dict) and x.get("tk")], key=lambda x: x.get("ts") or 0)
    except Exception:
        return []


def save_fills(fills) -> bool:
    """Atomic write of the fills beside the other durable state. Fail-soft."""
    try:
        path = os.path.join(_state_dir(), FILLS_FILE)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(list(fills), f)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def parse_fills(text: str, valid, now: float) -> tuple:
    """Lines of 'NAME buy|sell PRICE USDT [UNITS]' -> (fills, rejected lines). Units default to USDT / PRICE."""
    good, bad = [], []
    for i, line in enumerate((text or "").splitlines()):
        raw = line.strip()
        if not raw:
            continue
        parts = raw.replace(",", "").replace("$", "").split()
        try:
            tk, side = parts[0].upper(), parts[1].lower()
            nums = [float(x) for x in parts[2:5]]
            if tk not in valid or side not in ("buy", "sell") or len(nums) < 2 or nums[0] <= 0 or nums[1] <= 0:
                raise ValueError(raw)
            units = nums[2] if len(nums) > 2 and nums[2] > 0 else nums[1] / nums[0]
            good.append({"tk": tk, "side": side, "price": nums[0], "usd": nums[1], "units": units, "ts": now + i * 0.001})
        except Exception:
            bad.append(raw)
    return good, bad


def position(fills) -> dict | None:
    """The position in one name from its recorded fills, oldest first. Money decides, not the number of
    orders: 'in' is everything paid for what is held now, 'units' what is held, 'avg' the average buy price,
    'out' what sells of this holding have brought in, 'n_sells' how many sells it has had. When a holding is
    sold out completely its result moves to 'realized' and the count starts again with the next buy.
    'closed' = nothing is held now. None when there is no buy at all."""
    cyc_in = cyc_out = units = bought = realized = 0.0
    n_sells, ts0, any_buy = 0, None, False
    for f in sorted(fills, key=lambda x: x.get("ts") or 0):
        u, usd = float(f.get("units") or 0), float(f.get("usd") or 0)
        if f.get("side") == "buy":
            any_buy = True
            if units <= 0:
                ts0 = f.get("ts")
            cyc_in += usd
            units += u
            bought += u
        elif f.get("side") == "sell" and units > 0:
            cyc_out += usd
            units -= u
            n_sells += 1
            if units <= bought * 1e-6:              # sold out: this holding is finished
                realized += cyc_out - cyc_in
                cyc_in = cyc_out = units = bought = 0.0
                n_sells, ts0 = 0, None
    if not any_buy:
        return None
    return {"in": cyc_in, "out": cyc_out, "units": units, "avg": (cyc_in / bought) if bought > 0 else None, "n_sells": n_sells,
            "closed": units <= 0, "realized": realized, "ts": ts0}


def split_total(total: float, picks, money_in: dict, custom: dict | None = None) -> dict:
    """Planned dollars per name. With `custom`, those amounts (never less than what is already in). Otherwise
    the total is shared equally, levelling up: a name that already holds more than an equal share keeps what
    it has, and what is left is shared equally among the others."""
    picks = list(picks)
    ins = {t: float(money_in.get(t) or 0.0) for t in picks}
    if custom is not None:
        return {t: max(float(custom.get(t) or 0.0), ins[t]) for t in picks}
    out, left, rest = {}, float(total), list(picks)
    while rest:
        share = max(0.0, left / len(rest))
        over = [t for t in rest if ins[t] > share + 1e-9]
        if not over:
            out.update({t: share for t in rest})
            break
        for t in over:
            out[t] = ins[t]
            left -= ins[t]
            rest.remove(t)
    return out


def _norm(weights, n: int) -> list:
    w = [max(0.0, float(x)) for x in list(weights)[:n]] + [0.0] * (n - len(weights))
    tot = sum(w)
    return [x / tot for x in w] if tot > 0 else [1.0] + [0.0] * (n - 1)


def real_state(row: dict, pos: dict, alloc: float, weights=(1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0)) -> tuple:
    """(state, alloc) for a name really held, in the shape walk() returns, per 1.0 of `alloc` (the dollars
    planned for the name, never less than what is already in). The money already in counts against the
    tranches from the top: a tranche is done once the money in covers it, a part-covered tranche keeps only
    what is still to place at its level, and that is what state["weights"] holds for the open tranches.
    The n-th sell is sell level n. Nothing is inferred from candles."""
    n, m = len(row["rungs"]), len(row["tps"])
    w = _norm(weights, n)
    alloc = max(float(alloc), float(pos["in"]))
    if alloc <= 0:
        return None, 0.0
    tiny = max(1.0, 0.01 * alloc)                 # under $1 or 1% of the name's money is not an order
    left, cum = [], 0.0
    for k in range(n):
        lo, hi = cum * alloc, (cum + w[k]) * alloc
        cum += w[k]
        rem = max(0.0, hi - max(float(pos["in"]), lo))
        left.append(0.0 if rem < tiny else rem)
    filled = [x <= 0 for x in left]
    state = {"filled": filled, "fill_ts": [pos.get("ts") if f else None for f in filled], "fill_px": [pos["avg"] if f else None for f in filled],
             "sold": [j < pos["n_sells"] for j in range(m)], "sold_ts": [None] * m, "stopped": False, "stop_ts": None, "adds": [],
             "units": pos["units"] / alloc, "cash": (alloc - pos["in"] + pos["out"]) / alloc, "spent": pos["in"] / alloc,
             "weights": [(w[k] if filled[k] else left[k] / alloc) for k in range(n)], "avg_cost": pos["avg"],
             "hi": None, "lo": None, "last": None, "actual": True}
    return state, alloc


def fresh_state(row: dict, price: float, weights=(1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0)) -> dict:
    """State of a name NOT held yet, as if it were started at the price now: tranche 1 is bought at that
    price, and so is any lower tranche whose level the price has already reached. Sell levels the price is
    already above are behind it. At or under the stop nothing is bought."""
    rungs, tps = row["rungs"], row["tps"]
    n, p = len(rungs), float(price)
    w = _norm(weights, n)
    dead = p <= row["stop"]
    filled = [(not dead) and (k == 0 or rungs[k] >= p) and w[k] > 0 for k in range(n)]
    spent = sum(w[k] for k in range(n) if filled[k])
    return {"filled": filled, "fill_ts": [None] * n, "fill_px": [p if f else None for f in filled], "sold": [tp <= p for tp in tps],
            "sold_ts": [None] * len(tps), "stopped": dead, "stop_ts": None, "adds": [], "units": spent / p, "cash": 1.0 - spent,
            "spent": spent, "weights": w, "avg_cost": p if spent > 0 else None, "hi": None, "lo": None, "last": None, "fresh": True}


def to_place(row: dict, state: dict, price: float) -> list:
    """The buys still to make, top down: {"k", "price", "share", "now"}. 'now' = at the price now: the opening
    buys of a name not held yet, or a tranche whose level the price has already reached."""
    if state.get("stopped"):
        return []
    p, out = float(price), []
    for k, r in enumerate(row["rungs"]):
        sh = state["weights"][k]
        if sh <= 0:
            continue
        if state.get("fresh") and state["filled"][k]:
            out.append({"k": k, "price": p, "share": sh, "now": True})
        elif not state["filled"][k]:
            out.append({"k": k, "price": min(r, p) if r >= p else r, "share": sh, "now": r >= p})
    return out


def avg_if_filled(row: dict, state: dict) -> float | None:
    """Average buy price once every remaining tranche has filled at its own level."""
    money = state["spent"]
    units = (state["spent"] / state["avg_cost"]) if state.get("avg_cost") else 0.0
    if not state.get("stopped"):
        for k, r in enumerate(row["rungs"]):
            if not state["filled"][k] and state["weights"][k] > 0:
                money += state["weights"][k]
                units += state["weights"][k] / r
    return (money / units) if units > 0 else None
