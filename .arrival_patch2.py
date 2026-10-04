"""ARRIVAL BANNER — user 2026-10-05: "these 3 are solid numbers, all should go
accordingly, under the same banner". Every LONG break at an armed ⚡/🔥/💎 number
rings once under one banner with its tier and each tier keeps its own desk ledger:
  T1 HOT + strong coil  86% / +0.21R (n=154)  -> trig_hot
  T2 HOT, any source    83% / +0.23R (n=197)  -> arr_hot
  T3 any long break     76% / +0.11R (n=1190) -> arr_long
Shorts: no bell, no tier (58% / -0.11R at the number). Demo untouched. Replaces the
strong-coil-only HOT block from the previous commit. Anchors must match once."""
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

# 1) replace the HOT-only formatter with the tiered banner + tier rule
i = W.find("def _fmt_hot_arrival(a: dict, px: float) -> str:\n")
j = W.find("\n\n\ndef _fmt_trigger(a: dict, px: float, vk: float) -> str:\n")
if i < 0 or j < 0 or j < i:
    raise SystemExit("formatter markers not found")
NEW_FMT = '''ARRIVAL_TIERS = {
    1: ("\u26a1\U0001F525", "HOT strong coil", "86% / +0.21R over 154 replay breaks"),
    2: ("\u26a1\U0001F525", "HOT arrival", "83% / +0.23R over 197 replay breaks"),
    3: ("\u26a1", "long break at the number", "76% / +0.11R over 1,190 replay breaks"),
}


def _arrival_tier(src, side, grade):
    """The ARRIVAL banner tier for a break (user 2026-10-05, from the
    .prefire_study replay, Aug 15 - Sep 28):
      1 = HOT arrival at a \u26a1 strong-coil number     86% / +0.21R n=154
      2 = HOT arrival at any \u26a1/\U0001F525/\U0001F48E number     83% / +0.23R n=197
      3 = any LONG break at an armed number        76% / +0.11R n=1,190
      None = shorts (58% / -0.11R) or an unknown source.
    T1 is inside T2 is inside T3 — each keeps its own desk ledger. Pure."""
    s = str(src or "")
    if (side or "").upper() != "LONG" or s[:1] not in ("\u26a1", "\U0001F525", "\U0001F48E"):
        return None
    if grade == "HOT":
        return 1 if s.startswith("\u26a1") else 2
    return 3


def _fmt_arrival(a: dict, px: float, tier: int) -> str:
    """One banner for all three classes; the tier line says which one."""
    emo, label, rec = ARRIVAL_TIERS[int(tier)]
    g = a.get("arrival")
    v2, m3 = a.get("arr_vol2"), a.get("arr_mom3")
    if g == "HOT":
        how = f"arrived HOT: {v2}x the 7-day bar with a {m3} ATR drift into the number"
    elif g == "COLD":
        how = (f"arrived COLD: {v2}x volume, {m3} ATR drift (the weak end, "
               f"68% / -0.02R in the replay)")
    elif g == "NEUTRAL":
        how = f"arrival neutral: {v2}x volume, {m3} ATR drift"
    else:
        how = "arrival: no read (short candle history)"
    t2 = f" · TP2 `{float(a['tp2']):g}`" if a.get("tp2") else ""
    src = str(a.get("src") or "").strip()
    return (f"{emo} *ARRIVAL T{int(tier)} — {a['base']} LONG · {label}*\\n"
            f"{src} number `{float(a['trigger']):g}` broke · {how}\\n"
            f"entry `{float(px):g}` · SL `{float(a['stop']):g}` · TP1 "
            f"`{float(a['tp1']):g}`{t2}\\n"
            f"_this tier: {rec}. T1 HOT strong coil 86% / +0.21R · T2 HOT "
            f"83% / +0.23R · T3 any long break 76% / +0.11R (Aug 15 - Sep 28). "
            f"Shorts at the number lost 58% / -0.11R, so only longs ring. "
            f"Desk tiers arrival T1 / T2 / T3 prove it forward._")'''
W = W[:i] + NEW_FMT + W[j:]

# 2) the banner block: after the demo fire feed, before the (muted) plain trigger bell
W = rep(W,
        "                        del _DEMO_FIRES[:-40]\n"
        "                try:\n"
        "                    if store.should_alert(\n"
        "                            f\"trig:{a['symbol']}:{a['side']}\",\n",
        "                        del _DEMO_FIRES[:-40]\n"
        "                # \u26a1\U0001F525 ARRIVAL BANNER (user 2026-10-05: \"these 3 are\n"
        "                # solid numbers, all should go accordingly, under the\n"
        "                # same banner\"): every LONG break at an armed \u26a1/\U0001F525/\U0001F48E\n"
        "                # number rings ONCE under one banner with its tier, and\n"
        "                # each tier keeps its own desk ledger (T1 inside T2\n"
        "                # inside T3):\n"
        "                #   T1 HOT + strong coil  86% / +0.21R (n=154)  -> trig_hot\n"
        "                #   T2 HOT, any source    83% / +0.23R (n=197)  -> arr_hot\n"
        "                #   T3 any long break     76% / +0.11R (n=1190) -> arr_long\n"
        "                # Shorts at the number lost 58% / -0.11R: no bell, no\n"
        "                # tier. Demo untouched (user: nothing deploys to demo).\n"
        "                # Mute: tg.send -> _MUTE_R9 below.\n"
        "                _atier = _arrival_tier(_src0, a.get(\"side\"),\n"
        "                                       a.get(\"arrival\"))\n"
        "                if _atier is not None:\n"
        "                    try:\n"
        "                        _sig_a = {\"symbol\": a[\"symbol\"],\n"
        "                                  \"base\": a[\"base\"],\n"
        "                                  \"side\": a[\"side\"],\n"
        "                                  \"tier\": f\"T{_atier}\",\n"
        "                                  \"score\": a.get(\"score\"),\n"
        "                                  \"conf\": a.get(\"conf\"),\n"
        "                                  \"entry\": px, \"stop\": a[\"stop\"],\n"
        "                                  \"tp1\": a[\"tp1\"],\n"
        "                                  \"tp2\": a.get(\"tp2\"), \"src\": _src0,\n"
        "                                  \"arrival\": a.get(\"arrival\"),\n"
        "                                  \"arr_vol2\": a.get(\"arr_vol2\"),\n"
        "                                  \"arr_mom3\": a.get(\"arr_mom3\")}\n"
        "                        _tiers_a = ([\"arr_long\"]\n"
        "                                    + ([\"arr_hot\"] if _atier <= 2 else [])\n"
        "                                    + ([\"trig_hot\"] if _atier == 1 else []))\n"
        "                        for _tn in _tiers_a:\n"
        "                            store.record_signal(_tn, _sig_a)\n"
        "                            shadow_trader.open_from_signal(_tn, _sig_a, px)\n"
        "                        if (store.should_alert(\n"
        "                                f\"arrival:{a['symbol']}:LONG\", 6 * 3600)\n"
        "                                and not _bstock_quiet(a[\"symbol\"])):\n"
        "                            tg.send(_fmt_arrival(a, px, _atier)\n"
        "                                    + _kr_note(a))\n"
        "                    except Exception as _ar_exc:\n"
        "                        print(\"  arrival error:\", _ar_exc, flush=True)\n"
        "                try:\n"
        "                    if store.should_alert(\n"
        "                            f\"trig:{a['symbol']}:{a['side']}\",\n",
        "arrival banner block")

# 3) remove the strong-coil-only HOT block from the previous commit
s0 = W.find("                        # \u26a1\U0001F525 HOT ARRIVAL (study 2026-10-05): the\n")
e0 = W.find("                                print(\"  trig_hot error:\", _ha_exc,\n                                      flush=True)\n")
if s0 < 0 or e0 < 0:
    raise SystemExit("old HOT block markers not found")
e0 += len("                                print(\"  trig_hot error:\", _ha_exc,\n                                      flush=True)\n")
W = W[:s0] + W[e0:]

A = open(ROOT + "app.py", encoding="utf-8").read()
A = rep(A,
        '                   "trig_hot": "\u26a1\U0001F525 HOT ARRIVAL (strong-coil long that "\n'
        '                               "arrived on 1.3-3x volume + 0.3-1.5 ATR "\n'
        '                               "drift — 86%/+0.21R replay, proving)",\n',
        '                   "trig_hot": "\u26a1\U0001F525 ARRIVAL T1 — HOT strong-coil longs "\n'
        '                               "(1.3-3x volume + 0.3-1.5 ATR drift into "\n'
        '                               "the number; 86%/+0.21R replay, proving)",\n'
        '                   "arr_hot": "\u26a1\U0001F525 ARRIVAL T2 — HOT arrival longs, any "\n'
        '                              "source (83%/+0.23R replay, proving)",\n'
        '                   "arr_long": "\u26a1 ARRIVAL T3 — every long break at an "\n'
        '                               "armed number (76%/+0.11R replay, proving)",\n',
        "app tier names")

U = open(ROOT + "auditor.py", encoding="utf-8").read()
U = rep(U, '    "trig_hot": "trig_hot",\n',
        '    "trig_hot": "trig_hot",\n    "arr_hot": "arr_hot",\n    "arr_long": "arr_long",\n', "auditor tiers")

for path, s in (("agent_worker.py", W), ("app.py", A), ("auditor.py", U)):
    with open(ROOT + path, "w", encoding="utf-8", newline="") as f:
        f.write(s)
print("patched: ARRIVAL banner T1/T2/T3 live, old HOT block removed, names in app + auditor")
