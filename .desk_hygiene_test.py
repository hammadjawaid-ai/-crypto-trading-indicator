"""Guard test — 🧹 LEDGER HYGIENE (2026-11-05). Runs the zero-risk VOID sweep on a COPY of the
4 Nov ledger backup and checks: the 120 pre-guard rows move (−3,961R), apex / one_trade / fast30 /
ignition_strong / conviction_v2 flip back to their clean positive records, the sweep is idempotent,
every summary reader excludes VOID rows, the open guard still refuses a zero-risk seat, and the
0.1–0.3% band is untouched. No network, no Telegram, the real ledger is never opened for writing.
Run: research_meta\\.venv\\Scripts\\python.exe .desk_hygiene_test.py
"""
import os
import shutil
import sqlite3
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

TMP = tempfile.mkdtemp(prefix="hyg_")
SRC = os.path.join(ROOT, ".state_backup_1104")
for ext in ("", "-wal", "-shm"):
    if os.path.exists(os.path.join(SRC, "worker.db" + ext)):
        shutil.copy2(os.path.join(SRC, "worker.db" + ext), os.path.join(TMP, "worker.db" + ext))
DB = os.path.join(TMP, "worker.db")
os.environ["WORKER_DB_PATH"] = DB
import worker_store as store      # noqa: E402
import shadow_trader              # noqa: E402

assert store.DB_PATH == DB, store.DB_PATH
PASS = 0
FAIL = []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL.append(name)
        print(f"  ❌ {name} {detail}")


def q(sql, *args):
    c = sqlite3.connect(DB)
    try:
        return c.execute(sql, args).fetchall()
    finally:
        c.close()


def rec(tier):
    return next((r for r in store.shadow_summary() if r["tier"] == tier), None)


print("1. before the sweep — the poisoned desk")
before = {t: rec(t) for t in ("apex", "one_trade", "fast30", "ignition_strong", "conviction_v2")}
check("apex desk net is negative before (−372R)", before["apex"]["net_r"] < -300, before["apex"])
check("one_trade negative before", before["one_trade"]["net_r"] < 0)
check("ignition_strong mean worse than −0.9R before",
      before["ignition_strong"]["net_r"] / before["ignition_strong"]["n"] < -0.9)
n_band = q("SELECT COUNT(*) FROM shadow_trades WHERE status='CLOSED' AND entry>0 "
           "AND abs(entry-stop0)/entry BETWEEN 0.001 AND 0.003")[0][0]
n_closed_before = q("SELECT COUNT(*) FROM shadow_trades WHERE status='CLOSED'")[0][0]

print("2. the sweep")
res = store.shadow_void_degenerate()
print("   ", res)
check("floor is 0.3%", store.MIN_RISK_FRAC == 0.003)
check("voids exactly 554 rows (120 zero-risk + 434 in the 0.1–0.3% band)", res["voided"] == 554, res)
check("their sum is −3,316R (−3,961R noise down, +645R noise up)", abs(res["net_r_voided"] + 3316.0) < 1.0, res)
check("VOID total equals the voided count", res["void_total"] == 554, res)
check("212 of them were seated after the 17 Sep 0.1% guard (the band kept inflating until 3 Nov)",
      q("SELECT COUNT(*) FROM shadow_trades WHERE status='VOID' AND opened_at > ?",
        1789651343.0)[0][0] == 212)
check("CLOSED count dropped by exactly 554",
      q("SELECT COUNT(*) FROM shadow_trades WHERE status='CLOSED'")[0][0] == n_closed_before - 554)

print("3. after — the clean records")
after = {t: rec(t) for t in before}
check("apex clean net ≈ +324R", abs(after["apex"]["net_r"] - 324.3) < 1.0, after["apex"])
check("apex n = 3830 (3886 − 56)", after["apex"]["n"] == 3830, after["apex"])
check("apex mean ≈ +0.085R", abs(after["apex"]["net_r"] / after["apex"]["n"] - 0.085) < 0.005)
check("one_trade ≈ +196R", abs(after["one_trade"]["net_r"] - 195.7) < 1.0, after["one_trade"])
check("fast30 ≈ +391R", abs(after["fast30"]["net_r"] - 390.6) < 1.0, after["fast30"])
check("ignition_strong ≈ +114R", abs(after["ignition_strong"]["net_r"] - 113.6) < 1.0)
check("conviction_v2 ≈ +223R", abs(after["conviction_v2"]["net_r"] - 222.7) < 1.0)
check("kr_strong LOSES its thin-stop winners (248 → 109R)",
      abs(rec("kr_strong")["net_r"] - 108.8) < 1.0, rec("kr_strong"))
check("best_board loses the +65R COW row (155 → 112R)",
      abs(rec("best_board")["net_r"] - 111.8) < 1.0, rec("best_board"))
check("elite_star untouched (no thin-stop rows there)",
      q("SELECT COUNT(*) FROM shadow_trades WHERE tier='elite_star' AND status='VOID'")[0][0] == 0)
check("the 0.1–0.3% band is gone from CLOSED (was 434 rows)",
      n_band == 434 and q("SELECT COUNT(*) FROM shadow_trades WHERE status='CLOSED' AND entry>0 "
                          "AND abs(entry-stop0)/entry < 0.003")[0][0] == 0)

print("4. idempotent + the summary helper")
res2 = store.shadow_void_degenerate()
check("second sweep voids 0", res2["voided"] == 0 and res2["void_total"] == 554, res2)
vs = store.shadow_void_summary()
check("shadow_void_summary = 554 / −3,316R", vs["n"] == 554 and abs(vs["net_r"] + 3316.0) < 1.0, vs)

print("5. every reader excludes VOID")
rn = store.shadow_recent_net("apex", days=100000)
check("shadow_recent_net counts only CLOSED (3830)", rn["n"] == 3830, rn)
src = open(os.path.join(ROOT, "worker_store.py"), encoding="utf-8").read()
check("no `status != 'OPEN'` reader left in worker_store", "!= 'OPEN'" not in src)
hb = store.heat_bands()
n_heat = q("SELECT COUNT(*) FROM shadow_trades WHERE status='CLOSED' AND heat IS NOT NULL "
           "AND pnl_r IS NOT NULL")[0][0]
check("heat_bands sums to the CLOSED heat rows", sum(b["n"] for b in hb) == n_heat, (sum(b["n"] for b in hb), n_heat))
cb = store.conf_bands()
n_conf = q("SELECT COUNT(*) FROM shadow_trades WHERE status='CLOSED' AND conf IS NOT NULL "
           "AND pnl_r IS NOT NULL")[0][0]
n_cb_all = sum(b["n"] for b in cb if b["tier"] == "ALL")   # each trade sits under its tier AND "ALL"
check("conf_bands (ALL row) sums to the CLOSED conf rows", n_cb_all == n_conf, (n_cb_all, n_conf))
closed_all = store.shadow_closed_all(limit=10 ** 6)
check("shadow_closed_all carries no VOID row",
      len(closed_all) == q("SELECT COUNT(*) FROM shadow_trades WHERE status='CLOSED'")[0][0])
tr = next(r for r in shadow_trader.tier_records() if r["tier"] == "apex")
check("tier_records apex net positive, n 3830", tr["net_r"] > 300 and tr["n"] == 3830, tr)
check("no VOID row counted as open anywhere",
      sum(int(r["open_n"] or 0) for r in store.shadow_summary())
      == q("SELECT COUNT(*) FROM shadow_trades WHERE status='OPEN'")[0][0])
check("manage() walks OPEN rows only (VOID never re-managed)",
      all(t["status"] == "OPEN" for t in store.shadow_open_trades()))

print("5b. the sweep runs where Render actually starts the worker")
wsrc = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
lsrc = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
check("launch.py loops cycle() and never calls agent_worker.main()",
      "agent_worker.cycle()" in lsrc and "agent_worker.main()" not in lsrc)
_cyc = wsrc[wsrc.index("def cycle() -> None:"):wsrc.index("def cycle() -> None:") + 2500]
check("the sweep sits at the top of cycle(), once per process",
      "store.shadow_void_degenerate()" in _cyc and "_HYGIENE_DONE" in _cyc)
_main = wsrc[wsrc.index("def main() -> None:"):]
check("main() no longer owns the sweep", "shadow_void_degenerate" not in _main)
check("exactly one sweep call in the worker", wsrc.count("store.shadow_void_degenerate()") == 1)

print("6. the open guard refuses thin-stop seats at the 0.3% floor")
ok = shadow_trader.open_from_signal("apex", {"symbol": "XTZUSDT", "side": "LONG", "stop": 0.26318,
                                             "tp1": 0.28, "tp2": 0.30, "entry": 0.2632}, 0.2632)
check("stop 0.008% from entry → refused", ok is False)
ok25 = shadow_trader.open_from_signal("apex", {"symbol": "COWUSDT", "side": "LONG", "stop": 0.1602,
                                               "tp1": 0.17, "tp2": 0.18, "entry": 0.1606}, 0.1606)
check("stop 0.25% from entry (the COW +65R shape) → refused now", ok25 is False)
ok2 = shadow_trader.open_from_signal("hygiene_probe", {"symbol": "XTZUSDT", "side": "LONG",
                                                      "stop": 0.255, "tp1": 0.28, "tp2": 0.30,
                                                      "entry": 0.2632}, 0.2632)
check("stop 3.1% from entry → seated (sanity)", ok2 is True and store.shadow_has_open("hygiene_probe", "XTZUSDT"))

print(f"\n{PASS} passed, {len(FAIL)} failed" + (f": {FAIL}" if FAIL else " — ALL PASS"))
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
