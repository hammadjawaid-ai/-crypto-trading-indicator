"""Guard (2026-10-24, user): (1) 💎✅ ROOM — a records-only desk tier beside the
confirmed entry (TP1 >= 1R at the confirm close · plain pick, no 💎/⭐ record on the
coin+side in 48h · BTC day <= +1.5%), no bell, no demo seat, and the elite_confirm
record/open it sits beside is byte-for-byte the old one. (2) 💥🥇 PRIME × STRONG
TRIGGER: TG_PRIME_TRIG on with a real send path, a GEN 18.2 demo feed at the flat
10x as the 5th rung, the 🏦 TP1 ping roster knows it, the page says so.
Run: python .confirm_room_test.py  (exit 0 = green)."""
import ast
import io
import os
import sys
import textwrap

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
W = open(os.path.join(ROOT, "agent_worker.py"), encoding="utf-8").read()
A = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
fails = []

# ───────────────────────── (1) ROOM ─────────────────────────
i = W.find("# 💎✅ ROOM (user 2026-10-24")
j = W.find("_ECF_FIRES.append(dict(_sig9", i)
blk = W[i:j] if (i > 0 and j > i) else ""
if len(blk) < 800:
    fails.append("ROOM block missing")
k = W.find('shadow_trader.open_from_signal("elite_confirm", _sig9,')
if not (0 < k < i):
    fails.append("ROOM must follow the confirm's own record/open, never replace it")
for need, lab in (('store.record_signal("confirm_room", _sig_rm)', "records the tier"),
                  ('shadow_trader.open_from_signal("confirm_room", _sig_rm, _cl9)', "desk open at the confirm close"),
                  ("_rr_rm >= 1.0", "TP1 >= 1R rule"),
                  ('store.seen_between("elite_conv", _w9["symbol"], _w9["side"],', "conviction record check"),
                  ('store.seen_between("elite_star", _w9["symbol"], _w9["side"],', "star record check"),
                  ("_now - 48 * 3600", "48h look-back"),
                  ("_btc_rm is None or _btc_rm <= 1.5", "BTC day rule (unreadable passes)"),
                  ('room=("pass" if _room_ok else "fail")', "room stamp")):
    if need not in blk:
        fails.append(f"ROOM missing: {lab}")
for bad in ("tg.send", "_DEMO_", "send_thread"):
    if bad in blk:
        fails.append(f"ROOM is records-only — found {bad}")
# the confirm's own record + open are untouched (pinned text)
CONFIRM_PIN = ('            _sig9 = {"symbol": _w9["symbol"], "base": _w9["base"],\n'
               '                     "side": _w9["side"], "tier": _w9.get("tier"),\n'
               '                     "score": _w9.get("score"), "entry": _cl9,\n'
               '                     "stop": _w9["stop"], "tp1": _w9["tp1"],\n'
               '                     "tp2": _w9.get("tp2"), "conf": _cf0}\n'
               '            store.record_signal("elite_confirm", _sig9)\n'
               '            shadow_trader.open_from_signal("elite_confirm", _sig9,\n'
               '                                           _cl9)\n')
if W.count(CONFIRM_PIN) != 1:
    fails.append("the elite_confirm record/open changed — ROOM must not touch the confirm")
if W.count('store.record_signal("elite_confirm"') != 1:
    fails.append("elite_confirm must be recorded exactly once")

# behaviour: exec the ROOM try-block against stubs
room_src = blk[blk.find("            try:\n"):]
room_src = textwrap.dedent(room_src)


class _Store:
    def __init__(self, seen):
        self.seen, self.rec = seen, []

    def seen_between(self, stream, sym, side, t0, t1):
        return stream in self.seen

    def record_signal(self, tier, sig):
        self.rec.append((tier, dict(sig)))


class _Shadow:
    def __init__(self):
        self.opened = []

    def open_from_signal(self, tier, sig, px):
        self.opened.append((tier, px))


def run_room(tp1, stop, close, seen, btc):
    st, sh = _Store(seen), _Shadow()
    ns = {"store": st, "shadow_trader": sh, "_btc_day_pct": (lambda: btc),
          "_w9": {"symbol": "XUSDT", "side": "LONG", "tp1": tp1, "stop": stop},
          "_cl9": close, "_now": 1_700_000_000.0,
          "_sig9": {"symbol": "XUSDT", "side": "LONG", "entry": close, "stop": stop, "tp1": tp1},
          "print": lambda *a, **k: None}
    exec(compile(room_src, "<room>", "exec"), ns)
    return st, sh


# long from 100, stop 95 (risk 5): TP1 112 = 2.4R room, plain pick, BTC +0.5 → ROOM
st, sh = run_room(112.0, 95.0, 100.0, set(), 0.5)
if [t for t, _ in st.rec] != ["confirm_room"] or [t for t, _ in sh.opened] != ["confirm_room"]:
    fails.append(f"ROOM pass case must record + open once: {st.rec} {sh.opened}")
elif st.rec[0][1].get("room") != "pass" or st.rec[0][1].get("fire_kind") != "pick" or abs(st.rec[0][1].get("rr") - 2.4) > 0.01:
    fails.append(f"ROOM stamps wrong: {st.rec[0][1]}")
# TP1 104 = 0.8R → no room
st, sh = run_room(104.0, 95.0, 100.0, set(), 0.5)
if st.rec or sh.opened:
    fails.append("ROOM must not open when TP1 < 1R")
# a star record behind it → bell-backed, no room
st, sh = run_room(112.0, 95.0, 100.0, {"elite_star"}, 0.5)
if st.rec or sh.opened:
    fails.append("ROOM must not open on a star-backed confirm")
st, sh = run_room(112.0, 95.0, 100.0, {"elite_conv"}, 0.5)
if st.rec or sh.opened:
    fails.append("ROOM must not open on a conviction-backed confirm")
# BTC day +2.1% → no room; unreadable BTC → passes
st, sh = run_room(112.0, 95.0, 100.0, set(), 2.1)
if st.rec or sh.opened:
    fails.append("ROOM must not open on a BTC day > +1.5%")
st, sh = run_room(112.0, 95.0, 100.0, set(), None)
if len(st.rec) != 1:
    fails.append("an unreadable BTC day must pass the ROOM gate (every gate's law)")
# exactly 1R → pass (>=)
st, sh = run_room(105.0, 95.0, 100.0, set(), 0.0)
if len(st.rec) != 1:
    fails.append("TP1 at exactly 1R is ROOM (>=)")
# page label
if '"confirm_room": "💎✅ ROOM' not in A:
    fails.append("page: confirm_room tier label missing")

# ───────────────── (2) PRIME × STRONG TRIGGER: bell + demo ─────────────────
tree = ast.parse(W)
flags = {}
for n in tree.body:
    if isinstance(n, ast.Assign):
        for t in n.targets:
            if isinstance(t, ast.Name) and t.id in ("TG_PRIME_TRIG", "TP1_STREAMS", "PRIME_TRIG_REC"):
                try:
                    flags[t.id] = ast.literal_eval(n.value)
                except Exception:
                    flags[t.id] = None
if flags.get("TG_PRIME_TRIG") is not True:
    fails.append("TG_PRIME_TRIG must be True (bell on 2026-10-24)")
if "prime_trig" not in (flags.get("TP1_STREAMS") or {}):
    fails.append("🏦 TP1 ping roster must know prime_trig")
pt = W[W.find("# 💥🥇 PRIME × STRONG TRIGGER — records-only pass"):W.find("# 💯 CONVICTION v2")]
for need, lab in (('_DEMO_PT.append(dict(_sig_pt, src="prime_trig"', "demo feed"),
                  ("del _DEMO_PT[:-12]", "feed trimmed"),
                  ("if TG_PRIME_TRIG and not _bstock_quiet(_sym_pt):", "bell behind the switch + b-stock quiet"),
                  ("ok, _m_pt = tg.send(_fmt_prime_trig(", "send path"),
                  ("+ _kr_note(_sig_pt))", "KR note appended"),
                  ("n_alerts += 1 if ok else 0", "alert counted"),
                  ('store.record_signal("prime_trig", _sig_pt)', "desk record stays"),
                  ('shadow_trader.open_from_signal("prime_trig", _sig_pt, _px_pt)', "desk open stays")):
    if need not in pt:
        fails.append(f"prime_trig pass missing: {lab}")
if pt.find('store.record_signal("prime_trig", _sig_pt)') > pt.find("_DEMO_PT.append("):
    fails.append("the desk record must come before the demo feed / bell (records every fire first)")
if "_DEMO_PT: list = []" not in W:
    fails.append("_DEMO_PT feed list missing")
pools = W[W.find("_dz_pools = {"):W.find("_dz_active = set()", W.find("_dz_pools = {"))]
if '"prime_trig": ([dict(d) for d in _DEMO_PT' not in pools or "_now - d[\"fired_at\"] <= DEMO_FIRE_TTL_S" not in pools:
    fails.append("demo pool for prime_trig missing / not TTL-gated")
if '("prime_trig", "prime_trig")' not in W:
    fails.append("tier-form map must read prime_trig's own shadow ledger")
if '"star_prime", "conv_revival", "prime_trig")' not in W:
    fails.append("momentum re-entry must keep the prime_trig src")

# the bell text: exec _fmt_prime_trig against stubs
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_fmt_prime_trig")
src_fn = ast.get_source_segment(W, fn)


class _RS:
    @staticmethod
    def pkt_hm(ts):
        return "14:05"

    @staticmethod
    def rec(c):
        return "3 trades · 67% · +0.4R"

    @staticmethod
    def tier_rec(tier, days, now):
        return (3, 2, 0.4)

    @staticmethod
    def stamp_now(now):
        return "24 Oct 14:05 PKT"


class _BZ:
    @staticmethod
    def compute(entry, stop, tp1, side, levels=None, pct=0.9):
        return {"px": 110.0}

    @staticmethod
    def line(bz):
        return "🎯 bank zone 110"


ns = {"rung_stats": _RS, "bank_zone": _BZ, "_sr_levels": lambda s, d: [],
      "PRIME_TRIG_REC": "PRIME with a 💥 strong trigger 64% / +0.32R (155)"}
exec(compile(src_fn, "<fmt>", "exec"), ns)
sig = {"symbol": "XUSDT", "base": "X", "side": "LONG", "entry": 100.0, "stop": 95.0, "tp1": 112.0,
       "tp2": 120.0, "read_line": "🥇 read: pass — TP1 2.4R · stop 5% · BTC +0.5% · 14 PKT"}
txt = ns["_fmt_prime_trig"](sig, 100.5, 1_700_000_000.0)
for need in ("💥🥇 *PRIME × STRONG TRIGGER — X LONG · TAKE · 14:05 PKT*", "entry `100`", "live `100.5`",
             "SL `95`", "TP1 `112`", "TP2 `120`", "🥇 read: pass", "🎯 bank zone 110",
             "64% / +0.32R (155)", "forward ledger", "information, not a gate"):
    if need not in txt:
        fails.append(f"bell text missing: {need}")
if "83%" in txt.split("\n")[0]:
    fails.append("the decayed 83% claim must not head the bell")

# demo_account: 5th rung at the flat 10x, fade bank + no kronos exit like the four
import demo_account as da   # noqa: E402
if set(da.CLASS_W) != {"elite_star", "strong_trigger", "star_prime", "conv_revival", "prime_trig"}:
    fails.append(f"CLASS_W roster: {sorted(da.CLASS_W)}")
if not (da.CLASS_W["conv_revival"] > da.CLASS_W["prime_trig"]):
    fails.append("prime_trig is the 5th rung, below conviction revival")
if da.lev_for("prime_trig") != 10.0:
    fails.append(f"prime_trig leverage must be the flat 10x: {da.lev_for('prime_trig')}")
if "prime_trig" not in da.NEAR_TP_SRC or "prime_trig" not in da.SMART_EXIT_SKIP:
    fails.append("prime_trig must share the four's exits (fade bank on, no kronos exit)")
if da.CONF_GATE.get("prime_trig") is not None or "prime_trig" in da.LONG_ONLY:
    fails.append("prime_trig seats every band, both sides (user: every band)")
if not da.time_gate_ok("prime_trig", "LONG", 1_700_000_000.0) or not da.clock_ok("prime_trig", "SHORT", 1_700_000_000.0)[0]:
    fails.append("prime_trig must have no time gate / clock gate")
# ranker picks it up
ranked = da.rank_candidates({"prime_trig": [{"symbol": "XUSDT", "base": "X", "side": "LONG", "entry": 100.0,
                                             "stop": 95.0, "tp1": 112.0, "score": 85, "src": "prime_trig"}]}, {})
if not ranked or ranked[0].get("src") != "prime_trig":
    fails.append(f"rank_candidates must seat a prime_trig candidate: {ranked}")
# page
if "5. 💥🥇 PRIME × STRONG TRIGGER</b>, 10x" not in A:
    fails.append("demo page header must list the 5th rung")
if "demo seat + 💥🥇 bell since 24 Oct" not in A:
    fails.append("prime_trig tier label must say demo + bell")

if fails:
    print("FAIL")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("OK — ROOM records-only beside the untouched confirm; PRIME × STRONG TRIGGER bell on, 5th demo rung at 10x")
