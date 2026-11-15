"""Freeze the long-term plan for the live page (user 2026-11-14; names added 2026-11-15).

Reads research_meta/portfolio_1114/data.json (the workbook's data) and writes longterm_data/plan.json: for each
name the three buy tranches, the stop, the three take-profits and the add-up landmarks, exactly as the workbook
shows them, plus the time its plan starts (the first candle after the close the levels come from).

Default run: ADD every name the data holds that the plan does not, each frozen at the data's last close with
its own plan date. Names already in the plan are never touched, so their signals and fills keep their anchor.
`--reanchor` re-freezes EVERY name from the data: run that only to restart the whole plan.
Also copies the standalone workbook beside the plan (and the PDF when one has been made).
"""
import json
import os
import shutil
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
SRC = r"F:/Trading Indicator/research_meta/portfolio_1114"
DST = r"F:/Trading Indicator/longterm_data"
SYM = {"INJ": "INJUSDT", "SOL": "SOLUSDT", "NEAR": "NEARUSDT", "SUI": "SUIUSDT", "AVAX": "AVAXUSDT", "UNI": "UNIUSDT", "ARB": "ARBUSDT",
       "WLD": "WLDUSDT", "TAO": "TAOUSDT", "HYPE": "HYPEUSDT", "ONDO": "ONDOUSDT", "LINK": "LINKUSDT", "QNT": "QNTUSDT",
       "SNDK": "SNDKBUSDT", "NVDA": "NVDABUSDT", "AVGO": "AVGOBUSDT"}          # stocks: the tokenized tickers the app already reads
REANCHOR = "--reanchor" in sys.argv

d = json.load(open(SRC + "/data.json", encoding="utf-8"))
A = d["assets"]
asof = int(A["BTC"]["asof"])                 # open time of the last completed daily candle (UTC)
start = asof + 86400                         # the first candle after that close
label = lambda t: time.strftime("%d %b %Y", time.gmtime(t)).lstrip("0")


def entry(tk, own_date):
    a = A[tk]
    e = {"tk": tk, "name": a["name"], "sym": SYM[tk], "stock": bool(a["stock"]), "px0": a["px"],
         "rungs": [r["price"] for r in a["rungs"]], "depths": [r["depth"] for r in a["rungs"]],
         "stop": a["stop15"]["price"], "tps": [a["px"] * 1.5, a["px"] * 2.0, a["px"] * 3.0],
         "addups": [{"name": x["name"], "price": x["price"]} for x in a["addups"]]}
    if own_date:                             # a name added later carries its own plan date
        e.update(asof=asof, start=start, date_label=label(asof))
    return e


path = DST + "/plan.json"
cur = d["cycle"][2]
if REANCHOR or not os.path.exists(path):
    plan = {"asof": asof, "start": start, "plan_date": time.strftime("%Y-%m-%d", time.gmtime(asof)), "plan_date_label": label(asof),
            "btc": {"top": cur["top"], "top_ts": cur["top_t"]}, "names": [entry(tk, False) for tk in d["picks"]]}
    added = [n["tk"] for n in plan["names"]]
else:
    plan = json.load(open(path, encoding="utf-8"))
    have = {n["tk"] for n in plan["names"]}
    added = [tk for tk in d["picks"] if tk not in have]
    plan["names"] += [entry(tk, True) for tk in added]
plan["frozen_at"] = int(time.time())
plan["workbook_label"] = label(asof)         # the close the shipped workbook snapshot was built from
os.makedirs(DST, exist_ok=True)
json.dump(plan, open(path, "w", encoding="utf-8"), indent=1)
shutil.copyfile(SRC + "/portfolio_plan.html", DST + "/workbook.html")
if os.path.exists(SRC + "/share/Long-term-plan-workbook.pdf"):
    shutil.copyfile(SRC + "/share/Long-term-plan-workbook.pdf", DST + "/workbook.pdf")
print(("re-anchored every name at" if REANCHOR else "added " + (", ".join(added) or "nothing") + " at") + " the close of", label(asof),
      "· start", time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(start)))
for n in plan["names"]:
    print(f"  {n['tk']:5s} {n['sym']:10s} {n.get('date_label', plan['plan_date_label']):12s} px0 {n['px0']:.4g} rungs {' / '.join(f'{x:.4g}' for x in n['rungs'])} "
          f"stop {n['stop']:.4g} tps {' / '.join(f'{x:.4g}' for x in n['tps'])} addups {len(n['addups'])}")
print("files:", sorted(os.listdir(DST)))
