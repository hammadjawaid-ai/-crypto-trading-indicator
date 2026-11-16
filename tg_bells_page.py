"""🔔 Telegram Bells — the page (user 2026-11-17: "for every telegram streams we have show me the wn rates so I can
see or mute from my mobile phone"). Built for a phone: one card per bell with its record, and, when the page is
opened with the admin link, a switch on each bell that has one. Light by design: two ledger reads cached five
minutes and nothing from the scanner; app.py draws it before its shared header and then stops."""
from __future__ import annotations

import html
import time

import streamlit as st

import tg_switches as ts

SECTION = "🔔 Telegram Bells"


@st.cache_data(ttl=300, show_spinner=False)
def _records() -> dict:
    import worker_store
    con = worker_store._open()
    try:
        return ts.records(con)
    finally:
        con.close()


def _rec(c: dict | None) -> str:
    if not c or not c.get("n"):
        return "<span style='opacity:.5'>no closed trades</span>"
    col = "#34c26b" if c["r"] > 0 else "#ff6b6b" if c["r"] < 0 else "inherit"
    return f"<b>{c['win'] * 100:.0f}%</b> · <span style='color:{col}'>{c['r']:+.2f}R</span> · {c['n']}"


def render(admin: bool = False) -> None:
    st.markdown("<div style='font-size:1.7rem;font-weight:800;letter-spacing:-.02em'>🔔 Telegram Bells</div>"
                "<div style='opacity:.7;font-size:.88rem;margin:2px 0 10px'>Every stream that can ring the phone, and the streams the demo trades "
                "(🎮), each with its record on crypto and on tokenized stocks. Win rate · average result per trade in R · closed trades.</div>",
                unsafe_allow_html=True)
    st.caption("A win is a trade that closed above zero. The desk's R runs about 0.11 to 0.16R generous (10 Nov audit), so read "
               "+0.1R as roughly break-even. Small counts are noise: under about 30 trades a win rate says little.")
    try:
        recs = _records()
    except Exception as exc:
        recs = {}
        st.warning(f"The desk ledger could not be read: {exc}")
    rows = ts.status()
    if admin:
        st.caption("Switches take effect at the worker's next cycle, a few minutes at most. A muted bell keeps recording; only the phone goes quiet.")
    else:
        st.caption("Open this page with the admin link to switch bells on and off.")
    for r in rows:
        c = recs.get(r["tier"]) if r["tier"] else None
        chip = (("<span style='background:#1f9d55;color:#fff;border-radius:999px;padding:2px 9px;font-size:.72rem;font-weight:700'>RINGING · no switch</span>" if r.get("fixed")
                 else "<span style='background:#5b6472;color:#fff;border-radius:999px;padding:2px 9px;font-size:.72rem;font-weight:700'>SILENT · no switch</span>") if r["on"] is None
                else "<span style='background:#1f9d55;color:#fff;border-radius:999px;padding:2px 9px;font-size:.72rem;font-weight:700'>RINGING</span>" if r["on"]
                else "<span style='background:#b02a2a;color:#fff;border-radius:999px;padding:2px 9px;font-size:.72rem;font-weight:700'>MUTED</span>")
        body = ("<table style='font-size:.84rem;line-height:1.6;border-collapse:collapse;width:100%;margin-top:4px'>"
                "<tr style='opacity:.6;font-size:.74rem'><td></td><td>All history</td><td>Last 14 days</td></tr>"
                f"<tr><td style='padding-right:10px'>Crypto</td><td>{_rec(c['all'])}</td><td>{_rec(c['recent'])}</td></tr>"
                f"<tr><td style='padding-right:10px'>Stocks</td><td>{_rec(c['tok'])}</td><td>{_rec(c.get('tok_recent'))}</td></tr></table>" if c
                else "<div style='font-size:.86rem;opacity:.6'>no desk record of its own</div>")
        note = f"<div style='font-size:.76rem;opacity:.6'>{html.escape(r['note'])}</div>" if r["note"] else ""
        box = st.container(border=True)
        box.markdown(f"<div style='font-weight:700;font-size:1rem'>{html.escape(r['label'])} &nbsp;{chip}</div>{note}{body}", unsafe_allow_html=True)
        if admin and r["flag"]:
            new = box.toggle("Ring on the phone", value=bool(r["on"]), key=f"tgsw_{r['flag']}")
            if new != bool(r["on"]):
                if ts.set_switch(r["flag"], new):
                    st.rerun()
                else:
                    box.error("Could not save the switch.")
    st.caption(f"Updated {time.strftime('%H:%M:%S', time.gmtime())} UTC · records refresh every five minutes.")
