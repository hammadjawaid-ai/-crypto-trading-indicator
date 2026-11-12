"""Guard — 🕐 window stamps on every bell (2026-11-08, user: "time stamps on every signal and buzz on
telegram … green 68%+, yellow 60–68, red below 60 … for every stream"). Checks the light law, the stamp
text, every table's shape, and that each bell formatter carries the stamp. No network, no Telegram.
Run: .venv\\Scripts\\python.exe .tg_cells_test.py
"""
import calendar
import os
import re
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="tgcells_")
os.environ["WORKER_DB_PATH"] = os.path.join(TMP, "worker.db")
import tg_cells as tc       # noqa: E402
import rung_stats as rs     # noqa: E402
import clock_cells as cc    # noqa: E402

PASS, FAIL = 0, []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL.append(name)
        print(f"  ❌ {name} {detail}")


def T(h_pkt):
    return float(calendar.timegm((2026, 11, 8, (h_pkt - 5) % 24, 0, 0)))


print("1. the light law")
for w, e in ((68, "🟢"), (75, "🟢"), (100, "🟢"), (67.9, "🟡"), (60, "🟡"), (64, "🟡"), (59.9, "🔴"), (0, "🔴"), (None, "🟡")):
    check(f"win {w} → {e}", tc.light(w) == e, tc.light(w))
print("2. windows")
for h, w in ((7, "05–09"), (11, "09–13"), (15, "13–17"), (19, "17–21"), (23, "21–01"), (3, "01–05"), (0, "21–01")):
    check(f"{h:02d}:00 PKT → {w}", tc.window_of(T(h)) == w, tc.window_of(T(h)))
print("3. tables")
for name, (tab, label, kind) in tc.TABLES.items():
    keys = {k for k, _ in tab}
    wins = {w for _, w in tab}
    ok_keys = (keys <= {"LONG", "SHORT"} if kind == "side" else keys <= {"FAST", "LATE"} if kind == "go" else keys == {None})
    check(f"{name}: keys fit its kind, windows known", ok_keys and wins <= set(tc.WINDOWS)
          and all(v is None or (len(v) == 3 and 0 <= v[0] <= 100 and v[2] >= 0) for v in tab.values()), f"{keys} {wins}")
print("4. stamps")
s = tc.stamp("elite_star", "LONG", T(11))
check("⭐ long 09–13 → 🟢 75% / +0.58R (20)", s.startswith("🕐 🟢 09–13 longs 75% / +0.58R (20)") and "⭐ gated stars" in s and tc.MEASURED in s, s)
s = tc.stamp("elite_star", "LONG", T(19))
check("⭐ long 17–21 → 🟡 62%", s.startswith("🕐 🟡 17–21 longs 62% / +0.38R (48)"), s)
s = tc.stamp("elite_star", "LONG", T(15))
check("⭐ long 13–17 → 🔴 27%", s.startswith("🕐 🔴 13–17 longs 27% / -0.51R (11)"), s)
s = tc.stamp("elite_star", "SHORT", T(3))
check("⭐ short 01–05 → no record (gate)", "01–05 shorts — no record" in s, s)
s = tc.stamp("star_apexv2", "LONG", T(19))
check("pooled table ignores the side and says thin", "17–21 both sides 100% / +0.98R (4, thin)" in s, s)
s = tc.stamp("conv_revival", "LATE", T(7))
check("revival keyed by the GO tier", s.startswith("🕐 🟢 05–09 LATE 71% / +0.26R (17)"), s)
s = tc.stamp("conv_revival", "FAST", T(7))
check("FAST revival 05–09 → 🔴 41%", s.startswith("🕐 🔴 05–09 FAST 41%"), s)
check("unknown stream → no record line", tc.stamp("nope", None, T(7)) == "🕐 🟡 05–09 — no record")
check("stamp_src maps worker keys, '' when unknown", tc.stamp_src("apex_v2_gated", "SHORT", T(19)).startswith("\n🕐 🟢 17–21 shorts 78%")
      and tc.stamp_src("news_radar", None, T(19)) == "")
check("light_of reads the same cell", tc.light_of("elite_star", "SHORT", T(19)) == "🟢" and tc.light_of("elite_star", "LONG", T(3)) == "🟡")
print("5. the bells carry it")
ew = dict(base="ABC", side="LONG", symbol="ABCUSDT", entry0=1.0, stop=0.95, tp1=1.06, tp2=1.1, oneh="LIVE", star=True, fired_at=T(19))
v = rs.verdict_text(ew, 0.37, T(20))
check("⏱ LIVE verdict: 3 lines, 🕐 17–21 longs 79% / +1.12R (19) 🟢", len(v.split("\n")) == 3 and "🕐 🟢 17–21 longs 79% / +1.12R (19)" in v and "1H LIVE stars" in v, v)
v2 = rs.verdict_text(dict(ew, oneh="DEAD"), -0.1, T(20))
check("⏱ DEAD verdict: 🕐 17–21 longs 50% 🔴", "🕐 🔴 17–21 longs 50% / -0.15R (24)" in v2 and "1H DEAD stars" in v2, v2)
ewc = dict(ew, star=False)
vc = rs.verdict_text(ewc, 0.3, T(20))
check("conviction verdict (not a star): no stamp (its bell is muted)", len(vc.split("\n")) == 2, vc)
g = rs.go_text(dict(ew, oneh="LIVE"), 0.4, 1800, 1.02, T(19) + 1800)
l4 = g.split("\n")[3]
check("GO reply 🕐 line uses the 68/60 lights: fire cell + landing", l4.startswith("🕐 ") and "landing 17–21:" in l4 and ("🟢 entered" in l4 or "🟡 entered" in l4 or "🔴 entered" in l4) and ("entry pays" in l4 or "hold only" in l4), l4)
gl = cc.go_clock_short("LONG", T(7), T(7) + 1800, "FAST", True, False)
check("GO FAST long landing 05–09: 🟢 entered 92% / +0.33R (25) — entry pays", "🟢 entered 92% / +0.33R (25) — entry pays" in gl, gl)
gl2 = cc.go_clock_short("LONG", T(19), T(19) + 1800, "FAST", True, False)
check("GO FAST long landing 17–21: 🔴 entered 59% — hold only", "🔴 entered 59% / -0.11R (41) — hold only" in gl2, gl2)
W = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
for need, lab in (('tg_cells.stamp("elite_star", _pmx.get("side"), time.time())', "⭐ star card stamp"),
                  ('_cl9 = tg_cells.light_of("elite_star", _pmx.get("side"), time.time())', "⭐ size word from the same light"),
                  ('st_line = (tg_cells.stamp("conv_revival", cls, now)', "💎 revival stamp"),
                  ('lines.append(tg_cells.stamp(_tbl, side, now))', "pair card stamp"),
                  ('PAIR_STAMP = {"star": "star_prime", "startrig": "star_trig", "startn": "star_takenow"', "pair stamp map"),
                  ('l6 = (tg_cells.stamp("prime_trig", None, now)', "💥🥇 stamp"),
                  ('+ tg_cells.stamp("apex_v2", sd, now)', "🏆💎 APEX V2 GATED stamp"),
                  ('_st = (tg_cells.stamp("apex_v2", ew.get("side"), float(ew.get("fired_at") or time.time()))', "⏱🏆 APEX V2 verdict stamp"),
                  ('+ tg_cells.stamp_src(_rg_src, _rg_side, _rg_ts)', "🏦 TP1 ping stamp"),
                  ("import tg_cells", "import")):
    check(f"worker: {lab}", need in W)
check("worker: the old star clock line is gone from the card", "clock_cells.star_line_short(" not in W)
print("6. ⚠️ against the market (2026-11-13)")
check("no read stored -> no mark (tests and a cold worker stay quiet)", tc.market_note("LONG") == "")
up = [100.0] * 49 + [101.0]
dn = [100.0] * 49 + [90.0]
check("regime from 50 completed closes: above / below with the gap", tc.regime_from_closes(up)[0] is False and tc.regime_from_closes(dn)[0] is True
      and abs(tc.regime_from_closes(dn)[1] - (90.0 / 99.8 - 1) * 100) < 1e-6 and tc.regime_from_closes([1.0] * 49) == (None, None))
tc.set_btc_regime(dn)
mn = tc.market_note("LONG")
check("BTC below -> a LONG bell carries the mark with the gap and the record", mn.startswith(chr(10) + "⚠️ *AGAINST THE MARKET* — BTC 9.8% under its 50-day average") and "34% / −0.28R (1,332" in mn, mn)
check("shorts are never marked", tc.market_note("SHORT") == "" and tc.market_note(None) == "")
check("a stale read (older than 36h) prints nothing", tc.market_note("LONG", now=tc._MKT["t"] + 37 * 3600) == "")
tc.set_btc_regime(up)
check("BTC above -> no mark", tc.market_note("LONG") == "")
tc._MKT.update(t=0.0, below=None, gap=None)
check("worker: the read refreshes every cycle and rides the five fire bells",
      'tg_cells.set_btc_regime(_bd50["close"].to_numpy(float)[:-1])' in W and W.count("tg_cells.market_note(") == 5, W.count("tg_cells.market_note("))
print(f"\n{PASS} passed, {len(FAIL)} failed" + (f": {FAIL}" if FAIL else " — ALL PASS"))
sys.exit(1 if FAIL else 0)
