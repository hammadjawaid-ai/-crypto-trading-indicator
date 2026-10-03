"""One-shot patch: ELITE A-GRADE + SEATED-65 (bell + desk tiers), mute DUO 85+
and PRESSED & BROKE bells. Every anchor must match exactly once or the patch
aborts without writing. Run once: & .venv\\Scripts\\python.exe .agrade_patch.py"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = "F:/Trading Indicator/"


def rep(src, old, new, label):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"ANCHOR {label!r} matched {n} times — aborting, nothing written")
    return src.replace(old, new, 1)


# ============================ agent_worker.py ============================
W = open(ROOT + "agent_worker.py", encoding="utf-8").read()
W0 = W

HELPERS = '''# ---------------------------------------------------------------------------
# 💎🏆 ELITE A-GRADE + SEATED-65 (user 2026-10-04: "ok build this, deploy on
# my telegram notification as well and also make it part of the decision
# desk ... seated + 65+ conf band as well but no telegram notification,
# first it needs to prove").
# The 2026-10-03 study joined every elite conviction desk trade (Sep 1-28,
# 830 clean) to the Top Conviction board's eight confirmed seats (board 2h
# before .. 30m after the fire):
#   A-GRADE   = seated + 🎯 conf >= 65 + LONG + TP1 within 1.6R
#               68.6% / +0.493R over 35, every third green, still positive
#               after dropping the 3 best days (+0.16R) and coins (+0.29R).
#   SEATED-65 = seated + conf >= 65, any side / target: 59.3% / +0.326R
#               over 59 (thirds +++). RECORDS ONLY — no bell until proven.
#   Excluded shapes: unseated MAX 32% / -0.08R, targets over 1.6R 19%
#   win, shorts 39% / -0.09R.
# Replay (Aug 24-Sep 13) holds 7 A-grade fires and they lost, so the bell
# says "unproven" and the forward ledger (tier elite_agrade) is the judge.
# ---------------------------------------------------------------------------
_SEATS: dict = {}
SEAT_MEMORY_S = 2 * 3600          # the study's "board 2h before the fire"
AGRADE_CONF = 65.0
AGRADE_MAX_RR = 1.6


def _seats_update(tn_hot_list, now=None):
    """Remember the Top Conviction board's eight seats (confirmed TAKE
    NOW + HOT, top 8 by score — the same list the desk's top_conviction
    tier records) per coin+side for SEAT_MEMORY_S."""
    now = time.time() if now is None else now
    try:
        top = sorted(list(tn_hot_list or []),
                     key=lambda p: -float(p.get("score") or 0))[:8]
    except Exception:
        top = []
    for p in top:
        k = (p.get("symbol"), (p.get("side") or "").upper())
        _SEATS[k] = {"ts": now, "score": p.get("score"),
                     "lanes": p.get("lanes")}
    for k in [k for k, v in list(_SEATS.items())
              if now - float(v.get("ts") or 0) > SEAT_MEMORY_S]:
        _SEATS.pop(k, None)


def _seat_of(symbol, side, now=None):
    """The remembered seat for coin+side, or None once it is older than
    SEAT_MEMORY_S."""
    now = time.time() if now is None else now
    v = _SEATS.get((symbol, (side or "").upper()))
    if v and now - float(v.get("ts") or 0) <= SEAT_MEMORY_S:
        return v
    return None


def _plan_rr(p):
    """TP1 distance in R of the plan's own stop, or None."""
    try:
        e = float(p.get("entry") or 0)
        s = float(p.get("stop") or 0)
        t = float(p.get("tp1") or 0)
        if e and s and t and abs(e - s) > 0:
            return abs(t - e) / abs(e - s)
    except Exception:
        pass
    return None


def _elite_grade(p, conf, seat):
    """'A' / 'S65' / None for an elite conviction card — see the block
    comment above. Pure: no I/O, tested in .agrade_test.py. Garbage conf
    (outside 0-100, the 0917 lesson) reads as unknown."""
    if not seat or conf is None:
        return None
    try:
        c = float(conf)
        if not 0 <= c <= 100 or c < AGRADE_CONF:
            return None
    except (TypeError, ValueError):
        return None
    rr = _plan_rr(p)
    if ((p.get("side") or "").upper() == "LONG" and rr is not None
            and rr <= AGRADE_MAX_RR):
        return "A"
    return "S65"


def _grade_sig(p, conf, seat, grade):
    """Desk / record payload for a graded elite fire."""
    return {"symbol": p.get("symbol"),
            "base": p.get("base") or str(p.get("symbol")).replace("USDT", ""),
            "side": p.get("side"), "entry": p.get("entry"),
            "stop": p.get("stop"), "tp1": p.get("tp1"), "tp2": p.get("tp2"),
            "conf": conf, "heat": p.get("heat"), "tier": p.get("tier"),
            "score": p.get("score"), "appr": p.get("appr"),
            "seat_score": seat.get("score"), "seat_lanes": seat.get("lanes"),
            "rr": _plan_rr(p), "grade": grade}


def _agrade_banner(seat, conf, rr):
    """Headline block that LEADS an A-grade elite buzz. The study numbers
    stay; the live forward ledger joins once it has 10 closes."""
    fwd = ""
    try:
        rec = next((x for x in shadow_trader.tier_records()
                    if x.get("tier") == "elite_agrade"), None)
        if rec and int(rec.get("n") or 0) >= 10:
            fwd = (f" Forward ledger so far: {int(rec['n'])} closed · "
                   f"{float(rec['win_pct']):.0f}% · "
                   f"{float(rec['net_r']):+.1f}R net.")
    except Exception:
        fwd = ""
    bits = []
    try:
        if seat.get("score") is not None:
            bits.append(f"score {float(seat['score']):.0f}")
        if seat.get("lanes") is not None:
            bits.append(f"{int(seat['lanes'])} lanes")
    except Exception:
        pass
    seat_txt = ("🏆 seated on Top Conviction"
                + (f" ({', '.join(bits)})" if bits else ""))
    try:
        conf_txt = f"{float(conf):.0f}"
    except Exception:
        conf_txt = "?"
    rr_txt = f"{rr:.2f}R" if rr is not None else "?"
    return ("💎🏆 *ELITE A-GRADE — the measured best cell*\\n"
            f"_{seat_txt} · 🎯 conf {conf_txt} · LONG · TP1 {rr_txt} away. "
            "Desk Sep 1-28: 68.6% / +0.49R over 35 fires, every third "
            "green, still positive after the best-days and best-coins "
            "cuts. Replay unproven (7 fires) — size as a normal elite "
            f"trade until the forward ledger speaks.{fwd}_\\n")


'''
W = rep(W, "def _fmt_elite_conv(p) -> str:\n",
        HELPERS + "def _fmt_elite_conv(p) -> str:\n", "helpers before _fmt_elite_conv")

W = rep(W, '    tn_hot = [p for p in takenow if p.get("hot")]\n',
        '    tn_hot = [p for p in takenow if p.get("hot")]\n'
        '    _seats_update(tn_hot)   # 🏆 seat memory for the elite A-grade read\n',
        "seats update after tn_hot")

W = rep(W,
        "                except Exception:\n"
        "                    _star9 = False\n"
        "                if not _star9:\n"
        "                    # ── the PLAIN elite buzz gates (stars exempt) ──\n",
        "                except Exception:\n"
        "                    _star9 = False\n"
        "                # 💎🏆 A-GRADE READ (user 2026-10-04): seated on Top\n"
        "                # Conviction + conf>=65 + LONG + TP1 within 1.6R. Like\n"
        "                # the star it is its own stream: it skips the plain\n"
        "                # gates (its conf is >=65 by definition, so only the\n"
        "                # unapproved-needs-kronos gate is bypassed), carries\n"
        "                # its own alert key and LEADS the buzz with its banner.\n"
        "                # Desk records for elite_agrade / elite_seated65 are\n"
        "                # taken in the ✳️ desk tier loop from the FULL elite\n"
        "                # list, not here (buzz and ledger stay independent).\n"
        "                _seat9 = _seat_of(_pmx.get(\"symbol\"), _pmx.get(\"side\"))\n"
        "                _grade9 = _elite_grade(_pmx, _cf9, _seat9)\n"
        "                _ag9 = _grade9 == \"A\"\n"
        "                if not (_star9 or _ag9):\n"
        "                    # ── the PLAIN elite buzz gates (stars exempt) ──\n",
        "A-grade read + unified gate")

W = rep(W, '                _key9 = ("elitestar" if _star9 else "eliteconv")\n',
        '                _key9 = ("elitestar" if _star9\n'
        '                         else "eliteagrade" if _ag9 else "eliteconv")\n',
        "alert key")

W = rep(W, '                    # 🕐 BUZZ CLOCK (user 2026-10-01:',
        '                    # 💎🏆 A-GRADE BANNER leads everything (user\n'
        '                    # 2026-10-04) — single buzz, no double bell.\n'
        '                    if _ag9:\n'
        '                        try:\n'
        '                            _msg9 = _agrade_banner(\n'
        '                                _seat9, _cf9, _plan_rr(_pmx)) + _msg9\n'
        '                        except Exception:\n'
        '                            pass\n'
        '                    # 🕐 BUZZ CLOCK (user 2026-10-01:',
        "banner before buzz clock")

W = rep(W,
        '            if _pe.get("requal"):\n'
        '                _ec_buzz.append(_pe)\n'
        '                continue\n'
        '            _kv3 = _kr_get(_pe["symbol"], _pe["side"])\n',
        '            if _pe.get("requal"):\n'
        '                _ec_buzz.append(_pe)\n'
        '                continue\n'
        '            # 💎🏆 an unapproved A-GRADE fire buzzes without the kronos\n'
        '            # ticket (user 2026-10-04; the study did not condition on\n'
        '            # approval). Conf is stamped here so the grade can be read.\n'
        '            _sa3 = _seat_of(_pe["symbol"], _pe["side"])\n'
        '            if _sa3 is not None:\n'
        '                if _pe.get("conf") is None:\n'
        '                    try:\n'
        '                        _pe["conf"] = best_board.confidence(\n'
        '                            _pe.get("symbol"), _pe.get("side"))\n'
        '                    except Exception:\n'
        '                        pass\n'
        '                if _elite_grade(_pe, _pe.get("conf"), _sa3) == "A":\n'
        '                    _ec_buzz.append(_pe)\n'
        '                    continue\n'
        '            _kv3 = _kr_get(_pe["symbol"], _pe["side"])\n',
        "unapproved A-grade joins the buzz list (kronos-ok path)")

W = rep(W, '        _ec_buzz = [p for p in _ec_mh if p.get("appr")]\n',
        '        _ec_buzz = [p for p in _ec_mh if p.get("appr")]\n'
        '        for _pe in _ec_mh:      # 💎🏆 unapproved A-grade still buzzes\n'
        '            _sa4 = _seat_of(_pe["symbol"], _pe["side"])\n'
        '            if _pe.get("appr") or _sa4 is None:\n'
        '                continue\n'
        '            if _pe.get("conf") is None:\n'
        '                try:\n'
        '                    _pe["conf"] = best_board.confidence(\n'
        '                        _pe.get("symbol"), _pe.get("side"))\n'
        '                except Exception:\n'
        '                    pass\n'
        '            if _elite_grade(_pe, _pe.get("conf"), _sa4) == "A":\n'
        '                _ec_buzz.append(_pe)\n',
        "unapproved A-grade joins the buzz list (kronos-down path)")

W = rep(W, '        _tiers = (("top_conviction", _topc),\n',
        '        # 💎🏆 A-GRADE + SEATED-65 desk tiers (user 2026-10-04): read\n'
        '        # off the FULL elite list (approved or not, buzzed or not) so\n'
        '        # the ledger judges the exact cells the study measured.\n'
        '        # open_from_signal dedupes one open per (tier, symbol).\n'
        '        _ag_list, _s65_list = [], []\n'
        '        for _pq in _ec_mh:\n'
        '            try:\n'
        '                _sq = _seat_of(_pq.get("symbol"), _pq.get("side"))\n'
        '                if _sq is None:\n'
        '                    continue\n'
        '                if _pq.get("conf") is None:\n'
        '                    try:\n'
        '                        _pq["conf"] = best_board.confidence(\n'
        '                            _pq.get("symbol"), _pq.get("side"))\n'
        '                    except Exception:\n'
        '                        pass\n'
        '                _gq = _elite_grade(_pq, _pq.get("conf"), _sq)\n'
        '                if not _gq:\n'
        '                    continue\n'
        '                _gs = _grade_sig(_pq, _pq.get("conf"), _sq, _gq)\n'
        '                _s65_list.append(_gs)\n'
        '                store.record_signal("elite_seated65", _gs)\n'
        '                if _gq == "A":\n'
        '                    _ag_list.append(_gs)\n'
        '                    store.record_signal("elite_agrade", _gs)\n'
        '            except Exception as _gq_exc:\n'
        '                print("  elite grade error:", _gq_exc, flush=True)\n'
        '        _tiers = (("top_conviction", _topc),\n',
        "grade lists before the tiers tuple")

W = rep(W,
        '                  ("elite_conv", _ec_mh),\n'
        '                  ("best_board", best),\n',
        '                  ("elite_conv", _ec_mh),\n'
        '                  ("elite_agrade", _ag_list),      # 💎🏆 proving\n'
        '                  ("elite_seated65", _s65_list),   # records only\n'
        '                  ("best_board", best),\n',
        "tiers tuple")

W = rep(W,
        '            ok, _ = (tg.send(_du_msg) if _du_key == "duo85"\n'
        '                     else _MUTE_R9(_du_msg))\n',
        '            # 📵 MUTED (user 2026-10-04: "remove these from buzzes:\n'
        '            # DUO 85+"). Desk tier + demo seat feed unchanged.\n'
        '            # Revert: tg.send(_du_msg) if _du_key == "duo85" else\n'
        '            # _MUTE_R9(_du_msg).\n'
        '            ok, _ = _MUTE_R9(_du_msg)\n',
        "duo85 mute")

W = rep(W,
        '                            tg.send(_fmt_press_break(a, px, _pb_min)\n'
        '                                    + _kr_note(a))\n',
        '                            # 📵 MUTED (user 2026-10-04: "remove ...\n'
        '                            # Pressed and broke"). Record, desk tier\n'
        '                            # and board stay. Revert: _MUTE_R9 ->\n'
        '                            # tg.send.\n'
        '                            _MUTE_R9(_fmt_press_break(a, px, _pb_min)\n'
        '                                     + _kr_note(a))\n',
        "press & broke mute")

# ================================ app.py ================================
A = open(ROOT + "app.py", encoding="utf-8").read()
A = rep(A,
        '                   "elite_star": "💎⭐ ELITE STAR (the measured "\n'
        '                                 "winner profile)",\n',
        '                   "elite_star": "💎⭐ ELITE STAR (the measured "\n'
        '                                 "winner profile)",\n'
        '                   "elite_agrade": "💎🏆 ELITE A-GRADE (seated on Top "\n'
        '                                   "Conviction · conf 65+ · LONG · TP1 "\n'
        '                                   "≤1.6R — 68.6%/+0.49R desk Sep, "\n'
        '                                   "proving)",\n'
        '                   "elite_seated65": "💎🏆 ELITE SEATED 65+ (seated + "\n'
        '                                     "conf 65+, any side — records "\n'
        '                                     "only, no bell)",\n',
        "app tier names")

# ============================== auditor.py ==============================
U = open(ROOT + "auditor.py", encoding="utf-8").read()
U = rep(U, '    "elite_star": "elite_star",\n',
        '    "elite_star": "elite_star",\n'
        '    "elite_agrade": "elite_agrade",\n'
        '    "elite_seated65": "elite_seated65",\n',
        "auditor tiers")

for path, s in (("agent_worker.py", W), ("app.py", A), ("auditor.py", U)):
    with open(ROOT + path, "w", encoding="utf-8", newline="") as f:
        f.write(s)
print(f"patched: agent_worker.py (+{len(W) - len(W0)} chars), app.py, auditor.py")
