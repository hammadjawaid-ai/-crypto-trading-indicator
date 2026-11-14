"""📈 Long Term Investment — the page (user 2026-11-14: "deploy this as separate section … on the left
long term investment as headline" · "it should be updated as the market unfolds" · "have the portfolio and
colors to buy strong buy hold as per our plans").

Light by design: ten daily-candle requests for the names plus one for BTC, cached five minutes, and nothing
from the scanner. app.py calls render() before its shared header and market loads, then stops.
The logic is in longterm.py; the plan levels are frozen in longterm_data/plan.json.
"""
from __future__ import annotations

import html
import os
import time
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import binance_client
import longterm as lt

SECTION = "📈 Long Term Investment"
REFRESH_S = 300


@st.cache_data(ttl=REFRESH_S, show_spinner=False)
def _daily(sym: str, limit: int) -> list:
    """Daily bars as (ts, high, low, close), oldest first. [] when the feed has nothing."""
    try:
        df = binance_client.get_klines(sym, "1d", limit=int(limit))
    except Exception:
        return []
    if df is None or len(df) == 0:
        return []
    return [(pd.Timestamp(i).timestamp(), float(h), float(l), float(c))
            for i, h, l, c in zip(df.index, df["high"], df["low"], df["close"])]


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
        if os.path.exists(p) and stt.get("last_ok"):
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
</style>
"""


def _table(head: list, rows: list, cls: str = "") -> str:
    th = "".join(f"<th class='{c}'>{h}</th>" for h, c in head)
    body = "".join(rows)
    return f"<div class='lt-wrap'><table class='lt {cls}'><tr>{th}</tr>{body}</table></div>"


def render(load_fear_greed=None) -> None:
    """Draw the whole section. load_fear_greed: the app's cached Fear & Greed loader (optional)."""
    try:
        plan = lt.load_plan()
    except Exception as exc:                     # a missing plan must not take the page down
        st.error(f"The long-term plan file could not be read: {exc}")
        return
    now = time.time()
    start = float(plan["start"])
    days = max(1, int((now - start) // 86400) + 3)
    names = plan["names"]
    st.markdown(_TABLE_CSS, unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:1.9rem;font-weight:800;letter-spacing:-.02em;line-height:1.15'>📈 Long Term Investment</div>"
        f"<div style='opacity:.7;font-size:.9rem;margin:2px 0 10px'>Ten names, one plan each, fixed at the close of "
        f"{html.escape(plan.get('plan_date_label', ''))}. Prices and signals refresh every five minutes.</div>",
        unsafe_allow_html=True)
    st.info("This page tracks a plan; it does not give advice. A signal says which zone of the plan the price is in "
            "(for example, under buy 3). It is not a forecast, and the choice of names and amounts is yours.", icon="ℹ️")

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

    # ── every name: live price against its plan ──
    weights0 = lt.RUNG_PRESETS["Equal: 25 / 25 / 25 / 25"]
    live = {}
    for r in names:
        bars = [b for b in _daily(r["sym"], min(1000, days + 2)) if b[0] >= start]
        price = bars[-1][3] if bars else None
        if price is None:                         # no bar since the plan date yet: fall back to the latest close on record
            allb = _daily(r["sym"], 5)
            price = allb[-1][3] if allb else None
        live[r["tk"]] = {"bars": bars, "price": price, "state": lt.walk(r, bars, weights0)}

    st.markdown("#### The plan board")
    rows = []
    for r in names:
        L = live[r["tk"]]
        p, stt = L["price"], L["state"]
        sig = lt.signal(r, stt, p)
        if p is None:
            rows.append(f"<tr><td><b>{r['tk']}</b> <span class='mu'>{html.escape(r['name'])}</span></td><td colspan='8' class='l mu'>price feed unavailable</td></tr>")
            continue
        nb, na = lt.next_levels(r, stt, p)
        reached = sum(1 for x in stt["filled"] if x)
        tp_hit = sum(1 for x in stt["sold"] if x)
        prog = f"{reached} of {len(r['rungs'])} buys" + (f" · {tp_hit} take-profit{'s' if tp_hit > 1 else ''}" if tp_hit else "")
        rows.append(
            f"<tr><td><b>{r['tk']}</b> <span class='mu'>{html.escape(r['name'])}{' · tokenized, 24h' if r.get('stock') else ''}</span></td>"
            f"<td>{lt.fmt(p)}</td><td>{_pct_html(p / r['px0'] - 1, 1)}</td><td class='l'>{_chip(sig)}</td>"
            f"<td class='l w'>{html.escape(sig['detail'])}</td>"
            f"<td>{lt.fmt(nb[1])} <span class='mu'>{nb[0]} · {_pct(nb[1] / p - 1)}</span></td>"
            f"<td>{(lt.fmt(na[1]) + ' <span class=mu>' + html.escape(na[0]) + ' · ' + _pct(na[1] / p - 1) + '</span>') if na else '—'}</td>"
            f"<td>{prog}</td><td>{lt.fmt(r['stop'])}</td></tr>")
    st.markdown(_table([("Name", ""), ("Price now", ""), ("Since the plan date", ""), ("Plan signal", "l"), ("Where price sits", "l"),
                        ("Next level below", ""), ("Next level above", ""), ("Orders reached", ""), ("Stop", "")], rows), unsafe_allow_html=True)
    leg = " &nbsp; ".join(f"{_chip({'label': lt.SIGNALS[k][0], 'bg': lt.SIGNALS[k][1], 'fg': lt.SIGNALS[k][2]})} "
                          f"<span style='opacity:.75;font-size:.8rem'>{lt.SIGNALS[k][3]}</span>" for k in lt.SIGNAL_ORDER)
    st.markdown(f"<div style='margin:8px 0 2px;line-height:2.1'>{leg}</div>", unsafe_allow_html=True)
    st.caption("An order counts as reached when a daily candle since the plan date touched its price. Stock prices here are the "
               "tokenized tickers, which trade around the clock and can sit slightly off the US close.")

    # ── my three ──
    st.markdown("#### My portfolio")
    saved = lt.load_picks()
    tks = [r["tk"] for r in names]
    a1, a2, a3 = st.columns([3, 1.2, 2])
    picks = a1.multiselect("My three names", tks, default=[t for t in (saved.get("picks") or []) if t in tks][:3],
                           max_selections=3, key="lt_picks", format_func=lambda t: f"{t} · {next(r['name'] for r in names if r['tk'] == t)}")
    total = a2.number_input("Total ($)", min_value=0.0, value=float(saved.get("total") or 10000.0), step=500.0, key="lt_total")
    presets = list(lt.RUNG_PRESETS)
    preset = a3.selectbox("Money per rung", presets, index=presets.index(saved.get("preset")) if saved.get("preset") in presets else 0, key="lt_preset")
    if (picks, float(total), preset) != (list(saved.get("picks") or []), float(saved.get("total") or 10000.0), saved.get("preset") or presets[0]):
        lt.save_picks(picks, total, preset)
    if not picks:
        st.caption("Choose up to three names and this shows, for your amount, what the plan has bought and sold so far and what it is worth now.")
    else:
        w = lt.RUNG_PRESETS[preset]
        alloc = float(total) / len(picks)
        prow, orows = [], []
        t_work = t_val = 0.0
        for tk in picks:
            r = next(x for x in names if x["tk"] == tk)
            L = live[tk]
            p = L["price"]
            if p is None:
                prow.append(f"<tr><td><b>{tk}</b></td><td colspan='8' class='l mu'>price feed unavailable</td></tr>")
                t_val += alloc
                continue
            stt = lt.walk(r, L["bars"], w)
            sig = lt.signal(r, stt, p)
            val = lt.value(stt, p) * alloc
            held = stt["units"] * alloc
            t_work += stt["spent"] * alloc
            t_val += val
            prow.append(f"<tr><td><b>{tk}</b> <span class='mu'>{html.escape(r['name'])}</span></td><td class='l'>{_chip(sig)}</td>"
                        f"<td>{_usd(alloc)}</td><td>{_usd(stt['spent'] * alloc)}</td><td>{held:,.4g}</td>"
                        f"<td>{lt.fmt(stt['avg_cost'])}</td><td>{lt.fmt(p)}</td><td>{_usd(val)}</td>"
                        f"<td>{_usd(val - alloc)} {_pct_html(val / alloc - 1, 1) if alloc else ''}</td></tr>")
            for k, rg in enumerate(r["rungs"]):
                amt = w[k] * alloc
                if amt <= 0:
                    continue
                stat = ("bought at the plan date" if k == 0 else f"bought, reached {_d(stt['fill_ts'][k])}") if stt["filled"][k] else "waiting"
                orows.append(f"<tr><td><b>{tk}</b></td><td class='l'>Buy {k + 1}</td><td>{lt.fmt(rg)}</td><td>{_pct(rg / p - 1)}</td>"
                             f"<td>{_usd(amt)}</td><td class='l'>{stat}</td></tr>")
            for j, tp in enumerate(r["tps"]):
                stat = f"sold, reached {_d(stt['sold_ts'][j])}" if stt["sold"][j] else "waiting"
                orows.append(f"<tr><td><b>{tk}</b></td><td class='l'>Take profit {j + 1} ({'a third' if j < 2 else 'the rest'})</td>"
                             f"<td>{lt.fmt(tp)}</td><td>{_pct(tp / p - 1)}</td><td>—</td><td class='l'>{stat}</td></tr>")
            orows.append(f"<tr><td><b>{tk}</b></td><td class='l'>Stop-loss (sell everything)</td><td>{lt.fmt(r['stop'])}</td>"
                         f"<td>{_pct(r['stop'] / p - 1)}</td><td>—</td><td class='l'>{'hit ' + _d(stt['stop_ts']) if stt['stopped'] else 'waiting'}</td></tr>")
        prow.append(f"<tr class='tot'><td>Total</td><td></td><td>{_usd(float(total))}</td><td>{_usd(t_work)}</td><td></td><td></td><td></td>"
                    f"<td>{_usd(t_val)}</td><td>{_usd(t_val - float(total))} {_pct_html(t_val / float(total) - 1, 1) if total else ''}</td></tr>")
        st.markdown(_table([("Name", ""), ("Plan signal", "l"), ("Allocated", ""), ("Put to work", ""), ("Units held", ""), ("Average buy price", ""),
                            ("Price now", ""), ("Worth now", ""), ("Result", "")], prow), unsafe_allow_html=True)
        with st.expander("Every order in my plan, and whether the market has reached it"):
            st.markdown(_table([("Name", ""), ("Order", "l"), ("Price", ""), ("From the price now", ""), ("Amount", ""), ("Status", "l")], orows),
                        unsafe_allow_html=True)
        st.caption("This follows the plan mechanically from the plan date, as if every order was resting at its price. "
                   "It is not a record of trades you actually made.")

    # ── the research behind it ──
    st.markdown("#### The research workbook")
    wb_html, wb_st = None, {}
    try:
        wb_html, wb_st = _workbook()
    except Exception as exc:
        st.warning(f"The workbook could not be loaded: {exc}")
    pdl = html.escape(plan.get("plan_date_label", ""))
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
        b1.download_button(f"⬇ Download the PDF ({pdl} snapshot)", _workbook_pdf(), file_name="Three-of-Ten-workbook.pdf", mime="application/pdf", key="lt_pdf")
    except Exception:
        b1.caption("PDF not available")
    if b2.toggle("Show the full workbook here", value=False, key="lt_show_wb") and wb_html:
        components.html(wb_html, height=1400, scrolling=True)

    st.caption(f"Updated {datetime.now(timezone.utc):%H:%M:%S} UTC · reloads itself every {REFRESH_S // 60} minutes while this tab is open.")
    components.html(
        "<script>(function(){var P=window.parent||window;if(!P.__ltReload){P.__ltReload=1;setTimeout(function(){"
        "try{P.location.reload();}catch(e){}}," + str(REFRESH_S * 1000) + ");}})();</script>", height=0)
