"""🧵📵 TG RULES 2026-10-05 — the user's mute list + the rung-thread phone.

User: "Mute the following rows: Apex, Prime, Early Movers, Prime Entry, Live
Executor Safety, Elite conviction (your call shall we keep it or not), Morning
and evening reports — rest bring the ones we discussed."

ONE switch in agent_worker.py: TG_RULES = True. False = the phone exactly as
the git tag telegram-baseline-2026-10-05 (his one-word "revert telegram").
Every anchor below must match exactly once (twice for the two digest sends)
or nothing is written."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = "F:/Trading Indicator/"


def rep(src, old, new, label, n_expected=1):
    n = src.count(old)
    if n != n_expected:
        raise SystemExit(f"ANCHOR {label!r} matched {n} times (expected "
                         f"{n_expected}) — aborting, nothing written")
    return src.replace(old, new)


W = open(ROOT + "agent_worker.py", encoding="utf-8").read()

# ── 0. import + the switch ──────────────────────────────────────────────
W = rep(W, "import buzz_clock\n", "import buzz_clock\nimport rung_stats\n",
        "rung_stats import")
W = rep(W, '_MUTE_R9 = lambda *_a, **_k: (False, "roster9-muted")\n',
        '_MUTE_R9 = lambda *_a, **_k: (False, "roster9-muted")\n'
        "# 📵🧵 TG RULES (user 2026-10-05: \"Mute the following rows: Apex, Prime,\n"
        "# Early Movers, Prime Entry, Live Executor Safety, Elite conviction (your\n"
        "# call), Morning and evening reports — rest bring the ones we discussed\").\n"
        "# ONE switch. True = the rung-thread phone: ⭐ star / 💎🏆 A-GRADE / ⚡🔥\n"
        "# ARRIVAL bells lead with an action word (TAKE · TAKE HALF — a label by\n"
        "# PKT hour, never a gate) and carry measurement stamps; the ⏱ verdict,\n"
        "# ⭐⚡ GO and ❄️ FREEZE arrive as REPLIES in the fire's thread; the 09:00\n"
        "# PKT RUNG-1 SCOREBOARD; and every _MUTE_RULES site below is silent.\n"
        "# False = the phone exactly as the git tag telegram-baseline-2026-10-05\n"
        "# (the user's one-word \"revert telegram\"). Records, desk tiers, boards\n"
        "# and demo feeds never depend on this flag.\n"
        "TG_RULES = True\n"
        "_MUTE_RULES = _MUTE_R9 if TG_RULES else tg.send\n"
        "# 🧵 thread memory: (symbol, side) -> {ts, ids} of the fire bell the phone\n"
        "# heard, so a watch entry created after the send still answers in-thread.\n"
        "_TG_THREADS: dict = {}\n", "switch block")

# ── 1. _ego_add adopts the thread of a fire bell already sent ───────────
W = rep(W,
        '             "froze": False, "buzzed": False, "fam": fam,\n'
        '             "fired_at": _t9})\n'
        "        del _EGO_WATCH[:-80]\n",
        '             "froze": False, "buzzed": False, "fam": fam,\n'
        '             "fired_at": _t9})\n'
        "        try:\n"
        "            # 🧵 a fire bell already went out for this coin+side (<2h):\n"
        "            # adopt its thread so verdict / GO / freeze reply to it.\n"
        "            _th = _TG_THREADS.get((sym, side))\n"
        '            if (_th and fam == "elite"\n'
        '                    and _t9 - float(_th.get("ts") or 0) < 2 * 3600):\n'
        '                _EGO_WATCH[-1]["buzzed"] = True\n'
        '                _EGO_WATCH[-1]["tg_ids"] = _th.get("ids")\n'
        "        except Exception:\n"
        "            pass\n"
        "        del _EGO_WATCH[:-80]\n", "ego_add thread adoption")

# ── 2. _push roster: APEX, PRIME, PRIME ENTRY (em), EARLY MOVERS (emrest) off ─
W = rep(W,
        '        if key_prefix not in ("moon", "em", "emrest",\n'
        '                              "apex", "prime"):\n',
        '        if key_prefix not in (("moon",) if TG_RULES else\n'
        '                              ("moon", "em", "emrest",\n'
        '                               "apex", "prime")):\n'
        "            # 📵 TG RULES 2026-10-05: 🏆 APEX, 🥇 PRIME, ⭐🚀 PRIME ENTRY\n"
        "            # (em) and ⚡ EARLY MOVERS (emrest) off the phone on the\n"
        "            # user's row list; records, boards, desk tiers and demo\n"
        "            # feeds untouched. Revert: TG_RULES = False.\n",
        "push roster")

# ── 3. APEX V2 bell off (the APEX row) ──────────────────────────────────
W = rep(W,
        "                    tg.send(_fmt_apex_v2(_sig2, _px2, _rv2)\n"
        "                            + _kr_note(_sig2))\n",
        "                    # 📵 TG RULES 2026-10-05: the APEX row is muted —\n"
        "                    # V2 included (desk tier apex_v2 + its 1h stamps\n"
        "                    # continue). Revert: TG_RULES = False.\n"
        "                    _MUTE_RULES(_fmt_apex_v2(_sig2, _px2, _rv2)\n"
        "                                + _kr_note(_sig2))\n", "apex v2 mute")

# ── 4. morning + evening reports off (two identical send lines) ─────────
W = rep(W,
        '            ok, _dmsg = tg.send("\\n".join(lines))\n',
        '            ok, _dmsg = _MUTE_RULES("\\n".join(lines))   # 📵 TG RULES: reports off\n',
        "digest sends", n_expected=2)

# ── 5. live executor: receipts + mode notes off; 🛑 kill / ⛔ halt / ⚠️ Bybit stay ─
W = rep(W,
        '        for _po in _lx.get("opened", []):\n'
        "            ok, _ = tg.send(\n"
        '                f"💸 *LIVE OPENED*',
        '        for _po in _lx.get("opened", []):\n'
        "            # 📵 TG RULES 2026-10-05: live receipts off the phone; the\n"
        "            # 🛑 kill switch, ⛔ daily halt and ⚠️ Bybit-unreachable\n"
        "            # alerts below stay live (real-money safety).\n"
        "            ok, _ = _MUTE_RULES(\n"
        '                f"💸 *LIVE OPENED*', "live opened")
W = rep(W,
        "            ok, _ = tg.send(\n"
        '                f"💸 *LIVE CLOSED*',
        "            ok, _ = _MUTE_RULES(\n"
        '                f"💸 *LIVE CLOSED*', "live closed")
W = rep(W,
        '                ok, _ = tg.send(f"👀 *LIVE* — {_note}")\n',
        '                ok, _ = _MUTE_RULES(f"👀 *LIVE* — {_note}")\n',
        "live adopted")
W = rep(W,
        "                    ok, _ = tg.send(\n"
        '                        f"🤖💸 *LIVE EXECUTOR {_note}* — 🎮→💸 GEN 10 "',
        "                    ok, _ = _MUTE_RULES(\n"
        '                        f"🤖💸 *LIVE EXECUTOR {_note}* — 🎮→💸 GEN 10 "',
        "live mode gen10")
W = rep(W,
        "                    ok, _ = tg.send(\n"
        '                        f"🤖💸 *LIVE EXECUTOR {_note}* — trading the "',
        "                    ok, _ = _MUTE_RULES(\n"
        '                        f"🤖💸 *LIVE EXECUTOR {_note}* — trading the "',
        "live mode plain")
W = rep(W,
        "                ok, _ = tg.send(\n"
        '                    f"💸 *GEN10 LIVE OPENED*',
        "                ok, _ = _MUTE_RULES(\n"
        '                    f"💸 *GEN10 LIVE OPENED*', "gen10 opened")

# ── 6. A-grade banner: action head + next line under the rules ──────────
W = rep(W, "def _agrade_banner(seat, conf, rr):\n",
        'def _agrade_banner(seat, conf, rr, head=None, nxt=""):\n',
        "agrade banner signature")
W = rep(W,
        '    return ("💎🏆 *ELITE A-GRADE — the measured best cell*\\n"\n'
        '            f"_{seat_txt} · 🎯 conf {conf_txt} · LONG · TP1 {rr_txt} away. "\n',
        '    return ((head or "💎🏆 *ELITE A-GRADE — the measured best cell*") + "\\n"\n'
        '            f"_{seat_txt} · 🎯 conf {conf_txt} · LONG · TP1 {rr_txt} away. "\n',
        "agrade banner head")
W = rep(W,
        '            f"trade until the forward ledger speaks.{fwd}_\\n")\n',
        '            f"trade until the forward ledger speaks.{fwd}_\\n"\n'
        '            + (nxt + "\\n" if nxt else ""))\n', "agrade banner tail")
W = rep(W,
        "                    if _ag9:\n"
        "                        try:\n"
        "                            _msg9 = _agrade_banner(\n"
        "                                _seat9, _cf9, _plan_rr(_pmx)) + _msg9\n",
        "                    if _ag9:\n"
        "                        try:\n"
        "                            _msg9 = _agrade_banner(\n"
        "                                _seat9, _cf9, _plan_rr(_pmx),\n"
        "                                head=(rung_stats.agrade_head(\n"
        "                                    _pmx, time.time())\n"
        "                                      if TG_RULES else None),\n"
        "                                nxt=((rung_stats.next_line(time.time())\n"
        '                                      + "\\n"\n'
        "                                      + rung_stats.stamp_now(time.time()))\n"
        '                                     if TG_RULES else "")) + _msg9\n',
        "agrade banner call")

# ── 7. the elite send: thread anchors for star / A-grade, plain conviction off ─
W = rep(W,
        "                    ok, _m9 = tg.send(_msg9)\n"
        "                    n_alerts += 1 if ok else 0\n"
        "                    # ④ mark the fire BUZZED so the 1H VERDICT bell\n",
        "                    _ids9 = None\n"
        "                    if TG_RULES and (_star9 or _ag9):\n"
        "                        # 🧵 TG RULES (user 2026-10-05): the rung-1 bells\n"
        "                        # are thread anchors — the ⏱ verdict / ⭐⚡ GO /\n"
        "                        # ❄️ freeze answer INSIDE this message. A star\n"
        "                        # fire is re-set in the action format (TAKE /\n"
        "                        # TAKE HALF label by PKT hour — never a gate);\n"
        "                        # the A-GRADE keeps its banner + plan block.\n"
        "                        if _star9:\n"
        "                            try:\n"
        "                                _msg9 = rung_stats.star_fire(\n"
        "                                    _pmx, _cf9, time.time(), _cbits,\n"
        "                                    _kr_note(_pmx))\n"
        "                                if _ag9:\n"
        "                                    _msg9 = _agrade_banner(\n"
        "                                        _seat9, _cf9, _plan_rr(_pmx),\n"
        "                                        head=rung_stats.agrade_head(\n"
        "                                            _pmx, time.time())) + _msg9\n"
        "                            except Exception as _rs_exc:\n"
        '                                print("  star fire format error:",\n'
        "                                      _rs_exc, flush=True)\n"
        "                        ok, _m9, _ids9 = tg.send_thread(_msg9)\n"
        "                    elif TG_RULES:\n"
        "                        # 📵 plain 💎 conviction OFF the phone — Claude's\n"
        "                        # call on the user's \"your call\" (2026-10-05):\n"
        "                        # the stream is rally-only (-0.12R before the\n"
        "                        # rally / +0.17R in it / -0.21R replay); its two\n"
        "                        # measured subsets, ⭐ star and 💎🏆 A-grade, keep\n"
        "                        # ringing and carry the thread. Records, desk,\n"
        "                        # boards and 1h stamps all continue. Revert:\n"
        "                        # TG_RULES = False, or route this branch to tg.send.\n"
        "                        ok, _m9 = _MUTE_RULES(_msg9)\n"
        "                    else:\n"
        "                        ok, _m9 = tg.send(_msg9)\n"
        "                    n_alerts += 1 if ok else 0\n"
        "                    # ④ mark the fire BUZZED so the 1H VERDICT bell\n",
        "elite send")
W = rep(W,
        "                    if ok:\n"
        "                        try:\n"
        "                            for _ewb in _EGO_WATCH:\n"
        '                                if (_ewb["symbol"] == _pmx.get(\n'
        '                                        "symbol")\n'
        '                                        and _ewb["side"] == (\n'
        '                                            _pmx.get("side") or ""\n'
        "                                        ).upper()):\n"
        '                                    _ewb["buzzed"] = True\n'
        "                        except Exception:\n"
        "                            pass\n",
        "                    if ok:\n"
        "                        try:\n"
        "                            for _ewb in _EGO_WATCH:\n"
        '                                if (_ewb["symbol"] == _pmx.get(\n'
        '                                        "symbol")\n'
        '                                        and _ewb["side"] == (\n'
        '                                            _pmx.get("side") or ""\n'
        "                                        ).upper()\n"
        '                                        and _ewb.get("fam", "elite")\n'
        '                                        == "elite"):\n'
        '                                    _ewb["buzzed"] = True\n'
        "                                    if _ids9:\n"
        '                                        _ewb["tg_ids"] = _ids9\n'
        "                            # 🧵 thread memory for a watch entry that\n"
        "                            # is created after this send (star hook).\n"
        '                            _TG_THREADS[(_pmx.get("symbol"),\n'
        '                                         (_pmx.get("side") or "")\n'
        "                                         .upper())] = {\n"
        '                                "ts": time.time(), "ids": _ids9}\n'
        "                        except Exception:\n"
        "                            pass\n", "buzzed marking")

# ── 8. ignition checker: verdict / GO / freeze as thread replies ────────
W = rep(W,
        '                        if _ew.get("buzzed") or _ew.get("appr"):\n',
        "                        if TG_RULES:\n"
        "                            # 🧵 the verdict answers in the fire's thread,\n"
        "                            # only for fires the phone heard (star /\n"
        "                            # A-grade anchors). HOLD FULL (LIVE) ·\n"
        "                            # HOLD — no add, no cut (DEAD).\n"
        '                            if (_ew.get("buzzed")\n'
        '                                    and _ew.get("fam", "elite") == "elite"):\n'
        "                                try:\n"
        "                                    tg.send_thread(\n"
        "                                        rung_stats.verdict_text(\n"
        "                                            _ew, _prg, _ew_now),\n"
        '                                        reply_to=_ew.get("tg_ids"))\n'
        "                                    n_alerts += 1\n"
        "                                except Exception as _vt_exc:\n"
        '                                    print("  verdict thread error:",\n'
        "                                          _vt_exc, flush=True)\n"
        '                        elif _ew.get("buzzed") or _ew.get("appr"):\n', "verdict thread")
W = rep(W,
        '                        if (_ew.get("buzzed")\n'
        '                                and _ew.get("oneh") == "DEAD"):\n'
        "                            tg.send(\n"
        "                                f\"⭐⚡ *GO — {_ew['base']} \"\n",
        "                        if TG_RULES:\n"
        "                            # 🧵 GO answers in the thread for EVERY heard\n"
        "                            # star that ignites (+25% of the path), fast\n"
        "                            # or late. PROTECT — a hold bell with the\n"
        "                            # honest \"not in it\" line (R left to TP1 +\n"
        "                            # the GO-entry control record).\n"
        '                            if (_ew.get("buzzed")\n'
        '                                    and _ew.get("fam", "elite") == "elite"):\n'
        "                                try:\n"
        "                                    tg.send_thread(\n"
        "                                        rung_stats.go_text(\n"
        "                                            _ew, _prg, _age, _ew_px,\n"
        "                                            _ew_now),\n"
        '                                        reply_to=_ew.get("tg_ids"))\n'
        "                                    n_alerts += 1\n"
        "                                except Exception as _go_exc:\n"
        '                                    print("  GO thread error:", _go_exc,\n'
        "                                          flush=True)\n"
        '                        elif (_ew.get("buzzed")\n'
        '                                and _ew.get("oneh") == "DEAD"):\n'
        "                            tg.send(\n"
        "                                f\"⭐⚡ *GO — {_ew['base']} \"\n", "GO thread")
W = rep(W,
        '                        _ew["froze"] = True\n'
        "                        _MUTE_R9(          # 📵 muted 2026-09-14\n",
        '                        _ew["froze"] = True\n'
        '                        if (TG_RULES and _ew.get("buzzed")\n'
        '                                and _ew.get("fam", "elite") == "elite"):\n'
        "                            # 🧵 ❄️ FREEZE reply (new on the phone\n"
        "                            # 2026-10-05): night fire -> free the seat;\n"
        "                            # day fire -> hold, no adds. Never a cut.\n"
        "                            try:\n"
        "                                tg.send_thread(\n"
        "                                    rung_stats.freeze_text(_ew, _ew_now),\n"
        '                                    reply_to=_ew.get("tg_ids"))\n'
        "                                n_alerts += 1\n"
        "                            except Exception as _fz_exc:\n"
        '                                print("  freeze thread error:", _fz_exc,\n'
        "                                      flush=True)\n"
        "                        _MUTE_R9(          # 📵 muted 2026-09-14\n", "freeze thread")

# ── 9. ARRIVAL bell: action word + stamped record line ──────────────────
W = rep(W,
        "def _fmt_arrival(a: dict, px: float, tier: int) -> str:\n"
        '    """One banner for all three classes; the tier line says which one."""\n',
        "def _fmt_arrival(a: dict, px: float, tier: int, now=None) -> str:\n"
        '    """One banner for all three classes; the tier line says which one.\n'
        "    now (TG RULES 2026-10-05): when given, the header carries the action\n"
        '    word + fire time and a stamped record line follows the plan."""\n',
        "arrival signature")
W = rep(W,
        "    return (f\"{emo} *ARRIVAL T{int(tier)} — {a['base']} LONG · {label}*\\n\"\n"
        "            f\"{src} number `{float(a['trigger']):g}` broke · {how}\\n\"\n",
        "    head = f\"{emo} *ARRIVAL T{int(tier)} — {a['base']} LONG · {label}*\"\n"
        '    tail = ""\n'
        "    if now is not None:\n"
        "        head = (f\"{emo} *ARRIVAL T{int(tier)} — {a['base']} LONG · {label} · \"\n"
        '                f"TAKE · {rung_stats.pkt_hm(now)} PKT*")\n'
        "        try:\n"
        '            tail = "\\n" + rung_stats.arrival_record(int(tier), now)\n'
        "        except Exception:\n"
        '            tail = ""\n'
        '    return (head + "\\n"\n'
        "            f\"{src} number `{float(a['trigger']):g}` broke · {how}\\n\"\n",
        "arrival head")
W = rep(W,
        '            f"Desk tiers arrival T1 / T2 / T3 prove it forward._")\n',
        '            f"Desk tiers arrival T1 / T2 / T3 prove it forward._" + tail)\n',
        "arrival tail")
W = rep(W,
        "                            tg.send(_fmt_arrival(a, px, _atier)\n"
        "                                    + _kr_note(a))\n",
        "                            tg.send(_fmt_arrival(\n"
        "                                a, px, _atier,\n"
        "                                now=(time.time() if TG_RULES else None))\n"
        "                                    + _kr_note(a))\n", "arrival send")

# ── 10. 09:00 PKT RUNG-1 SCOREBOARD ─────────────────────────────────────
W = rep(W,
        "        if (_dh_utc <= _hr_now < _dh_utc + 3\n"
        '                and store.should_alert("daily_digest", 20 * 3600)):\n',
        "        # 📊 RUNG-1 SCOREBOARD (user 2026-10-05 thread design): yesterday's\n"
        "        # ⭐ / ⚡🔥 T1-T2 / 💎🏆 fires and how they resolved, once a day in\n"
        "        # the morning window. Its own key; fail-soft.\n"
        "        if (TG_RULES and _dh_utc <= _hr_now < _dh_utc + 3\n"
        '                and store.should_alert("rung_scoreboard", 20 * 3600)):\n'
        "            try:\n"
        "                _sb9 = rung_stats.scoreboard(time.time())\n"
        "                if _sb9:\n"
        "                    ok, _sbm = tg.send(_sb9)\n"
        '                    print(f"  rung scoreboard sent={ok}"\n'
        '                          + ("" if ok else f" ({_sbm})"), flush=True)\n'
        "            except Exception as _sb_exc:\n"
        '                print("  rung scoreboard error:", _sb_exc, flush=True)\n'
        "        if (_dh_utc <= _hr_now < _dh_utc + 3\n"
        '                and store.should_alert("daily_digest", 20 * 3600)):\n',
        "scoreboard")

# ── tests whose anchors move ────────────────────────────────────────────
T = open(ROOT + ".arrival_test.py", encoding="utf-8").read()
T = rep(T,
        'i_bell = W.find("tg.send(_fmt_arrival(a, px, _atier)\\n                                    + _kr_note(a))")\n',
        'i_bell = W.find("tg.send(_fmt_arrival(\\n                                a, px, _atier,\\n                                now=(time.time() if TG_RULES else None))\\n                                    + _kr_note(a))")\n',
        "arrival test bell anchor")
T = rep(T,
        "if '\"apex\", \"prime\", \"best\"):' in W or '\"apex\", \"prime\"):' not in W:\n"
        '    fails.append("BEST OF THE BEST must be out of the push roster")\n',
        "if '\"apex\", \"prime\", \"best\"):' in W or '((\"moon\",) if TG_RULES else' not in W:\n"
        '    fails.append("push roster must be moon-only under TG_RULES (best/apex/prime/em off)")\n',
        "arrival test roster anchor")
T = rep(T, 'ns = {"np": np, "pd": pd}\n',
        'import rung_stats\nns = {"np": np, "pd": pd, "rung_stats": rung_stats}\n',
        "arrival test ns")
T = rep(T,
        'm4 = fmt({**a, "arrival": None, "arr_vol2": None, "arr_mom3": None}, 0.2268, 3)\n',
        'm4 = fmt({**a, "arrival": None, "arr_vol2": None, "arr_mom3": None}, 0.2268, 3)\n'
        "m5 = fmt(a, 0.2268, 1, now=1791108000.0)   # 2026-10-03 00:40 UTC = 05:40 PKT\n"
        'if "*ARRIVAL T1 — XLM LONG · HOT strong coil · TAKE · 05:40 PKT*" not in m5 or "T1 record: replay 86% / +0.21R (154), 15 Aug → 28 Sep · forward desk" not in m5 or "refreshed 05:40 PKT" not in m5:\n'
        '    fails.append("TG RULES arrival header/record line wrong")\n'
        "if m5.count('*') % 2 or m5.count('`') % 2:\n"
        '    fails.append("TG RULES arrival markdown unbalanced")\n',
        "arrival test rules case")

A2 = open(ROOT + ".apex_v2_bell_test.py", encoding="utf-8").read()
A2 = rep(A2, '"_kr_note(_sig2)", "tg.send("):', '"_kr_note(_sig2)", "_MUTE_RULES("):',
         "apex v2 test mute anchor")

for path, s in (("agent_worker.py", W), (".arrival_test.py", T),
                (".apex_v2_bell_test.py", A2)):
    with open(ROOT + path, "w", encoding="utf-8", newline="") as f:
        f.write(s)
print("patched: TG RULES switch, mutes, rung threads, arrival stamps, scoreboard")
