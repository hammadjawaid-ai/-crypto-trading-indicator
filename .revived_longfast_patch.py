"""⭐⚡ GO REVIVED = LONG + FAST only (user 2026-10-09 "what can we extract or
build on this"): .go_entry_study.py replayed 119 recorded GOs entering at the GO
close with the fire stop + fire TP1 (24h, fees): LONG 79% / +1.15% / +0.21R
(77) vs SHORT 48% / -1.92% / -0.16R (42); FAST (<= 4h) 73% / +0.59% vs LATE 52%
/ -1.74%; a tighter ignition-base stop made every cell worse. Live ledger
06-09 Oct: 26 closed 38% / -7.0R = shorts + late GOs in a dump week. So the
standalone bell, the go_revived tier and the board take LONG + FAST only;
shorts and late GOs still stamp (star_go / elite_go) for the record.
Also: bottom-watch message gains the print-order and breadth facts."""
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
W = rep(W, "TG_FREEZE = False\n",
        "TG_FREEZE = False\n"
        "# ⭐⚡ GO REVIVED = LONG + FAST only (2026-10-09, .go_entry_study.py: 119\n"
        "# recorded GOs entered at the GO close with the fire stop — LONG 79% /\n"
        "# +1.15% / +0.21R (77) vs SHORT 48% / -1.92% (42); FAST 73% / +0.59% vs\n"
        "# LATE 52% / -1.74%). Shorts and late GOs still stamp; no bell, no tier.\n"
        "REVIVED_LONG_FAST = True\n", "switch")
W = rep(W,
        '                                        if _ew.get("star") or _ew.get("appr"):\n'
        "                                            _ok9, _m9x = tg.send(_go9)\n"
        '                                            _bell9 = ("sent-standalone" if _ok9\n'
        '                                                      else f"failed: {_m9x}")\n'
        "                                        else:\n",
        '                                        if ((_ew.get("star") or _ew.get("appr"))\n'
        "                                                and REVIVED_LONG_FAST\n"
        '                                                and not (_ew["side"] == "LONG"\n'
        '                                                         and _ew["go"] == "FAST")):\n'
        '                                            _bell9 = ("skipped (revived "\n'
        '                                                      f"{_ew[\'side\'].lower()} "\n'
        '                                                      f"{_ew[\'go\'].lower()}: shorts "\n'
        '                                                      "-1.9% / late -1.7% measured; "\n'
        '                                                      "records only)")\n'
        '                                        elif _ew.get("star") or _ew.get("appr"):\n'
        "                                            _ok9, _m9x = tg.send(_go9)\n"
        '                                            _bell9 = ("sent-standalone" if _ok9\n'
        '                                                      else f"failed: {_m9x}")\n'
        "                                        else:\n", "standalone bell gate")
W = rep(W,
        '                        if (_ew.get("oneh") == "DEAD"\n'
        '                                and (_ew.get("star") or _ew.get("appr"))):\n',
        '                        if (_ew.get("oneh") == "DEAD"\n'
        '                                and (_ew.get("star") or _ew.get("appr"))\n'
        "                                and (not REVIVED_LONG_FAST\n"
        '                                     or (_ew["side"] == "LONG"\n'
        '                                         and _ew["go"] == "FAST"))):\n', "tier gate")

A = open(ROOT + "app.py", encoding="utf-8").read()
A = rep(A,
        "        if str(_ex.get(\"oneh\") or \"\").upper() != \"DEAD\":\n"
        "            continue                      # only the revived class\n",
        "        if str(_ex.get(\"oneh\") or \"\").upper() != \"DEAD\":\n"
        "            continue                      # only the revived class\n"
        "        if (_r[3] or \"\").upper() != \"LONG\" or str(_r[8] or \"\").upper() != \"FAST\":\n"
        "            continue                      # LONG + FAST only (2026-10-09 GO-entry study)\n",
        "board filter")
A = rep(A,
        '        "at the GO itself measured +0.10R on the star chase tier — the ledger "\n'
        '        "line below is that entry, forward. Each card is a revived GO from the "\n'
        '        "last 24 hours; 📥 Open takes it at the live price with the plan.")\n',
        '        "at the GO itself, replayed on 119 recorded GOs with the fire stop: LONGS "\n'
        '        "within 4h 79% win / +1.15% / +0.21R a trade (77), shorts 48% / −1.92%, "\n'
        '        "late GOs 52% / −1.74% (14–28 Sep) — so this board and its bell carry "\n'
        '        "LONG + FAST only; shorts and late GOs keep stamping for the record. The "\n'
        '        "ledger line below is the GO entry, forward. Each card is a revived GO "\n'
        '        "from the last 24 hours; 📥 Open takes it at the live price with the plan.")\n',
        "board caption")

BW = open(ROOT + "bottom_watch.py", encoding="utf-8").read()
BW = rep(BW,
        '        "star_short": "75% / +0.28R (16)"}\n',
        '        "star_short": "75% / +0.28R (16)",\n'
        '        "second": "no better (57 second prints after a failed first bounce: median coin −0.1%)",\n'
        '        "breadth": "did not sort it either (the share of coins printing with BTC, 157 coins)"}\n',
        "odds extra")
BW = rep(BW,
        '            f"({o[\'hindsight\']}) and it is known afterwards — no entry bell.\\n"\n',
        '            f"({o[\'hindsight\']}) and it is known afterwards — no entry bell. A second "\n'
        '            f"print after a failed first bounce measured {o[\'second\']}; market breadth "\n'
        '            f"{o[\'breadth\']}.\\n"\n', "message facts")

T = open(ROOT + ".tg_rules_test.py", encoding="utf-8").read()
T = rep(T,
        '                  (\'if _ew.get("star") or _ew.get("appr"):\\n                                            _ok9, _m9x = tg.send(_go9)\', "revived: stars + approved elite only"),\n',
        '                  (\'elif _ew.get("star") or _ew.get("appr"):\\n                                            _ok9, _m9x = tg.send(_go9)\', "revived: stars + approved elite only"),\n'
        '                  ("REVIVED_LONG_FAST = True\\n", "revived long+fast switch on"),\n'
        '                  (\'and REVIVED_LONG_FAST\\n                                                and not (_ew["side"] == "LONG"\\n                                                         and _ew["go"] == "FAST")):\', "revived bell skips shorts and late GOs"),\n',
        "tg test anchors")
T2 = open(ROOT + ".revived_board_test.py", encoding="utf-8").read()
T2 = rep(T2,
         '                  (\'if (_ew.get("oneh") == "DEAD"\\n                                and (_ew.get("star") or _ew.get("appr"))):\', "tier gated like the bell"),\n',
         '                  (\'if (_ew.get("oneh") == "DEAD"\\n                                and (_ew.get("star") or _ew.get("appr"))\\n                                and (not REVIVED_LONG_FAST\', "tier gated like the bell (long + fast)"),\n',
         "board test tier anchor")
T2 = rep(T2,
         '                  ("no closes yet", "empty ledger line")):\n',
         '                  ("no closes yet", "empty ledger line"),\n'
         '                  (\'if (_r[3] or "").upper() != "LONG" or str(_r[8] or "").upper() != "FAST":\', "board shows LONG + FAST only")):\n',
         "board test filter anchor")
for path, s in (("agent_worker.py", W), ("app.py", A), ("bottom_watch.py", BW), (".tg_rules_test.py", T), (".revived_board_test.py", T2)):
    with open(ROOT + path, "w", encoding="utf-8", newline="") as f:
        f.write(s)
print("patched: GO REVIVED long+fast (bell, tier, board) + bottom message facts")
