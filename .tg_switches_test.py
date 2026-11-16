"""Guard for 🔔 Telegram Bells (2026-11-17): the registry points at real worker flags, a flip round-trips through the
state file and is applied to the worker module, the records come from clean desk closes (the gated star from the
bell's own stamp), and the page / worker wiring.
Run: .venv\Scripts\python.exe .tg_switches_test.py"""
import io
import os
import sqlite3
import sys
import tempfile
import types

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import tg_switches as ts  # noqa: E402

fails = []
d = ts.code_defaults()
if set(d) != set(ts.FLAGS) or len(ts.FLAGS) != len(set(ts.FLAGS)):
    fails.append(f"every registry flag must be a module-level True/False in agent_worker.py: missing {sorted(set(ts.FLAGS) - set(d))}")
tmp = tempfile.mkdtemp(prefix="tgsw_")
ts._state_dir = lambda: tmp
if ts.overrides() != {}:
    fails.append("no file means no overrides")
if ts.set_switch("NOT_A_FLAG", False) or ts.set_switch("TG_GATES", False):
    fails.append("only registry flags can be flipped")
if not ts.set_switch("TG_STAR_PRIME", False) or not ts.set_switch("TG_ARRIVAL_T1", True) or ts.overrides() != {"TG_STAR_PRIME": False, "TG_ARRIVAL_T1": True}:
    fails.append(f"flip round trip: {ts.overrides()}")
mod = types.SimpleNamespace(TG_STAR_PRIME=True, TG_ARRIVAL_T1=False, TG_PRIME_TRIG=True)
ch = ts.apply(mod)
if ch != {"TG_STAR_PRIME": False, "TG_ARRIVAL_T1": True} or mod.TG_STAR_PRIME or not mod.TG_ARRIVAL_T1 or not mod.TG_PRIME_TRIG or ts.apply(mod) != {}:
    fails.append(f"apply must set only the flipped flags, once: {ch}")
st = {r["flag"]: r for r in ts.status() if r["flag"]}
if st["TG_STAR_PRIME"]["on"] is not False or not st["TG_STAR_PRIME"]["set_here"] or st["TG_PRIME_TRIG"]["on"] != d["TG_PRIME_TRIG"] or st["TG_PRIME_TRIG"]["set_here"]:
    fails.append("status = the flip when there is one, the code's own setting otherwise")
nos = [r for r in ts.status() if r["flag"] is None]
if len(nos) != 2 or any(r["on"] is not None for r in nos) or {r["tier"]: r["fixed"] for r in nos} != ts.FIXED:
    fails.append("a bell without a switch reports what the code does with it (rings or silent)")
if not {"elite_confirm", "go_revived", "elite_star", "trig_strong"} <= {r["tier"] for r in ts.status()}:
    fails.append("the four demo streams are on the list")
con = sqlite3.connect(":memory:")
con.execute("create table shadow_trades (tier, symbol, side, opened_at, closed_at, pnl_r, status)")
con.execute("create table signals (ts, stream, symbol, side, extra)")
NOW = 2_000_000_000.0
rows = [("star_prime", "A", "LONG", NOW - 30 * 86400, NOW - 29 * 86400, 1.0, "CLOSED"), ("star_prime", "B", "LONG", NOW - 3 * 86400, NOW - 2 * 86400, -1.0, "CLOSED"),
        ("star_prime", "C", "LONG", NOW - 3 * 86400, NOW - 2 * 86400, 5.0, "VOID"), ("star_prime", "D", "LONG", NOW - 3600, None, None, "OPEN"),
        ("tok:star_prime", "T", "SHORT", NOW - 3 * 86400, NOW - 2 * 86400, 0.5, "CLOSED"),
        ("elite_star", "G1", "LONG", NOW - 5 * 86400, NOW - 4 * 86400, 1.5, "CLOSED"), ("elite_star", "G2", "SHORT", NOW - 5 * 86400, NOW - 4 * 86400, -1.0, "CLOSED"),
        ("elite_star", "M1", "LONG", NOW - 5 * 86400, NOW - 4 * 86400, -1.0, "CLOSED"), ("tok:elite_star", "TG", "SHORT", NOW - 5 * 86400, NOW - 4 * 86400, 0.7, "CLOSED")]
con.executemany("insert into shadow_trades values (?,?,?,?,?,?,?)", rows)
con.executemany("insert into signals values (?,?,?,?,?)", [
    (NOW - 5 * 86400 + 60, "elite_star", "G1", "LONG", '{"gate": "pass"}'), (NOW - 5 * 86400 - 60, "elite_star", "G2", "SHORT", '{"gate": "1317-pass"}'),
    (NOW - 5 * 86400, "elite_star", "M1", "LONG", '{"gate": "muted"}'), (NOW - 5 * 86400, "elite_star", "TG", "SHORT", '{"gate": "pass"}'),
    (NOW - 9 * 86400, "elite_star", "M1", "LONG", '{"gate": "pass"}')])
rec = ts.records(con, NOW)
sp, gs = rec["star_prime"], rec["elite_star:gated"]
if (sp["all"]["n"], sp["all"]["win"], sp["all"]["r"]) != (2, 0.5, 0.0) or sp["recent"]["n"] != 1 or sp["recent"]["win"] != 0.0 or sp["tok"]["n"] != 1 \
        or sp["tok_recent"]["n"] != 1 or rec["elite_star:gated"]["tok_recent"]["n"] != 1:
    fails.append(f"records count clean closes only, recent = last 14 days by close, tokenized apart: {sp}")
if (gs["all"]["n"], gs["all"]["win"]) != (2, 0.5) or abs(gs["all"]["r"] - 0.25) > 1e-9 or gs["tok"]["n"] != 1:
    fails.append(f"the gated star is the star tier cut to the bell's own pass stamp within 30 minutes: {gs}")
if rec["star_apexv2"]["all"]["n"] != 0 or rec["star_apexv2"]["all"]["win"] is not None:
    fails.append("an empty tier reads as no trades")
A = io.open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
W = io.open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
P = io.open(os.path.join(ROOT, "tg_bells_page.py"), encoding="utf-8").read()
i_sec, i_hdr = A.index('if active_section == "🔔 Telegram Bells":'), A.index("# Header — global market sentiment")
if A.count('"🔔 Telegram Bells",') != 1 or not i_sec < i_hdr or "_tgb_page.render(admin=bool(_mig_token and _qp.get(\"admin\") == _mig_token))\n    st.stop()" not in A[i_sec:i_sec + 260]:
    fails.append("the section is on the menu once, drawn before the shared header, admin from the site's own check, then stops")
i_c, i_h, i_m = W.index("def cycle() -> None:"), W.index("tg_switches.apply(sys.modules[__name__])"), W.index("def main() -> None:")
if not i_c < i_h < i_m or "except Exception as _tgsw_exc:" not in W[i_h:i_h + 400]:
    fails.append("the worker applies the switches inside cycle(), wrapped so an error cannot stop a cycle")
if 'if admin and r["flag"]:' not in P or "import agent_worker" in P or "scan_market" in P:
    fails.append("switches only with the admin link; the page never imports the worker or the scanner")
print("\n".join("FAIL: " + f for f in fails) if fails else "Telegram Bells guard: all checks passed")
sys.exit(1 if fails else 0)
