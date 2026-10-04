"""Before/after timing of one Paper Trader load against the Sep 28 state:
run 1 = cold (warmer thread starts with the app), then wait for the warmer's first
sweep, run 2 = warm. Prints both totals and the remaining cost centres of run 2.
Run: & .venv\\Scripts\\python.exe .pt_speed_check.py"""
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
S = r"C:\Users\HAMMAD~1.JAW\AppData\Local\Temp\claude\F--Trading-Indicator\761b8a7a-ac27-4b70-b7c6-e365893054c0\scratchpad"
STATE = os.path.join(S, "state0928")
os.environ["STATE_DIR"] = STATE
os.chdir(r"F:\Trading Indicator")
WARM_FILE = os.path.join(STATE, ".app_warm.json")
try:
    os.remove(WARM_FILE)
except OSError:
    pass
# make the worker scan look fresh the way it is on Render (the backup's copy is 6 days old)
LS = os.path.join(STATE, ".last_scan.json")
try:
    ob = json.load(open(LS, encoding="utf-8"))
    ob["ts"] = time.time() - 9 * 60
    json.dump(ob, open(LS, "w", encoding="utf-8"))
    print("worker scan file: ts set to 9 min ago, scan_n", ob.get("scan_n"), "picks", len(ob.get("picks") or []))
except Exception as exc:
    print("no worker scan file to freshen:", exc)

import streamlit as st
from streamlit.testing.v1 import AppTest

marks = []


def _wrap(name):
    f = getattr(st, name)

    def g(*a, **k):
        lab = (str(a[0]) if a else "").replace("\n", " ")[:80]
        marks.append((time.perf_counter(), name, lab))
        return f(*a, **k)
    return g


for _n in ("subheader", "markdown", "expander", "caption"):
    setattr(st, _n, _wrap(_n))


def load(tag):
    marks.clear()
    at = AppTest.from_file("app.py", default_timeout=2400)
    at.query_params["section"] = "\U0001F9EA Paper Trader"
    t0 = time.perf_counter()
    at.run()
    t1 = time.perf_counter()
    rows, prev_t, prev_lab = [], t0, "(module top)"
    for t, name, lab in marks:
        rows.append((t - prev_t, prev_lab))
        prev_t, prev_lab = t, f"{name}: {lab}"
    rows.append((t1 - prev_t, prev_lab))
    print(f"\n[{tag}] TOTAL {t1 - t0:.1f}s · exceptions {len(at.exception)}")
    for e in at.exception[:3]:
        print("   EXC:", str(getattr(e, 'value', e))[:160])
    for d, lab in sorted(rows, key=lambda r: -r[0])[:8]:
        if d >= 2:
            print(f"   {d:6.1f}s  {lab}")
    return t1 - t0


c = load("run 1, cold, warmer starting")
# wait for the warmer's first sweep (it started with run 1 and runs in this process)
t_wait = time.time()
while time.time() - t_wait < 1500:
    try:
        stt = json.load(open(WARM_FILE, encoding="utf-8"))
        if stt.get("last_sweep"):
            print(f"\nwarmer: first sweep done in {stt.get('sweep_s')}s · jobs {stt.get('jobs')} · errors {stt.get('errors')}")
            break
    except Exception:
        pass
    time.sleep(10)
else:
    print("warmer never reported a sweep")
w = load("run 2, warm")
print(f"\nCOLD {c:.0f}s -> WARM {w:.0f}s")
