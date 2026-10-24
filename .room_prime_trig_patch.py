"""2026-10-24 (user): (1) 💎✅ ROOM — a NEW records-only desk tier beside the confirmed
entry: the confirm whose close leaves TP1 >= 1R away, on a plain elite pick (no 💎
conviction / ⭐ star record on the coin+side in the prior 48h), BTC day <= +1.5%.
Study (.elite_confirm_study2.py + agent run): 50% / +0.47R (166), both halves, 100th
pct shuffle; rejects 50% / -0.01R. Decision desk only, no bell, no demo — nothing in the
confirm mechanism changes. (2) 💥🥇 PRIME × STRONG TRIGGER moves into the demo at the
flat 10x as the 5th rung and gets its Telegram bell (TG_PRIME_TRIG = True); the 🏦 TP1
ping roster learns it. Everything else untouched."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = "F:/Trading Indicator/"


def rep(src, old, new, label):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"ANCHOR {label!r} matched {n} times — nothing written")
    return src.replace(old, new)


W = open(ROOT + "agent_worker.py", encoding="utf-8").read()
# ── (1) ROOM beside the confirm
W = rep(W,
        "            shadow_trader.open_from_signal(\"elite_confirm\", _sig9,\n"
        "                                           _cl9)\n",
        "            shadow_trader.open_from_signal(\"elite_confirm\", _sig9,\n"
        "                                           _cl9)\n"
        "            # 💎✅ ROOM (user 2026-10-24: \"room to the decision desk only on paper\n"
        "            # trading first\"): a NEW records-only tier beside the confirm — the\n"
        "            # confirm whose close still leaves TP1 >= 1R away, whose fire was a\n"
        "            # plain elite pick (no 💎 conviction / ⭐ star record on the coin+side\n"
        "            # in the prior 48h) and on a BTC day <= +1.5%. Measured 23 Aug → 14 Oct:\n"
        "            # 50% / +0.47R (166), both halves, 100th pct shuffle; what it rejects\n"
        "            # 50% / -0.01R (768). Every confirm is stamped (rr / fire kind / BTC /\n"
        "            # room pass-fail) on the elite_confirm record's sibling; only passes\n"
        "            # open the tier. No bell, no demo seat.\n"
        "            try:\n"
        "                _rr_rm = (abs(float(_w9[\"tp1\"]) - float(_cl9))\n"
        "                          / max(1e-12, abs(float(_cl9) - float(_w9[\"stop\"]))))\n"
        "                _pick_rm = not (store.seen_between(\"elite_conv\", _w9[\"symbol\"], _w9[\"side\"],\n"
        "                                                   _now - 48 * 3600, _now + 1)\n"
        "                                or store.seen_between(\"elite_star\", _w9[\"symbol\"], _w9[\"side\"],\n"
        "                                                      _now - 48 * 3600, _now + 1))\n"
        "                try:\n"
        "                    _btc_rm = _btc_day_pct()\n"
        "                except Exception:\n"
        "                    _btc_rm = None\n"
        "                _room_ok = (_rr_rm >= 1.0 and _pick_rm\n"
        "                            and (_btc_rm is None or _btc_rm <= 1.5))\n"
        "                _sig_rm = dict(_sig9, rr=round(_rr_rm, 3),\n"
        "                               fire_kind=(\"pick\" if _pick_rm else \"bell\"),\n"
        "                               btc_day=_btc_rm, room=(\"pass\" if _room_ok else \"fail\"))\n"
        "                if _room_ok:\n"
        "                    store.record_signal(\"confirm_room\", _sig_rm)\n"
        "                    shadow_trader.open_from_signal(\"confirm_room\", _sig_rm, _cl9)\n"
        "                print(f\"  [room] {_w9['symbol']} {_w9['side']} rr {_rr_rm:.2f} \"\n"
        "                      f\"{'pick' if _pick_rm else 'bell-backed'} btc {_btc_rm} -> \"\n"
        "                      f\"{'ROOM' if _room_ok else 'no room'}\", flush=True)\n"
        "            except Exception as _rm_exc:\n"
        "                print(\"  room error:\", _rm_exc, flush=True)\n", "room")
# ── (2) PRIME × STRONG TRIGGER: bell on, demo feed, roster
W = rep(W,
        "TG_PRIME_TRIG = False    # 💥🥇 bell OFF — records only (no send path exists yet).\n",
        "TG_PRIME_TRIG = True     # 💥🥇 bell ON 2026-10-24 (user: \"on our telegram notifications we have this buzzed as well\"); False = silent, tier + demo continue.\n", "switch")
W = rep(W,
        '    "elite_star": "⭐ ELITE STAR",\n',
        '    "elite_star": "⭐ ELITE STAR",\n'
        '    "prime_trig": "💥🥇 PRIME × STRONG TRIGGER",   # bell since 2026-10-24\n', "tp1 roster")
W = rep(W, "_DEMO_SP: list = []\n", "_DEMO_SP: list = []\n_DEMO_PT: list = []     # 💥🥇 GEN 18.2 seat feed (user 2026-10-24)\n", "demo list")
W = rep(W,
        "def _prime_read(p, now, btc=None):\n",
        "def _fmt_prime_trig(sig, px, now):\n"
        "    \"\"\"💥🥇 PRIME × STRONG TRIGGER bell (user 2026-10-24): the two fires, the plan,\n"
        "    the PRIME read (information), the bank zone, the pair record + forward ledger.\"\"\"\n"
        "    side = (sig.get(\"side\") or \"\").upper()\n"
        "    head = (f\"💥🥇 *PRIME × STRONG TRIGGER — {sig.get('base')} {side} · TAKE · \"\n"
        "            f\"{rung_stats.pkt_hm(now)} PKT*\")\n"
        "    l2 = (\"🥇 PRIME fire + 💥 strong trigger on the same coin and side (trigger within \"\n"
        "          \"2h before → 30 min after the PRIME)\")\n"
        "    t2 = f\" · TP2 `{float(sig['tp2']):g}`\" if sig.get(\"tp2\") else \"\"\n"
        "    plan = (f\"entry `{float(sig['entry']):g}` · live `{float(px):g}` · SL \"\n"
        "            f\"`{float(sig['stop']):g}` · TP1 `{float(sig['tp1']):g}`{t2}\")\n"
        "    rd = str(sig.get(\"read_line\") or \"\")\n"
        "    try:\n"
        "        bl = bank_zone.line(bank_zone.compute(sig.get(\"entry\"), sig.get(\"stop\"), sig.get(\"tp1\"),\n"
        "                                              side, _sr_levels(sig.get(\"symbol\"), side)))\n"
        "    except Exception:\n"
        "        bl = \"\"\n"
        "    try:\n"
        "        fwd = rung_stats.rec(rung_stats.tier_rec(\"prime_trig\", None, now))\n"
        "    except Exception:\n"
        "        fwd = \"record unavailable\"\n"
        "    l5 = (f\"pair record: {PRIME_TRIG_REC} · forward ledger (💥🥇 tier since 19 Oct): {fwd} · \"\n"
        "          f\"{rung_stats.stamp_now(now)}\")\n"
        "    l6 = (\"_bank at TP1 · hold through the hour: a LIVE 60m read ran 83% / +0.69R (60) on the \"\n"
        "          \"replay · the PRIME read above is information, not a gate._\")\n"
        "    return \"\\n\".join(x for x in (head, l2, plan, rd, bl, l5, l6) if x)\n"
        "\n"
        "\n"
        "def _prime_read(p, now, btc=None):\n", "bell fmt")
W = rep(W,
        "                store.record_signal(\"prime_trig\", _sig_pt)\n"
        "                shadow_trader.open_from_signal(\"prime_trig\", _sig_pt, _px_pt)\n"
        "                print(f\"  [prime-trig] {_sym_pt} {_sd_pt} band={_sig_pt['band']} \"\n"
        "                      f\"read={_sig_pt['read']} bell=off\", flush=True)\n",
        "                store.record_signal(\"prime_trig\", _sig_pt)\n"
        "                shadow_trader.open_from_signal(\"prime_trig\", _sig_pt, _px_pt)\n"
        "                # 🎮 GEN 18.2 seat feed (user 2026-10-24: \"move it to demo trading\n"
        "                # with full leverage\") — the PRIME plan, every band, flat 10x.\n"
        "                _DEMO_PT.append(dict(_sig_pt, src=\"prime_trig\",\n"
        "                                     score=float(_sig_pt.get(\"score\") or 85),\n"
        "                                     burst=0.0, fired_at=_now_pt))\n"
        "                del _DEMO_PT[:-12]\n"
        "                # 💥🥇 bell (user 2026-10-24: \"on our telegram notifications we have\n"
        "                # this buzzed as well\"); the switch above silences it.\n"
        "                _bell_pt = \"off\"\n"
        "                if TG_PRIME_TRIG and not _bstock_quiet(_sym_pt):\n"
        "                    try:\n"
        "                        ok, _m_pt = tg.send(_fmt_prime_trig(\n"
        "                            _sig_pt, float(_px_pt or _sig_pt[\"entry\"]), _now_pt)\n"
        "                            + _kr_note(_sig_pt))\n"
        "                        n_alerts += 1 if ok else 0\n"
        "                        _bell_pt = \"sent\" if ok else f\"failed: {_m_pt}\"\n"
        "                    except Exception as _pb_exc:\n"
        "                        _bell_pt = f\"error: {_pb_exc}\"\n"
        "                print(f\"  [prime-trig] {_sym_pt} {_sd_pt} band={_sig_pt['band']} \"\n"
        "                      f\"read={_sig_pt['read']} bell={_bell_pt}\", flush=True)\n", "bell + feed")
W = rep(W,
        '                         ("conv_revival", "go_revived")):\n',
        '                         ("conv_revival", "go_revived"),\n'
        '                         ("prime_trig", "prime_trig")):        # GEN 18.2\n', "form map")
W = rep(W,
        "                             + [d for d in _dz_reo\n"
        "                                if d[\"src\"] == \"conv_revival\"])}\n",
        "                             + [d for d in _dz_reo\n"
        "                                if d[\"src\"] == \"conv_revival\"]),\n"
        "            # 5. 💥🥇 PRIME × STRONG TRIGGER (GEN 18.2, user 2026-10-24: \"move it to\n"
        "            # demo trading with full leverage\") — the PRIME plan, every band\n"
        "            \"prime_trig\": ([dict(d) for d in _DEMO_PT\n"
        "                            if _now - d[\"fired_at\"] <= DEMO_FIRE_TTL_S\n"
        "                            and d.get(\"entry\") and d.get(\"stop\")\n"
        "                            and d.get(\"tp1\")]\n"
        "                           + [d for d in _dz_reo\n"
        "                              if d[\"src\"] == \"prime_trig\"])}\n", "demo pool")
W = rep(W,
        "                             (\"elite_star\", \"strong_trigger\",\n"
        "                              \"star_prime\", \"conv_revival\")\n"
        "                             else \"strong_trigger\"),   # GEN 18\n",
        "                             (\"elite_star\", \"strong_trigger\",\n"
        "                              \"star_prime\", \"conv_revival\", \"prime_trig\")\n"
        "                             else \"strong_trigger\"),   # GEN 18.2\n", "reentry")
with open(ROOT + "agent_worker.py", "w", encoding="utf-8", newline="") as f:
    f.write(W)

D = open(ROOT + "demo_account.py", encoding="utf-8").read()
D = rep(D,
        '           "conv_revival": 101}   # 4. 💎 CONVICTION REVIVAL — the bell\'s own rule:\n'
        "                                  #    not a star, fire read passed, GO inside the\n"
        "                                  #    entry cell (0.3–0.6R left, not 21–05 PKT)\n",
        '           "conv_revival": 101,   # 4. 💎 CONVICTION REVIVAL — the bell\'s own rule:\n'
        "                                  #    not a star, fire read passed, GO inside the\n"
        "                                  #    entry cell (0.3–0.6R left, not 21–05 PKT)\n"
        '           "prime_trig": 100}     # 5. 💥🥇 PRIME × STRONG TRIGGER (GEN 18.2, user\n'
        "                                  #    2026-10-24: \"move it to demo trading with full\n"
        "                                  #    leverage\") — PRIME fire + strong trigger on the\n"
        "                                  #    coin+side; desk replay 64% / +0.32R (155)\n", "class_w")
D = rep(D,
        'NEAR_TP_SRC: set = {"elite_star", "strong_trigger", "star_prime", "conv_revival"}\n',
        'NEAR_TP_SRC: set = {"elite_star", "strong_trigger", "star_prime", "conv_revival", "prime_trig"}\n', "near tp")
D = rep(D,
        'SMART_EXIT_SKIP: set = {"elite_star", "strong_trigger",\n'
        '                        "star_prime", "conv_revival"}         # GEN 18: no kronos exit anywhere\n',
        'SMART_EXIT_SKIP: set = {"elite_star", "strong_trigger",\n'
        '                        "star_prime", "conv_revival", "prime_trig"}   # GEN 18.2: no kronos exit anywhere\n', "smart exit")
D = rep(D,
        '    return {"elite_star": 10.0, "strong_trigger": 10.0,\n'
        '            "star_prime": 10.0,\n'
        '            "conv_revival": 10.0}.get(src, LEV_GEN13)     # GEN 18: flat 10x\n',
        '    return {"elite_star": 10.0, "strong_trigger": 10.0,\n'
        '            "star_prime": 10.0, "conv_revival": 10.0,\n'
        '            "prime_trig": 10.0}.get(src, LEV_GEN13)       # GEN 18.2: flat 10x\n', "lev")
with open(ROOT + "demo_account.py", "w", encoding="utf-8", newline="") as f:
    f.write(D)

A = open(ROOT + "app.py", encoding="utf-8").read()
A = rep(A,
        '                   "apex_one": "🏆²👑 APEX V2 × ONE TRADE — APEX V2 fire + 👑 "\n',
        '                   "confirm_room": "💎✅ ROOM — a confirmed entry whose close still "\n'
        '                                   "leaves TP1 ≥ 1R away, on a plain elite pick (no "\n'
        '                                   "conviction / star bell behind it), BTC day ≤ +1.5% "\n'
        '                                   "(50%/+0.47R over 166 on the 23 Aug → 14 Oct desk, "\n'
        '                                   "both halves; decision desk first, no bell, proving)",\n'
        '                   "apex_one": "🏆²👑 APEX V2 × ONE TRADE — APEX V2 fire + 👑 "\n', "room label")
A = rep(A,
        '        "cell, not 21–05 PKT). Nothing else seats — GO REVIVED star revivals, ARRIVAL "\n',
        '        "cell, not 21–05 PKT) · <b>5. 💥🥇 PRIME × STRONG TRIGGER</b>, 10x (a PRIME fire with a "\n'
        '        "strong trigger on the coin and side 2h before → 30 min after; its own bell since 24 Oct; "\n'
        '        "desk replay 64%/+0.32R over 155). Nothing else seats — GO REVIVED star revivals, ARRIVAL "\n', "demo header")
with open(ROOT + "app.py", "w", encoding="utf-8", newline="") as f:
    f.write(A)

R = open(ROOT + ".tg_roster_audit.py", encoding="utf-8").read()
R = rep(R,
        '    ("💥🥇 PRIME × STRONG TRIGGER: records-only tier prime_trig, PRIME read stamped, no bell (2026-10-19)",\n'
        '     \'store.record_signal("prime_trig", _sig_pt)\' in W and flag("TG_PRIME_TRIG").startswith("False")\n'
        '     and "tg.send" not in W[W.find("# 💥🥇 PRIME × STRONG TRIGGER — records-only pass"):W.find("# 💯 CONVICTION v2")]),\n',
        '    ("💥🥇 PRIME × STRONG TRIGGER: tier prime_trig + demo seat + bell ON (2026-10-24), PRIME read stamped",\n'
        '     \'store.record_signal("prime_trig", _sig_pt)\' in W and flag("TG_PRIME_TRIG").startswith("True")\n'
        '     and "tg.send(_fmt_prime_trig(" in W and \'"prime_trig": "💥🥇 PRIME × STRONG TRIGGER"\' in W),\n'
        '    ("💎✅ ROOM: records-only tier confirm_room beside the confirm, no bell (2026-10-24)",\n'
        '     \'store.record_signal("confirm_room", _sig_rm)\' in W and "tg.send" not in W[W.find("# 💎✅ ROOM (user 2026-10-24"):W.find("# 💎✅ ROOM (user 2026-10-24") + 2600]),\n', "audit")
with open(ROOT + ".tg_roster_audit.py", "w", encoding="utf-8", newline="") as f:
    f.write(R)

# tests that pinned the old states
T = open(ROOT + ".prime_trig_test.py", encoding="utf-8").read()
T = rep(T, 'if ns.get("TG_PRIME_TRIG") is not False:\n    fails.append("TG_PRIME_TRIG must be False (records only)")\n',
        'if ns.get("TG_PRIME_TRIG") is not True:\n    fails.append("TG_PRIME_TRIG must be True (bell on since 2026-10-24)")\n', "trig test switch")
T = rep(T, 'if "tg.send" in blk or "send_thread" in blk or "_MUTE_RULES" in blk:\n    fails.append("records-only pass must have no send path")\n',
        'if "tg.send(_fmt_prime_trig(" not in blk or "_DEMO_PT.append(dict(_sig_pt, src=\\"prime_trig\\"" not in blk:\n    fails.append("the pass must ring the bell and feed the demo (2026-10-24)")\n', "trig test send")
with open(ROOT + ".prime_trig_test.py", "w", encoding="utf-8", newline="") as f:
    f.write(T)
G = open(ROOT + ".demo_gen18_test.py", encoding="utf-8").read()
G = rep(G, 'if set(da.CLASS_W) != {"elite_star", "strong_trigger", "star_prime", "conv_revival"}:\n',
        'if set(da.CLASS_W) != {"elite_star", "strong_trigger", "star_prime", "conv_revival", "prime_trig"}:\n', "gen18 roster")
G = rep(G, 'if not (da.CLASS_W["elite_star"] > da.CLASS_W["strong_trigger"] > da.CLASS_W["star_prime"] > da.CLASS_W["conv_revival"]):\n',
        'if not (da.CLASS_W["elite_star"] > da.CLASS_W["strong_trigger"] > da.CLASS_W["star_prime"] > da.CLASS_W["conv_revival"] > da.CLASS_W["prime_trig"]):\n', "gen18 ladder")
G = rep(G, 'if da.NEAR_TP_SRC != {"elite_star", "strong_trigger", "star_prime", "conv_revival"} or da.LONG_ONLY or da.RR_OPEN_BOUNDS or da.DEMO_RESET_BEFORE:\n',
        'if da.NEAR_TP_SRC != {"elite_star", "strong_trigger", "star_prime", "conv_revival", "prime_trig"} or da.LONG_ONLY or da.RR_OPEN_BOUNDS or da.DEMO_RESET_BEFORE:\n', "gen18 fade")
G = rep(G, '                  (\'"conv_revival": (\', "conv pool"),\n',
        '                  (\'"conv_revival": (\', "conv pool"),\n                  (\'"prime_trig": ([dict(d) for d in _DEMO_PT\', "prime_trig pool (GEN 18.2)"),\n', "gen18 pool anchor")
with open(ROOT + ".demo_gen18_test.py", "w", encoding="utf-8", newline="") as f:
    f.write(G)
print("patched: worker (ROOM tier, PRIME×TRIG bell + demo feed + TP1 roster) · demo (5th rung) · app (ROOM label, header) · audit · tests")
