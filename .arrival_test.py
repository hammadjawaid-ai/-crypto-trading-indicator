"""⚡🔥 ARRIVAL GRADE — pure-function tests on synthetic 15m frames, bell markdown,
and wiring (stamp on every break record, trig_hot tier for HOT strong-coil longs
only, bell muted, names in app/auditor)."""
import ast
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
ns = {"np": np, "pd": pd}
for name in ("_arrival_grade", "_fmt_hot_arrival"):
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), name, "exec"), ns)
grade, fmt = ns["_arrival_grade"], ns["_fmt_hot_arrival"]


def frame(n=800, base_vol=100.0, last_vols=(100, 100), drift_atr=0.0, side_up=True, seed=1):
    """Flat tape with a fixed true range (ATR ~ 1.0), then the last 3 closed bars
    drift by `drift_atr` and the last 2 closed bars carry `last_vols`; a forming
    bar is appended last."""
    rng = np.random.default_rng(seed)
    c = 100.0 + np.cumsum(rng.normal(0, 0.05, n))
    h, l = c + 0.5, c - 0.5                     # true range 1.0 -> ATR 1.0
    v = np.full(n, base_vol)
    sgn = 1.0 if side_up else -1.0
    step = sgn * drift_atr / 3.0
    for k, i in enumerate(range(n - 4, n - 1)):  # the 3 closed bars before the forming bar
        c[i] = c[n - 5] + step * (k + 1)
        h[i], l[i] = c[i] + 0.5, c[i] - 0.5
    v[n - 3], v[n - 2] = last_vols           # the two closed bars before the break bar
    v[n - 1] = 999.0                          # the forming (break) bar: must be ignored
    idx = pd.date_range("2026-10-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"open": c, "high": h, "low": l, "close": c, "volume": v}, index=idx)


cases = [
    (frame(last_vols=(200, 200), drift_atr=0.8), "LONG", "HOT", "2x volume, +0.8 ATR drift, long"),
    (frame(last_vols=(135, 135), drift_atr=0.35), "LONG", "HOT", "just inside the band edges 1.35x / 0.35 ATR"),
    (frame(last_vols=(300, 300), drift_atr=1.5), "LONG", "HOT", "band edges 3x / 1.5 ATR"),
    (frame(last_vols=(200, 200), drift_atr=0.8), "SHORT", "NEUTRAL", "same tape read as a short: drift is against it"),
    (frame(last_vols=(200, 200), drift_atr=0.8, side_up=False), "SHORT", "HOT", "short with drift down is hot"),
    (frame(last_vols=(50, 50), drift_atr=0.0), "LONG", "COLD", "quiet volume, flat"),
    (frame(last_vols=(500, 500), drift_atr=0.8), "LONG", "NEUTRAL", "volume already spiked 5x"),
    (frame(last_vols=(200, 200), drift_atr=2.5), "LONG", "NEUTRAL", "already running 2.5 ATR"),
    (frame(last_vols=(110, 110), drift_atr=0.1), "LONG", "NEUTRAL", "1.1x volume, 0.1 ATR: neither hot nor cold"),
    (frame(n=60), "LONG", None, "frame too short -> None"),
]
for df, side, want, lab in cases:
    g = grade(df, side)
    got = g["grade"] if g else None
    if got != want:
        fails.append(f"{lab}: got {got} (detail {g}), wanted {want}")
g = grade(frame(last_vols=(200, 200), drift_atr=0.8), "LONG")
if g and not (1.9 <= g["vol2"] <= 2.1 and 0.7 <= g["mom3"] <= 0.9):
    fails.append(f"vol2/mom3 off: {g}")
if grade(None, "LONG") is not None:
    fails.append("None frame must return None")
# the forming bar's volume must not count (999 would make it look spiked)
g2 = grade(frame(last_vols=(200, 200), drift_atr=0.8), "LONG")
if g2 is None or g2["grade"] != "HOT":
    fails.append("forming bar leaked into the grade")

# bell markdown
a = {"base": "XLM", "side": "LONG", "trigger": 0.2266, "stop": 0.218541, "tp1": 0.230499, "tp2": 0.2345, "arrival": "HOT", "arr_vol2": 2.1, "arr_mom3": 0.8}
m = fmt(a, 0.2268)
for need in ("⚡🔥 *HOT ARRIVAL — XLM LONG*", "`0.2266` broke on rising volume (2.1x", "0.8 ATR drift", "entry `0.2268`", "TP2 `0.2345`", "86% / +0.21R", "trig hot"):
    if need not in m:
        fails.append(f"bell missing {need!r}")
if m.count("*") % 2 or m.count("_") % 2 or m.count("`") % 2:
    fails.append("bell markdown unbalanced")
m2 = fmt({**a, "tp2": None}, 0.2268)
if "TP2" in m2:
    fails.append("no-TP2 variant wrong")

# wiring
i_pop = W.find("_TRIG_ARMED.pop(k, None)\n                # ⚡🔥 ARRIVAL GRADE")
i_grade = W.find('_arr = _arrival_grade(binance_client.get_klines(\n                        a["symbol"], "15m", limit=700), a["side"])')
i_src0 = W.find('_src0 = str(a.get("src", ""))')
if not (0 < i_pop < i_grade < i_src0):
    fails.append("arrival grade not computed right after the armed level is popped")
for need, lab in (('"arrival": a.get("arrival"),\n                             "src": _dsrc, "fired_at": _now})', "demo feed stamp"),
                  ('"arr_mom3": a.get("arr_mom3")}\n                        store.record_signal("press_break", _sig_pb)', "press_break stamp"),
                  ('"arr_mom3": a.get("arr_mom3")}\n                        store.record_signal("trig_strong", _sig_t)', "trig_strong stamp"),
                  ('if (a.get("arrival") == "HOT"\n                                and a["side"] == "LONG"):', "HOT long gate"),
                  ('store.record_signal("trig_hot", _sig_h)', "trig_hot record"),
                  ('shadow_trader.open_from_signal(\n                                    "trig_hot", _sig_h, px)', "trig_hot desk open"),
                  ('_MUTE_R9(_fmt_hot_arrival(a, px)\n                                             + _kr_note(a))', "bell muted")):
    if need not in W:
        fails.append(f"wiring missing: {lab}")
if "tg.send(_fmt_hot_arrival" in W:
    fails.append("HOT ARRIVAL bell must stay muted until the user's word")
# the trig_hot block sits inside the ⚡ strong-coil branch (after the trig_strong record, before the kronos co-sign)
i_ts = W.find('store.record_signal("trig_strong", _sig_t)')
i_th = W.find('store.record_signal("trig_hot", _sig_h)')
i_kr = W.find('_h2 = _KR_CACHE.get(a["symbol"])', i_ts)
if not (0 < i_ts < i_th < i_kr):
    fails.append("trig_hot block not inside the strong-coil branch")
if '"trig_hot": "⚡🔥 HOT ARRIVAL' not in A:
    fails.append("app tier name missing")
if '"trig_hot": "trig_hot",' not in U:
    fails.append("auditor tier missing")
print(m)
print("ARRIVAL GRADE:", "ALL PASS" if not fails else fails)
