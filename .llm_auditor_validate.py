"""🔬 AUDITOR VALIDATION — can the check-suite catch the defects we
actually lived through, without crying wolf?

The proposed nightly auditor is deterministic queries + a model-written
brief. The queries are the safety-critical part, so THEY get validated,
retrospectively, against this week's four REAL defects:

  D1  eagle `_b3` NameError — stream wired + parents firing, yet ZERO
      records ever (5 days silent)
  D2  `_pw_mult` NameError — buzzes SENT (alerts_sent rows) but
      record_signal silently failing (no signals rows)
  D3  BEST ZONE greens-gate mute — tier 14d form crossed below zero,
      stream fell off the phone with no notice
  D4  elite_conv missing desk tier — signals recorded for days, zero
      shadow trades ever opened

Each defect becomes a synthetic fixture (schema-identical temp DB, rows
arranged exactly as the defect arranged them). PASS = the check fires
on its fixture AND stays quiet on a healthy fixture. Then the whole
suite runs against the real (stale, July) .worker.db to observe
false-positive behaviour on real data — where the only correct finding
is "the worker is down", since that copy stopped on Jul 11.
"""
import io
import os
import sqlite3
import sys
import tempfile
import time

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

SCHEMA = """
CREATE TABLE signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL, stream TEXT, symbol TEXT, base TEXT, side TEXT,
  tier TEXT, score REAL, conviction REAL, hot INTEGER, atr_pct REAL,
  entry REAL, stop REAL, tp1 REAL, tp2 REAL, extra TEXT
);
CREATE TABLE alerts_sent (
  alert_id TEXT PRIMARY KEY, last_ts REAL, count INTEGER
);
CREATE TABLE shadow_trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tier TEXT, symbol TEXT, side TEXT,
  entry REAL, stop REAL, stop0 REAL, tp1 REAL, tp2 REAL,
  peak REAL, be_set INTEGER DEFAULT 0, tp1_hit INTEGER DEFAULT 0,
  opened_at REAL, status TEXT DEFAULT 'OPEN',
  exit_px REAL, exit_reason TEXT, closed_at REAL, pnl_r REAL, conf REAL
);
"""

# dependent stream -> (parent stream, max days a healthy dependent can
# stay at zero records while the parent keeps firing)
DEPENDENTS = {"eagle_heat": ("elite_conv", 3.0),
              "duo85": ("apex", 7.0)}
# buzz alert_id prefix -> the stream that must record alongside it
BUZZ_RECORD = {"pwatch": "personal_watch",
               "pwatch_early": "personal_watch_early"}
# tiers that must stamp conf at open (post 2026-08-28)
CONF_TIERS = ("apex", "best_board", "one_trade", "elite_conv")


def audit(db, now):
    """The five checks. Returns list of (code, message)."""
    c = sqlite3.connect(db)
    f = []
    try:
        # C1 signals-without-desk-rows (catches D4)
        for (st,) in c.execute(
                "SELECT DISTINCT stream FROM signals WHERE ts >= ?",
                (now - 5 * 86400,)):
            n_sig = c.execute(
                "SELECT COUNT(*) FROM signals WHERE stream=? AND ts>=?",
                (st, now - 5 * 86400)).fetchone()[0]
            n_desk = c.execute(
                "SELECT COUNT(*) FROM shadow_trades WHERE tier=? "
                "AND opened_at>=?", (st, now - 5 * 86400)).fetchone()[0]
            if n_sig >= 5 and n_desk == 0:
                f.append(("C1", f"{st}: {n_sig} signals in 5d but ZERO "
                                f"desk trades — recording or wiring is "
                                f"broken"))
        # C2 worker/stream stall
        base = c.execute(
            "SELECT COUNT(*) FROM signals WHERE ts BETWEEN ? AND ?",
            (now - 8 * 86400, now - 86400)).fetchone()[0] / 7.0
        last24 = c.execute(
            "SELECT COUNT(*) FROM signals WHERE ts >= ?",
            (now - 86400,)).fetchone()[0]
        if base >= 3 and last24 == 0:
            f.append(("C2", f"worker stalled: {base:.0f} signals/day "
                            f"baseline, 0 in the last 24h"))
        # C3 conf-stamp gaps (catches D2-class record damage)
        _cols = {r[1] for r in c.execute(
            "PRAGMA table_info(shadow_trades)")}
        for t in (CONF_TIERS if "conf" in _cols else ()):
            n_null = c.execute(
                "SELECT COUNT(*) FROM shadow_trades WHERE tier=? AND "
                "opened_at>=? AND conf IS NULL",
                (t, now - 3 * 86400)).fetchone()[0]
            if n_null >= 3:
                f.append(("C3", f"{t}: {n_null} desk trades in 3d "
                                f"missing their conf stamp"))
        # C4 greens-gate flips (catches D3): 14d form now vs 24h ago
        for (t,) in c.execute("SELECT DISTINCT tier FROM shadow_trades"):
            def form(upto):
                r = c.execute(
                    "SELECT COALESCE(SUM(pnl_r),0), COUNT(*) FROM "
                    "shadow_trades WHERE tier=? AND status='CLOSED' "
                    "AND closed_at BETWEEN ? AND ?",
                    (t, upto - 14 * 86400, upto)).fetchone()
                return float(r[0]), int(r[1])
            f_now, n_now = form(now)
            f_yday, n_yday = form(now - 86400)
            if n_now >= 10 and n_yday >= 10 and f_yday > 0 >= f_now:
                f.append(("C4", f"{t}: 14d form flipped negative "
                                f"({f_yday:+.1f}R → {f_now:+.1f}R) — "
                                f"the greens gate mutes it TODAY"))
        # C5 buzz-vs-record mismatch (catches D2)
        for pref, st in BUZZ_RECORD.items():
            n_bz = c.execute(
                "SELECT COUNT(*) FROM alerts_sent WHERE alert_id LIKE ? "
                "AND last_ts >= ?", (pref + ":%", now - 3 * 86400)
            ).fetchone()[0]
            n_rec = c.execute(
                "SELECT COUNT(*) FROM signals WHERE stream=? AND ts>=?",
                (st, now - 3 * 86400)).fetchone()[0]
            if n_bz >= 2 and n_rec == 0:
                f.append(("C5", f"{st}: {n_bz} buzzes sent in 3d but "
                                f"ZERO records — the ledger is "
                                f"silently losing this stream"))
        # C6 dependent-stream silence (catches D1)
        for dep, (parent, max_d) in DEPENDENTS.items():
            n_par = c.execute(
                "SELECT COUNT(*) FROM signals WHERE stream=? AND ts>=?",
                (parent, now - max_d * 86400)).fetchone()[0]
            n_dep = c.execute(
                "SELECT COUNT(*) FROM signals WHERE stream=? AND ts>=?",
                (dep, now - max_d * 86400)).fetchone()[0]
            ever = c.execute(
                "SELECT COUNT(*) FROM signals WHERE stream=?",
                (dep,)).fetchone()[0]
            if n_par >= 10 and n_dep == 0 and ever == 0:
                f.append(("C6", f"{dep}: parent {parent} fired "
                                f"{n_par}x in {max_d:.0f}d yet {dep} "
                                f"has NEVER recorded — its code path "
                                f"is likely crashing"))
    finally:
        c.close()
    return f


def make_db(rows_sig=(), rows_desk=(), rows_alert=()):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    c = sqlite3.connect(path)
    c.executescript(SCHEMA)
    for r in rows_sig:
        c.execute("INSERT INTO signals (ts,stream,symbol) VALUES (?,?,?)",
                  r)
    for r in rows_desk:
        c.execute("INSERT INTO shadow_trades (tier,symbol,side,opened_at,"
                  "status,closed_at,pnl_r,conf) VALUES (?,?,?,?,?,?,?,?)",
                  r)
    for r in rows_alert:
        c.execute("INSERT INTO alerts_sent VALUES (?,?,?)", r)
    c.commit()
    c.close()
    return path


NOW = 1_800_000_000.0
D = 86400.0
results = []


def run_case(name, expect_codes, **kw):
    path = make_db(**kw)
    found = audit(path, NOW)
    codes = {c for c, _ in found}
    ok = codes == set(expect_codes)
    results.append((name, ok, expect_codes, sorted(codes),
                    [m for _, m in found]))
    os.unlink(path)


# healthy baseline: parents fire, dependents fire, desk rows exist,
# conf stamped, forms positive both days, buzzes match records
_h_sig = ([(NOW - i * 3600, "elite_conv", "XUSDT") for i in range(1, 40)]
          + [(NOW - i * 3600, "apex", "XUSDT") for i in range(1, 40)]
          + [(NOW - 2 * 3600, "eagle_heat", "XUSDT"),
             (NOW - 5 * 3600, "duo85", "XUSDT"),
             (NOW - 4 * 3600, "personal_watch", "ENAUSDT")])
_h_desk = ([("elite_conv", "XUSDT", "LONG", NOW - i * 3600, "CLOSED",
             NOW - i * 3600 + 1800, 0.4, 65.0) for i in range(1, 15)]
           + [("apex", "XUSDT", "LONG", NOW - i * 3600, "CLOSED",
               NOW - i * 3600 + 1800, 0.3, 85.0) for i in range(1, 15)])
_h_alert = [("pwatch:ENAUSDT", NOW - 4 * 3600, 1)]
run_case("healthy — no findings expected", [],
         rows_sig=_h_sig, rows_desk=_h_desk, rows_alert=_h_alert)

# D1 eagle: elite parents fire for days, eagle_heat never recorded
run_case("D1 eagle _b3 silence", ["C6"],
         rows_sig=[(NOW - i * 3600, "elite_conv", "XUSDT")
                   for i in range(1, 40)]
         + [(NOW - i * 3600, "apex", "XUSDT") for i in range(1, 40)]
         + [(NOW - 5 * 3600, "duo85", "XUSDT")],
         rows_desk=[("elite_conv", "XUSDT", "LONG", NOW - 9000,
                     "CLOSED", NOW - 5400, 0.2, 65.0),
                    ("apex", "XUSDT", "LONG", NOW - 9000,
                     "CLOSED", NOW - 5400, 0.2, 85.0)])

# D2 _pw_mult: buzzes sent, records silently failing
run_case("D2 _pw_mult record loss", ["C5"],
         rows_sig=[(NOW - i * 3600, "apex", "XUSDT")
                   for i in range(1, 30)]
         + [(NOW - 5 * 3600, "duo85", "X"),
            (NOW - 5 * 3600, "eagle_heat", "X")],
         rows_desk=[("apex", "XUSDT", "LONG", NOW - 9000, "CLOSED",
                     NOW - 5400, 0.2, 85.0)],
         rows_alert=[("pwatch:ENAUSDT", NOW - 5 * 3600, 2),
                     ("pwatch:ZECUSDT", NOW - 9 * 3600, 1)])

# D3 BEST form flip: +2.5R yesterday -> -0.7R today (14d window)
_d3_desk = ([("best_board", "XUSDT", "LONG", NOW - 13.5 * D, "CLOSED",
              NOW - 13 * D, 0.30, 85.0) for _ in range(11)]
            + [("best_board", "YUSDT", "LONG", NOW - 0.6 * D, "CLOSED",
                NOW - 0.5 * D, -0.36, 85.0) for _ in range(11)])
run_case("D3 BEST greens-gate flip", ["C4"],
         rows_sig=[(NOW - i * 3600, "apex", "XUSDT")
                   for i in range(1, 30)]
         + [(NOW - 5 * 3600, "duo85", "X"),
            (NOW - 5 * 3600, "eagle_heat", "X")],
         rows_desk=_d3_desk
         + [("apex", "XUSDT", "LONG", NOW - 9000, "CLOSED",
             NOW - 5400, 0.2, 85.0)])

# D4 elite_conv missing desk tier: signals for days, zero desk rows
run_case("D4 elite_conv no desk tier", ["C1", "C6"],
         rows_sig=[(NOW - i * 3600, "elite_conv", "XUSDT")
                   for i in range(1, 40)]
         + [(NOW - i * 3600, "apex", "XUSDT") for i in range(1, 30)]
         + [(NOW - 5 * 3600, "duo85", "X")],
         rows_desk=[("apex", "XUSDT", "LONG", NOW - 9000, "CLOSED",
                     NOW - 5400, 0.2, 85.0)])

print("=" * 66)
print("🔬 AUDITOR CHECK-SUITE — retrospective validation")
print("=" * 66)
n_ok = 0
for name, ok, exp, got, msgs in results:
    n_ok += 1 if ok else 0
    print(f"\n  {'✅ PASS' if ok else '❌ FAIL'}  {name}")
    print(f"        expected {exp or ['(none)']} · fired {got or ['(none)']}")
    for m in msgs:
        print(f"        → {m}")
print(f"\n  {n_ok}/{len(results)} cases correct")

print("\n" + "=" * 66)
print("🔎 same suite on the REAL (stale July) .worker.db")
print("   correct answer here = 'the worker is down', nothing else")
print("=" * 66)
c = sqlite3.connect(".worker.db")
last_ts = c.execute("SELECT MAX(ts) FROM signals").fetchone()[0]
c.close()
for label, now in (("as of its own last day", last_ts),
                   ("as of today (worker 8 weeks gone)",
                    time.time())):
    print(f"\n  [{label}]")
    fnd = audit(".worker.db", now)
    if not fnd:
        print("    (no findings)")
    for code, m in fnd:
        print(f"    {code}: {m}")
