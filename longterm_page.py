"""📈 Long Term Investment — the page (user 2026-11-14: "deploy this as separate section … on the left
long term investment as headline" · "it should be updated as the market unfolds" · "have the portfolio and
colors to buy strong buy hold as per our plans" · "we are buying in 3 trenches not 4" · "can hold upto 4
instead of 3" · "show when its the time to buy the dip on the charts next buy zone … if the price hold above
when to buy on that level as well … do the calculations and show the returns and when to sell" ·
2026-11-15: six names added, "total will be option A at 10000 dollars option B at 12000", "a combine ROI as
well and calculation under one table … with their marking of numbers for buying and selling").

Light by design: one daily-candle request per name plus one for BTC, cached five minutes, and nothing
from the scanner. app.py calls render() before its shared header and market loads, then stops.
The logic is in longterm.py; the plan levels are frozen in longterm_data/plan.json.
"""
from __future__ import annotations

import html
import json
import math
import os
import time
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import binance_client
import longterm as lt

SECTION = "📈 Long Term Investment"
REFRESH_S = 300
C_PRICE, C_BUY, C_STRONG, C_STOP, C_SELL, C_ADD = "#3987e5", "#1f9d55", "#0b6b2e", "#e66767", "#6da7ec", "#d4a017"


@st.cache_data(ttl=REFRESH_S, show_spinner=False)
def _daily(sym: str, limit: int) -> list:
    """Daily bars as (ts, high, low, close), oldest first; the last one is still in progress. [] on failure."""
    try:
        df = binance_client.get_klines(sym, "1d", limit=int(limit))
    except Exception:
        return []
    if df is None or len(df) == 0:
        return []
    return [(pd.Timestamp(i).timestamp(), float(h), float(l), float(c))
            for i, h, l, c in zip(df.index, df["high"], df["low"], df["close"])]


@st.cache_data(ttl=3600, show_spinner=False)
def _seed(tk: str) -> list:
    """A stock's US daily history shipped with the code, as (ts, high, low, close)."""
    try:
        with open(os.path.join(lt.HERE, "longterm_data", "seed", f"yh_{tk}.json"), encoding="utf-8") as f:
            return [(float(r[0]), float(r[2]), float(r[3]), float(r[4])) for r in json.load(f)]
    except Exception:
        return []


def _history(r: dict, full: list) -> list:
    """Completed daily bars for the averages and the triggers. Coins: the feed itself. Stocks: the US
    history, then the tokenized ticker's weekday candles after it, so the averages count trading days."""
    done = full[:-1]
    if not r.get("stock"):
        return done
    seed = _seed(r["tk"])
    if not seed:
        return done
    last_day = int(seed[-1][0] // 86400)
    return seed + [b for b in done if int(b[0] // 86400) > last_day and time.gmtime(b[0]).tm_wday < 5]


@st.cache_data(ttl=3600, show_spinner=False)
def _read_text(path: str, mtime: float) -> str:
    """File text, cached per (path, modified time) so a fresh rebuild shows on the next load."""
    with open(path, encoding="utf-8") as f:
        return f.read()


def _workbook() -> tuple:
    """(html, status): the daily rebuild from the state disk when there is one, else the repo's snapshot."""
    stt = {}
    try:
        import longterm_build as lb
        p, stt = lb.live_workbook(), lb.read_status()
        if os.path.exists(p) and stt.get("last_ok") and stt.get("ver") == lb.BUILD_VER:
            return _read_text(p, os.path.getmtime(p)), stt
    except Exception:
        stt = {}
    return _read_text(lt.WORKBOOK_HTML, os.path.getmtime(lt.WORKBOOK_HTML)), {k: v for k, v in stt.items() if k == "error"}


@st.cache_data(ttl=3600, show_spinner=False)
def _workbook_pdf() -> bytes:
    with open(lt.WORKBOOK_PDF, "rb") as f:
        return f.read()


def _d(ts) -> str:
    return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%d %b") if ts else ""


def _pct(v, digits=0) -> str:
    if v is None:
        return "—"
    v = round(v * 100, digits) + 0.0               # a rounded zero carries no sign
    return f"{'+' if v > 0 else '−' if v < 0 else ''}{abs(v):.{digits}f}%"


def _pct_html(v, digits=0) -> str:
    if v is None:
        return "—"
    z = round(v * 100, digits)
    col = "#34c26b" if z > 0 else "#ff6b6b" if z < 0 else "inherit"
    return f"<span style='color:{col}'>{_pct(v, digits)}</span>"


def _usd(v) -> str:
    v = round(v)
    return f"{'−' if v < 0 else ''}${abs(v):,.0f}"


def _gain(v, base) -> str:
    """'$12,345 (+$2,345, +23%)' with the result coloured."""
    d = v - base
    col = "#34c26b" if d > 0 else "#ff6b6b" if d < 0 else "inherit"
    return f"{_usd(v)} <span style='color:{col}'>({'+' if d >= 0 else '−'}${abs(d):,.0f}, {_pct(d / base if base else 0)})</span>"


def _chip(sig: dict) -> str:
    return (f"<span style='display:inline-block;padding:3px 10px;border-radius:999px;font-weight:700;font-size:.78rem;"
            f"letter-spacing:.02em;background:{sig['bg']};color:{sig['fg']};white-space:nowrap'>{html.escape(sig['label'])}</span>")


_TABLE_CSS = """
<style>
.lt-wrap{overflow-x:auto}
table.lt{border-collapse:collapse;width:100%;font-size:.88rem;font-variant-numeric:tabular-nums}
table.lt th,table.lt td{padding:8px 10px;text-align:right;border-bottom:1px solid rgba(128,128,128,.22);white-space:nowrap}
table.lt th{font-weight:600;font-size:.74rem;opacity:.7;text-transform:none}
table.lt th:first-child,table.lt td:first-child,table.lt td.l,table.lt th.l{text-align:left}
table.lt td.w{white-space:normal;min-width:190px}
table.lt .mu{opacity:.6}
table.lt tr.tot td{font-weight:700;border-top:2px solid rgba(128,128,128,.4)}
.lt-do{border:1px solid rgba(128,128,128,.25);border-radius:10px;padding:10px 14px;margin:4px 0 10px;font-size:.92rem;line-height:1.65}
.lt-do b{font-weight:700}
</style>
"""


def _table(head: list, rows: list, cls: str = "") -> str:
    th = "".join(f"<th class='{c}'>{h}</th>" for h, c in head)
    body = "".join(rows)
    return f"<div class='lt-wrap'><table class='lt {cls}'><tr>{th}</tr>{body}</table></div>"


def _chart(r: dict, bars: list, state: dict, marks: list, price: float, alloc: float | None):
    """Daily closes with the plan's levels drawn in: the buy zones, the stop, the three sell levels and the
    live "holds above" levels. Log scale so the stop and the furthest sell level both fit."""
    show = bars[-240:]
    base = len(bars) - len(show)
    closes = [b[3] for b in bars]
    xs = [datetime.fromtimestamp(b[0], timezone.utc) for b in show]

    def sma(k):
        return [(sum(closes[base + i - k + 1:base + i + 1]) / k) if base + i - k + 1 >= 0 else None for i in range(len(show))]

    rungs, stop, tps, w = r["rungs"], r["stop"], r["tps"], state["weights"]
    lo, hi = stop * 0.88, max(tps[-1] * 1.07, max(b[3] for b in show) * 1.04)
    fig = go.Figure()
    fig.add_hrect(y0=rungs[-1], y1=rungs[0], fillcolor=C_BUY, opacity=0.10, line_width=0)
    fig.add_hrect(y0=stop, y1=rungs[-1], fillcolor=C_STRONG, opacity=0.24, line_width=0)
    fig.add_trace(go.Scatter(x=xs, y=sma(200), name="200-day average", mode="lines", line=dict(color="#898781", width=1.5),
                             hovertemplate="%{y:.4g}<extra>200-day average</extra>"))
    fig.add_trace(go.Scatter(x=xs, y=sma(50), name="50-day average", mode="lines", line=dict(color="#5f6570", width=1.5),
                             hovertemplate="%{y:.4g}<extra>50-day average</extra>"))
    fig.add_trace(go.Scatter(x=xs, y=[b[3] for b in show], name="Price", mode="lines", line=dict(color=C_PRICE, width=2),
                             hovertemplate="%{y:.4g}<extra>Price</extra>"))
    fig.add_trace(go.Scatter(x=[xs[-1]], y=[price], name="Now", mode="markers", showlegend=False,
                             marker=dict(color=C_PRICE, size=10, line=dict(color="#0b0c10", width=2)),
                             hovertemplate="%{y:.4g}<extra>Now</extra>"))
    labels = []
    for k, rg in enumerate(rungs):
        did = state["filled"][k]
        money = f" · {_usd(w[k] * alloc)}" if alloc else ""
        tail = (f" · buy now at {lt.fmt(price)}{money}" if state.get("fresh") else " · covered by what is in" if state.get("actual") else " · bought") if did else money
        fig.add_hline(y=rg, line=dict(color=C_BUY, width=1.3, dash="dash"))
        labels.append((rg, f"Buy {k + 1} · {lt.fmt(rg)}{tail}"))
    fig.add_hline(y=stop, line=dict(color=C_STOP, width=1.3, dash="dash"))
    labels.append((stop, f"Stop · {lt.fmt(stop)}"))
    for j, tp in enumerate(tps):
        fig.add_hline(y=tp, line=dict(color=C_SELL, width=1.3, dash="dash"))
        labels.append((tp, f"Sell {j + 1} · {lt.fmt(tp)} · {_pct(tp / price - 1)}" + (" · sold" if state["sold"][j] else "")))
    if not state["stopped"]:                       # where an add would trigger if price goes up, and with whose money
        plan_adds = lt.add_plan(r, state, marks)
        for i, m in enumerate(marks[:3]):
            if lo < m["price"] < hi:
                a = plan_adds[i] if i < len(plan_adds) else None
                money = (f" · {_usd(a['share'] * alloc)}" if alloc else "") if a else " · new money only"
                fig.add_hline(y=m["price"], line=dict(color=C_ADD, width=1.3, dash="dot"))
                labels.append((m["price"], f"Add {i + 1} above {lt.fmt(m['price'])} · {m['name'].split(' / ')[0].replace(' average', '')}{money}"))
    plot_h, span = 440 - 10 - 34, math.log(hi) - math.log(lo)
    pos = sorted(((math.log(y) - math.log(lo)) / span * plot_h, y, t) for y, t in labels)
    shift, prev = {}, -1e9
    for px_, y, t in pos:                          # keep right-hand labels at least 14px apart
        at = max(px_, prev + 14)
        shift[(y, t)] = at - px_
        prev = at
    for y, t in labels:
        fig.add_annotation(xref="paper", x=1.005, xanchor="left", yref="y", y=math.log10(y), text=t, showarrow=False,
                           yshift=shift[(y, t)], font=dict(size=11, color="#c3c2b7"), align="left")
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=440,
                      margin=dict(l=52, r=250, t=10, b=34), hovermode="x unified",
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, font=dict(size=11)))
    fig.update_yaxes(type="log", range=[math.log10(lo), math.log10(hi)], gridcolor="rgba(128,128,128,.15)", tickfont=dict(size=11))
    fig.update_xaxes(gridcolor="rgba(128,128,128,.08)", tickfont=dict(size=11))
    return fig


def _next_steps(r: dict, state: dict, marks: list, price: float, alloc: float | None) -> str:
    """Plain sentences: the next buy on a dip, the trigger if price rises instead, the sells and the stop."""
    rungs, stop, tps, w = r["rungs"], r["stop"], r["tps"], state["weights"]
    if state["stopped"]:
        return f"<div class='lt-do'><b>The stop at {lt.fmt(stop)} was reached on {_d(state['stop_ts'])}.</b> The plan for this name has ended; nothing further is bought or sold.</div>"
    open_k = [k for k, f in enumerate(state["filled"]) if not f and w[k] > 0]
    amt = lambda k: (f" ({_usd(w[k] * alloc)})" if alloc else "")
    out = []
    if state.get("fresh"):                         # not held yet: the opening buy is at the price now
        now_k = [k for k, f in enumerate(state["filled"]) if f]
        out.append(f"<b>To start this name:</b> buy {' and '.join(str(k + 1) for k in now_k)} at the price now, about <b>{lt.fmt(price)}</b>"
                   + (f" ({_usd(sum(w[k] for k in now_k) * alloc)})" if alloc else "")
                   + ("." if len(now_k) == 1 else ": price is already at or under the lower level, so that money goes in now too."))
    if open_k:
        k = open_k[0]
        if price <= rungs[k]:
            out.append(f"<b>Buy the dip:</b> price is in the buy {k + 1} zone now ({lt.fmt(rungs[k])} or lower){amt(k)}.")
        else:
            out.append(f"<b>Buy the dip:</b> the next buy zone starts at <b>{lt.fmt(rungs[k])}</b>, {_pct(rungs[k] / price - 1)} from here: buy {k + 1}{amt(k)}."
                       + (f" After it, buy {open_k[1] + 1} at {lt.fmt(rungs[open_k[1]])}{amt(open_k[1])}." if len(open_k) > 1 else ""))
        plan_adds = lt.add_plan(r, state, marks)
        if plan_adds:
            bits = [f"<b>add {i + 1}</b> puts in buy {a['k'] + 1}'s money{amt(a['k'])} once price has closed above the "
                    f"<b>{a['name']} at {lt.fmt(a['price'])}</b> ({_pct(a['price'] / price - 1)}) two days running" for i, a in enumerate(plan_adds)]
            out.append("<b>If price goes up instead, when to add:</b> " + "; then ".join(bits)
                       + f". A first close above the highest close of the last {lt.BREAKOUT_DAYS} days also counts as a trigger. "
                       + ("After these every tranche is in." if len(plan_adds) == len(open_k) else "The last tranche then waits for a dip or a new 90-day high."))
        else:
            out.append("<b>If price goes up instead:</b> there is no average or recent high left above the price to hold above; a new 90-day closing high is the trigger.")
    else:
        if state.get("actual"):
            out.append("<b>Nothing left to buy for the amount planned" + (f" ({_usd(alloc)})" if alloc else "") + ":</b> what is already in covers it. "
                       "To keep money for the lower buy levels of this name, give it a larger amount (set your own amount for each name, or choose fewer names).")
        else:
            out.append("<b>Buying is finished:</b> all three tranches are in. If price goes up from here the plan has nothing left to add; an add at the levels on the chart would be new money.")
    sells = [(j, tp) for j, tp in enumerate(tps) if not state["sold"][j]]
    if sells and state["units"] > 0:
        out.append("<b>When to sell:</b> " + ", then ".join(f"{'a third' if j < 2 else 'the rest'} at <b>{lt.fmt(tp)}</b> ({_pct(tp / price - 1)})" for j, tp in sells) + ".")
    out.append(f"<b>Stop:</b> {lt.fmt(stop)} ({_pct(stop / price - 1)}) sells everything and ends the plan for this name.")
    return "<div class='lt-do'>" + "<br>".join(out) + "</div>"


def _returns(r: dict, state: dict, price: float, alloc: float, marks: list) -> str:
    """What each sell level is worth in dollars, three ways: with what is held now, if price rises first and
    the adds trigger on the way, and if every buy fills on a dip first."""
    oc = lt.outcomes(r, state, marks)
    rows = []
    for j, tp in enumerate(r["tps"]):
        rows.append(f"<tr><td class='l'>Sell {j + 1}: {'a third' if j < 2 else 'the rest'}</td><td>{lt.fmt(tp)}</td><td>{_pct(tp / price - 1)}</td>"
                    f"<td>{_gain(oc['now'][j] * alloc, alloc)}</td><td>{_gain(oc['up'][j] * alloc, alloc)}</td><td>{_gain(oc['full'][j] * alloc, alloc)}</td></tr>")
    rows.append(f"<tr><td class='l'>Stop: sell everything</td><td>{lt.fmt(r['stop'])}</td><td>{_pct(r['stop'] / price - 1)}</td>"
                f"<td>{_gain(oc['stop_now'] * alloc, alloc)}</td><td class='mu'>—</td><td>{_gain(oc['stop_full'] * alloc, alloc)}</td></tr>")
    return _table([("If price reaches", "l"), ("Price", ""), ("From now", ""), ("This name is worth, with what is held now", ""),
                   ("If price goes up first and the adds trigger", ""), ("If every buy fills on a dip first", "")], rows)


def _build(by_name: dict, live: dict, pos: dict, picks, targets: dict, w, addup: bool, fresh_mode: bool) -> list:
    """One entry per picked name: its state, the dollars planned for it and its outcomes. A name really held
    comes from the recorded fills; one not held is priced as if started at the price now (when real fills
    are in view) or follows the plan from its plan date as if every order was resting."""
    out = []
    for tk in picks:
        r, L = by_name[tk], live[tk]
        price, alloc = L["price"], float(targets.get(tk) or 0.0)
        x = {"tk": tk, "r": r, "L": L, "ok": False, "alloc": alloc, "p": price}
        if price is not None and alloc > 0:
            if tk in pos:
                stt, alloc = lt.real_state(r, pos[tk], alloc, w)
                tag = "mine"
            elif fresh_mode:
                stt, tag = lt.fresh_state(r, price, w), "if bought now"
            else:
                stt, tag = lt.walk(r, L["since"], w, L["events"], addup), "plan"
            if stt:
                x.update(ok=True, stt=stt, alloc=alloc, tag=tag, oc=lt.outcomes(r, stt, L["marks"]))
        out.append(x)
    return out


def _worth(rows: list, spare: float, fn) -> float:
    """Portfolio worth under one outcome: every name's worth plus the money not assigned to a name."""
    return spare + sum(fn(x) * x["alloc"] for x in rows if x["ok"])


def _two(top: str, sub: str) -> str:
    return f"{top}<br><span class='mu' style='font-size:.78rem'>{sub}</span>"


def _calc_table(rows: list, path: str, total: float, spare: float, realized: dict) -> str:
    """The calculator: one row per name with what is in, what is still to buy and where, the stop, and what
    each sell level is worth; the last row adds the portfolio up against the total."""
    body = []
    t_in = t_place = 0.0
    for x in rows:
        r, tk = x["r"], x["tk"]
        if not x["ok"]:
            body.append(f"<tr><td><b>{tk}</b></td><td colspan='10' class='l mu'>{'price feed unavailable' if x['p'] is None else 'no money assigned'}</td></tr>")
            continue
        stt, alloc, price, oc = x["stt"], x["alloc"], x["p"], x["oc"]
        fresh = bool(stt.get("fresh"))
        units, in_usd = stt["units"] * alloc, stt["spent"] * alloc
        val = lt.value(stt, price) * alloc
        buys = lt.to_place(r, stt, price)
        place = sum(b["share"] for b in buys) * alloc
        t_place += place
        if not fresh:
            t_in += in_usd
        sig = lt.signal(r, None if x["tag"] == "mine" else stt, price, x["L"]["fresh"])
        c_in = "<span class='mu'>not held</span>" if fresh else _two(_usd(in_usd), f"{units:,.4g} units at {lt.fmt(stt['avg_cost'])}")
        c_now = "<span class='mu'>—</span>" if fresh else _two(_usd(units * price), f"{_usd(val - alloc)} {_pct_html((val - alloc) / in_usd if in_usd else 0, 1)}")
        c_buy = "<br>".join(f"Buy {b['k'] + 1} {'now ' if b['now'] else ''}at {lt.fmt(b['price'])}: <b>{_usd(b['share'] * alloc)}</b>" for b in buys) \
            or ("<span class='mu'>stop reached</span>" if stt.get("stopped") else "<span class='mu'>all in</span>")
        stop_v = oc["stop_full"] * alloc
        sells = "".join(
            f"<td>{_two(lt.fmt(tp) + ' <span class=mu>' + _pct(tp / price - 1) + '</span>', _usd(oc[path][j] * alloc) + ' ' + _pct_html(oc[path][j] - 1))}</td>"
            for j, tp in enumerate(r["tps"]))
        body.append(
            f"<tr><td>{_two('<b>' + tk + '</b> ' + html.escape(r['name']), x['tag'])}</td><td class='l'>{_chip(sig)}</td>"
            f"<td>{_two(_usd(alloc), f'{alloc / total * 100:.0f}% of the total' if total else '')}</td><td>{c_in}</td><td>{c_now}</td>"
            f"<td class='l'>{c_buy}</td><td>{lt.fmt(lt.avg_if_filled(r, stt))}</td>"
            f"<td>{_two(lt.fmt(r['stop']) + ' <span class=mu>' + _pct(r['stop'] / price - 1) + '</span>', _usd(stop_v - alloc) + ' ' + _pct_html(oc['stop_full'] - 1))}</td>{sells}</tr>")
    for tk, v in realized.items():
        body.append(f"<tr><td>{_two('<b>' + tk + '</b>', 'sold out')}</td><td colspan='3' class='l mu'>finished holding, result counted in the total</td>"
                    f"<td>{_usd(v)}</td><td colspan='6'></td></tr>")
    if abs(spare) >= 1:
        body.append(f"<tr><td colspan='2' class='l mu'>{'Not assigned to a name' if spare > 0 else 'Assigned beyond the total'}</td><td>{_usd(abs(spare))}</td><td colspan='8'></td></tr>")
    ok = [x for x in rows if x["ok"]]
    if ok and total:
        now_w = _worth(ok, spare, lambda x: lt.value(x["stt"], x["p"]))
        stop_w = _worth(ok, spare, lambda x: x["oc"]["stop_full"])
        sells = "".join(f"<td>{_two(_usd(v), _usd(v - total) + ' ' + _pct_html(v / total - 1))}</td>"
                        for v in (_worth(ok, spare, lambda x, j=j: x["oc"][path][j]) for j in range(3)))
        body.append(f"<tr class='tot'><td>Whole portfolio</td><td></td><td>{_usd(total)}</td><td>{_usd(t_in)}</td>"
                    f"<td>{_two(_usd(now_w), _usd(now_w - total) + ' ' + _pct_html(now_w / total - 1, 1))}</td>"
                    f"<td class='l'>Still to place: {_usd(t_place)}</td><td></td>"
                    f"<td>{_two('every stop', _usd(stop_w - total) + ' ' + _pct_html(stop_w / total - 1))}</td>{sells}</tr>")
    return _table([("Name", ""), ("Plan signal", "l"), ("Planned", ""), ("In so far", ""), ("Worth now · result", ""), ("Buys still to make", "l"),
                   ("Average price if all fill", ""), ("Stop · result if hit after every buy", ""), ("Sell 1 (a third) · worth then", ""),
                   ("Sell 2 (a third) · worth then", ""), ("Sell 3 (the rest) · worth then", "")], body)


def _roi_grid(rows: list, total: float, spare: float) -> str:
    """Combined result of the whole portfolio at each stage, on the three paths, against the total."""
    ok = [x for x in rows if x["ok"]]
    cell = lambda v: _gain(v, total)
    now_w = _worth(ok, spare, lambda x: lt.value(x["stt"], x["p"]))
    body = [f"<tr><td class='l'>Today: everything at the prices now</td><td>{cell(now_w)}</td><td class='mu'>—</td><td class='mu'>—</td></tr>",
            f"<tr><td class='l'>Every stop is hit</td><td>{cell(_worth(ok, spare, lambda x: x['oc']['stop_now']))}</td><td class='mu'>—</td>"
            f"<td>{cell(_worth(ok, spare, lambda x: x['oc']['stop_full']))}</td></tr>"]
    for j, nm in enumerate(("Sell 1 is reached on every name (1.5× its plan price)", "Sell 2 is reached on every name (2×)", "Sell 3 is reached on every name (3×): everything sold")):
        body.append(f"<tr><td class='l'>{nm}</td>" + "".join(f"<td>{cell(_worth(ok, spare, lambda x, j=j, k=k: x['oc'][k][j]))}</td>" for k in lt.PATHS) + "</tr>")
    return _table([("If", "l")] + [(v, "") for v in lt.PATHS.values()], body)


def _orders(rows: list, path: str) -> str:
    """Every order with its numbers: money and units for each buy, units and proceeds for each sell."""
    body = []
    for x in rows:
        if not x["ok"]:
            continue
        r, tk, stt, alloc, price, oc = x["r"], x["tk"], x["stt"], x["alloc"], x["p"], x["oc"]
        nm = f"<td><b>{tk}</b></td>"
        if not stt.get("fresh") and stt["spent"] > 0:
            body.append(f"<tr>{nm}<td class='l'>Bought so far</td><td>{lt.fmt(stt['avg_cost'])}</td><td>{_pct(stt['avg_cost'] / price - 1) if stt['avg_cost'] else '—'}</td>"
                        f"<td>{_usd(stt['spent'] * alloc)}</td><td>{stt['spent'] * alloc / stt['avg_cost']:,.4g}</td><td class='l'>{'recorded buys, average price' if x['tag'] == 'mine' else 'the plan’s buys so far, as if resting'}</td></tr>")
        for b in lt.to_place(r, stt, price):
            usd = b["share"] * alloc
            body.append(f"<tr>{nm}<td class='l'>Buy {b['k'] + 1}</td><td>{lt.fmt(b['price'])}</td><td>{_pct(b['price'] / price - 1)}</td><td>{_usd(usd)}</td>"
                        f"<td>{usd / b['price']:,.4g}</td><td class='l'>{'at the price now' if b['now'] else 'waiting for the dip'}</td></tr>")
        for j, tp in enumerate(r["tps"]):
            u = oc["sells"][path][j] * alloc
            stat = "sold" if stt["sold"][j] else "waiting"
            body.append(f"<tr>{nm}<td class='l'>Sell {j + 1} ({'a third' if j < 2 else 'the rest'})</td><td>{lt.fmt(tp)}</td><td>{_pct(tp / price - 1)}</td>"
                        f"<td>{_usd(u * tp) if u else '—'}</td><td>{f'{u:,.4g}' if u else '—'}</td><td class='l'>{stat}</td></tr>")
        us = (oc["units_full"] if path == "full" else stt["units"]) * alloc
        body.append(f"<tr>{nm}<td class='l'>Stop-loss (sell everything)</td><td>{lt.fmt(r['stop'])}</td><td>{_pct(r['stop'] / price - 1)}</td>"
                    f"<td>{_usd(us * r['stop'])}</td><td>{us:,.4g}</td><td class='l'>{'reached' if stt['stopped'] else 'waiting'}</td></tr>")
    return _table([("Name", ""), ("Order", "l"), ("Price", ""), ("From the price now", ""), ("Money", ""), ("Units", ""), ("Status", "l")], body)


def render(load_fear_greed=None, admin: bool = False) -> None:
    """Draw the whole section. load_fear_greed: the app's cached Fear & Greed loader (optional).
    admin: the page was opened with the site's admin link; only then are real fills shown and editable."""
    try:
        plan = lt.load_plan()
    except Exception as exc:                     # a missing plan must not take the page down
        st.error(f"The long-term plan file could not be read: {exc}")
        return
    now = time.time()
    names = plan["names"]
    tks = [r["tk"] for r in names]
    by_name = {r["tk"]: r for r in names}
    pdl = html.escape(plan.get("plan_date_label", ""))
    wbl = html.escape(plan.get("workbook_label") or plan.get("plan_date_label", ""))
    later = {}
    for r in names:
        if r.get("date_label"):
            later.setdefault(r["date_label"], []).append(r["tk"])
    later_txt = "".join(f" {', '.join(v)} joined later and are fixed at the close of {html.escape(k)}." for k, v in later.items())
    st.markdown(_TABLE_CSS, unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:1.9rem;font-weight:800;letter-spacing:-.02em;line-height:1.15'>📈 Long Term Investment</div>"
        f"<div style='opacity:.7;font-size:.9rem;margin:2px 0 10px'>{len(names)} names, one plan each: three buy tranches, a stop and three sell "
        f"levels, fixed at the close of {pdl}.{later_txt} Prices and signals refresh every five minutes.</div>", unsafe_allow_html=True)
    st.info("This page tracks a plan; it does not give advice. A signal says which zone of the plan the price is in "
            "(for example, under the last buy). It is not a forecast, and the choice of names and amounts is yours.", icon="ℹ️")

    # ── market strip ──
    btc_bars = _daily("BTCUSDT", 260)
    br = lt.btc_read([b[3] for b in btc_bars], plan, now)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Bitcoin", f"${br['price']:,.0f}" if br["price"] else "unavailable")
    c2.metric("Bitcoin against its 200-day average",
              (f"{_pct(br['vs200'])} · {'above' if br['vs200'] > 0 else 'below'}") if br["vs200"] is not None else "unavailable")
    c3.metric("From the Oct 2025 top" + (f" · day {br['day']}" if br["day"] is not None else ""),
              _pct(br["from_top"]) if br["from_top"] is not None else "unavailable")
    fg = None
    if load_fear_greed is not None:
        try:
            fg = load_fear_greed()
        except Exception:
            fg = None
    c4.metric("Fear & Greed", f"{fg['value']} · {fg['label']}" if fg else "unavailable")

    # ── real fills: private to the admin link unless LONGTERM_FILLS_PUBLIC=1 ──
    show_real = bool(admin) or os.environ.get("LONGTERM_FILLS_PUBLIC") == "1"
    fills = lt.load_fills() if show_real else []
    by_tk = {}
    for f in fills:
        if f["tk"] in tks:
            by_tk.setdefault(f["tk"], []).append(f)
    pos_all = {tk: lt.position(v) for tk, v in by_tk.items()}
    pos = {tk: q for tk, q in pos_all.items() if q and not q["closed"]}                             # held now
    realized = {tk: q["realized"] for tk, q in pos_all.items() if q and abs(q["realized"]) >= 0.005}   # finished holdings

    # ── every name: live price, history, triggers ──
    saved = lt.load_picks()
    addup0 = bool(saved.get("addup", True))
    weights0 = next(iter(lt.RUNG_PRESETS.values()))
    live = {}
    for r in names:
        start = float(r.get("start") or plan["start"])
        full = _daily(r["sym"], 500)
        if not full:
            live[r["tk"]] = {"price": None}
            continue
        hist = _history(r, full)
        since = [b for b in full if b[0] >= start]
        price = full[-1][3]
        events = lt.addup_events(hist, start)
        fresh = next((e for e in events if hist and e["ts"] == hist[-1][0]), None)
        live[r["tk"]] = {"price": price, "since": since, "events": events, "fresh": fresh, "marks": lt.landmarks(hist, price),
                         "chart": hist + [full[-1]], "mech": lt.walk(r, since, weights0, events, addup0)}

    st.markdown("#### The plan board")
    rows = []
    for r in names:
        L = live[r["tk"]]
        p = L["price"]
        if p is None:
            rows.append(f"<tr><td><b>{r['tk']}</b> <span class='mu'>{html.escape(r['name'])}</span></td><td colspan='8' class='l mu'>price feed unavailable</td></tr>")
            continue
        stt = L["mech"]
        mine = r["tk"] in pos
        sig = lt.signal(r, None if mine else stt, p, L["fresh"])
        nb, na = lt.next_levels(r, stt, p, L["marks"])
        reached = sum(1 for x in stt["filled"] if x)
        tp_hit = sum(1 for x in stt["sold"] if x)
        prog = f"mine · {_usd(pos[r['tk']]['in'])} in" if mine else (f"{reached} of {len(r['rungs'])} buys" + (f" · {tp_hit} sold" if tp_hit else ""))
        extra = (" · tokenized, 24h" if r.get("stock") else "") + (f" · plan from {html.escape(r['date_label'].rsplit(' ', 1)[0])}" if r.get("date_label") else "")
        rows.append(
            f"<tr><td><b>{r['tk']}</b> <span class='mu'>{html.escape(r['name'])}{extra}</span></td>"
            f"<td>{lt.fmt(p)}</td><td>{_pct_html(p / r['px0'] - 1, 1)}</td><td class='l'>{_chip(sig)}</td>"
            f"<td class='l w'>{html.escape(sig['detail'])}</td>"
            f"<td>{lt.fmt(nb[1])} <span class='mu'>{nb[0]} · {_pct(nb[1] / p - 1)}</span></td>"
            f"<td>{(lt.fmt(na[1]) + ' <span class=mu>' + html.escape(na[0]) + ' · ' + _pct(na[1] / p - 1) + '</span>') if na else '—'}</td>"
            f"<td>{prog}</td><td>{lt.fmt(r['stop'])}</td></tr>")
    st.markdown(_table([("Name", ""), ("Price now", ""), ("Since its plan date", ""), ("Plan signal", "l"), ("Where price sits", "l"),
                        ("Next buy zone below", ""), ("Next level above", ""), ("Orders reached", ""), ("Stop", "")], rows), unsafe_allow_html=True)
    leg = " &nbsp; ".join(f"{_chip({'label': lt.SIGNALS[k][0], 'bg': lt.SIGNALS[k][1], 'fg': lt.SIGNALS[k][2]})} "
                          f"<span style='opacity:.75;font-size:.8rem'>{lt.SIGNALS[k][3]}</span>" for k in lt.SIGNAL_ORDER)
    st.markdown(f"<div style='margin:8px 0 2px;line-height:2.1'>{leg}</div>", unsafe_allow_html=True)
    st.caption("An order counts as reached when a daily candle since the name's plan date touched its price. Stock prices here are the "
               "tokenized tickers, which trade around the clock and can sit slightly off the US close.")

    # ── my portfolio: the calculator ──
    st.markdown("#### My portfolio: the calculator")
    label = lambda t: f"{t} · {by_name[t]['name']}"
    held = [t for t in tks if t in pos]
    default = (held + [t for t in (saved.get("picks") or []) if t in tks and t not in held])[:lt.MAX_PICKS]
    a1, a2, a3 = st.columns([3.2, 1.5, 1.9])
    picks = a1.multiselect(f"Names (up to {lt.MAX_PICKS})", tks, default=default, max_selections=lt.MAX_PICKS, key="lt_picks", format_func=label)
    opts = list(lt.TOTAL_OPTIONS) + ["Other amount"]
    total0 = float(saved.get("total") or 10000.0)
    opt = a2.radio("Total to invest", opts, key="lt_opt",
                   index=next((i for i, k in enumerate(lt.TOTAL_OPTIONS) if abs(lt.TOTAL_OPTIONS[k] - total0) < 0.5), len(opts) - 1))
    total = lt.TOTAL_OPTIONS[opt] if opt in lt.TOTAL_OPTIONS else a2.number_input("Amount ($)", min_value=0.0, value=total0, step=500.0, key="lt_total")
    presets = list(lt.RUNG_PRESETS)
    preset = a3.selectbox("Money per tranche", presets, index=presets.index(saved.get("preset")) if saved.get("preset") in presets else 0, key="lt_preset")
    w = lt.RUNG_PRESETS[preset]
    addup = st.toggle("If price goes up instead of dipping, add the lowest unfilled tranche once it holds above a landmark", value=addup0, key="lt_addup")
    st.caption("Holds above = two daily closes in a row over the 50-day or 200-day average, or a first close over the highest close of the last 90 days. "
               "In the past this did not help for the coins: six months after a first close back over the 200-day average their median result was −12%, "
               "against −8% for any ordinary day. For Nvidia, Broadcom and Marvell it was somewhat better, on only 12 cases.")
    ins = {t: pos[t]["in"] for t in picks if t in pos}
    banked = sum(realized.values())
    avail = float(total) + banked                  # finished holdings add their result to (or take it from) the money to share out
    equal = lt.split_total(avail, picks, ins)
    custom = None
    if picks and st.toggle("Set my own amount for each name (off: the total is shared equally, names already holding more keep what they have)",
                           value=bool(saved.get("custom")), key="lt_custom_on"):
        sc, cols, custom = saved.get("custom") or {}, st.columns(4), {}
        for i, t in enumerate(picks):
            custom[t] = cols[i % 4].number_input(f"{t} ($)", min_value=0.0, value=float(sc.get(t, round(equal[t]))), step=100.0, key=f"lt_amt_{t}")
    targets = lt.split_total(avail, picks, ins, custom)
    if (list(picks), float(total), preset, bool(addup), custom or {}) != (list(saved.get("picks") or []), float(saved.get("total") or 10000.0),
                                                                           saved.get("preset") or presets[0], addup0, saved.get("custom") or {}):
        lt.save_picks(picks, total, preset, addup, custom)
    fresh_mode = bool(pos)
    if show_real and pos:
        st.caption("Names marked “mine” come from the buys and sells you recorded, at your real prices and amounts. A name marked “if bought now” "
                   "is not held: it is priced as if its first tranche were bought at the price now.")
    elif not show_real:
        st.caption("Real buys and sells are private: they are shown and recorded only when this page is opened with the admin link. "
                   "Without it the calculator follows the plan from each name's plan date, as if every order was resting at its price.")
    if not picks:
        st.caption(f"Choose up to {lt.MAX_PICKS} names and this shows, in one table, what is in, what is still to buy and where, the stop, "
                   "what each sell level is worth, and the combined result of the whole portfolio.")
        see = st.selectbox("Or look at the chart and levels of one name", ["—"] + tks, key="lt_see", format_func=lambda t: t if t == "—" else label(t))
        if see != "—" and live[see]["price"] is not None:
            r, L = by_name[see], live[see]
            stt = lt.walk(r, L["since"], weights0, L["events"], addup)
            st.plotly_chart(_chart(r, L["chart"], stt, L["marks"], L["price"], None), use_container_width=True, key=f"lt_ch_{see}")
            st.markdown(_next_steps(r, stt, L["marks"], L["price"], None), unsafe_allow_html=True)
    else:
        calc = _build(by_name, live, pos, picks, targets, w, addup, fresh_mode)
        ok = [x for x in calc if x["ok"]]
        spare = avail - sum(x["alloc"] for x in ok)
        path = st.radio("Work out the sell levels", list(lt.PATHS), format_func=lt.PATHS.get, horizontal=True, key="lt_path")
        st.markdown(_calc_table(calc, path, float(total), spare, realized), unsafe_allow_html=True)
        st.caption("Each sell cell shows the sell price, how far it is from the price now, and what the name is then worth with its result on the money "
                   "planned for it; money not yet spent counts at face value. The last row adds the names up against the total. Fees are left out.")
        if ok and total:
            st.markdown("##### Combined result of the whole portfolio")
            st.markdown(_roi_grid(calc, float(total), spare), unsafe_allow_html=True)
            st.caption("Each line assumes every name reaches that level, which coins that move together often do and names that do not move together "
                       "often do not. These are sums of the plan's own levels, not forecasts.")
            if custom is None:
                cmp_rows = {}
                for lab, tv in lt.TOTAL_OPTIONS.items():
                    cx = [x for x in _build(by_name, live, pos, picks, lt.split_total(tv + banked, picks, ins), w, addup, fresh_mode) if x["ok"]]
                    sp = tv + banked - sum(x["alloc"] for x in cx)
                    cmp_rows[lab] = (tv, sum(sum(b["share"] for b in lt.to_place(x["r"], x["stt"], x["p"])) * x["alloc"] for x in cx),
                                     _worth(cx, sp, lambda x: x["oc"]["stop_full"]), _worth(cx, sp, lambda x: x["oc"]["now"][-1]),
                                     _worth(cx, sp, lambda x: x["oc"]["full"][-1]))
                labs = list(cmp_rows)
                st.markdown("##### Option A against Option B, same names, shared equally")
                st.markdown(_table([("", "l")] + [(k, "") for k in labs], [
                    "<tr><td class='l'>Money still to place</td>" + "".join(f"<td>{_usd(cmp_rows[k][1])}</td>" for k in labs) + "</tr>",
                    "<tr><td class='l'>Every remaining buy fills, then every stop is hit</td>" + "".join(f"<td>{_gain(cmp_rows[k][2], cmp_rows[k][0])}</td>" for k in labs) + "</tr>",
                    "<tr><td class='l'>Every sell level is reached with what is held now</td>" + "".join(f"<td>{_gain(cmp_rows[k][3], cmp_rows[k][0])}</td>" for k in labs) + "</tr>",
                    "<tr><td class='l'>Every remaining buy fills on a dip, then every sell level is reached</td>" + "".join(f"<td>{_gain(cmp_rows[k][4], cmp_rows[k][0])}</td>" for k in labs) + "</tr>"]),
                    unsafe_allow_html=True)
        with st.expander("Every order with its numbers: money and units for each buy, units and proceeds for each sell"):
            st.markdown(_orders(calc, path), unsafe_allow_html=True)
            st.caption(f"Sells and the stop are worked out on the path chosen above: {lt.PATHS[path].lower()}.")
        if ok:
            see = st.radio("Chart and next steps for", [x["tk"] for x in ok] + ["All"], horizontal=True, key="lt_detail",
                           index=len(ok) if len(ok) <= 3 else 0)
            for x in ok:
                if see not in ("All", x["tk"]):
                    continue
                r, L, stt, alloc = x["r"], x["L"], x["stt"], x["alloc"]
                sig = lt.signal(r, None if x["tag"] == "mine" else stt, L["price"], L["fresh"])
                st.markdown(f"##### {r['tk']} · {html.escape(r['name'])} &nbsp; {_chip(sig)} <span style='opacity:.6;font-size:.8rem'>{x['tag']}</span>", unsafe_allow_html=True)
                st.plotly_chart(_chart(r, L["chart"], stt, L["marks"], L["price"], alloc), use_container_width=True, key=f"lt_ch_{r['tk']}")
                st.caption("Light green band: the buy zone between buy 1 and the last buy. Dark green band: under the last buy, down to the stop. "
                           "Blue dashed lines are the sell levels. Amber dotted lines are the adds if price goes up: each needs two daily closes above it, "
                           "and shows the money it would put in. Log scale.")
                st.markdown(_next_steps(r, stt, L["marks"], L["price"], alloc), unsafe_allow_html=True)
                st.markdown(_returns(r, stt, L["price"], alloc, L["marks"]), unsafe_allow_html=True)

    # ── record real buys and sells (admin link only) ──
    if admin:
        with st.expander("Record a buy or a sell I actually made" + (f" · {len(fills)} recorded" if fills else "")):
            st.caption("One per line: NAME buy|sell PRICE USDT UNITS, for example “SOL buy 70.00 1400 20”. Units are optional. A line can be one "
                       "order or a whole position at its average price. These are saved on this server's private disk only.")
            with st.form("lt_fill_form", clear_on_submit=True):
                txt = st.text_area("Fills to add", height=110, key="lt_fill_text")
                wipe = st.checkbox("Replace everything recorded so far with these lines", value=False, key="lt_fill_wipe")
                ok_btn = st.form_submit_button("Save")
            if ok_btn:
                good, bad = lt.parse_fills(txt, tks, time.time())
                if good and lt.save_fills(([] if wipe else fills) + good):
                    st.success(f"Saved {len(good)} fill(s).")
                    st.rerun()
                if bad:
                    st.warning("Could not read: " + " | ".join(html.escape(b) for b in bad))
            if fills:
                st.markdown(_table([("Recorded", "l"), ("Name", "l"), ("Side", "l"), ("Price", ""), ("USDT", ""), ("Units", "")],
                                   [f"<tr><td class='l'>{_d(f.get('ts'))}</td><td class='l'><b>{f['tk']}</b></td><td class='l'>{f['side']}</td>"
                                    f"<td>{lt.fmt(f['price'])}</td><td>{_usd(f['usd'])}</td><td>{f['units']:,.6g}</td></tr>" for f in fills]),
                            unsafe_allow_html=True)
                if st.button("Remove the last recorded fill", key="lt_fill_undo"):
                    lt.save_fills(fills[:-1])
                    st.rerun()

    # ── the research behind it ──
    st.markdown("#### The research workbook")
    wb_html, wb_st = None, {}
    try:
        wb_html, wb_st = _workbook()
    except Exception as exc:
        st.warning(f"The workbook could not be loaded: {exc}")
    if wb_st.get("last_ok"):
        st.caption("Charts, odds, fundamentals, the plan builder and the method. Rebuilt automatically every day after the 00:00 UTC close: "
                   f"last rebuilt {datetime.fromtimestamp(float(wb_st['last_ok']), timezone.utc):%d %b %H:%M} UTC with prices to the close of "
                   f"{html.escape(str(wb_st.get('asof_label') or ''))}. Its buy levels restart from that close, so they differ from the fixed plan above.")
    else:
        st.caption(f"Charts, odds, fundamentals, the plan builder and the method, as a snapshot from the close of {wbl}. Its buy levels start "
                   "from that close, so they differ from the fixed plan above. The automatic daily rebuild replaces it after its first run.")
    if wb_st.get("error"):
        st.caption(f"The latest rebuild attempt did not finish ({html.escape(str(wb_st['error'])[:140])}); the copy shown is the last good one.")
    b1, b2 = st.columns([1, 3])
    try:
        b1.download_button(f"⬇ Download the PDF ({wbl} snapshot)", _workbook_pdf(), file_name="Long-term-plan-workbook.pdf", mime="application/pdf", key="lt_pdf")
    except Exception:
        b1.caption("PDF not available")
    if b2.toggle("Show the full workbook here", value=False, key="lt_show_wb") and wb_html:
        components.html(wb_html, height=1400, scrolling=True)

    st.caption(f"Updated {datetime.now(timezone.utc):%H:%M:%S} UTC · reloads itself every {REFRESH_S // 60} minutes while this tab is open.")
    components.html(
        "<script>(function(){var P=window.parent||window;if(!P.__ltReload){P.__ltReload=1;setTimeout(function(){"
        "try{P.location.reload();}catch(e){}}," + str(REFRESH_S * 1000) + ");}})();</script>", height=0)
