"""24/7 web dashboard + scan loop in ONE always-on service.

Deploy as a Render/Railway WEB service and you get a public URL you can open
in any browser, on any device, 24/7 — showing the latest best setups, the
alerts it pushed, and the scan history. The scan loop runs in a background
thread (Telegram alerts still fire). Alert-only — it places no trades.

    gunicorn -w 1 -t 120 -b 0.0.0.0:$PORT web_dashboard:app     # production
    python web_dashboard.py                                     # local test
"""
from __future__ import annotations

import html
import os
import threading
import time
from datetime import datetime, timezone

from flask import Flask

import agent_worker
import telegram_notify as tg
import worker_store as store

app = Flask(__name__)

_started = False
_start_lock = threading.Lock()


def _loop() -> None:
    if tg.enabled():
        tg.send("🟢 *24/7 worker online* — dashboard live. Watching for "
                "✅🔥 TAKE NOW HOT and 💠 SST1 conv≥70.", silent=True)
    while True:
        try:
            agent_worker.cycle()
        except Exception as exc:
            print("loop error:", exc, flush=True)
        time.sleep(agent_worker.INTERVAL)


def _start_once() -> None:
    global _started
    with _start_lock:
        if _started:
            return
        _started = True
        threading.Thread(target=_loop, daemon=True).start()


# Start the scan loop as soon as the module is imported (gunicorn -w 1 →
# imported once in the single worker → exactly one loop).
_start_once()


def _ago(ts) -> str:
    if not ts:
        return "—"
    secs = max(0, time.time() - float(ts))
    if secs < 90:
        return f"{int(secs)}s ago"
    if secs < 5400:
        return f"{int(secs // 60)}m ago"
    if secs < 172800:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def _fmt(v, nd=6):
    try:
        return f"{float(v):g}"
    except Exception:
        return "—"


_CSS = """
*{box-sizing:border-box}body{margin:0;background:#0b0e14;color:#e6e9f0;
font-family:-apple-system,Segoe UI,Roboto,sans-serif;padding:18px}
h1{font-size:1.35rem;margin:0 0 2px}h2{font-size:1rem;margin:22px 0 8px;
color:#a78bfa}.sub{color:#8b93a7;font-size:.82rem;margin-bottom:14px}
.bar{display:flex;flex-wrap:wrap;gap:10px;margin:10px 0 4px}
.chip{background:#151a24;border:1px solid #232a38;border-radius:9px;
padding:7px 12px;font-size:.82rem}.chip b{color:#fff}
table{width:100%;border-collapse:collapse;font-size:.82rem;margin-bottom:6px}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid #1c2230}
th{color:#8b93a7;font-weight:600}tr:hover td{background:#11151d}
.long{color:#2ed47a;font-weight:700}.short{color:#ff5c5c;font-weight:700}
.hot{background:rgba(255,107,53,.18);color:#ff6b35;padding:1px 7px;
border-radius:5px;font-weight:800;font-size:.72rem}
.tn{background:#0b8a3e;color:#fff;padding:1px 7px;border-radius:5px;
font-weight:800;font-size:.72rem}.ss{background:rgba(56,189,248,.18);
color:#38bdf8;padding:1px 7px;border-radius:5px;font-weight:800;font-size:.72rem}
.muted{color:#8b93a7}.empty{color:#8b93a7;padding:10px 2px}
a{color:#38bdf8}
"""


def _side(s):
    s = (s or "").upper()
    cls = "long" if s == "LONG" else "short" if s == "SHORT" else "muted"
    return f"<span class='{cls}'>{html.escape(s)}</span>"


def _signal_row(r):
    stream = r.get("stream")
    tag = ("<span class='ss'>💠 SST1</span>" if stream == "sst1"
           else "<span class='tn'>✅ TAKE NOW</span>"
                + (" <span class='hot'>🔥 HOT</span>" if r.get("hot") else ""))
    strength = (f"{r.get('conviction'):.0f}" if stream == "sst1"
                and r.get("conviction") is not None
                else f"{r.get('tier') or ''} {r.get('score') or 0:.0f}")
    return (f"<tr><td>{_ago(r.get('ts'))}</td><td>{tag}</td>"
            f"<td><b>{html.escape(str(r.get('base') or '?'))}</b></td>"
            f"<td>{_side(r.get('side'))}</td><td class='muted'>{strength}</td>"
            f"<td>{_fmt(r.get('entry'))}</td><td>{_fmt(r.get('stop'))}</td>"
            f"<td>{_fmt(r.get('tp1'))}</td></tr>")


@app.route("/health")
def health():
    return "ok"


@app.route("/")
def home():
    st = store.stats()
    last = store.last_cycle()
    sigs = store.recent_signals(30)
    alerts = store.recent_alerts(20)
    cycles = store.recent_cycles(20)

    regime = (last or {}).get("regime", "—")
    last_ts = (last or {}).get("ts")
    tg_on = "🟢 on" if tg.enabled() else "🔴 off"

    sig_rows = "".join(_signal_row(r) for r in sigs) or (
        "<tr><td colspan='8' class='empty'>No premium setups logged yet — "
        "they're selective. The worker is scanning; this fills in when SST1 "
        "conv≥70 or a TAKE NOW 🔥 appears.</td></tr>")

    alert_rows = "".join(
        f"<tr><td>{_ago(a.get('last_ts'))}</td>"
        f"<td class='muted'>{html.escape(str(a.get('alert_id')))}</td>"
        f"<td>{a.get('count')}×</td></tr>" for a in alerts) or (
        "<tr><td colspan='3' class='empty'>No alerts pushed yet.</td></tr>")

    cyc_rows = "".join(
        f"<tr><td>{_ago(c.get('ts'))}</td>"
        f"<td class='muted'>{html.escape(str(c.get('regime')))}</td>"
        f"<td>{c.get('n_sst1')}</td><td>{c.get('n_takenow')}</td>"
        f"<td>{c.get('n_alerts')}</td></tr>" for c in cycles) or (
        "<tr><td colspan='5' class='empty'>Warming up…</td></tr>")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>24/7 Signal Worker</title><style>{_CSS}</style></head><body>
<h1>🛰️ 24/7 Signal Worker</h1>
<div class="sub">Always-on · alert-only · scans every
{agent_worker.INTERVAL // 60} min · page auto-refreshes every 60s · {now}</div>
<div class="bar">
  <div class="chip">Last scan <b>{_ago(last_ts)}</b></div>
  <div class="chip">Regime <b>{html.escape(str(regime))}</b></div>
  <div class="chip">Telegram <b>{tg_on}</b></div>
  <div class="chip">Signals logged <b>{st.get('signals')}</b></div>
  <div class="chip">Cycles <b>{st.get('cycles')}</b></div>
</div>
<h2>🏆 Latest best setups</h2>
<table><tr><th>seen</th><th>signal</th><th>coin</th><th>side</th>
<th>strength</th><th>entry</th><th>SL</th><th>TP1</th></tr>{sig_rows}</table>
<h2>🔔 Alerts pushed to your phone</h2>
<table><tr><th>last</th><th>alert</th><th>fired</th></tr>{alert_rows}</table>
<h2>📊 Scan history</h2>
<table><tr><th>when</th><th>regime</th><th>SST1≥70</th><th>TAKE NOW🔥</th>
<th>alerts</th></tr>{cyc_rows}</table>
<div class="sub" style="margin-top:18px">Alert-only — no trades are placed.
Telegram is your buzz; this page is your window. Quiet is normal — the bar is
high on purpose.</div>
</body></html>"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
