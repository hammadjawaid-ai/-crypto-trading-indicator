"""GO for the whole elite family (user 2026-10-06: "I want the go revived for
elite also not just stars … and it should also have separate notification on
telegram"). Detection runs for every elite-family watch entry; a DEAD-at-1h
fire that ignites rings a STANDALONE revived bell whether or not its fire was
on the phone (⭐⚡ for stars, 💎⚡ for the rest); a LIVE fire that ignites
replies in its thread when it has one. Stamps: star_go (stars) / elite_go
(others), both carrying the bell status; the star_go_chase control tier stays
star-only. The TG_RULES=False path keeps its old star-only revival."""
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
W = rep(W,
        '                    if (_ew.get("star") and _ew.get("go") is None\n'
        "                            and not _stopped and _prg >= 0.25):\n",
        "                    # (user 2026-10-06: GO for the whole elite family, not\n"
        "                    # just stars — desk 13-28 Sep: DEAD-then-ignited non-star\n"
        "                    # elite 59% / +0.63R (86), stars 68% / +0.35R (56).)\n"
        '                    if (_ew.get("fam", "elite") == "elite"\n'
        '                            and _ew.get("go") is None\n'
        "                            and not _stopped and _prg >= 0.25):\n", "GO gate")
W = rep(W,
        '                            _bell9 = "not-buzzed (fire not on the phone)"\n'
        '                            if (_ew.get("buzzed")\n'
        '                                    and _ew.get("fam", "elite") == "elite"):\n'
        "                                try:\n"
        "                                    _go9 = rung_stats.go_text(\n"
        "                                        _ew, _prg, _age, _ew_px,\n"
        "                                        _ew_now)\n"
        '                                    if _ew.get("oneh") == "DEAD":\n'
        "                                        # ⭐⚡ GO REVIVED is its own\n"
        "                                        # bell (user 2026-10-05:\n"
        '                                        # "have a GO revived as a\n'
        '                                        # separate one") — standalone,\n'
        "                                        # not a thread reply.\n"
        "                                        _ok9, _m9x = tg.send(_go9)\n"
        '                                        _bell9 = ("sent-standalone" if _ok9\n'
        '                                                  else f"failed: {_m9x}")\n'
        "                                    else:\n"
        "                                        _ok9, _m9x, _ = tg.send_thread(\n"
        "                                            _go9,\n"
        '                                            reply_to=_ew.get("tg_ids"))\n'
        '                                        _bell9 = ("sent-thread" if _ok9\n'
        '                                                  else f"failed: {_m9x}")\n'
        "                                    n_alerts += 1\n"
        "                                except Exception as _go_exc:\n",
        '                            _bell9 = "not-buzzed (LIVE fire not on the phone)"\n'
        "                            if True:\n"
        "                                try:\n"
        "                                    _go9 = rung_stats.go_text(\n"
        "                                        _ew, _prg, _age, _ew_px,\n"
        "                                        _ew_now)\n"
        '                                    if _ew.get("oneh") == "DEAD":\n'
        "                                        # GO REVIVED is its own bell\n"
        "                                        # for EVERY elite-family fire,\n"
        "                                        # heard or not (user 2026-10-05\n"
        '                                        # "separate one"; 2026-10-06\n'
        '                                        # "for elite also, separate\n'
        '                                        # notification").\n'
        "                                        _ok9, _m9x = tg.send(_go9)\n"
        '                                        _bell9 = ("sent-standalone" if _ok9\n'
        '                                                  else f"failed: {_m9x}")\n'
        '                                    elif _ew.get("buzzed"):\n'
        "                                        _ok9, _m9x, _ = tg.send_thread(\n"
        "                                            _go9,\n"
        '                                            reply_to=_ew.get("tg_ids"))\n'
        '                                        _bell9 = ("sent-thread" if _ok9\n'
        '                                                  else f"failed: {_m9x}")\n'
        '                                    if _bell9.startswith("sent"):\n'
        "                                        n_alerts += 1\n"
        "                                except Exception as _go_exc:\n", "GO bells")
W = rep(W,
        '                        elif (_ew.get("buzzed")\n'
        '                                and _ew.get("oneh") == "DEAD"):\n'
        "                            tg.send(\n"
        "                                f\"⭐⚡ *GO — {_ew['base']} \"\n",
        '                        elif (_ew.get("buzzed") and _ew.get("star")\n'
        '                                and _ew.get("oneh") == "DEAD"):\n'
        "                            tg.send(\n"
        "                                f\"⭐⚡ *GO — {_ew['base']} \"\n", "old path star-only")
W = rep(W,
        '                        store.record_signal("star_go", {\n'
        '                            "symbol": _ew["symbol"],\n'
        '                            "base": _ew["base"],\n'
        '                            "side": _ew["side"],\n'
        '                            "tier": _ew["go"],\n'
        '                            "score": round(_age / 60.0, 1),\n'
        '                            "entry": _e0, "stop": _ew["stop"],\n'
        '                            "tp1": _ew["tp1"], "oneh": _ew.get("oneh"),\n'
        '                            "bell": _bell9})\n'
        '                        if _ew["go"] == "FAST":\n',
        '                        store.record_signal(\n'
        '                            "star_go" if _ew.get("star") else "elite_go", {\n'
        '                            "symbol": _ew["symbol"],\n'
        '                            "base": _ew["base"],\n'
        '                            "side": _ew["side"],\n'
        '                            "tier": _ew["go"],\n'
        '                            "score": round(_age / 60.0, 1),\n'
        '                            "entry": _e0, "stop": _ew["stop"],\n'
        '                            "tp1": _ew["tp1"], "oneh": _ew.get("oneh"),\n'
        '                            "star": bool(_ew.get("star")),\n'
        '                            "bell": _bell9})\n'
        '                        if _ew["go"] == "FAST" and _ew.get("star"):\n', "stamp + chase star-only")

R = open(ROOT + "rung_stats.py", encoding="utf-8").read()
R = rep(R,
        "        go = con.execute(\"SELECT symbol, side, ts FROM signals \"\n"
        "                         \"WHERE stream='star_go'\").fetchall()\n",
        "        go = con.execute(\"SELECT symbol, side, ts FROM signals \"\n"
        "                         \"WHERE stream IN ('star_go', 'elite_go')\").fetchall()\n",
        "load both GO streams")
R = rep(R,
        "    star = bool(ew.get(\"star\"))\n"
        "    st = classes(\"elite_star\" if star else \"elite_conv\", now, db_path)\n"
        "    C = st[\"cls\"]\n"
        "    fam = \"⭐ stars\" if star else \"elite fires\"\n"
        "    base, side, when = ew[\"base\"], ew[\"side\"], pkt_hm(now)\n"
        "    if ew.get(\"oneh\") == \"LIVE\":\n"
        "        return (f\"⏱ *{base} {side} · 1H LIVE at {when} PKT · HOLD FULL*\\n\"\n"
        "                f\"{prg * 100:+.0f}% of the path at 60 min · LIVE class \"\n"
        "                f\"({fam}) {rec(C['live'])}\\n{stamp(st)}\")\n"
        "    if star:\n"
        "        l3 = (f\"DEAD then ignited: {rec(C['dead_go'])} · DEAD never ignited: \"\n"
        "              f\"{rec(C['dead_nogo'])}\")\n"
        "    else:\n"
        "        l3 = (f\"DEAD class ({fam}): {rec(C['dead'])} — the ignition split is \"\n"
        "              f\"measured on ⭐ stars only\")\n",
        "    star = bool(ew.get(\"star\"))\n"
        "    st = classes(\"elite_star\" if star else \"elite_conv\", now, db_path)\n"
        "    C = st[\"cls\"]\n"
        "    fam = \"⭐ stars\" if star else \"elite fires\"\n"
        "    base, side, when = ew[\"base\"], ew[\"side\"], pkt_hm(now)\n"
        "    if ew.get(\"oneh\") == \"LIVE\":\n"
        "        return (f\"⏱ *{base} {side} · 1H LIVE at {when} PKT · HOLD FULL*\\n\"\n"
        "                f\"{prg * 100:+.0f}% of the path at 60 min · LIVE class \"\n"
        "                f\"({fam}) {rec(C['live'])}\\n{stamp(st)}\")\n"
        "    l3 = (f\"DEAD then ignited ({fam}): {rec(C['dead_go'])} · DEAD never \"\n"
        "          f\"ignited: {rec(C['dead_nogo'])}\")\n", "verdict split for every family")
R = rep(R,
        "    st = classes(\"elite_star\", now, db_path)\n"
        "    C = st[\"cls\"]\n"
        "    base, side = ew[\"base\"], ew[\"side\"]\n"
        "    late = age_s > 4 * 3600\n",
        "    star = bool(ew.get(\"star\"))\n"
        "    st = classes(\"elite_star\" if star else \"elite_conv\", now, db_path)\n"
        "    C = st[\"cls\"]\n"
        "    fam = \"⭐ stars\" if star else \"elite fires\"\n"
        "    emo = \"⭐⚡\" if star else \"💎⚡\"\n"
        "    base, side = ew[\"base\"], ew[\"side\"]\n"
        "    late = age_s > 4 * 3600\n", "go family")
R = rep(R,
        "    head = (f\"⭐⚡ *GO — {base} {side} · {'REVIVED · ' if rev else ''}PROTECT · \"\n",
        "    head = (f\"{emo} *GO — {base} {side} · {'REVIVED · ' if rev else ''}PROTECT · \"\n",
        "go head")
R = rep(R,
        "    if ew.get(\"oneh\") == \"DEAD\":\n"
        "        lab, c = \"DEAD then ignited\", C[\"dead_go\"]\n"
        "    else:\n"
        "        lab, c = \"ignited within 4h\", C[\"go4h\"]\n",
        "    if ew.get(\"oneh\") == \"DEAD\":\n"
        "        lab, c = f\"DEAD then ignited ({fam})\", C[\"dead_go\"]\n"
        "    else:\n"
        "        lab, c = f\"ignited within 4h ({fam})\", C[\"go4h\"]\n", "go class label")

T = open(ROOT + ".tg_rules_test.py", encoding="utf-8").read()
T = rep(T,
        'if "measured on ⭐ stars only" not in v_plain or "(elite fires)" not in v_plain:\n'
        '    fails.append("non-star verdict must say the split is star-only")\n',
        'if "DEAD then ignited (elite fires):" not in v_plain:\n'
        '    fails.append("non-star verdict must carry the elite ignition split")\n'
        'ge = rs.go_text(dict(ew, star=False, oneh="DEAD", entry0=0.0121, stop=0.0119), 0.26, 2.0 * H, 0.01215, NOW, DB)\n'
        'if not ge.startswith("💎⚡ *GO — GLMR LONG · REVIVED · PROTECT · 13:40 PKT (2.0h after the fire)*") or "DEAD then ignited (elite fires)" not in ge:\n'
        '    fails.append(f"elite GO revived text wrong:\\n{ge}")\n',
        "elite go text")
T = rep(T,
        '             "holding it: hold to TP1 / TP2, do not bank early · ignited within 4h 86% / +0.67R (28)",\n',
        '             "holding it: hold to TP1 / TP2, do not bank early · ignited within 4h (⭐ stars) 86% / +0.67R (28)",\n',
        "go label star")
T = rep(T, '"DEAD then ignited 70% / +0.26R (10)" not in g2', '"DEAD then ignited (⭐ stars) 70% / +0.26R (10)" not in g2', "go2 label")
T = rep(T,
        'for m in (day_msg, night_msg, v_live, v_dead, v_plain, g, g2, fz_n, fz_d, ar, sb):\n',
        'for m in (day_msg, night_msg, v_live, v_dead, v_plain, g, g2, ge, fz_n, fz_d, ar, sb):\n', "markdown loop")
T = rep(T,
        '                  (\'_bell9 = "not-buzzed (fire not on the phone)"\', "GO bell status default"),\n',
        '                  (\'_bell9 = "not-buzzed (LIVE fire not on the phone)"\', "GO bell status default"),\n'
        '                  (\'if (_ew.get("fam", "elite") == "elite"\\n                            and _ew.get("go") is None\', "GO for the whole elite family"),\n'
        '                  (\'"star_go" if _ew.get("star") else "elite_go", {\', "elite_go stamp"),\n'
        '                  (\'if _ew["go"] == "FAST" and _ew.get("star"):\', "chase tier star-only"),\n'
        '                  (\'elif (_ew.get("buzzed") and _ew.get("star")\\n                                and _ew.get("oneh") == "DEAD"):\', "old path stays star-only"),\n'
        '                  ("WHERE stream IN (\'star_go\', \'elite_go\')", "classes read both GO streams"),\n',
        "wiring anchors")
T = rep(T, 'if not (0 < W.find("_bell9 = \\"not-buzzed") < W.find(\'"bell": _bell9})\') < W.find(\'if _ew["go"] == "FAST":\')):\n',
        'if not (0 < W.find("_bell9 = \\"not-buzzed") < W.find(\'"bell": _bell9})\') < W.find(\'if _ew["go"] == "FAST" and _ew.get("star"):\')):\n',
        "order anchor")
# the revived bell must not depend on buzzed: no `buzzed` check between the DEAD test and tg.send(_go9)
T = rep(T, "# persistence round-trip (the two helpers run standalone)\n",
        '_i_d = W.find(\'if _ew.get("oneh") == "DEAD":\\n                                        # GO REVIVED is its own bell\')\n'
        '_i_s = W.find("_ok9, _m9x = tg.send(_go9)")\n'
        'if not (0 < _i_d < _i_s) or "buzzed" in W[_i_d:_i_s]:\n'
        '    fails.append("the revived bell must ring whether or not the fire was on the phone")\n'
        "# persistence round-trip (the two helpers run standalone)\n", "revived unconditional")
R_ = R
for need in ("WHERE stream IN ('star_go', 'elite_go')",):
    if need not in R_:
        raise SystemExit("rung_stats anchor missing after patch")
for path, s in (("agent_worker.py", W), ("rung_stats.py", R), (".tg_rules_test.py", T)):
    with open(ROOT + path, "w", encoding="utf-8", newline="") as f:
        f.write(s)
print("patched: GO for the whole elite family, standalone revived bell for every elite fire")
