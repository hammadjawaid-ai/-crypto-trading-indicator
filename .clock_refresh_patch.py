"""2026-11-04 (user: "update these scores for paper trading for elite stars and elite revived and
also on the telegram notifications"): refresh the dated clock cells with the 4 Nov ledger and add
the ⭐ GO FAST / GO LATE timing read (held from the fire · entered at the bell) to the star card,
the ⭐ fire bell and the ⭐⚡ GO bells. Nothing in the reads/gates changes — only the printed
records and one new information line."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = "F:/Trading Indicator/"


def rep(src, old, new, label):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"ANCHOR {label!r} matched {n} times — nothing written")
    return src.replace(old, new)


# ───────────── clock_cells.py ─────────────
C = open(ROOT + "clock_cells.py", encoding="utf-8").read()
C = rep(C, 'STAR_MEASURED = "gated ⭐ record 09 Sep → 14 Oct"\n',
        'STAR_MEASURED = "gated ⭐ record 09 Sep → 04 Nov"   # 2026-11-04 refresh: 226 rung / 282 muted desk closes, gate stamped since 14 Oct, the same four rules reconstructed before\n', "star label")
C = rep(C,
        'STAR_CELLS = {\n'
        '    ("LONG", "05–09"): (75, 0.52, 20), ("LONG", "09–13"): (75, 0.50, 16),\n'
        '    ("LONG", "13–17"): (33, -0.40, 9), ("LONG", "17–21"): (73, 0.43, 22),\n'
        '    ("LONG", "21–01"): (75, 0.69, 28), ("LONG", "01–05"): None,       # closed by the gate\n'
        '    ("SHORT", "05–09"): (71, 0.57, 7), ("SHORT", "09–13"): (40, 0.02, 5),\n'
        '    ("SHORT", "13–17"): (86, 0.43, 7), ("SHORT", "17–21"): (76, 0.54, 25),\n'
        '    ("SHORT", "21–01"): (57, 0.22, 7), ("SHORT", "01–05"): None,\n'
        '}\n',
        'STAR_CELLS = {   # rung stars (gate pass), desk closes 09 Sep → 04 Nov, by side × FIRE window\n'
        '    ("LONG", "05–09"): (69, 0.44, 26), ("LONG", "09–13"): (71, 0.50, 21),\n'
        '    ("LONG", "13–17"): (27, -0.51, 11), ("LONG", "17–21"): (64, 0.41, 47),\n'
        '    ("LONG", "21–01"): (66, 0.42, 38), ("LONG", "01–05"): None,       # closed by the gate\n'
        '    ("SHORT", "05–09"): (71, 0.33, 17), ("SHORT", "09–13"): (45, -0.09, 11),\n'
        '    ("SHORT", "13–17"): (73, 0.21, 11), ("SHORT", "17–21"): (79, 0.60, 33),\n'
        '    ("SHORT", "21–01"): (82, 0.63, 11), ("SHORT", "01–05"): None,\n'
        '}\n', "star cells")
C = rep(C, 'REVIVED_STAR_MEASURED = "gated ⭐ star revived record 13 Sep → 14 Oct"\n'
           'REVIVED_CONV_MEASURED = "gated 💎 conviction revived record 13 Sep → 14 Oct"\n',
        'REVIVED_STAR_MEASURED = "⭐ star revived record 14 Sep → 04 Nov (DEAD at the hour then GO, from the fire price)"\n'
        'REVIVED_CONV_MEASURED = "💎 conviction revived record 14 Sep → 04 Nov (DEAD at the hour then GO, from the fire price)"\n', "revived labels")
C = rep(C,
        'REVIVED_STAR_CELLS = {     # desk, star DEAD at the hour then GO, two card rules passed\n'
        '    ("LONG", "05–09"): (69, 0.29, 13), ("LONG", "09–13"): (92, 0.75, 12), ("LONG", "13–17"): (43, -0.04, 7),\n'
        '    ("LONG", "17–21"): (67, 0.42, 9), ("LONG", "21–01"): (67, 0.38, 12), ("LONG", "01–05"): (50, 0.07, 12),\n'
        '    ("SHORT", "05–09"): (83, 0.67, 6), ("SHORT", "09–13"): (67, 0.37, 3), ("SHORT", "13–17"): (50, -0.08, 4),\n'
        '    ("SHORT", "17–21"): (79, 0.60, 14), ("SHORT", "01–05"): (67, 0.12, 9),\n'
        '}\n'
        'REVIVED_CONV_CELLS = {     # desk, conviction DEAD at the hour then GO, two card rules passed\n'
        '    ("LONG", "05–09"): (17, -0.44, 6), ("LONG", "09–13"): (0, -0.74, 3), ("LONG", "13–17"): (25, 0.02, 4),\n'
        '    ("LONG", "17–21"): (40, 0.47, 5), ("LONG", "21–01"): (80, 1.10, 5), ("LONG", "01–05"): (75, 1.52, 4),\n'
        '    ("SHORT", "05–09"): (67, 0.76, 3), ("SHORT", "09–13"): (33, -0.01, 3), ("SHORT", "13–17"): (33, 0.53, 3),\n'
        '    ("SHORT", "17–21"): (80, 0.68, 5), ("SHORT", "21–01"): (0, -1.01, 1),\n'
        '}\n',
        'REVIVED_STAR_CELLS = {     # 2026-11-04: star DEAD at the hour then GO (all), FIRE plan from the FIRE price, 14 Sep → 04 Nov, by the FIRE\'s window\n'
        '    ("LONG", "05–09"): (60, 0.14, 5), ("LONG", "09–13"): (59, 0.10, 17), ("LONG", "13–17"): (29, -0.38, 7),\n'
        '    ("LONG", "17–21"): (64, 0.24, 14), ("LONG", "21–01"): (50, -0.19, 10),\n'
        '    ("SHORT", "05–09"): (50, -0.29, 6), ("SHORT", "09–13"): (87, 0.57, 15), ("SHORT", "13–17"): (100, 0.75, 3),\n'
        '    ("SHORT", "17–21"): (92, 0.59, 12), ("SHORT", "21–01"): (83, 0.52, 6),\n'
        '}\n'
        'REVIVED_CONV_CELLS = {     # 2026-11-04: conviction DEAD at the hour then GO (all), from the FIRE price, 14 Sep → 04 Nov\n'
        '    ("LONG", "05–09"): (35, -0.40, 17), ("LONG", "09–13"): (58, 0.19, 31), ("LONG", "13–17"): (55, 1.00, 11),\n'
        '    ("LONG", "17–21"): (65, 0.47, 26), ("LONG", "21–01"): (68, 0.74, 19),\n'
        '    ("SHORT", "05–09"): (75, 0.27, 8), ("SHORT", "09–13"): (89, 0.91, 27), ("SHORT", "13–17"): (75, 0.73, 8),\n'
        '    ("SHORT", "17–21"): (77, 0.44, 13), ("SHORT", "21–01"): (56, 0.10, 16),\n'
        '}\n', "revived cells")
C = C.rstrip("\n") + '''


# ───────────── ⭐ GO FAST / GO LATE by timing (user 2026-11-04: "update these scores") ─────────────
# (held win %, held R, entered win %, entered R, n): HELD = the fire plan from the FIRE price
# (the bell's claim) · ENTERED = buying at the bell, same stop / TP1. Star GOs 14 Sep → 04 Nov,
# 15m candles, 48h, fees. Two keys: the FIRE's window (known at the fire, for the card and the
# ⭐ bell) and the GO's own window (known when the GO lands, for the GO bell). The one entry
# cell that pays is the early-morning GO (01–09 PKT): everything else entered at the bell ≈ 0.
GO_MEASURED = "⭐ GO record 14 Sep → 04 Nov"
GO_FAST_FIRE_CELLS = {
    ("LONG", "05–09"): (91, 0.73, 91, 0.34, 23), ("LONG", "09–13"): (75, 0.33, 72, 0.04, 40), ("LONG", "13–17"): (67, 0.23, 61, -0.04, 24),
    ("LONG", "17–21"): (66, 0.26, 62, -0.06, 50), ("LONG", "21–01"): (77, 0.56, 83, 0.23, 26),
    ("SHORT", "05–09"): (76, 0.31, 76, 0.01, 17), ("SHORT", "09–13"): (86, 0.56, 86, 0.17, 14), ("SHORT", "13–17"): (78, 0.41, 78, 0.08, 9),
    ("SHORT", "17–21"): (78, 0.45, 72, 0.01, 40), ("SHORT", "21–01"): (71, 0.50, 71, 0.11, 7),
}
GO_FAST_GO_CELLS = {
    ("LONG", "05–09"): (92, 0.73, 92, 0.33, 25), ("LONG", "09–13"): (79, 0.46, 78, 0.15, 47), ("LONG", "13–17"): (67, 0.13, 65, -0.08, 21),
    ("LONG", "17–21"): (61, 0.17, 59, -0.11, 41), ("LONG", "21–01"): (72, 0.47, 68, 0.05, 29),
    ("SHORT", "05–09"): (79, 0.40, 79, 0.03, 14), ("SHORT", "09–13"): (82, 0.47, 82, 0.13, 22), ("SHORT", "13–17"): (75, 0.41, 75, 0.06, 8),
    ("SHORT", "17–21"): (79, 0.45, 72, 0.00, 29), ("SHORT", "21–01"): (71, 0.45, 71, 0.05, 14),
}
GO_LATE_FIRE_CELLS = {
    ("LONG", "05–09"): (71, 0.23, 71, -0.02, 7), ("LONG", "09–13"): (83, 0.49, 61, 0.10, 18), ("LONG", "13–17"): (40, -0.17, 40, -0.38, 5),
    ("LONG", "17–21"): (60, 0.73, 60, -0.03, 10), ("LONG", "21–01"): (64, 0.10, 45, -0.17, 11),
    ("SHORT", "05–09"): (60, -0.12, 40, -0.28, 5), ("SHORT", "09–13"): (76, 0.30, 65, -0.06, 17), ("SHORT", "13–17"): (100, 0.77, 100, 0.53, 1),
    ("SHORT", "17–21"): (86, 0.53, 86, 0.15, 7), ("SHORT", "21–01"): (86, 0.46, 86, 0.14, 7),
}
GO_LATE_GO_CELLS = {
    ("LONG", "05–09"): (78, 0.60, 78, 0.18, 9), ("LONG", "09–13"): (78, 0.64, 67, 0.09, 18), ("LONG", "13–17"): (86, 0.29, 57, -0.02, 7),
    ("LONG", "17–21"): (57, 0.13, 43, -0.19, 14), ("LONG", "21–01"): (0, -0.91, 0, -0.93, 3),
    ("SHORT", "05–09"): (85, 0.48, 85, 0.08, 13), ("SHORT", "09–13"): (83, 0.44, 67, 0.05, 6), ("SHORT", "13–17"): (44, -0.30, 33, -0.44, 9),
    ("SHORT", "17–21"): (100, 0.59, 83, 0.30, 6), ("SHORT", "21–01"): (100, 0.80, 100, 0.32, 3),
}
# both sides pooled by the GO's window (the fallback when a side cell is thin)
GO_FAST_GO_POOLED = {"05–09": (87, 0.61, 87, 0.22, 39), "09–13": (80, 0.46, 78, 0.14, 69), "13–17": (69, 0.20, 66, -0.04, 29),
                     "17–21": (69, 0.29, 64, -0.06, 70), "21–01": (72, 0.47, 67, 0.05, 43)}
GO_LATE_GO_POOLED = {"05–09": (82, 0.53, 82, 0.12, 22), "09–13": (79, 0.59, 67, 0.08, 24), "13–17": (59, -0.04, 41, -0.26, 17),
                     "17–21": (70, 0.27, 55, -0.04, 20), "21–01": (50, -0.06, 50, -0.30, 6)}


def go_timing_line(kind: str, side: str, fired_at: float, go_at: float = None) -> str:
    """🕐 the ⭐ GO FAST / LATE timing read. Without go_at: the FIRE's window (for the card and
    the fire bell — what a GO on this fire has done). With go_at: the GO's own window (for the
    GO bell), with the entry call: buy-at-the-bell pays only when the GO lands 01–09 PKT."""
    kind = "LATE" if str(kind).upper() == "LATE" else "FAST"
    side = (side or "").upper()
    if go_at is None:
        cells = GO_FAST_FIRE_CELLS if kind == "FAST" else GO_LATE_FIRE_CELLS
        win = window_of(fired_at)
        c = cells.get((side, win))
        if c is None or c[4] < MIN_N:
            return (f"🕐 ⭐ GO {kind} for {win} PKT {side.lower()}s — thin ({0 if c is None else c[4]}), no record · {GO_MEASURED}")
        hw, hr, ew, er, n = c
        return (f"🕐 ⭐ GO {kind} for {win} PKT {side.lower()}s: held from the fire {hw}% / {hr:+.2f}R · "
                f"entered at the bell {ew}% / {er:+.2f}R ({n}) · {GO_MEASURED}")
    cells = GO_FAST_GO_CELLS if kind == "FAST" else GO_LATE_GO_CELLS
    pooled = GO_FAST_GO_POOLED if kind == "FAST" else GO_LATE_GO_POOLED
    win = window_of(go_at)
    c = cells.get((side, win)); src = f"{side.lower()}s"
    if c is None or c[4] < MIN_N:
        c = pooled.get(win); src = "both sides"
    if c is None or c[4] < MIN_N:
        return f"🕐 GO landing {win} PKT — thin, no entry call · {GO_MEASURED}"
    hw, hr, ew, er, n = c
    call = ("🟢 entry at the bell has paid here" if (er >= 0.10 and ew >= 65)
            else "🟡 hold read only — entry at the bell ≈ flat here" if er > -0.10
            else "🔴 hold read only — entry at the bell LOST here")
    return (f"🕐 GO landing {win} PKT ({src}): held from the fire {hw}% / {hr:+.2f}R · entered at the bell {ew}% / {er:+.2f}R ({n}) — "
            f"{call} · {GO_MEASURED}")
'''
with open(ROOT + "clock_cells.py", "w", encoding="utf-8", newline="") as f:
    f.write(C + "\n")

# ───────────── agent_worker.py ─────────────
W = open(ROOT + "agent_worker.py", encoding="utf-8").read()
W = rep(W,
        'STAR_REV_RANG_REC = ("revivals of rung stars 80% / +0.64R (46), FAST 87% / "\n'
        '                     "+0.74R (30) · desk 13 Sep → 14 Oct")\n'
        'STAR_REV_MUTED_REC = "revivals of muted stars 58% / +0.12R (55) · desk 13 Sep → 14 Oct"\n'
        'STAR_REV_ALL_REC = "all star revivals 68% / +0.36R (101) · desk 13 Sep → 14 Oct"\n',
        'STAR_REV_RANG_REC = ("revivals of rung stars 68% / +0.22R (44) held from the fire · "\n'
        '                     "entered at the GO ≈ −0.07R · 14 Sep → 04 Nov")   # 2026-11-04 refresh\n'
        'STAR_REV_MUTED_REC = "revivals of muted stars 68% / +0.24R (31) held from the fire · 14 Sep → 04 Nov"\n'
        'STAR_REV_ALL_REC = "all star revivals 67% / +0.21R (95) held from the fire · 14 Sep → 04 Nov"\n', "star rev recs")
W = rep(W,
        'STAR_REV_CLASS_REC = ("star revivals FAST 72% / +0.45R (58) · LATE 63% / +0.24R (43) · "\n'
        '                      "desk 13 Sep → 14 Oct")\n'
        'CONV_REV_CLASS_REC = ("conviction revivals FAST 57% / +0.63R (28) · LATE 21% / -0.15R (14) · "\n'
        '                      "desk 13 Sep → 14 Oct; 7-week replay LATE 52% / +0.04R (201)")\n',
        'STAR_REV_CLASS_REC = ("star revivals FAST 67% / +0.24R (48) · LATE 68% / +0.19R (47) held from the fire · "\n'
        '                      "entered at the GO FAST −0.07R · LATE −0.11R · 14 Sep → 04 Nov")   # 2026-11-04 refresh\n'
        'CONV_REV_CLASS_REC = ("conviction revivals FAST 63% / +0.47R (91) · LATE 68% / +0.40R (85) held from the fire · "\n'
        '                      "entered at the GO FAST −0.10R · LATE 0.00R · 14 Sep → 04 Nov")\n', "class recs")
# ⭐ fire bell: the GO FAST timing read for this fire's window, under the clock line
W = rep(W,
        '                                _msg9 = _msg9.replace(\n'
        '                                    "\\n", "\\n" + _gate9[1] + "\\n"\n'
        '                                    + clock_cells.star_line(\n'
        '                                        _pmx.get("side"), time.time())\n'
        '                                    + "\\n", 1)\n',
        '                                _msg9 = _msg9.replace(\n'
        '                                    "\\n", "\\n" + _gate9[1] + "\\n"\n'
        '                                    + clock_cells.star_line(\n'
        '                                        _pmx.get("side"), time.time())\n'
        '                                    + "\\n" + clock_cells.go_timing_line(   # 2026-11-04: what a GO FAST on this window has done\n'
        '                                        "FAST", _pmx.get("side"), time.time())\n'
        '                                    + "\\n", 1)\n', "star bell go line")
# ⭐⚡ GO bells (star fires): the GO-window read with the entry call, right after the ELITE GO line
W = rep(W,
        '                                    if _ew.get("oneh") == "DEAD":\n'
        '                                        # GO REVIVED is its own bell\n',
        '                                    if _ew.get("star"):\n'
        '                                        # 🕐 GO FAST / LATE timing read by the GO\'s own\n'
        '                                        # window, with the entry call (user 2026-11-04).\n'
        '                                        try:\n'
        '                                            _go9 = _go9.replace(\n'
        '                                                "\\n", "\\n" + clock_cells.go_timing_line(\n'
        '                                                    "LATE" if _age > 4 * 3600 else "FAST",\n'
        '                                                    _ew["side"], float(_ew.get("fired_at") or _ew_now),\n'
        '                                                    go_at=_ew_now) + "\\n", 1)\n'
        '                                        except Exception:\n'
        '                                            pass\n'
        '                                    if _ew.get("oneh") == "DEAD":\n'
        '                                        # GO REVIVED is its own bell\n', "go bell timing line")
with open(ROOT + "agent_worker.py", "w", encoding="utf-8", newline="") as f:
    f.write(W)

# ───────────── app.py: star card ─────────────
A = open(ROOT + "app.py", encoding="utf-8").read()
A = rep(A,
        '                + f"<br><span style=\'color:#ffd54a;font-size:0.8rem\'>"\n'
        '                + clock_cells.star_line(_sd, _ts) + "</span>"\n',
        '                + f"<br><span style=\'color:#ffd54a;font-size:0.8rem\'>"\n'
        '                + clock_cells.star_line(_sd, _ts) + "</span>"\n'
        '                + f"<br><span style=\'color:#9ad0ff;font-size:0.78rem\'>"   # 2026-11-04: GO FAST timing read for this fire\'s window\n'
        '                + clock_cells.go_timing_line("FAST", _sd, _ts) + "</span>"\n', "star card go line")
with open(ROOT + "app.py", "w", encoding="utf-8", newline="") as f:
    f.write(A)

# ───────────── guards ─────────────
G = open(ROOT + ".go_live_test.py", encoding="utf-8").read()
G = rep(G,
        "def _norm_sb(x):\n    return _strip_path_block(_strip_bank_chip(_strip_gate_chip((x or \"\")))).replace(_EGO_INS, \"\").replace(_CLOCK_INS, \"\").replace(_TP1_INS, _TP1_WAS)\n",
        "_GOT_INS = (\"                + f\\\"<br><span style='color:#9ad0ff;font-size:0.78rem'>\\\"   # 2026-11-04: GO FAST timing read for this fire's window\\n\"\n"
        "            \"                + clock_cells.go_timing_line(\\\"FAST\\\", _sd, _ts) + \\\"</span>\\\"\\n\")   # 2026-11-04 🕐 GO timing line\n"
        "\n\n"
        "def _norm_sb(x):\n    return _strip_path_block(_strip_bank_chip(_strip_gate_chip((x or \"\")))).replace(_GOT_INS, \"\").replace(_EGO_INS, \"\").replace(_CLOCK_INS, \"\").replace(_TP1_INS, _TP1_WAS)\n",
        "go_live stripper")
with open(ROOT + ".go_live_test.py", "w", encoding="utf-8", newline="") as f:
    f.write(G)
T = open(ROOT + ".clock_cells_test.py", encoding="utf-8").read()
T = rep(T, 'for h, side, want in ((6, "LONG", "TAKE"), (22, "LONG", "TAKE"), (14, "LONG", "THIN"), (2, "LONG", "DON\'T"), (18, "SHORT", "TAKE"), (10, "SHORT", "THIN"), (3, "SHORT", "DON\'T")):',
        'for h, side, want in ((6, "LONG", "TAKE"), (22, "LONG", "TAKE"), (14, "LONG", "DON\'T"), (2, "LONG", "DON\'T"), (18, "SHORT", "TAKE"), (10, "SHORT", "DON\'T"), (3, "SHORT", "DON\'T")):   # 2026-11-04 cells', "star verdicts")
T = rep(T,
        '                                  (14, "SHORT", True, "THIN", "thin on the desk (4)"),      # star short 13–17: thin both ways\n'
        '                                  (10, "LONG", True, "TAKE", "92% / +0.75R (12)"),         # star long 09–13: desk\n'
        '                                  (6, "LONG", False, "HALF", "63% / +0.51R (27)"),          # conviction long 05–09: desk 6 -> replay\n'
        '                                  (18, "LONG", False, "DON\'T", "46% / -0.01R (57)"),        # conviction long 17–21: desk 5 -> replay\n'
        '                                  (18, "SHORT", True, "TAKE", "79% / +0.60R (14)")):        # star short 17–21: desk\n',
        '                                  (14, "SHORT", True, "THIN", "thin on the desk (3)"),      # star short 13–17: thin both ways (2026-11-04 cells)\n'
        '                                  (10, "LONG", True, "HALF", "59% / +0.10R (17)"),         # star long 09–13: desk\n'
        '                                  (6, "LONG", False, "DON\'T", "35% / -0.40R (17)"),        # conviction long 05–09: desk\n'
        '                                  (18, "LONG", False, "TAKE", "65% / +0.47R (26)"),         # conviction long 17–21: desk\n'
        '                                  (18, "SHORT", True, "TAKE", "92% / +0.59R (12)")):        # star short 17–21: desk\n', "family verdicts")
T = rep(T, 'if "💎 conviction revivals, 7-week candle replay" not in cc.revived_line("LONG", T(22), False) or "gated ⭐ star revived record" not in cc.revived_line("LONG", T(10), True) \\\n',
        'if "💎 conviction revivals, 7-week candle replay" not in cc.revived_line("LONG", T(22), False) or "⭐ star revived record" not in cc.revived_line("LONG", T(10), True) \\\n', "family label")
T = rep(T, 'if not s.startswith("🕐 🟢 TAKE — 05–09 PKT longs 75% / +0.52R (20)") or "09 Sep → 14 Oct" not in s:\n',
        'if not s.startswith("🕐 🟢 TAKE — 05–09 PKT longs 69% / +0.44R (26)") or "09 Sep → 04 Nov" not in s:\n', "star line")
T = rep(T, 'd = cc.star_line("LONG", T(14))\nif "THIN" not in d or "thin, no time call" not in d:\n    fails.append(f"thin cell must say so: {d}")\n',
        'd = cc.star_line("LONG", T(14))\nif "DON\'T" not in d or "the time, not the card" not in d:   # 2026-11-04: 13–17 longs now 11 trades, a DON\'T\n    fails.append(f"13–17 long cell must blame the time: {d}")\n'
        '# 🕐 GO FAST / LATE timing read (2026-11-04)\n'
        'gt = cc.go_timing_line("FAST", "LONG", T(6))\n'
        'if not gt.startswith("🕐 ⭐ GO FAST for 05–09 PKT longs: held from the fire 91% / +0.73R · entered at the bell 91% / +0.34R (23)") or "14 Sep → 04 Nov" not in gt:\n'
        '    fails.append(f"go timing (fire window): {gt}")\n'
        'gb = cc.go_timing_line("FAST", "LONG", T(2), go_at=T(6))\n'
        'if "GO landing 05–09 PKT (longs): held from the fire 92% / +0.73R · entered at the bell 92% / +0.33R (25)" not in gb or "🟢 entry at the bell has paid here" not in gb:\n'
        '    fails.append(f"go timing (GO window, pays): {gb}")\n'
        'gb2 = cc.go_timing_line("FAST", "LONG", T(2), go_at=T(18))\n'
        'if "🔴 hold read only — entry at the bell LOST here" not in gb2 or "(longs)" not in gb2:\n'
        '    fails.append(f"go timing (GO window, lost): {gb2}")\n'
        'gb3 = cc.go_timing_line("LATE", "SHORT", T(2), go_at=T(14))\n'
        'if "(both sides)" not in gb3 or "59% / -0.04R" not in gb3:   # short LATE 13–17 thin (9) -> pooled\n'
        '    fails.append(f"go timing (thin -> pooled): {gb3}")\n'
        'if "thin (7), no record" not in cc.go_timing_line("LATE", "LONG", T(6)):\n'
        '    fails.append("thin fire-window cell must say so")\n'
        'for need, lab in (("+ \\"\\\\n\\" + clock_cells.go_timing_line(   # 2026-11-04: what a GO FAST on this window has done", "star bell go line"),\n'
        '                  ("                                    if _ew.get(\\"star\\"):\\n                                        # 🕐 GO FAST / LATE timing read by the GO\'s own", "go bell timing block")):\n'
        '    if need not in W:\n'
        '        fails.append(f"worker missing: {lab}")\n'
        'if "+ clock_cells.go_timing_line(\\"FAST\\", _sd, _ts) + \\"</span>\\"" not in A:\n'
        '    fails.append("star card must carry the GO timing line")\n', "thin → go timing tests")
with open(ROOT + ".clock_cells_test.py", "w", encoding="utf-8", newline="") as f:
    f.write(T)
R = open(ROOT + ".revival_bells_test.py", encoding="utf-8").read()
R = rep(R, 'if "class: FAST — star revivals FAST 72% / +0.45R (58) · LATE 63% / +0.24R (43)" not in out or "shorts entered at the GO" in out:',
        'if "class: FAST — star revivals FAST 67% / +0.24R (48) · LATE 68% / +0.19R (47)" not in out or "shorts entered at the GO" in out:', "rev test star")
R = rep(R, 'l.startswith("class: LATE — conviction revivals FAST 57% / +0.63R (28) · LATE 21% / -0.15R (14)")',
        'l.startswith("class: LATE — conviction revivals FAST 63% / +0.47R (91) · LATE 68% / +0.40R (85)")', "rev test conv")
with open(ROOT + ".revival_bells_test.py", "w", encoding="utf-8", newline="") as f:
    f.write(R)
print("patched: clock_cells (star + revived cells, GO timing cells + line) · worker (records, ⭐ bell + GO bell lines) · app (star card line) · tests")
