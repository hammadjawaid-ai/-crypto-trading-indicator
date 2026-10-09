"""GO REVIVED: every class rings, with a heading (user 2026-10-09: "it's ok to
have shorts or late but it should have the heading to it, we are not letting go
of any notifications"). REVIVED_LONG_FAST -> False (bell, tier and board take
every class again); rung_stats.go_text adds a class line on every GO bell from
the 119-GO replay; the board shows the class chip instead of filtering."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = "F:/Trading Indicator/"


def rep(src, old, new, label):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"ANCHOR {label!r} matched {n} times — aborting, nothing written")
    return src.replace(old, new)


W = open(ROOT + "agent_worker.py", encoding="utf-8").read()
W = rep(W, "REVIVED_LONG_FAST = True\n",
        "# (user 2026-10-09 later: \"it's ok to have shorts or late but it should have\n"
        "#  the heading to it, we are not letting go of any notifications\" -> every\n"
        "#  class rings; rung_stats.go_text names the class with its numbers.)\n"
        "REVIVED_LONG_FAST = False\n", "switch off")

R = open(ROOT + "rung_stats.py", encoding="utf-8").read()
R = rep(R,
        "ARRIVAL_WINDOW = \"15 Aug → 28 Sep\"\n",
        "ARRIVAL_WINDOW = \"15 Aug → 28 Sep\"\n"
        "# ⭐⚡ GO entry classes (.go_entry_study.py, 119 recorded GOs entered at the GO\n"
        "# close with the fire stop + fire TP1, 24h, fees; replay 14 → 28 Sep). The\n"
        "# user keeps every class on the phone; the heading names the class.\n"
        "GO_CLASS = {\"long_fast\": \"✅ LONG · FAST — the measured cell: 79% win / +1.15% / \"\n"
        "                         \"+0.21R per GO entry (77)\",\n"
        "            \"short\": \"⚠️ SHORT — shorts entered at the GO measured 48% / −1.92% / \"\n"
        "                     \"−0.16R (42): size down or pass\",\n"
        "            \"late\": \"⚠️ LATE (over 4h) — late GOs measured 52% / −1.74% / −0.10R \"\n"
        "                    \"(27): size down or pass\",\n"
        "            \"window\": \"replay 14 → 28 Sep, fire stop\"}\n", "class table")
R = rep(R,
        "    rev = ew.get(\"oneh\") == \"DEAD\"\n",
        "    rev = ew.get(\"oneh\") == \"DEAD\"\n"
        "    cls = (GO_CLASS[\"short\"] if side == \"SHORT\" else\n"
        "           GO_CLASS[\"late\"] if late else GO_CLASS[\"long_fast\"])\n"
        "    cls_line = f\"class: {cls} · {GO_CLASS['window']}\"\n", "class line")
R = rep(R,
        "    return \"\\n\".join([head, plan, l2, l3, l4, stamp(st)])\n",
        "    return \"\\n\".join([head, cls_line, plan, l2, l3, l4, stamp(st)])\n", "join")

A = open(ROOT + "app.py", encoding="utf-8").read()
A = rep(A,
        "        if (_r[3] or \"\").upper() != \"LONG\" or str(_r[8] or \"\").upper() != \"FAST\":\n"
        "            continue                      # LONG + FAST only (2026-10-09 GO-entry study)\n",
        "", "board filter removed")
A = rep(A,
        "            _chips = [\"⭐ star\" if _ex.get(\"star\") else \"💎 elite\",\n"
        "                      f\"⭐⚡ GO {_tier or ''}\".strip(),\n",
        "            _chips = [\"⭐ star\" if _ex.get(\"star\") else \"💎 elite\",\n"
        "                      f\"⭐⚡ GO {_tier or ''}\".strip(),\n"
        "                      (\"✅ LONG·FAST class 79% / +1.15%\" if (_lng and str(_tier or '').upper() == 'FAST')\n"
        "                       else \"⚠️ SHORT class 48% / −1.92%\" if not _lng\n"
        "                       else \"⚠️ LATE class 52% / −1.74%\"),\n", "class chip")
A = rep(A,
        '        "late GOs 52% / −1.74% (14–28 Sep) — so this board and its bell carry "\n'
        '        "LONG + FAST only; shorts and late GOs keep stamping for the record. The "\n',
        '        "late GOs 52% / −1.74% (14–28 Sep) — every class stays on the board and "\n'
        '        "the bell, each card names its class. The "\n', "board caption")

T = open(ROOT + ".tg_rules_test.py", encoding="utf-8").read()
T = rep(T, '                  ("REVIVED_LONG_FAST = True\\n", "revived long+fast switch on"),\n',
        '                  ("REVIVED_LONG_FAST = False\\n", "every revived class rings (user 2026-10-09)"),\n', "switch anchor")
T = rep(T,
        '             "fire entry `0.0121` · SL `0.010827` · TP1 `0.01343`",\n',
        '             "fire entry `0.0121` · SL `0.010827` · TP1 `0.01343`",\n'
        '             "class: ✅ LONG · FAST — the measured cell: 79% win / +1.15% / +0.21R per GO entry (77) · replay 14 → 28 Sep, fire stop",\n',
        "go class anchor")
T = rep(T,
        'if "⭐⚡ *GO — GLMR LONG · REVIVED · PROTECT · 13:40 PKT (5.0h after the fire, late)*" not in g2 or "REVIVED" in g or',
        'if "⭐⚡ *GO — GLMR LONG · REVIVED · PROTECT · 13:40 PKT (5.0h after the fire, late)*" not in g2 or "class: ⚠️ LATE (over 4h)" not in g2 or "REVIVED" in g or',
        "late class anchor")
T = rep(T,
        "ge = rs.go_text(dict(ew, star=False, oneh=\"DEAD\", entry0=0.0121, stop=0.0119), 0.26, 2.0 * H, 0.01215, NOW, DB)\n",
        "ge = rs.go_text(dict(ew, star=False, oneh=\"DEAD\", entry0=0.0121, stop=0.0119), 0.26, 2.0 * H, 0.01215, NOW, DB)\n"
        "gs = rs.go_text(dict(ew, side=\"SHORT\", oneh=\"DEAD\", entry0=0.0121, stop=0.0125), 0.26, 2.0 * H, 0.01195, NOW, DB)\n"
        "if \"class: ⚠️ SHORT — shorts entered at the GO measured 48%\" not in gs:\n"
        "    fails.append(\"short GO must carry the short class heading\")\n", "short class case")
T = rep(T,
        "for m in (day_msg, night_msg, v_live, v_dead, v_plain, g, g2, ge, fz_n, fz_d, ar, sb):\n",
        "for m in (day_msg, night_msg, v_live, v_dead, v_plain, g, g2, ge, gs, fz_n, fz_d, ar, sb):\n", "markdown loop")

T2 = open(ROOT + ".revived_board_test.py", encoding="utf-8").read()
T2 = rep(T2,
         '                  (\'if (_r[3] or "").upper() != "LONG" or str(_r[8] or "").upper() != "FAST":\', "board shows LONG + FAST only")):\n',
         '                  (\'"✅ LONG·FAST class 79% / +1.15%" if (_lng and str(_tier or \\\'\\\').upper() == \\\'FAST\\\')\', "class chip on every card")):\n',
         "board test chip anchor")
for path, s in (("agent_worker.py", W), ("rung_stats.py", R), ("app.py", A), (".tg_rules_test.py", T), (".revived_board_test.py", T2)):
    with open(ROOT + path, "w", encoding="utf-8", newline="") as f:
        f.write(s)
print("patched: every revived class rings with its heading; board keeps every card with a class chip")
