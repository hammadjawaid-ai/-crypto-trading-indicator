"""Long-term portfolio pack, local run (research only). The computation lives in longterm_build.py so the
server can run the same build daily; this wrapper writes data.json, the standalone page, the shell-less copy
for the published artifact, and prints the review tables."""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"F:/Trading Indicator")
import truststore
truststore.inject_into_ssl()
import longterm_build as lb

OUT = r"F:/Trading Indicator/research_meta/portfolio_1114"
PICKS = lb.PICKS
out = lb.compute(OUT + "/raw", log=print)
json.dump(out, open(OUT + "/data.json", "w", encoding="utf-8"))
if os.path.exists(OUT + "/template.html"):          # the workbook page = the template with the data dropped in
    _tpl = open(OUT + "/template.html", encoding="utf-8").read()
    assert _tpl.count("/*DATA*/null") == 1
    _page = _tpl.replace("/*DATA*/null", json.dumps(out, separators=(",", ":")).replace("</", "<\\/"))
    open(OUT + "/portfolio_plan.html", "w", encoding="utf-8", newline="\n").write(_page)
    # the copy for publishing as a shareable page: same content without the document shell (the host adds its own)
    _frag = _page
    for _s in ("<!doctype html>\n", '<html lang="en">\n', "<head>\n", '<meta charset="utf-8">\n', '<meta name="viewport" content="width=device-width,initial-scale=1">\n',
               "</head>\n", "<body>\n", "</body>\n", "</html>\n"):
        assert _frag.count(_s) == 1, _s
        _frag = _frag.replace(_s, "")
    _frag = _frag.replace("<title>Three of Ten</title>", '<title>Three of Ten</title>\n<meta name="claude:viewport-fit-sides" content="cover">')
    os.makedirs(OUT + "/share", exist_ok=True)
    open(OUT + "/share/three-of-ten.html", "w", encoding="utf-8", newline="\n").write(_frag)
    print("wrote portfolio_plan.html + share/three-of-ten.html")

# ── console review ──
P = lambda x, p=0: "  —" if x is None else f"{x * 100:+.{p}f}%"
Q = lambda x: " —" if x is None else f"{x * 100:.0f}%"
M = lambda x: "—" if not x else (f"${x / 1e9:.2f}B" if x >= 1e9 else f"${x / 1e6:.0f}M")
print("as of", time.strftime("%Y-%m-%d", time.gmtime(out["assets"]["BTC"]["asof"])), "· BTC below 200D:", out["assets"]["SOL"]["reg_now"])
print(f"{'':5s} {'price':>9s} {'vsATH':>6s} {'52wpos':>6s} {'1y':>6s} {'90d':>6s} {'30d':>6s} {'RSId/w':>7s} {'vs200D':>7s} {'vol':>5s} {'beta':>5s} {'corr':>5s} {'yrs':>4s}")
for tk in PICKS + ["BTC", "QQQ", "SOXX"]:
    a = out["assets"][tk]
    print(f"{tk:5s} {a['px']:>9.4g} {P(a['dd_ath']):>6s} {a['pos52'] * 100:>5.0f}% {P(a['ret_1y']):>6s} {P(a['ret_90d']):>6s} {P(a['ret_30d']):>6s} {a['rsi_d']:>3.0f}/{a['rsi_w']:<3.0f} "
          f"{P(a['px'] / a['s200'] - 1) if a['s200'] else '—':>7s} {a['vol_y'] * 100:>4.0f}% {str(a.get('beta', '')):>5s} {str(a.get('corr_ref', '')):>5s} {a['years']:>4}")
print("\nRUNGS (price · depth · model touch 6m · empirical all / regime)")
for tk in PICKS:
    a = out["assets"][tk]
    print(f"{tk:5s} " + " | ".join(f"{r['price']:.4g} ({-r['depth'] * 100:.0f}%) {Q(r['p'])} {Q(r['emp_all'])}/{Q(r['emp_reg'])}" for r in a["rungs"]) + f"   n6 {a['n6']}/{a['n6_reg']}")
print("\nUP within 12m: +50% +100% +200% +400%  as model / touch all / touch regime / END all / END regime   (median 12m end all, regime)")
for tk in PICKS:
    a = out["assets"][tk]
    print(f"{tk:5s} " + " | ".join(f"{Q(a['up'][k]['model'])} {Q(a['up'][k]['all'])} {Q(a['up'][k]['reg'])} {Q(a['up'][k]['end_all'])} {Q(a['up'][k]['end_reg'])}" for k in ("0.50", "1.00", "2.00", "4.00"))
          + f"   med {P(a['end12_med_all'])} / {P(a['end12_med_reg'])} · n12 {a['n12']}/{a['n12_reg']}")
print("\nISOLATED LIQUIDATION within 6m (model / empirical all / regime) at 2x 3x 5x 10x")
for tk in PICKS:
    a = out["assets"][tk]
    print(f"{tk:5s} " + " | ".join(f"{L}x −{a['liq'][L]['dist'] * 100:.0f}%: {Q(a['liq'][L]['m6'])} {Q(a['liq'][L]['e6'])} {Q(a['liq'][L]['r6'])}" for L in ("2", "3", "5", "10")))
print("\nSPOT PLAN: rungs | avg cost if all fill | stop (15% dip; history all/regime) | loss at stop after all fills | sells 1.5x / 2x / 3x")
for tk in PICKS:
    a = out["assets"][tk]
    r, s = a["rungs"], a["stop15"]
    avg = len(r) / sum(1 / x["price"] for x in r)
    print(f"{tk:5s} " + " / ".join(f"{x['price']:.4g}" for x in r) + f" | avg {avg:.4g} | stop {s['price']:.4g} ({-s['depth'] * 100:.0f}%, {Q(s['emp_all'])}/{Q(s['emp_reg'])})"
          f" | loss {-(1 - s['price'] / avg) * 100:.0f}% | sells {a['px'] * 1.5:.4g} / {a['px'] * 2:.4g} / {a['px'] * 3:.4g}")
print("\nISOLATED (one entry at today's price; stop = the 50% dip, kept 5 points above liquidation)")
print("      L  liq price (dist)  stop price (dist)  loss on margin | 12m history ALL: 2x first / stop first / neither (mean end) | REGIME: same")
for tk in PICKS:
    a = out["assets"][tk]
    for L in (2, 3):
        dist = a["liq"][str(L)]["dist"]
        sd = min(a["rungs"][2]["depth"], dist - 0.05)
        k = int(round(sd * 100)) - 5
        t = a["ft"]["t"]["1.00"] if a.get("ft") else None
        fa = t["all"][k] if t and t["all"] else None
        fr_ = t["reg"][k] if t and t["reg"] else None
        g = lambda v: "—" if not v else f"{v[0] * 100:.0f}% / {v[1] * 100:.0f}% / {v[2] * 100:.0f}% ({P(v[3])})"
        print(f"{tk:5s} {L}x  {a['px'] * (1 - dist):.4g} (-{dist * 100:.0f}%)  {a['px'] * (1 - sd):.4g} (-{sd * 100:.0f}%)  -{sd * L * 100:.0f}% | {g(fa)} | {g(fr_)}")
print("\nADD-UP LEVELS (next landmarks above today's price)")
for tk in PICKS + ["MRVL"]:
    a = out["assets"][tk]
    print(f"{tk:5s} px {a['px']:.4g} | " + " | ".join(f"{x['name']} {x['price']:.4g} ({x['up'] * 100:+.0f}%)" for x in a["addups"]))
print("\nADD-ON-STRENGTH EVIDENCE (pooled): n · median 6m · up 6m · median 12m · up 12m · median worst pullback in the next 6m")
for grp, r in out["addup_ev"].items():
    for k, lab in (("e50", "reclaim 50D"), ("e200", "reclaim 200D"), ("e90", "fresh 90d high"), ("base", "ANY DAY")):
        v = r[k]
        print(f"  {grp:6s} {lab:14s} n {v['n6']:>5}/{v['n12']:<5} · {P(v['med6'])} · {Q(v['up6'])} · {P(v['med12'])} · {Q(v['up12'])} · {P(v['mae6'])}")
print("\nNVDA / AVGO / MRVL: episodes (drawdown, days to recover) · capture vs QQQ (down/up) · worst week · weeks <=-10% · days 25%+ under high (5y) · since 4 Nov")
for tk, r in out["stk_cmp"]["rows"].items():
    a = out["assets"][tk]
    print(f"{tk:5s} " + " | ".join(("—" if not e else f"{e['dd'] * 100:.0f}% ({e['rec'] if e['rec'] is not None else 'not yet'}d)") for e in r["eps"])
          + f" · cap {r['down_cap']}/{r['up_cap']} · {P(r['worst_week'])} · {Q(r['weeks_m10'])} · {Q(r['under25'])} · {P(r['since_nov4'])}"
          + f" · now {P(a['dd_ath'])} from high, vol {a['vol_y'] * 100:.0f}%, RSI {a['rsi_d']:.0f}, vs200D {P(a['px'] / a['s200'] - 1)}, 1y {P(a['ret_1y'])}, 90d {P(a['ret_90d'])}, med12 reg {P(a['end12_med_reg'])}, 2x kept {Q(a['up']['1.00']['end_reg'])}, stop15 reg {Q(a['stop15']['emp_reg'])}, beta {a.get('beta')}")
print("\nCYCLE")
for c in out["cycle"]:
    print(" ", c["label"], time.strftime("%Y-%m-%d", time.gmtime(c["top_t"])), f"top {c['top']:.0f} · low day {c['bottom_day']} at {P(c['bottom_dd'])} · days on record {c['days']} · 12m after low {P(c['after_bottom_365'])}")
print("\nFEAR & GREED now", out["fng"].get("now"), "30d avg", out["fng"].get("avg30"), out["fng"].get("stats"))
for e in out["fng"]["episodes"]:
    print(" ", time.strftime("%Y-%m-%d", time.gmtime(e["t"])), e["v"], f"BTC {e['btc']:.0f} · 90d {P(e['f90'])} · 180d {P(e['f180'])} · 365d {P(e['f365'])} · worst in 180d {P(e['mae180'])} ·",
          " ".join(f"{k} {P(v)}" for k, v in e["alts"].items()))
print("\nCORR (weekly,", out["corr"]["weeks"], "weeks)")
print("      " + " ".join(f"{k:>5s}" for k in out["corr"]["order"]))
for k, row in zip(out["corr"]["order"], out["corr"]["m"]):
    print(f"{k:5s} " + " ".join(f"{v:>5.2f}" for v in row))
print("\nFUNDAMENTALS")
for tk in PICKS:
    f = out["assets"][tk].get("fund")
    if f:
        print(f"{tk:5s} rank {f.get('rank')} mcap {M(f.get('mcap'))} fdv {M(f.get('fdv'))} circ/total {(f.get('circ') or 0) / (f.get('total') or 1) * 100:.0f}% · TVL {M(f.get('tvl'))} (1y ago {M(f.get('tvl_1y'))}) · stables {M(f.get('stables'))} "
              f"· DEX 30d {M(f.get('dex30'))} · chain fees 30d {M(f.get('fees30'))} rev {M(f.get('rev30'))} · app fees 30d {M(f.get('appfees30'))}")
