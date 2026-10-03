"""One-shot patch — GEN 16.5 demo: PRESSED & BROKE longs as priority 1 and
the 🟢/🟡-only PKT time gate on long seats for star / strong trigger /
TRIG×KR / early lane / early movers. Every anchor must match exactly once or
nothing is written. Run once: & .venv\\Scripts\\python.exe .gen165_patch.py"""
import calendar
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = "F:/Trading Indicator/"


def rep(src, old, new, label):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"ANCHOR {label!r} matched {n} times — aborting, nothing written")
    return src.replace(old, new, 1)


# ============================ demo_account.py ============================
D = open(ROOT + "demo_account.py", encoding="utf-8").read()

D = rep(D,
        'CLASS_W = {"elite_star": 106,     # 1. ⭐ conf 40-54 / 65+   PRIORITY\n',
        '# 🔶💥 GEN 16.5 (user 2026-10-04: "add PRESSED & BROKE to priority 1 but\n'
        '# only longs no shorts ... timings should matter"): the pressed-first\n'
        '# break takes the TOP rung, longs only, any conf, no time gate; the\n'
        '# rest of the ladder is unchanged below it. GEN stays 16 (balance and\n'
        '# history carry on).\n'
        'CLASS_W = {"press_break": 107,    # 1. 🔶💥 PRESSED & BROKE, LONGS ONLY (GEN 16.5)\n'
        '           "elite_star": 106,     # 2. ⭐ conf 40-54 / 65+   PRIORITY\n',
        "CLASS_W head")

D = rep(D,
        'SMART_EXIT_SKIP: set = {"moonshot", "strong_trigger", "elite_star",\n'
        '                        "early_movers", "early_lane",\n'
        '                        "strig_kr"}                        # GEN 16.4\n',
        'SMART_EXIT_SKIP: set = {"moonshot", "strong_trigger", "elite_star",\n'
        '                        "early_movers", "early_lane",\n'
        '                        "strig_kr", "press_break"}         # GEN 16.5\n',
        "SMART_EXIT_SKIP")

D = rep(D,
        '    return {"moonshot": 10.0, "strong_trigger": 10.0,\n'
        '            "elite_star": 10.0, "early_movers": 10.0,\n'
        '            "early_lane": 10.0, "strig_kr": 10.0}.get(src, LEV_GEN13)\n',
        '    return {"moonshot": 10.0, "strong_trigger": 10.0,\n'
        '            "elite_star": 10.0, "early_movers": 10.0,\n'
        '            "early_lane": 10.0, "strig_kr": 10.0,\n'
        '            "press_break": 10.0}.get(src, LEV_GEN13)      # GEN 16.5\n',
        "lev_for map")

D = rep(D,
        'SPARE_RESERVE: dict = {"early_lane": 5, "strig_kr": 5,\n'
        '                       "early_movers": 5}\n',
        'SPARE_RESERVE: dict = {"early_lane": 5, "strig_kr": 5,\n'
        '                       "early_movers": 5}\n'
        '# 🔶💥 GEN 16.5 (user 2026-10-04: "add PRESSED & BROKE to priority 1 but\n'
        '# only longs no shorts"): an armed ⚡/🔥/💎 number that was PRESSED\n'
        '# (price within 0.4% of it for a while) before it broke, from the\n'
        '# worker\'s _trigger_watch; desk tier press_break (17 closed, 71%,\n'
        '# +3.6R at wiring — young, proving). LONG only, any conf, no spare\n'
        '# reserve, no time gate (his call), flat 10x like every lane.\n'
        'LONG_ONLY: set = {"press_break"}\n'
        '# ⏰ GEN 16.5 TIME GATE (user 2026-10-04: "timings should matter — we\n'
        '# will take long trades as per our finding for elite star with yellow\n'
        '# and green timings not red timings; same goes for early lane and\n'
        '# early movers and strong trigger but not pressed and broke ... and\n'
        '# for shorts whichever timings do that accordingly").\n'
        '# LONGS — his order: the PKT clock law on the BTC pulse, 🟢 13-21 ·\n'
        '# 🟡 05-13 open, 🔴 21-05 closed (star longs 22:00 PKT 17% / -0.61R,\n'
        '# 01-05 ~0R, 21-01 unstable desk vs replay), applied to all five.\n'
        '# HONEST NOTE for the record (desk 09-01..09-28): strong trigger\n'
        '# longs were green in every window incl. 21-01 +0.17R n=156 and\n'
        '# 01-05 +0.21R n=123, and early lane / movers longs were +0.23 /\n'
        '# +0.28R at 01-05 — the 🔴 law is the star\'s, applied by his call.\n'
        '# SHORTS — per stream from the same desk ledger, closing only the\n'
        '# proven-red 4h windows (avg <= -0.10R with n >= 15, the buzz-clock\n'
        '# 🔴 rule; star also uses the desk+replay clock study):\n'
        '#   elite_star    shorts best 17-21 (62% / +0.26R n=24); red 09-13,\n'
        '#                 21-01, 01-05 (both sources)      -> those 3 closed\n'
        '#   strong_trig   shorts -0.10R overall; 17-21 -0.29R n=78 and\n'
        '#                 09-13 -0.18R n=48 red            -> those 2 closed\n'
        '#   strig_kr      inherits its parent (own cells n=12-18, thin)\n'
        '#   early lane /  no proven-red window (17-21 -0.05R n=116 is flat;\n'
        '#   early movers  21-01 +0.33R n=50 is their best) -> nothing closed\n'
        '# Shorts and longs of PRESSED & BROKE and moonshot are untouched\n'
        '# (moonshot is green all day by its own finding). Momentum\n'
        '# re-entries are gated too: a seat taken at 23:00 is taken at 23:00.\n'
        'TIME_WINDOWS = ("05-09", "09-13", "13-17", "17-21", "21-01", "01-05")\n'
        '_RED_LONG = {"21-01", "01-05"}\n'
        'TIME_CLOSED: dict = {\n'
        '    ("elite_star", "LONG"): set(_RED_LONG),\n'
        '    ("strong_trigger", "LONG"): set(_RED_LONG),\n'
        '    ("strig_kr", "LONG"): set(_RED_LONG),\n'
        '    ("early_lane", "LONG"): set(_RED_LONG),\n'
        '    ("early_movers", "LONG"): set(_RED_LONG),\n'
        '    ("elite_star", "SHORT"): {"09-13", "21-01", "01-05"},\n'
        '    ("strong_trigger", "SHORT"): {"09-13", "17-21"},\n'
        '    ("strig_kr", "SHORT"): {"09-13", "17-21"},\n'
        '    ("early_lane", "SHORT"): set(),\n'
        '    ("early_movers", "SHORT"): set(),\n'
        '}\n'
        'TIME_GATED: set = {s for s, _ in TIME_CLOSED}\n'
        'PKT_OFFSET_S = 5 * 3600\n'
        '_clock = time.time                # tests pin the clock here\n'
        '\n'
        '\n'
        'def pkt_hour(now=None) -> int:\n'
        '    t = float(_clock() if now is None else now)\n'
        '    return int((t + PKT_OFFSET_S) // 3600 % 24)\n'
        '\n'
        '\n'
        'def pkt_window4(now=None) -> str:\n'
        '    """The 4h PKT window label the clock study uses."""\n'
        '    h = pkt_hour(now)\n'
        '    if 5 <= h < 9:\n'
        '        return "05-09"\n'
        '    if 9 <= h < 13:\n'
        '        return "09-13"\n'
        '    if 13 <= h < 17:\n'
        '        return "13-17"\n'
        '    if 17 <= h < 21:\n'
        '        return "17-21"\n'
        '    return "21-01" if h >= 21 or h < 1 else "01-05"\n'
        '\n'
        '\n'
        'def pkt_window(now=None) -> str:\n'
        '    """The pulse colour for LONGS: green 13-21 · yellow 05-13 · red\n'
        '    21-05 (PKT)."""\n'
        '    h = pkt_hour(now)\n'
        '    if 13 <= h < 21:\n'
        '        return "green"\n'
        '    if 5 <= h < 13:\n'
        '        return "yellow"\n'
        '    return "red"\n'
        '\n'
        '\n'
        'def time_gate_ok(src, side, now=None) -> bool:\n'
        '    """False only when (stream, side) has the current 4h PKT window\n'
        '    in its TIME_CLOSED set."""\n'
        '    closed = TIME_CLOSED.get((src, (side or "").upper()))\n'
        '    if not closed:\n'
        '        return True\n'
        '    return pkt_window4(now) not in closed\n',
        "LONG_ONLY + time gate block")

D = rep(D,
        '            if not sym or side not in ("LONG", "SHORT"):\n'
        '                continue\n',
        '            if not sym or side not in ("LONG", "SHORT"):\n'
        '                continue\n'
        '            if name in LONG_ONLY and side != "LONG":\n'
        '                continue        # 🔶 GEN 16.5: PRESSED & BROKE longs only\n',
        "rank_candidates long-only")

D = rep(D,
        'def try_open(state: dict, cands: list, live_fn, active=None):\n',
        'def try_open(state: dict, cands: list, live_fn, active=None,\n'
        '             now=None):\n',
        "try_open signature")

D = rep(D,
        '    _day0 = time.time() - 24 * 3600\n',
        '    _t = float(_clock() if now is None else now)   # GEN 16.5 clock\n'
        '    _day0 = _t - 24 * 3600\n',
        "try_open clock")

D = rep(D,
        '        if c["symbol"] in held:\n'
        '            continue\n'
        '        _res = SPARE_RESERVE.get(c["src"])\n',
        '        if c["symbol"] in held:\n'
        '            continue\n'
        '        if not time_gate_ok(c["src"], c["side"], _t):\n'
        '            continue            # ⏰ GEN 16.5: 🔴 21-05 PKT, long seat closed\n'
        '        _res = SPARE_RESERVE.get(c["src"])\n',
        "try_open time gate")

D = rep(D,
        '               "opened_at": time.time(), "fees": fee_in,\n',
        '               "opened_at": _t, "fees": fee_in,\n',
        "opened_at clock")

# ============================ agent_worker.py ============================
W = open(ROOT + "agent_worker.py", encoding="utf-8").read()

W = rep(W, '_DEMO_STARS: list = []\n',
        '_DEMO_STARS: list = []\n'
        '_DEMO_PB: list = []     # 🔶💥 GEN 16.5 pressed-first breaks, LONGS ONLY\n',
        "_DEMO_PB list")

W = rep(W,
        '                        store.record_signal("press_break", _sig_pb)\n',
        '                        store.record_signal("press_break", _sig_pb)\n'
        '                        # 🎮 GEN 16.5 (user 2026-10-04): priority-1\n'
        '                        # demo seat, LONGS ONLY — same plan as the\n'
        '                        # desk row, conf as stamped on the armed level.\n'
        '                        if (a.get("side") or "").upper() == "LONG":\n'
        '                            _DEMO_PB.append(dict(_sig_pb,\n'
        '                                                 src="press_break",\n'
        '                                                 fired_at=_now))\n'
        '                            del _DEMO_PB[:-12]\n',
        "press site demo feed")

W = rep(W,
        '        _DEMO_STARS[:] = [d for d in _DEMO_STARS\n'
        '                          if _now - d["fired_at"] <= DEMO_FIRE_TTL_S]\n',
        '        _DEMO_STARS[:] = [d for d in _DEMO_STARS\n'
        '                          if _now - d["fired_at"] <= DEMO_FIRE_TTL_S]\n'
        '        _DEMO_PB[:] = [d for d in _DEMO_PB\n'
        '                       if _now - d["fired_at"] <= DEMO_FIRE_TTL_S]\n',
        "prune")

W = rep(W,
        '                         ("strig_kr", "trig_strong_kr")):\n',
        '                         ("strig_kr", "trig_strong_kr"),\n'
        '                         ("press_break", "press_break")):   # GEN 16.5\n',
        "_dz_form")

W = rep(W,
        '        _dz_pools = {\n'
        '            # 🚀 GEN 16.4 (user 2026-09-28): moonshot fires take the\n',
        '        _dz_pools = {\n'
        '            # 🔶💥 GEN 16.5 (user 2026-10-04): PRESSED & BROKE longs\n'
        '            # lead the ladder (priority 1). Fed by _trigger_watch\'s\n'
        '            # pressed-first break record (LONG filter at the feed,\n'
        '            # LONG_ONLY guard again in rank_candidates).\n'
        '            "press_break": ([dict(d) for d in _DEMO_PB\n'
        '                             if d.get("entry") and d.get("stop")\n'
        '                             and d.get("tp1")]\n'
        '                            + [d for d in _dz_reo\n'
        '                               if d["src"] == "press_break"]),\n'
        '            # 🚀 GEN 16.4 (user 2026-09-28): moonshot fires take the\n',
        "_dz_pools")

W = rep(W,
        '                             ("moonshot", "strong_trigger",\n'
        '                              "elite_star", "early_movers",\n'
        '                              "early_lane", "strig_kr")\n'
        '                             else "strong_trigger"),   # GEN 16.4\n',
        '                             ("moonshot", "strong_trigger",\n'
        '                              "elite_star", "early_movers",\n'
        '                              "early_lane", "strig_kr",\n'
        '                              "press_break")\n'
        '                             else "strong_trigger"),   # GEN 16.5\n',
        "reopen allowlist")

# ================================ app.py ================================
A = open(ROOT + "app.py", encoding="utf-8").read()
A = rep(A, "clip:text'>🎮 DEMO $2,000 — GEN 16.4 · THE PRIORITY THREE",
        "clip:text'>🎮 DEMO $2,000 — GEN 16.5 · THE PRIORITY FOUR", "caption head")
A = rep(A,
        '        "$2,000 ledger (2026-09-14; GEN 16.4 ladder 2026-09-29). "\n'
        '        "<b>PRIORITY THREE:</b> <b>1. ⭐ ELITE STAR conf 40-54 / 65+</b> "\n',
        '        "$2,000 ledger (2026-09-14; GEN 16.5 ladder 2026-10-04). "\n'
        '        "<b>PRIORITY FOUR:</b> <b>1. 🔶💥 PRESSED &amp; BROKE, longs "\n'
        '        "only</b> (an armed number pressed within 0.4% before it broke; "\n'
        '        "any conf, trades all day) · <b>2. ⭐ ELITE STAR conf 40-54 / "\n'
        '        "65+</b> "\n',
        "caption priority list head")
A = rep(A,
        '        "rr&lt;1.2R profile law re-checked at the live fill) · <b>2. 💥 "\n'
        '        "STRONG TRIGGER conf ≥65</b> · <b>3. 🚀 MOONSHOT conf 55-64</b> "\n',
        '        "rr&lt;1.2R profile law re-checked at the live fill) · <b>3. 💥 "\n'
        '        "STRONG TRIGGER conf ≥65</b> · <b>4. 🚀 MOONSHOT conf 55-64</b> "\n',
        "caption 2-3 renumber")
A = rep(A,
        '        "<b>4. ⭐🚀 PRIME ENTRY / early lane conf ≥85</b> · <b>5. 💥🔮 "\n'
        '        "TRIG×KR conf ≥40</b> · <b>6. ⚡ EARLY MOVERS conf 55-64 or "\n'
        '        "85+</b>. "\n',
        '        "<b>5. ⭐🚀 PRIME ENTRY / early lane conf ≥85</b> · <b>6. 💥🔮 "\n'
        '        "TRIG×KR conf ≥40</b> · <b>7. ⚡ EARLY MOVERS conf 55-64 or "\n'
        '        "85+</b>. ⏰ <b>TIME GATE (2026-10-04):</b> LONG seats for star, "\n'
        '        "strong trigger, TRIG×KR, early lane and early movers open only "\n'
        '        "in the 🟢 13-21 and 🟡 05-13 PKT windows — the 🔴 21-05 window "\n'
        '        "is closed to them (star longs at 22:00 PKT measured 17% / "\n'
        '        "-0.61R). SHORT seats close only their measured-red windows: "\n'
        '        "star 09-13 / 21-01 / 01-05 (its shorts live at 17-21, 62% / "\n'
        '        "+0.26R), strong trigger + TRIG×KR 09-13 / 17-21 (-0.18R / "\n'
        '        "-0.29R), early lane + movers none (no red window; 21-01 is "\n'
        '        "their best short hour, +0.33R). PRESSED &amp; BROKE and "\n'
        '        "moonshot trade all day. "\n',
        "caption spare list + time gate")

# ========================= .demo_gen16_test.py =========================
T = open(ROOT + ".demo_gen16_test.py", encoding="utf-8").read()
GREEN = calendar.timegm((2026, 10, 4, 10, 0, 0))      # 15:00 PKT, 🟢
T = rep(T,
        '        "early_lane", "strig_kr"}          # GEN 16.4: six streams\n',
        '        "early_lane", "strig_kr", "press_break"}   # GEN 16.5: seven\n',
        "test roster set")
T = rep(T,
        'assert (da.CLASS_W["elite_star"] > da.CLASS_W["strong_trigger"]\n',
        'assert (da.CLASS_W["press_break"] > da.CLASS_W["elite_star"]\n'
        '        > da.CLASS_W["strong_trigger"]\n',
        "test ladder assert")
T = rep(T,
        'import demo_account as da\nimport time\n',
        'import demo_account as da\nimport time\n'
        f'da._clock = lambda: {GREEN}.0   # GEN 16.5: pin 15:00 PKT (🟢) so the time gate stays open here\n',
        "test clock pin")

for path, s in (("demo_account.py", D), ("agent_worker.py", W), ("app.py", A), (".demo_gen16_test.py", T)):
    with open(ROOT + path, "w", encoding="utf-8", newline="") as f:
        f.write(s)
print("patched demo_account.py, agent_worker.py, app.py, .demo_gen16_test.py  (GREEN ts", GREEN, ")")
