"""One-shot patch — ⚡🔥 ARRIVAL GRADE (study 2026-10-05, .prefire_study.py; user:
"run it ... build a system on it overnight").
Every trigger break gets an `arrival` stamp read off the two CLOSED 15m bars before
the break bar: HOT = volume 1.3-3x the 7-day median bar AND drift toward the number
0.3-1.5 ATR(14); COLD = volume <1x AND drift <0.3 ATR; else NEUTRAL. Replay: long
breaks HOT 83%/+0.23R (n=197) vs COLD 68%/-0.02R; strong-coil longs HOT 86%/+0.21R.
Wiring: stamp on the trig_strong + press_break desk records and the demo fire feed;
HOT strong-coil LONG breaks also record + shadow-trade under tier `trig_hot`; a
HOT ARRIVAL bell is written but MUTED (_MUTE_R9) until the user's word. Nothing
existing changes behaviour. Anchors must match exactly once."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = "F:/Trading Indicator/"


def rep(src, old, new, label):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"ANCHOR {label!r} matched {n} times — aborting, nothing written")
    return src.replace(old, new, 1)


W = open(ROOT + "agent_worker.py", encoding="utf-8").read()

HELPERS = '''def _arrival_grade(d15, side) -> dict | None:
    """⚡🔥 ARRIVAL GRADE (study 2026-10-05, .prefire_study.py, 1,691 breaks):
    how the price ARRIVED at the number in the two CLOSED 15m bars before
    the break bar. HOT = volume 1.3-3x the 7-day median bar AND drift
    toward the number 0.3-1.5 ATR(14) -> long breaks 83% / +0.23R (n=197;
    strong-coil longs 86% / +0.21R, 6 of 8 weeks green, survives the
    drop-3-days and day-weighted tests). COLD = volume <1x AND drift
    <0.3 ATR -> 68% / -0.02R. Everything else NEUTRAL. Shorts are not
    rescued by a hot arrival (59% / -0.07R). `d15` = 15m frame with the
    FORMING (break) bar last. Pure; None when the frame is too short."""
    try:
        import numpy as _np
        if d15 is None or len(d15) < 120:
            return None
        closed = d15.iloc[:-1]
        c = closed["close"].to_numpy(float)
        h = closed["high"].to_numpy(float)
        l = closed["low"].to_numpy(float)
        v = closed["volume"].to_numpy(float)
        if len(c) < 20:
            return None
        tr = (_np.maximum(h[-14:], c[-15:-1])
              - _np.minimum(l[-14:], c[-15:-1]))
        atr = float(tr.mean())
        if not atr > 0:
            return None
        sgn = 1.0 if (side or "").upper() == "LONG" else -1.0
        mom3 = sgn * (c[-1] - c[-4]) / atr
        base = float(_np.median(v[max(0, len(v) - 674):-2])) or 1e-12
        vol2 = float(v[-2:].mean()) / base
        if 1.3 <= vol2 <= 3.0 and 0.3 <= mom3 <= 1.5:
            grade = "HOT"
        elif vol2 < 1.0 and mom3 < 0.3:
            grade = "COLD"
        else:
            grade = "NEUTRAL"
        return {"grade": grade, "vol2": round(vol2, 2), "mom3": round(mom3, 2)}
    except Exception:
        return None


def _fmt_hot_arrival(a: dict, px: float) -> str:
    """⚡🔥 the HOT ARRIVAL bell (written 2026-10-05, MUTED until the user's
    word): a strong-coil LONG number that broke after arriving on rising,
    not-yet-spiked volume with a steady drift into it."""
    v2 = a.get("arr_vol2")
    m3 = a.get("arr_mom3")
    t2 = f" · TP2 `{float(a['tp2']):g}`" if a.get("tp2") else ""
    return (f"⚡🔥 *HOT ARRIVAL — {a['base']} LONG*\\n"
            f"the number `{float(a['trigger']):g}` broke on rising volume "
            f"({v2}x the 7-day bar) with a {m3} ATR drift into it\\n"
            f"entry `{float(px):g}` · SL `{float(a['stop']):g}` · TP1 "
            f"`{float(a['tp1']):g}`{t2}\\n"
            f"_the measured best cell on the trigger desk: strong-coil longs "
            f"arriving like this ran 86% / +0.21R over 154 breaks (Aug 15 - "
            f"Sep 28); quiet arrivals 70% / +0.01R. Proving on tier trig hot._")


'''
W = rep(W, "def _fmt_trigger(a: dict, px: float, vk: float) -> str:\n",
        HELPERS + "def _fmt_trigger(a: dict, px: float, vk: float) -> str:\n", "helpers before _fmt_trigger")

# grade computed at the break, right after the armed level is popped
W = rep(W,
        "                    _TRIG_ARMED.pop(k, None)\n"
        "                # 🎮 GEN 6 demo feed",
        "                    _TRIG_ARMED.pop(k, None)\n"
        "                # ⚡🔥 ARRIVAL GRADE (2026-10-05): the two closed 15m\n"
        "                # bars before this break bar — stamped on every break\n"
        "                # record so the ledger can split HOT / COLD arrivals.\n"
        "                _arr = None\n"
        "                try:\n"
        "                    _arr = _arrival_grade(binance_client.get_klines(\n"
        "                        a[\"symbol\"], \"15m\", limit=700), a[\"side\"])\n"
        "                except Exception:\n"
        "                    _arr = None\n"
        "                a[\"arrival\"] = (_arr or {}).get(\"grade\")\n"
        "                a[\"arr_vol2\"] = (_arr or {}).get(\"vol2\")\n"
        "                a[\"arr_mom3\"] = (_arr or {}).get(\"mom3\")\n"
        "                # 🎮 GEN 6 demo feed",
        "arrival grade at the break")

# demo fire feed carries the stamp (no gate yet — a future seat rule can read it)
W = rep(W,
        "                             \"conf\": a.get(\"conf\"),\n"
        "                             \"src\": _dsrc, \"fired_at\": _now})\n"
        "                        del _DEMO_FIRES[:-40]\n",
        "                             \"conf\": a.get(\"conf\"),\n"
        "                             \"arrival\": a.get(\"arrival\"),\n"
        "                             \"src\": _dsrc, \"fired_at\": _now})\n"
        "                        del _DEMO_FIRES[:-40]\n",
        "demo fire feed stamp")

# press_break record carries the stamp
W = rep(W,
        "                                   \"tp1\": a[\"tp1\"],\n"
        "                                   \"tp2\": a.get(\"tp2\")}\n"
        "                        store.record_signal(\"press_break\", _sig_pb)\n",
        "                                   \"tp1\": a[\"tp1\"],\n"
        "                                   \"tp2\": a.get(\"tp2\"),\n"
        "                                   \"arrival\": a.get(\"arrival\"),\n"
        "                                   \"arr_vol2\": a.get(\"arr_vol2\"),\n"
        "                                   \"arr_mom3\": a.get(\"arr_mom3\")}\n"
        "                        store.record_signal(\"press_break\", _sig_pb)\n",
        "press_break stamp")

# trig_strong record carries the stamp + the HOT ARRIVAL tier
W = rep(W,
        "                                  \"tp1\": a[\"tp1\"],\n"
        "                                  \"tp2\": a.get(\"tp2\")}\n"
        "                        store.record_signal(\"trig_strong\", _sig_t)\n",
        "                                  \"tp1\": a[\"tp1\"],\n"
        "                                  \"tp2\": a.get(\"tp2\"),\n"
        "                                  \"arrival\": a.get(\"arrival\"),\n"
        "                                  \"arr_vol2\": a.get(\"arr_vol2\"),\n"
        "                                  \"arr_mom3\": a.get(\"arr_mom3\")}\n"
        "                        store.record_signal(\"trig_strong\", _sig_t)\n"
        "                        # ⚡🔥 HOT ARRIVAL (study 2026-10-05): the\n"
        "                        # strong-coil LONG break that arrived on\n"
        "                        # 1.3-3x volume + 0.3-1.5 ATR drift — 86% /\n"
        "                        # +0.21R over 154 replay breaks. Own desk\n"
        "                        # tier `trig_hot` proves it forward; the bell\n"
        "                        # is written but MUTED until the user's word\n"
        "                        # (revert: _MUTE_R9 -> tg.send).\n"
        "                        if (a.get(\"arrival\") == \"HOT\"\n"
        "                                and a[\"side\"] == \"LONG\"):\n"
        "                            try:\n"
        "                                _sig_h = dict(_sig_t, tier=\"HOT\")\n"
        "                                store.record_signal(\"trig_hot\", _sig_h)\n"
        "                                shadow_trader.open_from_signal(\n"
        "                                    \"trig_hot\", _sig_h, px)\n"
        "                                if (store.should_alert(\n"
        "                                        f\"trighot:{a['symbol']}:\"\n"
        "                                        f\"{a['side']}\", 6 * 3600)\n"
        "                                        and not _bstock_quiet(\n"
        "                                            a[\"symbol\"])):\n"
        "                                    _MUTE_R9(_fmt_hot_arrival(a, px)\n"
        "                                             + _kr_note(a))\n"
        "                            except Exception as _ha_exc:\n"
        "                                print(\"  trig_hot error:\", _ha_exc,\n"
        "                                      flush=True)\n",
        "trig_strong stamp + trig_hot tier")

A = open(ROOT + "app.py", encoding="utf-8").read()
A = rep(A,
        '                   "elite_seated65": "💎🏆 ELITE SEATED 65+ (seated + "\n'
        '                                     "conf 65+, any side — records "\n'
        '                                     "only, no bell)",\n',
        '                   "elite_seated65": "💎🏆 ELITE SEATED 65+ (seated + "\n'
        '                                     "conf 65+, any side — records "\n'
        '                                     "only, no bell)",\n'
        '                   "trig_hot": "⚡🔥 HOT ARRIVAL (strong-coil long that "\n'
        '                               "arrived on 1.3-3x volume + 0.3-1.5 ATR "\n'
        '                               "drift — 86%/+0.21R replay, proving)",\n',
        "app tier name")

U = open(ROOT + "auditor.py", encoding="utf-8").read()
U = rep(U, '    "elite_seated65": "elite_seated65",\n',
        '    "elite_seated65": "elite_seated65",\n    "trig_hot": "trig_hot",\n', "auditor tier")

for path, s in (("agent_worker.py", W), ("app.py", A), ("auditor.py", U)):
    with open(ROOT + path, "w", encoding="utf-8", newline="") as f:
        f.write(s)
print("patched agent_worker.py, app.py, auditor.py")
