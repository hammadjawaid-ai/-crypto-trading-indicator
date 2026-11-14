"""Freeze the long-term plan for the live page (user 2026-11-14).

Reads research_meta/portfolio_1114/data.json (the workbook's data) and writes longterm_data/plan.json: for each
of the ten names the four buy rungs, the stop, the three take-profits and the add-up landmarks, exactly as
the workbook shows them, plus the plan's start time (the first candle after the close the levels come from).
Also copies the standalone workbook and its PDF beside it. Run this ONLY to re-anchor the plan: the page's
signals and fills are measured against whatever this file holds.
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
       "SNDK": "SNDKBUSDT", "NVDA": "NVDABUSDT", "AVGO": "AVGOBUSDT"}          # stocks: the tokenized tickers the app already reads

d = json.load(open(SRC + "/data.json", encoding="utf-8"))
A = d["assets"]
asof = int(A["BTC"]["asof"])                 # open time of the last completed daily candle (UTC)
start = asof + 86400                         # the first candle after the plan-date close
names = []
for tk in d["picks"]:
    a = A[tk]
    names.append({"tk": tk, "name": a["name"], "sym": SYM[tk], "stock": bool(a["stock"]), "px0": a["px"],
                  "rungs": [r["price"] for r in a["rungs"]], "depths": [r["depth"] for r in a["rungs"]],
                  "stop": a["stop15"]["price"], "tps": [a["px"] * 1.5, a["px"] * 2.0, a["px"] * 3.0],
                  "addups": [{"name": x["name"], "price": x["price"]} for x in a["addups"]]})
cur = d["cycle"][2]
plan = {"asof": asof, "start": start, "plan_date": time.strftime("%Y-%m-%d", time.gmtime(asof)),
        "plan_date_label": time.strftime("%d %b %Y", time.gmtime(asof)).lstrip("0"),
        "btc": {"top": cur["top"], "top_ts": cur["top_t"]}, "names": names, "frozen_at": int(time.time())}
os.makedirs(DST, exist_ok=True)
json.dump(plan, open(DST + "/plan.json", "w", encoding="utf-8"), indent=1)
shutil.copyfile(SRC + "/portfolio_plan.html", DST + "/workbook.html")
if os.path.exists(SRC + "/share/Three-of-Ten-workbook.pdf"):
    shutil.copyfile(SRC + "/share/Three-of-Ten-workbook.pdf", DST + "/workbook.pdf")
print("plan frozen at the close of", plan["plan_date_label"], "· start", time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(start)))
for n in names:
    print(f"  {n['tk']:5s} {n['sym']:10s} px0 {n['px0']:.4g} rungs {' / '.join(f'{x:.4g}' for x in n['rungs'])} stop {n['stop']:.4g} "
          f"tps {' / '.join(f'{x:.4g}' for x in n['tps'])} addups {len(n['addups'])}")
print("files:", sorted(os.listdir(DST)))
