"""2026-11-01 (user: "bring the apex v2 gated with 1h verdict to telegram notifications and also
on decision desk on paper trading … ungated … can go to decision desk"): 🏆💎 APEX V2 GATED.
Gate at the fire (all known then): BTC day within ±1.5% · stop 2–4% · not fired 17–21 PKT.
Study 2026-11-01 (.apex_v2_advance.py): gated 61% / +0.33R (129) vs rest 50% / −0.04R (657) on
the APEX core 10 Sep → 24 Oct, both halves, both months; the V2 stream itself 69% / +0.58R (29).
- every apex_v2 record now carries gate / gate_read (the ungated desk tier stays as it is)
- PASS → new desk tier apex_v2_gated (records + shadow trade) + the 🏆💎 bell (thread message)
- the 1H VERDICT replies in the bell's thread (LIVE: 85–91% / +1.0R held, TP1 usually inside 2h
  while above the entry; back at the entry → ≈ even, 8–12h · DEAD: ≈ flat, plan in charge)
- the old ungated bell line stays muted (untouched); 🏦 TP1 ping roster learns the gated stream
Page: desk label for apex_v2_gated. Demo untouched."""
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

# 1. switch + records, beside the other bell switches
W = rep(W, "TG_PRIME_TRIG = True     # 💥🥇 bell ON 2026-10-24",
        'TG_APEX_V2_GATED = True  # 🏆💎 APEX V2 GATED bell ON 2026-11-01 (user); the ungated APEX V2 bell stays muted. False = silent, tiers continue.\n'
        'APEX_V2_GATE_REC = ("gated 61% / +0.33R (129) vs rest 50% / −0.04R (657) on the APEX core "\n'
        '                    "10 Sep → 24 Oct · the V2 stream itself 69% / +0.58R (29) · from the fire price")\n'
        'APEX_V2_LIVE_REC = ("gated + LIVE at the hour 85% / +1.01R (48) held · TP1 usually inside 2h while "\n'
        '                    "it holds above the entry · back at the entry → odds ≈ even, 8–12h more")\n'
        "TG_PRIME_TRIG = True     # 💥🥇 bell ON 2026-10-24", "switch")

# 2. the gate read + the two formatters, before _fmt_apex_v2
W = rep(W, "def _fmt_apex_v2(sig, px=None, rec=None) -> str:\n",
        '''def _apex_v2_gate(sig, now=None):
    """🏆💎 APEX V2 three-rule read (user 2026-11-01), all known at the fire: BTC day within
    ±1.5% (unreadable passes, every gate's law) · stop 2–4% of entry · not fired 17–21 PKT.
    Returns (passed, line). Study: gated 61% / +0.33R (129) vs rest 50% / −0.04R (657)."""
    now = time.time() if now is None else float(now)
    try:
        btc = _btc_day_pct()
    except Exception:
        btc = None
    ok_btc = btc is None or -1.5 <= float(btc) <= 1.5
    try:
        sp = abs(float(sig["entry"]) - float(sig["stop"])) / float(sig["entry"]) * 100
    except Exception:
        sp = None
    ok_stop = sp is not None and 2.0 <= sp <= 4.0
    h = int((now // 3600 + 5) % 24)
    ok_clock = not (17 <= h < 21)
    line = (f"read: {'✅' if ok_btc else '⚠️'} BTC {('%+.2f%%' % btc) if btc is not None else '?'} today · "
            f"{'✅' if ok_stop else '⚠️'} stop {sp:.1f}%" + (" (needs 2–4%)" if not ok_stop else "") + " · "
            f"{'✅' if ok_clock else '⚠️'} {h:02d} PKT" + (" (17–21 is the weak window)" if not ok_clock else "")
            + f" — {APEX_V2_GATE_REC}")
    return (ok_btc and ok_stop and ok_clock), line


def _fmt_apex_v2_gated(sig, px, read_line, now):
    """🏆💎 APEX V2 GATED bell (user 2026-11-01): the read that let it through, the plan at the
    live price, the ladder, the hold law (the 1H VERDICT answers in this thread), the record."""
    sd = (sig.get("side") or "").upper()
    sg = 1 if sd == "LONG" else -1
    e = float(px or sig["entry"])
    st, t1 = float(sig["stop"]), float(sig["tp1"])
    t2 = float(sig["tp2"]) if sig.get("tp2") else None
    rk = max(1e-12, sg * (e - st))
    tps = f"TP1 `{t1:g}` (+{sg * (t1 - e) / rk:.1f}R)" + (f" · TP2 `{t2:g}` (+{sg * (t2 - e) / rk:.1f}R)" if t2 else "")
    try:
        fwd = rung_stats.rec(rung_stats.tier_rec("apex_v2_gated", None, now))
    except Exception:
        fwd = "record unavailable"
    return (f"🏆💎 *APEX V2 GATED — {sig['base']} {sd} · TAKE · {rung_stats.pkt_hm(now)} PKT*\\n"
            f"{read_line}\\n"
            f"STRONG · score {float(sig.get('score') or 0):.0f} · heat {float(sig.get('heat') or 0):.0f} · "
            f"entry `{float(sig['entry']):g}` · live `{e:g}` · SL `{st:g}` · {tps}\\n"
            f"🪜 plan: at +1R move SL to entry · at TP1 lock SL at TP1 and ride to TP2, trailing 1.2R · 48h max\\n"
            f"⏱ the 1H VERDICT answers in this thread — {APEX_V2_LIVE_REC}\\n"
            f"forward ledger (gated tier since 01 Nov): {fwd} · {rung_stats.stamp_now(now)}\\n"
            f"_two months of evidence behind the gate (10 Sep → 24 Oct); the 14 Oct 78-day replay did not find the "
            f"BTC rule — re-read at 30 gated closes. Gate fails record silently on the desk._")


def _fmt_apex_v2_verdict(ew, prg):
    """⏱🏆 the 1H VERDICT reply under a gated APEX V2 bell (user 2026-11-01)."""
    if ew.get("oneh") == "LIVE":
        return (f"⏱🏆 *{ew['base']} {ew['side']} — 1H VERDICT: 🟢 LIVE* (APEX V2 gated)\\n"
                f"covered {prg * 100:.0f}% of the path to TP1 in the first hour.\\n"
                f"_{APEX_V2_LIVE_REC}. In from the fire? Hold the plan, don't add. Not in? Entering at the hour "
                f"measured +0.2R on gated fires — the fire was the entry._")
    return (f"⏱🏆 *{ew['base']} {ew['side']} — 1H VERDICT: 🔴 DEAD* (APEX V2 gated)\\n"
            f"flat/under water at the hour ({prg * 100:+.0f}% of path).\\n"
            f"_gated + DEAD finished ≈ flat (47–56% win, −0.1…+0.2R held) — not the loser an ungated DEAD is. "
            f"The plan's SL / TP stay in charge; no add._")


def _fmt_apex_v2(sig, px=None, rec=None) -> str:
''', "formatters")

# 3. the fire site: stamp the read on the record, open the gated tier, ring, mark the watch
W = rep(W,
        '                     "tp2": _av2.get("tp2"), "tier": "STRONG",\n'
        '                     "score": _sc2, "heat": _ht2}\n'
        '            store.record_signal("apex_v2", _sig2)\n',
        '                     "tp2": _av2.get("tp2"), "tier": "STRONG",\n'
        '                     "score": _sc2, "heat": _ht2}\n'
        '            # 🏆💎 GATED read (user 2026-11-01): stamped on every record; only a\n'
        '            # pass opens the gated tier and rings. The ungated tier below is\n'
        '            # untouched — the two ledgers are the comparison he asked for.\n'
        '            try:\n'
        '                _gok2, _grd2 = _apex_v2_gate(_sig2, time.time())\n'
        '            except Exception:\n'
        '                _gok2, _grd2 = False, "read unavailable"\n'
        '            _sig2["gate"] = "pass" if _gok2 else "muted"\n'
        '            _sig2["gate_read"] = _grd2\n'
        '            store.record_signal("apex_v2", _sig2)\n', "fire record")
W = rep(W,
        '            shadow_trader.open_from_signal("apex_v2", _sig2, _px2)\n'
        '            _ego_add(dict(_sig2), fam="apexv2")\n',
        '            shadow_trader.open_from_signal("apex_v2", _sig2, _px2)\n'
        '            _ego_add(dict(_sig2), fam="apexv2")\n'
        '            if _gok2:\n'
        '                try:\n'
        '                    store.record_signal("apex_v2_gated", _sig2)\n'
        '                    shadow_trader.open_from_signal("apex_v2_gated", _sig2, _px2)\n'
        '                except Exception as _g2_exc:\n'
        '                    print("  apexv2 gated tier error:", _g2_exc, flush=True)\n'
        '                _gb2 = "off"\n'
        '                if TG_APEX_V2_GATED and not _bstock_quiet(_sym2):\n'
        '                    try:\n'
        '                        _okg, _mg2, _idg2 = tg.send_thread(\n'
        '                            _fmt_apex_v2_gated(_sig2, _px2, _grd2, time.time())\n'
        '                            + _kr_note(_sig2))\n'
        '                        n_alerts += 1 if _okg else 0\n'
        '                        _gb2 = "sent" if _okg else f"failed: {_mg2}"\n'
        '                        if _okg:   # the 1H VERDICT answers in this thread\n'
        '                            for _ewb2 in _EGO_WATCH:\n'
        '                                if (_ewb2["symbol"] == _sym2 and _ewb2["side"] == _sd2\n'
        '                                        and _ewb2.get("fam") == "apexv2"):\n'
        '                                    _ewb2["buzzed"] = True\n'
        '                                    _ewb2["gated"] = True\n'
        '                                    _ewb2["tg_ids"] = _idg2\n'
        '                    except Exception as _gb_exc:\n'
        '                        _gb2 = f"error: {_gb_exc}"\n'
        '                print(f"  [apexv2-gated] {_sig2[\'base\']} {_sd2} bell={_gb2}", flush=True)\n', "gated open + bell")

# 4. the verdict reply for a gated APEX V2 bell (before the widened elif, which never saw apexv2)
W = rep(W,
        "                        elif _ew.get(\"buzzed\") or _ew.get(\"appr\"):\n"
        "                            # 🔊 1H VERDICT — WIDENED (user\n",
        "                        elif _ew.get(\"buzzed\") and _ew.get(\"fam\") == \"apexv2\":\n"
        "                            # 🏆💎 the gated APEX V2 bell's verdict answers in its\n"
        "                            # thread (user 2026-11-01); ungated APEX V2 never\n"
        "                            # buzzes, so it never lands here.\n"
        "                            try:\n"
        "                                _okv2, _mv2, _ = tg.send_thread(\n"
        "                                    _fmt_apex_v2_verdict(_ew, _prg),\n"
        "                                    reply_to=_ew.get(\"tg_ids\"))\n"
        "                                n_alerts += 1 if _okv2 else 0\n"
        "                                print(f\"  [thread] apexv2 verdict {_ew['base']} \"\n"
        "                                      f\"{_ew['side']} {_ew['oneh']} sent={_okv2} {_mv2}\", flush=True)\n"
        "                            except Exception as _v2t_exc:\n"
        "                                print(\"  apexv2 verdict thread error:\", _v2t_exc, flush=True)\n"
        "                        elif _ew.get(\"buzzed\") or _ew.get(\"appr\"):\n"
        "                            # 🔊 1H VERDICT — WIDENED (user\n", "verdict branch")

# 5. TP1 ping roster
W = rep(W, '    "apex_v2": "🏆💎 APEX V2",\n',
        '    "apex_v2": "🏆💎 APEX V2",\n    "apex_v2_gated": "🏆💎 APEX V2 (gated)",   # bell since 2026-11-01\n', "tp1 roster")
with open(ROOT + "agent_worker.py", "w", encoding="utf-8", newline="") as f:
    f.write(W)

# page label on the desk
A = open(ROOT + "app.py", encoding="utf-8").read()
A = rep(A,
        '                   "apex_v2": "🏆² APEX V2 (certified core: STRONG "\n'
        '                              "· score 90-94 · heat<75 — 59%/+0.14R "\n'
        '                              "backtest, proving forward)",\n',
        '                   "apex_v2": "🏆² APEX V2 (certified core: STRONG "\n'
        '                              "· score 90-94 · heat<75 — 59%/+0.14R "\n'
        '                              "backtest, proving forward; UNGATED, no bell — "\n'
        '                              "the comparison ledger)",\n'
        '                   "apex_v2_gated": "🏆💎 APEX V2 GATED (the bell since 01 Nov: "\n'
        '                                    "BTC day within ±1.5% · stop 2–4% · not 17–21 "\n'
        '                                    "PKT — 61%/+0.33R over 129 on the APEX core, "\n'
        '                                    "69%/+0.58R over 29 on the stream, 10 Sep → 24 "\n'
        '                                    "Oct; 1H verdict replies in the thread)",\n', "page label")
with open(ROOT + "app.py", "w", encoding="utf-8", newline="") as f:
    f.write(A)

# roster audit (reads origin/main — passes after the push)
R = open(ROOT + ".tg_roster_audit.py", encoding="utf-8").read()
R = rep(R, '    ("muted: APEX V2, moonshot", "_MUTE_RULES(_fmt_apex_v2(" in W and "if key_prefix not in (() if TG_RULES else" in W),\n',
        '    ("muted: APEX V2 ungated, moonshot", "_MUTE_RULES(_fmt_apex_v2(" in W and "if key_prefix not in (() if TG_RULES else" in W),\n'
        '    ("🏆💎 APEX V2 GATED rings (2026-11-01): switch True, gated tier + thread bell + 1H verdict reply, on the TP1 roster",\n'
        '     flag("TG_APEX_V2_GATED").startswith("True") and \'store.record_signal("apex_v2_gated", _sig2)\' in W\n'
        '     and "tg.send_thread(\\n                            _fmt_apex_v2_gated(" in W and "_fmt_apex_v2_verdict(_ew, _prg)" in W\n'
        '     and \'"apex_v2_gated": "🏆💎 APEX V2 (gated)"\' in W),\n', "audit")
with open(ROOT + ".tg_roster_audit.py", "w", encoding="utf-8", newline="") as f:
    f.write(R)
print("patched: worker (switch, gate read, formatters, fire site, verdict reply, TP1 roster) · page label · audit")
