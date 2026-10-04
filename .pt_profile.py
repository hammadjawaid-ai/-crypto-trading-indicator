"""Profile one load of the Paper Trader page in-process (Streamlit AppTest) against the
Sep 28 state backup, with a per-board timeline (time between consecutive headers /
expanders) and a cProfile top list. Read-only: nothing in the repo state is touched.
Run: & .venv\\Scripts\\python.exe .pt_profile.py [section]"""
import cProfile
import io
import os
import pstats
import sys
import time
import zipfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
S = r"C:\Users\HAMMAD~1.JAW\AppData\Local\Temp\claude\F--Trading-Indicator\761b8a7a-ac27-4b70-b7c6-e365893054c0\scratchpad"
STATE = os.path.join(S, "state0928")
if not os.path.isdir(STATE):
    os.makedirs(STATE, exist_ok=True)
    with zipfile.ZipFile(r"C:\Users\hammad.jawaid\Downloads\state-backup-20260928-1251.zip") as z:
        z.extractall(STATE)
    print("state extracted:", len(os.listdir(STATE)), "files")
os.environ["STATE_DIR"] = STATE
os.chdir(r"F:\Trading Indicator")
SECTION = sys.argv[1] if len(sys.argv) > 1 else "\U0001F9EA Paper Trader"

import streamlit as st
from streamlit.testing.v1 import AppTest

marks = []
T0 = time.perf_counter()


def _wrap(name):
    f = getattr(st, name)

    def g(*a, **k):
        lab = str(a[0]) if a else str(k.get("label") or k.get("body") or "")
        lab = lab.replace("\n", " ")[:90]
        marks.append((time.perf_counter(), name, lab))
        return f(*a, **k)
    return g


for _n in ("subheader", "header", "markdown", "expander", "caption", "dataframe", "plotly_chart", "metric"):
    setattr(st, _n, _wrap(_n))

at = AppTest.from_file("app.py", default_timeout=2400)
try:
    at.query_params["section"] = SECTION
except Exception as exc:
    print("query_params not settable:", exc)
pr = cProfile.Profile()
t0 = time.perf_counter()
pr.enable()
try:
    at.run()
finally:
    pr.disable()
t1 = time.perf_counter()
print(f"\nTOTAL script run: {t1 - t0:.1f}s  · exceptions: {len(at.exception)}")
for e in at.exception[:5]:
    print("  EXC:", str(e.value)[:200] if hasattr(e, "value") else str(e)[:200])
# timeline: cost attributed to the header that PRECEDES the gap
rows = []
prev_t, prev_lab = t0, "(module top: prices, scans before the section)"
for t, name, lab in marks:
    rows.append((t - prev_t, prev_lab))
    prev_t, prev_lab = t, f"{name}: {lab}"
rows.append((t1 - prev_t, prev_lab))
print("\n=== TOP 30 COST CENTRES (seconds until the next header rendered) ===")
for d, lab in sorted(rows, key=lambda r: -r[0])[:30]:
    if d >= 0.3:
        print(f"{d:7.1f}s  {lab}")
print("\n=== TIMELINE (first 60 marks over 1s) ===")
acc = 0.0
for d, lab in rows:
    acc += d
    if d >= 1.0:
        print(f"t={acc:6.1f}s  +{d:5.1f}s  {lab}")
print("\n=== cProfile: top 35 by cumulative time (our modules + I/O) ===")
sio = io.StringIO()
ps = pstats.Stats(pr, stream=sio).sort_stats("cumulative")
ps.print_stats(r"app\.py|worker_store|shadow_trader|binance_client|paper_bot|demo_account|best_board|sqlite3|requests|urllib3|news_radar|btc2h|buzz_clock|shock_watch|json", 35)
out = sio.getvalue()
print("\n".join(out.splitlines()[:70]))
print("\n=== cProfile: top 25 by own time ===")
sio = io.StringIO()
pstats.Stats(pr, stream=sio).sort_stats("tottime").print_stats(25)
print("\n".join(sio.getvalue().splitlines()[:45]))
