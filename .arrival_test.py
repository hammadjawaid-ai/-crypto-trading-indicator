"""⚡🔥 ARRIVAL — grade on synthetic 15m frames, the T1/T2/T3 tier rule, the banner
markdown for every grade, and wiring: banner block after the demo feed and before
the plain trigger bell, three desk tiers nested, bell live for T1+T2 only with a
1.5h per-coin window, BEST OF THE BEST out of the push roster, demo roster
untouched, names in app/auditor."""
import ast
import importlib.util
import io
import sys

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
W = open(r"F:\Trading Indicator\agent_worker.py", encoding="utf-8").read()
A = open(r"F:\Trading Indicator\app.py", encoding="utf-8").read()
U = open(r"F:\Trading Indicator\auditor.py", encoding="utf-8").read()
fails = []
tree = ast.parse(W)
import rung_stats
ns = {"np": np, "pd": pd, "rung_stats": rung_stats}
for n in tree.body:
    if isinstance(n, ast.FunctionDef) and n.name in ("_arrival_grade", "_arrival_tier", "_fmt_arrival"):
        exec(compile(ast.Module(body=[n], type_ignores=[]), n.name, "exec"), ns)
    elif isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "ARRIVAL_TIERS":
        exec(compile(ast.Module(body=[n], type_ignores=[]), "tiers", "exec"), ns)
grade, tier, fmt = ns["_arrival_grade"], ns["_arrival_tier"], ns["_fmt_arrival"]


def frame(n=800, base_vol=100.0, last_vols=(100, 100), drift_atr=0.0, side_up=True, seed=1):
    rng = np.random.default_rng(seed)
    c = 100.0 + np.cumsum(rng.normal(0, 0.05, n))
    h, l = c + 0.5, c - 0.5
    v = np.full(n, base_vol)
    sgn = 1.0 if side_up else -1.0
    step = sgn * drift_atr / 3.0
    for k, i in enumerate(range(n - 4, n - 1)):
        c[i] = c[n - 5] + step * (k + 1)
        h[i], l[i] = c[i] + 0.5, c[i] - 0.5
    v[n - 3], v[n - 2] = last_vols
    v[n - 1] = 999.0
    idx = pd.date_range("2026-10-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"open": c, "high": h, "low": l, "close": c, "volume": v}, index=idx)


for df, side, want, lab in [
    (frame(last_vols=(200, 200), drift_atr=0.8), "LONG", "HOT", "2x volume, +0.8 ATR drift, long"),
    (frame(last_vols=(135, 135), drift_atr=0.35), "LONG", "HOT", "just inside the band edges"),
    (frame(last_vols=(300, 300), drift_atr=1.5), "LONG", "HOT", "band edges 3x / 1.5 ATR"),
    (frame(last_vols=(200, 200), drift_atr=0.8), "SHORT", "NEUTRAL", "same tape read as a short"),
    (frame(last_vols=(200, 200), drift_atr=0.8, side_up=False), "SHORT", "HOT", "short with drift down is hot"),
    (frame(last_vols=(50, 50), drift_atr=0.0), "LONG", "COLD", "quiet volume, flat"),
    (frame(last_vols=(500, 500), drift_atr=0.8), "LONG", "NEUTRAL", "volume already spiked 5x"),
    (frame(last_vols=(200, 200), drift_atr=2.5), "LONG", "NEUTRAL", "already running 2.5 ATR"),
    (frame(n=60), "LONG", None, "frame too short -> None"),
]:
    g = grade(df, side)
    got = g["grade"] if g else None
    if got != want:
        fails.append(f"grade({lab}) = {got} ({g}), wanted {want}")

for src, side, g, want, lab in [
    ("\u26a1 STRONG", "LONG", "HOT", 1, "hot strong coil -> T1"),
    ("\U0001F525 2ND LEG", "LONG", "HOT", 2, "hot 2nd leg -> T2"),
    ("\U0001F48E ELITE HIGH", "LONG", "HOT", 2, "hot elite -> T2"),
    ("\u26a1 STRONG", "LONG", "NEUTRAL", 3, "neutral strong coil -> T3"),
    ("\u26a1 STRONG", "LONG", "COLD", 3, "cold -> T3"),
    ("\u26a1 STRONG", "LONG", None, 3, "no read -> T3"),
    ("\u26a1 STRONG", "SHORT", "HOT", None, "shorts never ring"),
    ("\U0001F575\ufe0f OI", "LONG", "HOT", None, "unknown source -> none"),
    ("", "LONG", "HOT", None, "empty source -> none"),
    ("\u26a1 STRONG", "long", "HOT", 1, "side case-insensitive"),
]:
    if tier(src, side, g) != want:
        fails.append(f"tier({lab}) = {tier(src, side, g)}, wanted {want}")

a = {"base": "XLM", "side": "LONG", "src": "\u26a1 STRONG", "trigger": 0.2266, "stop": 0.218541, "tp1": 0.230499, "tp2": 0.2345,
     "arrival": "HOT", "arr_vol2": 2.1, "arr_mom3": 0.8}
m1 = fmt(a, 0.2268, 1)
for need in ("\u26a1\U0001F525 *ARRIVAL T1 — XLM LONG · HOT strong coil*", "number `0.2266` broke · arrived HOT: 2.1x the 7-day bar with a 0.8 ATR drift",
             "entry `0.2268`", "TP2 `0.2345`", "this tier: 86% / +0.21R over 154 replay breaks", "only longs ring"):
    if need not in m1:
        fails.append(f"T1 banner missing {need!r}")
m2 = fmt({**a, "src": "\U0001F525 2ND LEG"}, 0.2268, 2)
if "*ARRIVAL T2 — XLM LONG · HOT arrival*" not in m2 or "83% / +0.23R over 197" not in m2:
    fails.append("T2 banner wrong")
m3 = fmt({**a, "arrival": "COLD", "arr_vol2": 0.6, "arr_mom3": 0.1, "tp2": None}, 0.2268, 3)
if "\u26a1 *ARRIVAL T3 — XLM LONG · long break at the number*" not in m3 or "arrived COLD: 0.6x volume" not in m3 or "TP2" in m3:
    fails.append("T3 cold banner wrong")
m4 = fmt({**a, "arrival": None, "arr_vol2": None, "arr_mom3": None}, 0.2268, 3)
import calendar
m5 = fmt(a, 0.2268, 1, now=float(calendar.timegm((2026, 10, 3, 0, 40, 0))))   # 00:40 UTC = 05:40 PKT
if "*ARRIVAL T1 — XLM LONG · HOT strong coil · TAKE · 05:40 PKT*" not in m5 or "T1 record: replay 86% / +0.21R (154), 15 Aug → 28 Sep · forward desk" not in m5 or "refreshed 05:40 PKT" not in m5:
    fails.append("TG RULES arrival header/record line wrong")
if m5.count('*') % 2 or m5.count('`') % 2:
    fails.append("TG RULES arrival markdown unbalanced")
if "arrival: no read" not in m4:
    fails.append("no-read banner wrong")
for m in (m1, m2, m3, m4):
    if m.count("*") % 2 or m.count("_") % 2 or m.count("`") % 2:
        fails.append("banner markdown unbalanced")

# ---- wiring ----
i_grade = W.find('_arr = _arrival_grade(binance_client.get_klines(\n                        a["symbol"], "15m", limit=700), a["side"])')
i_src0 = W.find('_src0 = str(a.get("src", ""))')
i_feed = W.find("                        del _DEMO_FIRES[:-40]\n                # \u26a1\U0001F525 ARRIVAL BANNER")
i_tier = W.find('_atier = _arrival_tier(_src0, a.get("side"),')
i_gate = W.find("if (_atier <= 2 and store.should_alert(")
i_bell = W.find("tg.send(_fmt_arrival(\n                                a, px, _atier,\n                                now=(time.time() if TG_RULES else None))\n                                    + _kr_note(a))")
i_trig = W.find('f"trig:{a[\'symbol\']}:{a[\'side\']}",')
if not (0 < i_grade < i_src0 < i_feed < i_tier < i_gate < i_bell < i_trig):
    fails.append(f"banner block order wrong: grade {i_grade} src0 {i_src0} feed {i_feed} tier {i_tier} gate {i_gate} bell {i_bell} trig {i_trig}")
for need, lab in (('_tiers_a = (["arr_long"]\n                                    + (["arr_hot"] if _atier <= 2 else [])\n                                    + (["trig_hot"] if _atier == 1 else []))', "nested tiers"),
                  ("for _tn in _tiers_a:\n                            store.record_signal(_tn, _sig_a)\n                            shadow_trader.open_from_signal(_tn, _sig_a, px)", "record + desk open per tier"),
                  ('f"arrival:{a[\'symbol\']}:LONG",\n                                int(1.5 * 3600))', "1.5h per coin"),
                  ('"arr_mom3": a.get("arr_mom3")}\n                        store.record_signal("press_break", _sig_pb)', "press_break stamp"),
                  ('"arr_mom3": a.get("arr_mom3")}\n                        store.record_signal("trig_strong", _sig_t)', "trig_strong stamp")):
    if need not in W:
        fails.append(f"wiring missing: {lab}")
for gone in ('_sig_h = dict(_sig_t, tier="HOT")', "_fmt_hot_arrival", "trighot:", "LONG\", 6 * 3600)"):
    if gone in W:
        fails.append(f"stale text still present: {gone}")
if "_MUTE_R9(_fmt_arrival" in W:
    fails.append("ARRIVAL bell must be live")
if '"apex", "prime", "best"):' in W or '(("moon",) if TG_RULES else' not in W:
    fails.append("push roster must be moon-only under TG_RULES (best/apex/prime/em off)")
for need in ('"trig_hot": "\u26a1\U0001F525 ARRIVAL T1', '"arr_hot": "\u26a1\U0001F525 ARRIVAL T2', '"arr_long": "\u26a1 ARRIVAL T3'):
    if need not in A:
        fails.append(f"app name missing: {need}")
for need in ('"trig_hot": "trig_hot",', '"arr_hot": "arr_hot",', '"arr_long": "arr_long",'):
    if need not in U:
        fails.append(f"auditor missing: {need}")
spec = importlib.util.spec_from_file_location("da", r"F:\Trading Indicator\demo_account.py")
da = importlib.util.module_from_spec(spec)
spec.loader.exec_module(da)
if any(k in da.CLASS_W for k in ("trig_hot", "arr_hot", "arr_long")):
    fails.append("arrival tiers must not be on the demo roster")
print(m1)
print("ARRIVAL:", "ALL PASS" if not fails else fails)
