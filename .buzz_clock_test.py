"""BUZZ CLOCK tests — fixture DB cells, verdict rules, markdown safety,
fail-soft, wiring, and a live render off the 09-28 backup."""
import calendar
import io
import os
import sqlite3
import sys
import tempfile
import zipfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, "F:/Trading Indicator")
import buzz_clock as bc

fails = []
tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "t.db")
c = sqlite3.connect(db)
c.execute("CREATE TABLE shadow_trades (tier TEXT, symbol TEXT, side TEXT, "
          "entry REAL, stop0 REAL, pnl_r REAL, opened_at REAL, status TEXT)")


def add(tier, side, pkt_hour, rs, day=1):
    for k, r in enumerate(rs):
        ts = calendar.timegm((2026, 9, day + k % 5, pkt_hour, 30, 0)) - bc.PK
        c.execute("INSERT INTO shadow_trades VALUES (?,?,?,?,?,?,?,?)",
                  (tier, "XUSDT", side, 100.0, 97.0, r, ts, "CLOSED"))


add("elite_star", "LONG", 19, [1.0] * 12 + [-1.0] * 6)      # 17-21: 18 trades, 67%, +0.33
add("elite_star", "LONG", 22, [-1.0] * 11 + [1.0] * 2)      # 22:00 hour: 13 trades, 15%, -0.69
add("elite_star", "SHORT", 10, [-1.0] * 10 + [0.5] * 6)     # 09-13: 16 trades, 38%, -0.44
add("elite_conv", "LONG", 14, [0.2, -0.1, 0.1, 0.05] * 4)   # 13-17: 16 trades, 75%, +0.06 -> flat
add("elite_conv", "SHORT", 6, [1.0] * 5)                    # 05-09: 5 trades -> thin
# noise rows that must be ignored: tiny stop, |R|>5, open
c.execute("INSERT INTO shadow_trades VALUES ('elite_star','Y','LONG',100,99.95,80,?, 'CLOSED')",
          (calendar.timegm((2026, 9, 3, 19, 0, 0)) - bc.PK,))
c.execute("INSERT INTO shadow_trades VALUES ('elite_star','Y','LONG',100,97,-9,?, 'CLOSED')",
          (calendar.timegm((2026, 9, 3, 19, 0, 0)) - bc.PK,))
c.execute("INSERT INTO shadow_trades VALUES ('elite_star','Y','LONG',100,97,NULL,?, 'OPEN')",
          (calendar.timegm((2026, 9, 3, 19, 0, 0)) - bc.PK,))
c.commit(); c.close()


def at(pkt_h, pkt_m=15):
    return calendar.timegm((2026, 9, 20, pkt_h, pkt_m, 0)) - bc.PK


cases = [
    ("elite_star", "LONG", 20, ["🟢", "17–21 window: 67% win", "+0.33R", "18 star longs", "enter at the buzz"]),
    ("elite_star", "LONG", 22, ["21–01 PKT window", "⚠️ 22:00 itself: 15% win · −0.69R (13)"]),
    ("elite_star", "SHORT", 11, ["🔴", "09–13 window: 38% win", "−0.44R", "16 star shorts", "skip or half size"]),
    ("elite_conv", "LONG", 15, ["🟡", "13–17 window: 75% win", "+0.06R", "flat here"]),
    ("elite_conv", "SHORT", 7, ["🟡 not enough data for conviction shorts in the 05–09 PKT window yet (5 trades)"]),
]
for tier, side, h, needs in cases:
    bc._CACHE.clear()
    line = bc.tagline(tier, side, now=at(h), db_path=db)
    if not line.startswith(f"🕐 {h:02d}:15 PKT · {side} · "):
        fails.append(f"{tier}/{side}@{h}: bad head -> {line[:40]}")
    for nd in needs:
        if nd not in line:
            fails.append(f"{tier}/{side}@{h}: missing '{nd}' in: {line}")
    if any(ch in line for ch in "*_`[]"):
        fails.append(f"markdown-unsafe char in: {line}")
# the 22:00 star case must NOT carry a window verdict from the 21-01 cell (13 trades < 15 -> thin)
bc._CACHE.clear()
ln = bc.tagline("elite_star", "LONG", now=at(22), db_path=db)
if "not enough data" not in ln:
    fails.append(f"21-01 window with 13 trades should be thin: {ln}")
# noise rows ignored: the 17-21 star long cell stays at 18 trades
bc._CACHE.clear()
if bc.stats("elite_star", now=at(20), db_path=db)[("LONG", "17–21")][0] != 18:
    fails.append("tiny-stop / |R|>5 / OPEN rows leaked into the stats")
# cache: a second call inside TTL returns the same object without re-reading
s1 = bc.stats("elite_star", now=at(20), db_path=db)
s2 = bc.stats("elite_star", now=at(20) + 60, db_path=db)
if s1 is not s2:
    fails.append("stats not cached inside TTL")
# fail-soft: missing DB -> ""
bc._CACHE.clear()
if bc.tagline("elite_star", "LONG", now=at(20), db_path=os.path.join(tmp, "nope.db")) != "":
    fails.append("missing DB should yield an empty tagline")
if bc.tagline("elite_star", "FLAT", now=at(20), db_path=db) != "" or bc.tagline("apex", "LONG", now=at(20), db_path=db) != "":
    fails.append("unsupported side/tier should yield an empty tagline")
# wiring: the elite send path appends the tagline before tg.send(_msg9)
src = open("F:/Trading Indicator/agent_worker.py", encoding="utf-8").read()
i = src.find("_ck9 = buzz_clock.tagline(")
j = src.find("ok, _m9 = tg.send(_msg9)")
if not (0 < i < j) or "import buzz_clock" not in src:
    fails.append("tagline not wired before the elite send")
if src.count("_ck9 = buzz_clock.tagline(") != 1:
    fails.append("tagline should be appended exactly once")
# live render off the 09-28 backup (not asserted — printed for the eye)
try:
    with zipfile.ZipFile("C:/Users/hammad.jawaid/Downloads/state-backup-20260928-1251.zip") as z:
        z.extract("worker.db", tmp)
    live = os.path.join(tmp, "worker.db")
    print("LIVE RENDER (09-28 desk record):")
    for tier, side, h in (("elite_star", "LONG", 20), ("elite_star", "SHORT", 19), ("elite_star", "LONG", 22),
                          ("elite_star", "SHORT", 10), ("elite_conv", "LONG", 14), ("elite_conv", "SHORT", 15),
                          ("elite_conv", "SHORT", 19), ("elite_star", "LONG", 3)):
        bc._CACHE.clear()
        print("  " + bc.tagline(tier, side, now=at(h, 40), db_path=live))
except Exception as exc:
    print("live render skipped:", exc)
print("\nBUZZ CLOCK:", "ALL PASS" if not fails else "FAILS:")
for f in fails:
    print("  x", f)
