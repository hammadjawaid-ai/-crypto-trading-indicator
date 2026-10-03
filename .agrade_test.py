"""ELITE A-GRADE + SEATED-65 — pure-function tests (grade, seat memory,
banner markdown) + wiring checks in worker/app/auditor + the two mutes."""
import ast
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
W = open("F:/Trading Indicator/agent_worker.py", encoding="utf-8").read()
A = open("F:/Trading Indicator/app.py", encoding="utf-8").read()
U = open("F:/Trading Indicator/auditor.py", encoding="utf-8").read()
fails = []

# ---- pull the pure helpers out of the worker without importing it ----
tree = ast.parse(W)
want_fn = {"_seats_update", "_seat_of", "_plan_rr", "_elite_grade", "_grade_sig", "_agrade_banner"}
want_var = {"_SEATS", "SEAT_MEMORY_S", "AGRADE_CONF", "AGRADE_MAX_RR"}
body = []
for n in tree.body:
    if isinstance(n, ast.FunctionDef) and n.name in want_fn:
        body.append(n)
    elif isinstance(n, (ast.Assign, ast.AnnAssign)):
        tgt = n.targets[0] if isinstance(n, ast.Assign) else n.target
        if isinstance(tgt, ast.Name) and tgt.id in want_var:
            body.append(n)
if len(body) != len(want_fn) + len(want_var):
    fails.append(f"helpers missing from the worker: found {len(body)}")


class _ShadowStub:
    recs = []

    @classmethod
    def tier_records(cls):
        return cls.recs


ns = {"time": __import__("time"), "shadow_trader": _ShadowStub}
exec(compile(ast.Module(body=body, type_ignores=[]), "agrade_helpers", "exec"), ns)
seats_update, seat_of, grade, grade_sig, banner, plan_rr = (
    ns["_seats_update"], ns["_seat_of"], ns["_elite_grade"], ns["_grade_sig"], ns["_agrade_banner"], ns["_plan_rr"])

# ---- seat memory: top 8 by score, side-insensitive, 2h expiry ----
T0 = 1_800_000_000.0
board = [{"symbol": f"C{i}USDT", "side": "LONG", "score": 70 + i, "lanes": 2} for i in range(12)]
board.append({"symbol": "SHRTUSDT", "side": "short", "score": 99, "lanes": 3})
seats_update(board, now=T0)
if seat_of("C11USDT", "LONG", now=T0) is None or seat_of("SHRTUSDT", "SHORT", now=T0) is None:
    fails.append("top seats not remembered")
if seat_of("C0USDT", "LONG", now=T0) is not None or seat_of("C4USDT", "LONG", now=T0) is not None:
    fails.append("board must keep only the top 8 by score")
if seat_of("C11USDT", "LONG", now=T0 + 2 * 3600 - 1) is None:
    fails.append("seat should still count at 1h59")
if seat_of("C11USDT", "LONG", now=T0 + 2 * 3600 + 1) is not None:
    fails.append("seat should expire after 2h")
seats_update([], now=T0 + 3 * 3600)
if ns["_SEATS"]:
    fails.append("stale seats not purged on update")

# ---- the grade ----
seat = {"ts": T0, "score": 94, "lanes": 3}
L = {"symbol": "XRPUSDT", "side": "LONG", "entry": 2.84, "stop": 2.75, "tp1": 2.95, "tp2": 3.04, "tier": "MAX", "score": 92}
cases = [
    (L, 71, seat, "A", "seated conf71 LONG rr1.22"),
    (L, 65, seat, "A", "conf exactly 65 counts"),
    (L, 64.9, seat, None, "conf 64.9 is out"),
    (L, None, seat, None, "no conf -> no grade"),
    (L, 71, None, None, "no seat -> no grade"),
    (dict(L, side="SHORT"), 71, seat, "S65", "short with seat -> seated-65 only"),
    (dict(L, tp1=3.05), 71, seat, "S65", "rr 2.33 -> seated-65 only"),
    (dict(L, tp1=2.9839), 71, seat, "A", "rr 1.599 is still an A"),
    (dict(L, side="long"), 80, seat, "A", "side case-insensitive"),
    (L, 5.5e12, seat, None, "garbage conf reads as unknown"),
    (dict(L, entry=None), 71, seat, "S65", "no plan geometry -> cannot be A"),
    (dict(L, tier="HIGH", score=81), 66, seat, "A", "HIGH qualifies the same way"),
]
for p, c, s, want, lab in cases:
    got = grade(p, c, s)
    if got != want:
        fails.append(f"grade({lab}) = {got!r}, wanted {want!r}")
rr = plan_rr(L)
if not (1.21 < rr < 1.23):
    fails.append(f"plan_rr wrong: {rr}")
gs = grade_sig(L, 71, seat, "A")
for k in ("symbol", "base", "side", "entry", "stop", "tp1", "tp2", "conf", "tier", "seat_score", "seat_lanes", "rr", "grade"):
    if k not in gs:
        fails.append(f"grade_sig missing {k}")
if gs["base"] != "XRP" or gs["grade"] != "A" or gs["seat_lanes"] != 3:
    fails.append(f"grade_sig values wrong: {gs}")

# ---- banner: markdown-safe, study numbers, forward ledger only at n>=10 ----
_ShadowStub.recs = []
m = banner(seat, 71, rr)
for need in ("💎🏆 *ELITE A-GRADE", "seated on Top Conviction (score 94, 3 lanes)", "conf 71", "TP1 1.22R", "68.6% / +0.49R", "unproven"):
    if need not in m:
        fails.append(f"banner missing {need!r}")
if "Forward ledger" in m:
    fails.append("banner must not quote an empty forward ledger")
if m.count("*") % 2 or m.count("_") % 2 or m.count("`") % 2:
    fails.append("banner markdown unbalanced")
_ShadowStub.recs = [{"tier": "elite_agrade", "n": 12, "win_pct": 66.7, "net_r": 4.2}]
m2 = banner({"ts": T0}, 80.0, None)
if "Forward ledger so far: 12 closed · 67% · +4.2R net" not in m2:
    fails.append("forward ledger line missing once 10 closes exist")
if "(" in m2.split("\n")[1][:40]:
    fails.append("empty seat details should not print parentheses")
_ShadowStub.recs = [{"tier": "elite_agrade", "n": 9, "win_pct": 66.7, "net_r": 4.2}]
if "Forward ledger" in banner(seat, 71, rr):
    fails.append("forward ledger quoted below 10 closes")

# ---- wiring ----
i_push = W.find("    def _push_elite(items):")
blk = W[i_push:W.find("    tn_hot = [p for p in takenow")]
i_star = blk.find('_star9 = (bool(_pmx.get("appr"))')
i_read = blk.find("_grade9 = _elite_grade(_pmx, _cf9, _seat9)")
i_gate = blk.find("if not (_star9 or _ag9):")
i_conf = blk.find("if _cf9 is not None and _cf9 < 40:")
i_key = blk.find('else "eliteagrade" if _ag9 else "eliteconv")')
i_ban = blk.find("_msg9 = _agrade_banner(")
i_clock = blk.find("_ck9 = buzz_clock.tagline(")
i_send = blk.find("ok, _m9 = tg.send(_msg9)")
if not (0 < i_star < i_read < i_gate < i_conf < i_key < i_ban < i_clock < i_send):
    fails.append(f"buzz wiring order wrong: star {i_star} read {i_read} gate {i_gate} conf {i_conf} key {i_key} banner {i_ban} clock {i_clock} send {i_send}")
if "if not _star9:" in blk:
    fails.append("the old star-only gate is still there")
if '    _seats_update(tn_hot)' not in W or W.find("_seats_update(tn_hot)") < W.find('    tn_hot = [p for p in takenow if p.get("hot")]'):
    fails.append("seat memory not refreshed right after tn_hot")
for need, lab in (('if _elite_grade(_pe, _pe.get("conf"), _sa3) == "A":', "unapproved A-grade joins the kronos-ok buzz list"),
                  ('if _elite_grade(_pe, _pe.get("conf"), _sa4) == "A":', "unapproved A-grade joins the kronos-down buzz list"),
                  ('("elite_agrade", _ag_list),', "elite_agrade desk tier"),
                  ('("elite_seated65", _s65_list),', "elite_seated65 desk tier"),
                  ('store.record_signal("elite_agrade", _gs)', "elite_agrade record"),
                  ('store.record_signal("elite_seated65", _gs)', "elite_seated65 record")):
    if need not in W:
        fails.append(f"wiring missing: {lab}")
i_lists = W.find("_ag_list, _s65_list = [], []")
i_tiers = W.find('_tiers = (("top_conviction", _topc),')
if not (0 < i_lists < i_tiers):
    fails.append("grade lists must be built before the tiers tuple")
# seated-65 never reaches Telegram
for ln in W.splitlines():
    if "tg.send" in ln and "seated65" in ln:
        fails.append("elite_seated65 must not have a bell")
# the two mutes
if "tg.send(_du_msg)" in W.replace("# Revert: tg.send(_du_msg)", ""):
    fails.append("DUO 85+ bell still live")
if "ok, _ = _MUTE_R9(_du_msg)" not in W:
    fails.append("DUO 85+ mute not wired")
if "tg.send(_fmt_press_break(" in W:
    fails.append("PRESSED & BROKE bell still live")
if "_MUTE_R9(_fmt_press_break(a, px, _pb_min)" not in W:
    fails.append("PRESSED & BROKE mute not wired")
if '_du_seat = {"duo85": "duo_band"}.get(_du_key)' not in W or 'store.record_signal(_du_key, _du_sig)' not in W:
    fails.append("duo85 desk record / demo seat feed must stay")
if 'store.record_signal("press_break", _sig_pb)' not in W:
    fails.append("press_break desk record must stay")
# app + auditor
for need, lab in (('"elite_agrade": "💎🏆 ELITE A-GRADE', "app A-grade name"), ('"elite_seated65": "💎🏆 ELITE SEATED 65+', "app seated-65 name")):
    if need not in A:
        fails.append(f"missing {lab}")
for need in ('"elite_agrade": "elite_agrade",', '"elite_seated65": "elite_seated65",'):
    if need not in U:
        fails.append(f"auditor missing {need}")
print(m)
print("ELITE A-GRADE:", "ALL PASS" if not fails else fails)
