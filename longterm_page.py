"""📈 Long Term Investment — the page (user 2026-11-14: "deploy this as separate section … on the left
long term investment as headline" · "it should be updated as the market unfolds" · "have the portfolio and
colors to buy strong buy hold as per our plans" · "we are buying in 3 trenches not 4" · "can hold upto 4
instead of 3" · "show when its the time to buy the dip on the charts next buy zone … if the price hold above
when to buy on that level as well … do the calculations and show the returns and when to sell").

Light by design: ten daily-candle requests for the names plus one for BTC, cached five minutes, and nothing
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
    return f"{'+' if v > 0 else '−' if v < 0 else ''}{abs(v) * 100:.{digits}f}%"


def _pct_html(v, digits=0) -> str:
    if v is None:
        return "—"
    col = "#34c26b" if v > 0 else "#ff6b6b" if v < 0 else "inherit"
    return f"<span style='color:{col}'>{_pct(v, digits)}</span>"


def _usd(v) -> str:
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
        amt = f" · {_usd(w[k] * alloc)}" if (alloc and not did) else ""
        fig.add_hline(y=rg, line=dict(color=C_BUY, width=1.3, dash="dash"))
        labels.append((rg, f"Buy {k + 1} · {lt.fmt(rg)}{' · bought' if did else amt}"))
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


def render(load_fear_greed=None, admin: bool = False) -> None:
    """Draw the whole section. load_fear_greed: the app's cached Fear & Greed loader (optional).
    admin: the page was opened with the site's admin link; only then are real fills shown and editable."""
    try:
        plan = lt.load_plan()
    except Exception as exc:                     # a missing plan must not take the page down
        st.error(f"The long-term plan file could not be read: {exc}")
        return
    now = time.time()
    start = float(plan["start"])
    names = plan["names"]
    tks = [r["tk"] for r in names]
    pdl = html.escape(plan.get("plan_date_label", ""))
    st.markdown(_TABLE_CSS, unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:1.9rem;font-weight:800;letter-spacing:-.02em;line-height:1.15'>📈 Long Term Investment</div>"
        f"<div style='opacity:.7;font-size:.9rem;margin:2px 0 10px'>Ten names, one plan each: three buy tranches, a stop and three sell "
        f"levels, fixed at the close of {pdl}. Prices and signals refresh every five minutes.</div>", unsafe_allow_html=True)
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

    # ── every name: live price, history, triggers ──
    saved = lt.load_picks()
    addup0 = bool(saved.get("addup", True))
    weights0 = next(iter(lt.RUNG_PRESETS.values()))
    live = {}
    for r in names:
        full = _daily(r["sym"], 500)
        if not full:
            live[r["tk"]] = {"price": None, "act": None}
            continue
        hist = _history(r, full)
        since = [b for b in full if b[0] >= start]
        price = full[-1][3]
        events = lt.addup_events(hist, start)
        fresh = next((e for e in events if hist and e["ts"] == hist[-1][0]), None)
        mech = lt.walk(r, since, weights0, events, addup0)
        act = lt.actual_state(r, by_tk[r["tk"]]) if r["tk"] in by_tk else (None, 0.0)
        live[r["tk"]] = {"price": price, "since": since, "events": events, "fresh": fresh, "marks": lt.landmarks(hist, price),
                         "chart": hist + [full[-1]], "mech": mech, "act": act if act[0] else None, "state": act[0] or mech}

    st.markdown("#### The plan board")
    rows = []
    for r in names:
        L = live[r["tk"]]
        p = L["price"]
        if p is None:
            rows.append(f"<tr><td><b>{r['tk']}</b> <span class='mu'>{html.escape(r['name'])}</span></td><td colspan='8' class='l mu'>price feed unavailable</td></tr>")
            continue
        stt = L["state"]
        sig = lt.signal(r, stt, p, L["fresh"])
        nb, na = lt.next_levels(r, stt, p, L["marks"])
        reached = sum(1 for x in stt["filled"] if x)
        tp_hit = sum(1 for x in stt["sold"] if x)
        prog = (f"{reached} of {len(r['rungs'])} bought · mine" if L["act"] else f"{reached} of {len(r['rungs'])} buys") + (f" · {tp_hit} sold" if tp_hit else "")
        rows.append(
            f"<tr><td><b>{r['tk']}</b> <span class='mu'>{html.escape(r['name'])}{' · tokenized, 24h' if r.get('stock') else ''}</span></td>"
            f"<td>{lt.fmt(p)}</td><td>{_pct_html(p / r['px0'] - 1, 1)}</td><td class='l'>{_chip(sig)}</td>"
            f"<td class='l w'>{html.escape(sig['detail'])}</td>"
            f"<td>{lt.fmt(nb[1])} <span class='mu'>{nb[0]} · {_pct(nb[1] / p - 1)}</span></td>"
            f"<td>{(lt.fmt(na[1]) + ' <span class=mu>' + html.escape(na[0]) + ' · ' + _pct(na[1] / p - 1) + '</span>') if na else '—'}</td>"
            f"<td>{prog}</td><td>{lt.fmt(r['stop'])}</td></tr>")
    st.markdown(_table([("Name", ""), ("Price now", ""), ("Since the plan date", ""), ("Plan signal", "l"), ("Where price sits", "l"),
                        ("Next buy zone below", ""), ("Next level above", ""), ("Orders reached", ""), ("Stop", "")], rows), unsafe_allow_html=True)
    leg = " &nbsp; ".join(f"{_chip({'label': lt.SIGNALS[k][0], 'bg': lt.SIGNALS[k][1], 'fg': lt.SIGNALS[k][2]})} "
                          f"<span style='opacity:.75;font-size:.8rem'>{lt.SIGNALS[k][3]}</span>" for k in lt.SIGNAL_ORDER)
    st.markdown(f"<div style='margin:8px 0 2px;line-height:2.1'>{leg}</div>", unsafe_allow_html=True)
    st.caption("An order counts as reached when a daily candle since the plan date touched its price. Stock prices here are the "
               "tokenized tickers, which trade around the clock and can sit slightly off the US close.")

    # ── my portfolio ──
    st.markdown("#### My portfolio")
    mine = [t for t in tks if t in by_tk]
    default = (mine + [t for t in (saved.get("picks") or []) if t in tks and t not in mine])[:lt.MAX_PICKS]
    a1, a2, a3 = st.columns([3, 1.2, 2])
    picks = a1.multiselect("My names (up to four)", tks, default=default, max_selections=lt.MAX_PICKS, key="lt_picks",
                           format_func=lambda t: f"{t} · {next(r['name'] for r in names if r['tk'] == t)}")
    total = a2.number_input("Total ($), for names without real buys", min_value=0.0, value=float(saved.get("total") or 10000.0), step=500.0, key="lt_total")
    presets = list(lt.RUNG_PRESETS)
    preset = a3.selectbox("Money per tranche", presets, index=presets.index(saved.get("preset")) if saved.get("preset") in presets else 0, key="lt_preset")
    addup = st.toggle("If price goes up instead of dipping, add the lowest unfilled tranche once it holds above a landmark", value=addup0, key="lt_addup")
    st.caption("Holds above = two daily closes in a row over the 50-day or 200-day average, or a first close over the highest close of the last 90 days. "
               "In the past this did not help for the coins: six months after a first close back over the 200-day average their median result was −17%, "
               "against −10% for any ordinary day. For Nvidia, Broadcom and Marvell it was somewhat better, on only 12 cases.")
    if (list(picks), float(total), preset, bool(addup)) != (list(saved.get("picks") or []), float(saved.get("total") or 10000.0),
                                                              saved.get("preset") or presets[0], addup0):
        lt.save_picks(picks, total, preset, addup)
    if show_real and mine:
        st.caption("Names marked “mine” are tracked from the buys and sells you recorded, at your real prices and amounts. "
                   "Each tranche still to come is sized like your first buy of that name.")
    elif not show_real:
        st.caption("Real buys and sells are private: they are shown and recorded only when this page is opened with the admin link. "
                   "Without it the portfolio below follows the plan as if every order was resting at its price.")
    if not picks:
        st.caption("Choose up to four names and this shows, for your amount, the chart with the next buy zone, the adds if price goes up, "
                   "what each sell level returns, and what has been bought and sold so far.")
        see = st.selectbox("Or look at the chart and levels of one name", ["—"] + tks, key="lt_see",
                           format_func=lambda t: t if t == "—" else f"{t} · {next(r['name'] for r in names if r['tk'] == t)}")
        if see != "—" and live[see]["price"] is not None:
            r, L = next(x for x in names if x["tk"] == see), live[see]
            stt = lt.walk(r, L["since"], weights0, L["events"], addup)
            st.plotly_chart(_chart(r, L["chart"], stt, L["marks"], L["price"], None), use_container_width=True, key=f"lt_ch_{see}")
            st.markdown(_next_steps(r, stt, L["marks"], L["price"], None), unsafe_allow_html=True)
    else:
        w = lt.RUNG_PRESETS[preset]
        alloc_h = float(total) / len(picks)
        prow, orows, blocks = [], [], []
        t_alloc = t_work = t_val = t_tp_now = t_tp_up = t_tp_full = t_stop_full = 0.0
        for tk in picks:
            r = next(x for x in names if x["tk"] == tk)
            L = live[tk]
            p = L["price"]
            real = bool(L.get("act"))
            if p is None:
                prow.append(f"<tr><td><b>{tk}</b></td><td colspan='8' class='l mu'>price feed unavailable</td></tr>")
                continue
            if real:
                stt, alloc = L["act"]
            else:
                stt, alloc = lt.walk(r, L["since"], w, L["events"], addup), alloc_h
            mech = L["mech"]
            sig = lt.signal(r, stt, p, L["fresh"])
            oc = lt.outcomes(r, stt, L["marks"])
            val = lt.value(stt, p) * alloc
            t_alloc += alloc
            t_work += stt["spent"] * alloc
            t_val += val
            t_tp_now += oc["now"][-1] * alloc
            t_tp_up += oc["up"][-1] * alloc
            t_tp_full += oc["full"][-1] * alloc
            t_stop_full += oc["stop_full"] * alloc
            blocks.append((r, L, stt, sig, alloc))
            spent_d = stt["spent"] * alloc
            cost_v = stt["units"] * alloc * (stt["avg_cost"] or 0)
            held_v = stt["units"] * alloc * p
            prow.append(f"<tr><td><b>{tk}</b> <span class='mu'>{html.escape(r['name'])}{' · mine' if real else ' · plan only'}</span></td><td class='l'>{_chip(sig)}</td>"
                        f"<td>{_usd(alloc)}</td><td>{_usd(spent_d)}</td><td>{stt['units'] * alloc:,.4g}</td>"
                        f"<td>{lt.fmt(stt['avg_cost'])}</td><td>{lt.fmt(p)}</td><td>{_usd(held_v)}</td>"
                        f"<td>{_usd(val - alloc)} {_pct_html((held_v / cost_v - 1) if cost_v else 0, 1)}</td></tr>")
            for k, rg in enumerate(r["rungs"]):
                amt = stt["weights"][k] * alloc
                if amt <= 0:
                    continue
                if stt["filled"][k]:
                    if real:
                        stat = f"bought {_d(stt['fill_ts'][k])} at {lt.fmt(stt['fill_px'][k])}"
                    elif k == 0:
                        stat = "bought at the plan date"
                    else:
                        add = next((x for x in stt["adds"] if x["k"] == k), None)
                        stat = (f"bought {_d(add['ts'])} at {lt.fmt(add['price'])}: {add['label']}" if add else f"bought, reached {_d(stt['fill_ts'][k])}")
                elif real and mech["filled"][k]:
                    stat = f"price touched this level on {_d(mech['fill_ts'][k])}: record the buy if your order filled"
                else:
                    stat = "waiting"
                orows.append(f"<tr><td><b>{tk}</b></td><td class='l'>Buy {k + 1}</td><td>{lt.fmt(rg)}</td><td>{_pct(rg / p - 1)}</td>"
                             f"<td>{_usd(amt)}</td><td class='l'>{stat}</td></tr>")
            for j, tp in enumerate(r["tps"]):
                if stt["sold"][j]:
                    stat = "sold" + (f", {_d(stt['sold_ts'][j])}" if stt["sold_ts"][j] else "")
                elif real and mech["sold"][j]:
                    stat = f"price touched this level on {_d(mech['sold_ts'][j])}: record the sale if your order filled"
                else:
                    stat = "waiting"
                orows.append(f"<tr><td><b>{tk}</b></td><td class='l'>Sell {j + 1} ({'a third' if j < 2 else 'the rest'})</td>"
                             f"<td>{lt.fmt(tp)}</td><td>{_pct(tp / p - 1)}</td><td>—</td><td class='l'>{stat}</td></tr>")
            stop_stat = ("hit " + _d(stt["stop_ts"])) if stt["stopped"] else (f"price touched the stop on {_d(mech['stop_ts'])}" if (real and mech["stopped"]) else "waiting")
            orows.append(f"<tr><td><b>{tk}</b></td><td class='l'>Stop-loss (sell everything)</td><td>{lt.fmt(r['stop'])}</td>"
                         f"<td>{_pct(r['stop'] / p - 1)}</td><td>—</td><td class='l'>{stop_stat}</td></tr>")
        if t_alloc:
            prow.append(f"<tr class='tot'><td>Total</td><td></td><td>{_usd(t_alloc)}</td><td>{_usd(t_work)}</td><td></td><td></td><td></td>"
                        f"<td></td><td>{_usd(t_val - t_alloc)} {_pct_html((t_val - t_alloc) / t_work if t_work else 0, 1)}</td></tr>")
        st.markdown(_table([("Name", ""), ("Plan signal", "l"), ("Planned for this name", ""), ("Put in so far", ""), ("Units held", ""), ("Average buy price", ""),
                            ("Price now", ""), ("Holding worth now", ""), ("Result so far", "")], prow), unsafe_allow_html=True)
        st.caption("Planned for this name = what is in plus the tranches still to come. Result so far is on the money actually put in.")
        if t_alloc:
            st.markdown("##### What the whole portfolio would be worth")
            st.markdown(_table([("If", "l"), ("Portfolio, against the planned total", "")], [
                f"<tr><td class='l'>every sell level is reached from here, with what is held now</td><td>{_gain(t_tp_now, t_alloc)}</td></tr>",
                f"<tr><td class='l'>price goes up first: the adds trigger at their levels, then every sell level is reached</td><td>{_gain(t_tp_up, t_alloc)}</td></tr>",
                f"<tr><td class='l'>every remaining buy fills on a dip first, then every sell level is reached</td><td>{_gain(t_tp_full, t_alloc)}</td></tr>",
                f"<tr><td class='l'>every remaining buy fills, then every stop is hit</td><td>{_gain(t_stop_full, t_alloc)}</td></tr>"]), unsafe_allow_html=True)
        for r, L, stt, sig, alloc in blocks:
            st.markdown(f"##### {r['tk']} · {html.escape(r['name'])} &nbsp; {_chip(sig)}", unsafe_allow_html=True)
            st.plotly_chart(_chart(r, L["chart"], stt, L["marks"], L["price"], alloc), use_container_width=True, key=f"lt_ch_{r['tk']}")
            st.caption("Light green band: the buy zone between buy 1 and the last buy. Dark green band: under the last buy, down to the stop. "
                       "Blue dashed lines are the sell levels. Amber dotted lines are the adds if price goes up: each needs two daily closes above it, "
                       "and shows the money it would put in. Log scale.")
            st.markdown(_next_steps(r, stt, L["marks"], L["price"], alloc), unsafe_allow_html=True)
            st.markdown(_returns(r, stt, L["price"], alloc, L["marks"]), unsafe_allow_html=True)
        with st.expander("Every order in the plan, and where it stands"):
            st.markdown(_table([("Name", ""), ("Order", "l"), ("Price", ""), ("From the price now", ""), ("Amount", ""), ("Status", "l")], orows),
                        unsafe_allow_html=True)
        st.caption("Names marked “plan only” follow the plan mechanically from the plan date, as if every order was resting at its price. "
                   "Dollar figures leave out fees.")

    # ── record real buys and sells (admin link only) ──
    if admin:
        with st.expander("Record a buy or a sell I actually made" + (f" · {len(fills)} recorded" if fills else "")):
            st.caption("One per line: NAME buy|sell PRICE USDT UNITS, for example “SOL buy 75.98 1000 13.147”. Units are optional. "
                       "These are saved on this server's private disk only.")
            with st.form("lt_fill_form", clear_on_submit=True):
                txt = st.text_area("Fills to add", height=110, key="lt_fill_text")
                ok_btn = st.form_submit_button("Save")
            if ok_btn:
                good, bad = lt.parse_fills(txt, tks, time.time())
                if good and lt.save_fills(fills + good):
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
        st.caption(f"Charts, odds, fundamentals, the plan builder and the method, as a snapshot from {pdl}; its levels match the board above. "
                   "The automatic daily rebuild replaces it after its first run.")
    if wb_st.get("error"):
        st.caption(f"The latest rebuild attempt did not finish ({html.escape(str(wb_st['error'])[:140])}); the copy shown is the last good one.")
    b1, b2 = st.columns([1, 3])
    try:
        b1.download_button(f"⬇ Download the PDF ({pdl} snapshot)", _workbook_pdf(), file_name="Long-term-plan-workbook.pdf", mime="application/pdf", key="lt_pdf")
    except Exception:
        b1.caption("PDF not available")
    if b2.toggle("Show the full workbook here", value=False, key="lt_show_wb") and wb_html:
        components.html(wb_html, height=1400, scrolling=True)

    st.caption(f"Updated {datetime.now(timezone.utc):%H:%M:%S} UTC · reloads itself every {REFRESH_S // 60} minutes while this tab is open.")
    components.html(
        "<script>(function(){var P=window.parent||window;if(!P.__ltReload){P.__ltReload=1;setTimeout(function(){"
        "try{P.location.reload();}catch(e){}}," + str(REFRESH_S * 1000) + ");}})();</script>", height=0)
