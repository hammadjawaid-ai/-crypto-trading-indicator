"""Guard test — 💯↩️ CONVICTION v2 REVERSED (2026-11-06). The mirror helper's geometry, a mirrored
seat on a fresh temp ledger walked through the desk ladder (target = the plan's old stop → TP1 lock;
the plan's old TP1 → stop), the worker hook mirrors conviction_v2 and nothing else, the page labels
the tier. No network, no Telegram, the real ledger is never opened.
Run: .venv\\Scripts\\python.exe .conv_rev_test.py
"""
import os
import re
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="crev_")
os.environ["WORKER_DB_PATH"] = os.path.join(TMP, "worker.db")
import worker_store as store      # noqa: E402
import shadow_trader as sh        # noqa: E402

PASS, FAIL = 0, []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL.append(name)
        print(f"  ❌ {name} {detail}")


print("1. mirror_signal geometry")
plan = dict(symbol="ABCUSDT", side="LONG", entry=1.0, stop=0.97, tp1=1.05, tp2=1.08, conf=72.0, heat=61.0,
            score=88.0)
m = sh.mirror_signal(plan)
check("side flips LONG → SHORT", m["side"] == "SHORT")
check("the plan's TP1 is the mirror's stop", m["stop"] == 1.05)
check("the plan's stop is the mirror's TP1", m["tp1"] == 0.97)
check("TP2 dropped", m["tp2"] == 0.0)
check("conf / heat / score carried from the fire", (m["conf"], m["heat"], m["score"]) == (72.0, 61.0, 88.0))
check("tagged mirror_of conviction_v2", m.get("mirror_of") == "conviction_v2")
check("original dict untouched", plan["side"] == "LONG" and plan["stop"] == 0.97 and plan["tp1"] == 1.05)
ms = sh.mirror_signal(dict(symbol="XYZUSDT", side="SHORT", entry=2.0, stop=2.1, tp1=1.9, tp2=1.8))
check("SHORT plan mirrors to LONG with stop 1.9 / tp1 2.1", (ms["side"], ms["stop"], ms["tp1"]) == ("LONG", 1.9, 2.1))

print("2. a mirrored seat on the desk ladder (temp ledger)")
ok = sh.open_from_signal("conviction_v2_rev", m, 1.0)
check("mirror seats (stop > entry > tp1 holds for the SHORT)", ok is True)
row = next(t for t in store.shadow_open_trades() if t["tier"] == "conviction_v2_rev")
check("seated SHORT at the live price with stop 1.05 / tp1 0.97",
      row["side"] == "SHORT" and row["entry"] == 1.0 and row["stop0"] == 1.05 and row["tp1"] == 0.97, dict(row))
check("conf stamped on the mirror row", row["conf"] == 72.0)
closed = sh.manage({"ABCUSDT": 0.97})       # price reaches the plan's OLD STOP = the mirror's target
check("old stop reached → mirror closes TP1_LOCK", len(closed) == 1 and closed[0]["reason"] == "TP1_LOCK", closed)
exp = 0.03 / 0.05 - 2 * sh.TAKER_FEE * 1.0 / 0.05
check(f"pnl ≈ {exp:+.3f}R (0.6R target minus fees)", closed and abs(closed[0]["pnl_r"] - exp) < 1e-6, closed)
m2 = sh.mirror_signal(dict(symbol="DEFUSDT", side="LONG", entry=1.0, stop=0.97, tp1=1.05, tp2=1.08))
sh.open_from_signal("conviction_v2_rev", m2, 1.0)
closed2 = sh.manage({"DEFUSDT": 1.05})      # price reaches the plan's OLD TP1 = the mirror's stop
check("old TP1 reached → mirror stopped at −1R − fees",
      len(closed2) == 1 and closed2[0]["reason"] == "STOP" and abs(closed2[0]["pnl_r"] + 1 + 2 * sh.TAKER_FEE / 0.05) < 1e-6,
      closed2)
rec = next(r for r in store.shadow_summary() if r["tier"] == "conviction_v2_rev")
check("the tier's record carries both closes", rec["n"] == 2 and rec["wins"] == 1, dict(rec))
deg = sh.mirror_signal(dict(symbol="ZZZUSDT", side="LONG", entry=1.0, stop=0.9995, tp1=1.0004, tp2=0))
check("a degenerate mirror is refused by the open guard", sh.open_from_signal("conviction_v2_rev", deg, 1.0) is False)

print("3. the worker mirrors conviction_v2 and nothing else")
src = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
check("tier (conviction_v2_rev, _conv) in the seat list", '("conviction_v2_rev", _conv)' in src)
check("exactly one mirror_signal call in the worker", src.count("shadow_trader.mirror_signal(") == 1)
check("the flip is gated on the rev tier name",
      re.search(r'if _tname == "conviction_v2_rev":\s*#[^\n]*\n\s*p = shadow_trader\.mirror_signal\(p\)', src) is not None)
_tiers_blk = src[src.index("_tiers = ("):src.index("for _tname, _sigs in _tiers:")]
check("the seat list carries exactly one mirrored tier (conviction_v2_rev)",
      _tiers_blk.count('_rev"') == 1 and '("conviction_v2_rev", _conv)' in _tiers_blk)
app = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
check("page labels the tier", '"conviction_v2_rev": "💯↩️ CONVICTION v2 REVERSED' in app)
check("no bell / demo wiring for the mirror (records only)",
      "conviction_v2_rev" not in open(os.path.join(ROOT, "demo_account.py"), encoding="utf-8").read()
      and "conviction_v2_rev" not in open(os.path.join(ROOT, "telegram_notify.py"), encoding="utf-8").read())

print(f"\n{PASS} passed, {len(FAIL)} failed" + (f": {FAIL}" if FAIL else " — ALL PASS"))
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
