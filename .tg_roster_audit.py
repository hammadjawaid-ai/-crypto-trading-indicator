"""Audit every Telegram switch and send path in the DEPLOYED worker (origin/main)
against the agreed plan (2026-10-18). Read-only."""
import io
import re
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"F:\Trading Indicator"
sha = subprocess.run(["git", "rev-parse", "--short", "origin/main"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
W = subprocess.run(["git", "show", "origin/main:agent_worker.py"], cwd=ROOT, capture_output=True).stdout.decode("utf-8")
print("deployed commit:", sha)


def flag(name):
    m = re.search(rf"^{name}\s*=\s*([^\n#]+)", W, re.M)
    return m.group(1).strip() if m else "MISSING"


print("switches:")
for n in ("TG_RULES", "TG_FREEZE", "TG_GATES", "TG_GO_LIVE", "STAR_BTC_MAX", "GATE_BTC_MIN", "STAR_UNGATED_1317",
          "REVIVED_LONG_FAST", "TG_STAR_PRIME", "TG_CONV_PRIME", "TG_LEG2_PRIME", "TG_TRIGKR_PRIME"):
    print(f"  {n:20s} {flag(n)}")
sg = W[W.find("def _star_gate("):W.find("def _revived_gate(")]
rg = W[W.find("def _revived_gate("):W.find("def _golive_gate(")]
checks = [
    ("⭐ star: four-rule read gates the send (heat / BTC day / not 01–05 / stop)",
     "_gate9 = _star_gate(_pmx, time.time()," in W and 'and not _gate9[0] and not _w1317:\n                            ok, _m9, _ids9 = False, "gated", None' in W
     and 'win != "01–05"' in sg and "heat >= 25" in sg and "btc <= STAR_BTC_MAX" in sg and "sp <= 7.0" in sg and "13–17" not in sg),
    ("⭐ star: 13–17 PKT rings regardless of the read, caution first, PASSED / FAILED named",
     "_w1317 = (_star9 and STAR_UNGATED_1317" in W and "read FAILED — ringing ONLY because" in W and "read PASSED — would have rung anyway" in W),
    ("⭐ star: record stamps pass / muted / 1317-pass / 1317-muted", '"1317-pass" if _gate9[0] else' in W),
    ("⭐ star: clock line under the read", 'clock_cells.star_line(\n                                        _pmx.get("side"), time.time())' in W),
    ("⭐⚡ ELITE GO reply: FAST sends in the thread (ungated), LATE skipped since 2026-10-19, clock line before the branches",
     'elif _ew.get("buzzed"):\n                                        if _ew.get("go") == "LATE":' in W
     and 'else:\n                                            _ok9, _m9x, _ = tg.send_thread(\n                                                _go9,\n                                                reply_to=_ew.get("tg_ids"))' in W
     and "clock_cells.elite_go_line(" in W),
    ("revival bells: ⭐ STAR REVIVAL rings FAST + LATE; 💎 CONVICTION REVIVAL only inside the entry cell",
     "_go9x = _revival_dress(_go9x, _ew, _age, _ew_now)" in W and '_bell9 = f"gated: entry cell not met — {_rg9[2]}"' in W),
    ("GO REVIVED: gate = not MAX + score < 90 only", 'tier != "MAX"' in rg and "score < 90" in rg and "(conf," not in rg and "fwin" not in rg and 'btc >= GATE_BTC_MIN, f"BTC' not in rg),
    ("GO REVIVED: BTC day shown as a caution, never a gate", "(caution, not a gate)" in rg),
    ("GO REVIVED: unapproved elite fires ring, tagged, stamped", '"sent-standalone-unapproved"' in W and "REVIVED_UNAPPR" in W),
    ("GO REVIVED: entry-cell line + clock line on the bell", "clock_cells.revived_line(" in W and "REVIVED_ENTRY_OK" in W),
    ("💎⚡ GO LIVE: profile gate HIGH / stop < 5 / BTC >= -1.5, approved and unapproved", "_gl9 = _golive_gate(" in W and "else GO_LIVE_UNAPPR)" in W and 'tier == "HIGH"' in W and "sp < 5.0" in W),
    ("⚡🔥 ARRIVAL T1 rings with the window line; T2 silent", "T1_WINDOWS" in W and "_atier == 1" in W),
    ("🏦 TP1 HIT ping: roster streams only, with the from: line", "TP1_STREAMS" in W and "from:" in W),
    ("pairs on: STAR×PRIME, ELITE×PRIME, SECOND LEG×PRIME; TRIG×KR×PRIME off",
     flag("TG_STAR_PRIME").startswith("True") and flag("TG_CONV_PRIME").startswith("True") and flag("TG_LEG2_PRIME").startswith("True") and flag("TG_TRIGKR_PRIME").startswith("False")),
    ("muted: APEX V2, moonshot", "_MUTE_RULES(_fmt_apex_v2(" in W and "if key_prefix not in (() if TG_RULES else" in W),
    ("⚡🔮 KR-STRONG PREMIUM rings (back 2026-10-19), honest record + non-gating read, 83% claim gone",
     'ok, _ = tg.send(\n                        f"⚡🔮 *KR-STRONG PREMIUM — "' in W and "83.1%" not in W[W.find('f"⚡🔮 *KR-STRONG PREMIUM — "'):W.find('f"⚡🔮 *KR-STRONG PREMIUM — "') + 1500]),
    ("clock_cells imported by the worker", "import clock_cells" in W),
]
bad = 0
print("roster audit:")
for lab, ok in checks:
    print(f"  {'✅' if ok else '❌'} {lab}")
    bad += (not ok)
print("\nALL MATCH THE PLAN" if not bad else f"\n{bad} MISMATCH(ES)")
