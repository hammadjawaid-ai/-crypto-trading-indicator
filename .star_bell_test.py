"""Guard test — ⭐ STAR BELL re-set (2026-11-07, user: "sort elite star fires and notifications first").
Checks: the header carries TAKE + size by window (full in 05–09 / 09–13 / 17–21, half elsewhere, half with a
👑 ONE TRADE beside it), the partner line names TAKE NOW HOT / STRONG TRIGGER / PRIME with their cells, the old
window-record and stamp lines are gone, the 13–17 ungated exception is off, the GO-timing line left the fire
card, the standalone revived bell requires a fire the phone rang, and worker_store.streams_between reads the
partner fires. No network, no Telegram.
Run: .venv\\Scripts\\python.exe .star_bell_test.py
"""
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="starbell_")
os.environ["WORKER_DB_PATH"] = os.path.join(TMP, "worker.db")
import worker_store as store   # noqa: E402
import rung_stats as rs        # noqa: E402

PASS, FAIL = 0, []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL.append(name)
        print(f"  ❌ {name} {detail}")


PKT = timezone(timedelta(hours=5))


def at(h):
    return datetime(2026, 11, 7, h, 30, tzinfo=PKT).timestamp()


plan = dict(symbol="ABCUSDT", base="ABC", side="LONG", entry=1.0, stop=0.95, tp1=1.06, tp2=1.1, tier="HIGH",
            score=84, appr=True)
print("1. header: TAKE + size by window")
for h, size in ((18, "full"), (6, "full"), (10, "full"), (22, "half"), (14, "half"), (3, "half")):
    m = rs.star_fire(plan, 60, at(h))
    head = m.split("\n")[0]
    check(f"{h:02d}:30 PKT → TAKE · {size}", f"· TAKE · {size} ·" in head, head)
m = rs.star_fire(plan, 60, at(18), size_down=True)
check("ONE TRADE beside it → half + the size-down line", "· TAKE · half ·" in m.split("\n")[0] and "ONE TRADE beside it" in m)
print("2. partner line")
m = rs.star_fire(plan, 60, at(18), partners=("takenow", "trig_strong"))
check("names TAKE NOW HOT and STRONG TRIGGER with their cells", "✅🔥 TAKE NOW HOT (84% / +0.82R (25))" in m and "💥 STRONG TRIGGER (81% / +0.62R (27))" in m)
m0 = rs.star_fire(plan, 60, at(18))
check("no partner → no partner line", "with:" not in m0)
print("3. the card is shorter: no window-record / stamp lines, rule + next kept")
check("no 'window record:' line", "window record:" not in m0)
check("no 'measured on the desk' stamp", "measured on the desk" not in m0)
check("rule line kept", "rule: enter at the buzz" in m0)
check("next line kept", m0.split("\n")[-1].startswith("next:") or "next:" in m0)
check("plan line kept", "entry `1`" in m0 and "SL `0.95`" in m0 and "TP1 `1.06`" in m0)
print("4. worker wiring")
w = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
check("13–17 ungated exception OFF", re.search(r"^STAR_UNGATED_1317 = False", w, re.M) is not None)
check("partner read feeds star_fire", "store.streams_between(" in w and "partners=_partners9, size_down=_sizedown9" in w)
gate_blk = w[w.index("_gate9 = _star_gate(_pmx, time.time(),"):w.index("_w1317 = (_star9 and STAR_UNGATED_1317")]
check("GO-timing line left the fire card", "go_timing_line" not in gate_blk)
rev = w[w.index('elif not _ew.get("buzzed"):'):w.index('_un9 = not (_ew.get("star")')]
check("standalone revived bell requires a fire the phone rang", "muted: fire never rang" in rev)
check("the revived standalone send still exists for rung fires", "_ok9, _m9x = tg.send(_go9x)" in w)
print("5. streams_between on a temp ledger")
now = time.time()
store.record_signal("takenow", {"symbol": "ABCUSDT", "side": "LONG", "hot": True}, ts=now - 1800)
store.record_signal("trig_strong", {"symbol": "ABCUSDT", "side": "long"}, ts=now - 600)
store.record_signal("one_trade", {"symbol": "ABCUSDT", "side": "LONG"}, ts=now - 3 * 3600)
store.record_signal("takenow", {"symbol": "XYZUSDT", "side": "LONG", "hot": False}, ts=now - 100)
got = store.streams_between("ABCUSDT", "LONG", now - 2 * 3600, now + 60)
check("finds takenow (hot) and trig_strong within 2h, case-insensitive side", got.get("takenow") is True and "trig_strong" in got, got)
check("one_trade 3h ago is outside the window", "one_trade" not in got)
check("a non-hot takenow reads hot=False", store.streams_between("XYZUSDT", "LONG", now - 3600, now + 60).get("takenow") is False)

print(f"\n{PASS} passed, {len(FAIL)} failed" + (f": {FAIL}" if FAIL else " — ALL PASS"))
sys.exit(1 if FAIL else 0)
