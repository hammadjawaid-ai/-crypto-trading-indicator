"""Guard test — 2026-11-07 bell re-set part 2 + Paper Trader page (user: "lets build it and deploy").
Checks: the three ⭐ pair kinds and their partner streams, the partner-time lookup on a temp ledger, every
card ≤ its line budget (pair 4, conviction revival 4, verdict 2, GO 3, Kronos 1), the switches (GO LIVE off,
90% ping off, pair bells on), star revival = thread reply, the page's hidden boards / bench toggle / star
pairs board / tier labels. No network, no Telegram.
Run: .venv\\Scripts\\python.exe .bells2_test.py
"""
import os
import re
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="bells2_")
os.environ["WORKER_DB_PATH"] = os.path.join(TMP, "worker.db")
import worker_store as store   # noqa: E402
import rung_stats as rs        # noqa: E402
import clock_cells as cc       # noqa: E402

PASS, FAIL = 0, []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL.append(name)
        print(f"  ❌ {name} {detail}")


W = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
A = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
now = time.time()

print("1. switches and pair kinds (source)")
for name, val in (("TG_GO_LIVE", "False"), ("TG_NEAR90", "False"), ("TG_STAR_TRIG", "True"),
                  ("TG_STAR_TAKENOW", "True"), ("TG_STAR_APEXV2", "True"), ("STAR_UNGATED_1317", "False")):
    check(f"{name} = {val}", re.search(rf"^{name} = {val}\b", W, re.M) is not None)
check("PAIR_KINDS has the three star pairs",
      all(f'"{k}": dict(tier="{t}"' in W for k, t in (("startrig", "star_trig"), ("startn", "star_takenow"), ("starv2", "star_apexv2"))))
check("PAIR_PARTNER maps them to trig_strong / takenow / apex_v2",
      '"startrig": "trig_strong", "startn": "takenow", "starv2": "apex_v2"' in W)
check("the pairing pass lists the three new kinds",
      all(f'("{k}", "elite_star", "{t}", None, {s})' in W for k, t, s in
          (("startrig", "star_trig", "TG_STAR_TRIG"), ("startn", "star_takenow", "TG_STAR_TAKENOW"), ("starv2", "star_apexv2", "TG_STAR_APEXV2"))))
check("the pass uses the kind-aware partner lookup", "_pts_pp = _pair_partner_ts(_kind, _sym_pp, _sd_pp, _ts_pp)" in W
      and 'store.seen_between(\n                            "prime", _sym_pp' not in W)
check("the pass sends the concise pair card", "_fmt_pair_card(\n                                _kind, _sig_pp," in W)
check("90% ping gated on TG_NEAR90", "if TG_NEAR90 and _rg_n90 and store.should_alert(" in W)
check("star revival = thread reply under its own bell",
      'if _ew.get("oneh") == "DEAD" and _ew.get("star"):' in W and '"sent-thread (revived)"' in W)
check("GO LATE after a LIVE verdict replies in the thread again (2026-11-07)", '"skipped (LATE elite GO reply)"' not in W)
check("a star bell marks only the star watch entry (no duplicate GO / verdict replies)", 'and bool(_ewb.get("star")) == bool(_star9)):' in W)
check("conviction revival kept, concise card", "_go9x = _fmt_conv_revival(" in W and "def _fmt_conv_revival(" in W)
check("the un-rung-fire mute from fab9030 is gone (conviction revivals ring again)", 'elif not _ew.get("buzzed"):' not in W)

print("2. partner time on a temp ledger")
store.record_signal("trig_strong", {"symbol": "ABCUSDT", "side": "LONG"}, ts=now - 40 * 60)
store.record_signal("takenow", {"symbol": "ABCUSDT", "side": "long", "hot": False}, ts=now - 30 * 60)
store.record_signal("takenow", {"symbol": "ABCUSDT", "side": "LONG", "hot": True}, ts=now - 20 * 60)
check("last_between finds the latest trigger", abs(store.last_between("trig_strong", "ABCUSDT", "LONG", now - 7200, now + 60) - (now - 2400)) < 2)
check("hot_only skips the cold TAKE NOW row", abs(store.last_between("takenow", "ABCUSDT", "LONG", now - 7200, now + 60, hot_only=True) - (now - 1200)) < 2)
check("nothing in the window → None", store.last_between("apex_v2", "ABCUSDT", "LONG", now - 7200, now + 60) is None)

print("3. the cards fit their line budgets")
plan = dict(symbol="ABCUSDT", base="ABC", side="LONG", entry=1.0, stop=0.95, tp1=1.06, tp2=1.1, tier="HIGH", score=84, appr=True, heat=62)
m = rs.star_fire(plan, 60, now, (), "\n🔮 ❌ DOWN -3.3%", partners=("takenow", "trig_strong"))
lines = [x for x in m.split("\n") if x]
check(f"star card ≤ 6 lines before the gate's two ({len(lines)})", len(lines) <= 6, m)
check("star card: with-line carries partners · conf · heat", "with: ✅🔥 TAKE NOW HOT · 💥 STRONG TRIGGER · conf 60 · heat 62" in m, m)
check("star card: short next line", re.search(r"^next: ⏱ verdict \d\d:\d\d · GO till \d\d:\d\d$", m, re.M) is not None, m)
ew = dict(base="ABC", side="LONG", symbol="ABCUSDT", entry0=1.0, stop=0.95, tp1=1.06, tp2=1.1, oneh="LIVE", star=True)
v = rs.verdict_text(ew, 0.37, now)
check("verdict reply = 3 lines (+ 🕐 stamp), HOLD FULL", len(v.split("\n")) == 3 and "HOLD FULL" in v and v.split("\n")[2].startswith("🕐"), v)
ew["oneh"] = "DEAD"
v2 = rs.verdict_text(ew, -0.1, now)
check("DEAD verdict reply = 3 lines (+ 🕐 stamp), HOLD no add", len(v2.split("\n")) == 3 and "HOLD, no add" in v2 and "1H DEAD stars" in v2, v2)
g = rs.go_text(dict(ew, oneh="LIVE"), 0.4, 1800, 1.02, now)
check("GO reply = 5 lines (header · plan · record · 🕐 clock · class), PROTECT not an entry, FAST",
      len(g.split("\n")) == 5 and "PROTECT, not an entry" in g and "GO FAST" in g
      and g.split("\n")[3].startswith("🕐") and "landing" in g and g.split("\n")[4].startswith("class ✅ LONG · FAST 79%"), g)
g2 = rs.go_text(dict(ew, oneh="DEAD"), 0.3, 5 * 3600, 1.02, now)
check("DEAD→GO reply says REVIVED and LATE", "GO LATE · REVIVED" in g2, g2)
check("short clock line", re.match(r"^🕐 [🟢🟡🔴] \d\d–\d\d (longs|shorts)( |$)", cc.star_line_short("LONG", now)) is not None, cc.star_line_short("LONG", now))   # 01–05: gate-closed cell ends at the side word
# pair card + conviction revival card without the full worker import: exec the two functions' source
ns = {}
src = W
for fn in ("_fmt_pair_card", "_fmt_conv_revival"):
    i = src.index(f"def {fn}(")
    j = src.index("\n\n\n", i)
    ns[fn + "_src"] = src[i:j]
import types  # noqa: E402
stub = types.SimpleNamespace(pkt_hm=rs.pkt_hm, rec=lambda c: "no closes yet", tier_rec=lambda *a, **k: (0, 0.0, 0.0), go_text=rs.go_text)
import tg_cells  # noqa: E402
env = {"rung_stats": stub, "PAIR_KINDS": {}, "PAIR_FIRST": {}, "PAIR_SECOND": {}, "PAIR_LINE": {}, "CONV_REV_CARD_REC": {},
       "_conf_band": lambda c: None, "_revival_dress": lambda m, *a: m, "tg_cells": tg_cells}
i = src.index("PAIR_KINDS = {"); j = src.index("def _pair_partner_ts(")
blk = src[i:j]
for const in ("STAR_PRIME_REC", "CONV_PRIME_REC", "TRIGKR_PRIME_REC", "LEG2_PRIME_REC"):
    env[const] = {"window": "x", "all": "x", "alone": "x"}
exec(blk, env)
k = src.index("CONV_REV_CARD_REC = {"); env2 = {}
exec(src[k:src.index("\n\n\n", k)], env)
exec(ns["_fmt_pair_card_src"], env)
exec(ns["_fmt_conv_revival_src"], env)
sig = dict(symbol="ABCUSDT", base="ABC", side="LONG", entry=1.0, stop=0.95, tp1=1.06, tp2=1.1, conf=66, elite_ts=now - 2700)
card = env["_fmt_pair_card"]("startrig", sig, 1.01, now, now - 300)
check("pair card = 6 lines (+ 🕐 stamp + 🚦 gate)", len(card.split("\n")) == 6 and card.split("\n")[5].startswith("🚦 *GATE") and card.split("\n")[4].startswith("🕐") and "⭐💥 entered at the 2nd fire" in card, card)
check("pair card: STAR × STRONG TRIGGER header with TAKE", card.startswith("⭐💥 *STAR × STRONG TRIGGER — ABC LONG · TAKE ·"), card)
check("pair card: fires in time order with the gap", "⭐ star" in card.split("\n")[1] and "→ 💥 trigger" in card.split("\n")[1] and "(40 min)" in card.split("\n")[1], card)
check("pair card: the pair record line", "pair 71% / +0.18R entered (77)" in card, card)
rev = env["_fmt_conv_revival"](dict(base="ABC", side="LONG", entry0=1.0, stop=0.95, tp1=1.06, go="LATE"), 0.28, 5 * 3600, 1.03, now, (True, "read: ✅ not MAX · ✅ score 84 — rec", "✅ entry cell — rec"), False)
check("conviction revival card ≤ 6 lines (+ 🕐 stamp + 🚦 gate), HOLD READ, LATE", len(rev.split("\n")) <= 6 and "🚦 *GATE" in rev and "CONVICTION REVIVAL — ABC LONG · LATE" in rev and "HOLD READ" in rev and "💎 revival entered at the GO" in rev, rev)
check("conviction revival card carries the entered-at-GO record", "entered at the GO 58% / +0.06R (50)" in rev, rev)
k = src.index("def _kr_note(")
check("Kronos line is one short glance", 'return f"\\n🔮 {\'✅\' if agree else \'❌\'} {d} {_e:+.1f}%"' in src[k:k + 2500])

print("4. the Paper Trader page")
check("PT_HIDDEN names the ten boards", all(f'"{k}"' in A[A.index("PT_HIDDEN = {"):A.index("PT_HIDDEN = {") + 300] for k in
      ("elite_confirm", "sentry", "conviction", "pressing", "preburst", "oi_load", "t1", "apex", "fresh", "early_movers")))
for key, call in (("elite_confirm", "_elite_confirm_board(pb_state)"), ("sentry", "_sentry_board(pb_state)"),
                  ("conviction", "_conviction_board(pb_state)"), ("preburst", "_preburst_board(None)"),
                  ("oi_load", "_oi_load_board()"), ("t1", "_render_t1_board(pb_state, live_prices)")):
    check(f"{key} board guarded", re.search(rf'if _pt_show\("{key}"\):\s*\n\s+{re.escape(call)}', A) is not None)
for key in ("pressing", "apex", "fresh", "early_movers"):
    check(f"{key} block guarded", f'if _pt_show("{key}"):' in A)
check("bench behind a toggle, ACTIVE stays", 'key="desk_bench_toggle"' in A and "ACTIVE — earning right now (14d form positive)" in A)
check("⭐🤝 star pairs board exists and is called", "def _render_star_pairs_board(pb_state)" in A and "_render_star_pairs_board(pb_state)" in A[A.index("def _render_star_pairs_board") + 100:])
check("star pairs board draws the four streams", all(f'("{s}", ' in A for s in ("star_trig", "star_prime", "star_takenow", "star_apexv2")))
check("tier labels for the three new tiers", all(f'"{t}": "' in A for t in ("star_trig", "star_takenow", "star_apexv2")))
check("GEN 19 header says THE FIVE, GATED", "GEN 19 · THE FIVE, GATED" in A)

print(f"\n{PASS} passed, {len(FAIL)} failed" + (f": {FAIL}" if FAIL else " — ALL PASS"))
sys.exit(1 if FAIL else 0)
