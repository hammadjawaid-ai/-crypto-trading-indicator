"""Long-term portfolio pack (research only, nothing here touches the live system).
Daily history for the user's 10 names + BTC + QQQ/SOXX + Fear & Greed; one set of measures for all:
dip map (how often each depth was reached), ladder rungs by one volatility rule, upside map, isolated-leverage
liquidation odds, BTC cycle clock, extreme-fear episodes, correlations, on-chain fundamentals. Writes data.json."""
import json
import math
import os
import sys
import time
from statistics import NormalDist

sys.stdout.reconfigure(encoding="utf-8")
import truststore
truststore.inject_into_ssl()
import numpy as np
import pandas as pd
import requests

OUT = r"F:/Trading Indicator/research_meta/portfolio_1114"
RAW = OUT + "/raw"
os.makedirs(RAW, exist_ok=True)
S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (research script)"})
N = NormalDist()
CRYPTO = {"INJ": "INJUSDT", "SOL": "SOLUSDT", "NEAR": "NEARUSDT", "SUI": "SUIUSDT", "AVAX": "AVAXUSDT", "UNI": "UNIUSDT", "ARB": "ARBUSDT", "BTC": "BTCUSDT"}
STOCKS = {"SNDK": "SNDK", "NVDA": "NVDA", "AVGO": "AVGO", "MRVL": "MRVL", "QQQ": "QQQ", "SOXX": "SOXX"}
NAMES = {"INJ": "Injective", "SOL": "Solana", "NEAR": "NEAR Protocol", "SUI": "Sui", "AVAX": "Avalanche", "UNI": "Uniswap", "ARB": "Arbitrum",
         "SNDK": "SanDisk", "NVDA": "Nvidia", "AVGO": "Broadcom", "MRVL": "Marvell", "BTC": "Bitcoin", "QQQ": "Nasdaq 100 (QQQ)", "SOXX": "Semiconductors (SOXX)"}
PICKS = ["INJ", "SOL", "NEAR", "SNDK", "NVDA", "AVGO", "SUI", "AVAX", "UNI", "ARB"]
CG = {"INJ": "injective-protocol", "SOL": "solana", "NEAR": "near", "SUI": "sui", "AVAX": "avalanche-2", "UNI": "uniswap", "ARB": "arbitrum", "BTC": "bitcoin"}
LLAMA_CHAIN = {"INJ": "Injective", "SOL": "Solana", "NEAR": "Near", "SUI": "Sui", "AVAX": "Avalanche", "ARB": "Arbitrum"}
LLAMA_FEES = {"INJ": "injective", "SOL": "solana", "NEAR": "near", "SUI": "sui", "AVAX": "avalanche", "ARB": "arbitrum", "UNI": "uniswap"}
RUNG_P = [0.75, 0.50, 0.30]            # rungs sit at the dips reached in 75% / 50% / 30% of six-month windows
DIPS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70]
UPS = [0.25, 0.50, 1.00, 2.00, 4.00]
LEV = [1, 2, 3, 5, 10]
MM = 0.02                               # maintenance margin used for the isolated-liquidation distance


def cached(name, fn, max_age=6 * 3600):
    p = f"{RAW}/{name}.json"
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < max_age:
        return json.load(open(p, encoding="utf-8"))
    v = fn()
    json.dump(v, open(p, "w", encoding="utf-8"))
    return v


def binance_daily(sym):
    rows, start = [], 1501545600000          # 1 Aug 2017
    while True:
        r = S.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1d", "limit": 1000, "startTime": start}, timeout=25)
        k = r.json()
        if not isinstance(k, list) or not k:
            break
        rows += [[int(x[0]) // 1000, float(x[1]), float(x[2]), float(x[3]), float(x[4])] for x in k]
        if len(k) < 1000:
            break
        start = int(k[-1][0]) + 86400000
        time.sleep(0.25)
    return rows[:-1]                         # drop the bar still in progress


def yahoo_daily(sym):
    r = S.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", params={"range": "10y", "interval": "1d"}, timeout=25)
    j = r.json()["chart"]["result"][0]
    q = j["indicators"]["quote"][0]
    return [[int(t), o, h, l, c] for t, o, h, l, c in zip(j["timestamp"], q["open"], q["high"], q["low"], q["close"]) if None not in (o, h, l, c)]


def frame(rows):
    return pd.DataFrame(rows, columns=["t", "o", "h", "l", "c"]).drop_duplicates("t").reset_index(drop=True)


def rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def fwd_ext(s, h, kind):
    """min (kind='min') / max over the NEXT h bars (t+1..t+h); NaN where the window is incomplete."""
    r = s[::-1].rolling(h, min_periods=h)
    return (r.min() if kind == "min" else r.max())[::-1].shift(-1)


def nn(x, nd=4):
    return None if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else round(float(x), nd)


frames = {}
for tk, sym in CRYPTO.items():
    try:
        frames[tk] = frame(cached("bn_" + sym, lambda s=sym: binance_daily(s)))
    except Exception as e:
        print("FAIL", tk, e)
for tk, sym in STOCKS.items():
    try:
        frames[tk] = frame(cached("yh_" + sym, lambda s=sym: yahoo_daily(s)))
    except Exception as e:
        print("FAIL", tk, e)

btc = frames["BTC"].copy()
btc["s200"] = btc.c.rolling(200).mean()
btc_below = dict(zip(btc.t, (btc.c < btc.s200)))


def measures(tk):
    d = frames[tk].copy()
    stock = tk in STOCKS
    ppy = 252 if stock else 365
    h6, h12 = ppy // 2, ppy
    c = d.c
    d["s50"], d["s200"], d["rsi"] = c.rolling(50).mean(), c.rolling(200).mean(), rsi(c)
    wk = d.set_index(pd.to_datetime(d.t, unit="s")).c.resample("W").last().dropna()
    px = float(c.iloc[-1])
    ath = float(d.h.max()); ath_t = int(d.t[d.h.idxmax()])
    y = d.tail(ppy)
    hi52, lo52 = float(y.h.max()), float(y.l.min())
    lr = np.log(c).diff()
    vol_d = float(lr.tail(ppy).std())
    vol_y = vol_d * math.sqrt(ppy)
    s6, s12 = vol_y * math.sqrt(0.5), vol_y
    run = d.h.cummax()
    dd = c / run - 1
    # regime: crypto = BTC below its 200-day average that day; stocks = the stock itself 25%+ under its high
    if stock:
        reg = dd <= -0.25
        reg_name = "while the stock was 25%+ below its high"
    else:
        reg = d.t.map(btc_below).fillna(False).astype(bool)
        reg_name = "while BTC was below its 200-day average"
    mae6 = fwd_ext(d.l, h6, "min") / c - 1
    mae12 = fwd_ext(d.l, h12, "min") / c - 1
    mfe12 = fwd_ext(d.h, h12, "max") / c - 1
    end12 = c.shift(-h12) / c - 1
    end6 = c.shift(-h6) / c - 1
    ok6, ok12 = mae6.notna(), mae12.notna()

    def pr(mask, cond):
        m = mask & cond.notna() if hasattr(cond, "notna") else mask
        return None if int(mask.sum()) < 60 else float(cond[mask].mean())

    dip = {}
    for x in DIPS:
        dip[f"{x:.2f}"] = {"model": 2 * N.cdf(math.log(1 - x) / s6), "all": pr(ok6, mae6 <= -x), "reg": pr(ok6 & reg, mae6 <= -x)}
    rungs = [{"p": 1.0, "depth": 0.0, "price": px, "emp_all": None, "emp_reg": None}]
    for p in RUNG_P:
        dep = 1 - math.exp(s6 * N.inv_cdf(p / 2))
        rungs.append({"p": p, "depth": dep, "price": px * (1 - dep), "emp_all": pr(ok6, mae6 <= -dep), "emp_reg": pr(ok6 & reg, mae6 <= -dep)})
    up = {}
    for x in UPS:
        up[f"{x:.2f}"] = {"model": 2 * N.cdf(-math.log(1 + x) / s12), "all": pr(ok12, mfe12 >= x), "reg": pr(ok12 & reg, mfe12 >= x),
                          "end_all": pr(ok12, end12 >= x), "end_reg": pr(ok12 & reg, end12 >= x)}
    liq = {}
    for L in LEV:
        dist = 1.0 if L == 1 else (1 / L - MM)
        liq[str(L)] = {"dist": dist,
                       "m6": 0.0 if L == 1 else 2 * N.cdf(math.log(1 - dist) / s6), "m12": 0.0 if L == 1 else 2 * N.cdf(math.log(1 - dist) / s12),
                       "e6": 0.0 if L == 1 else pr(ok6, mae6 <= -dist), "e12": 0.0 if L == 1 else pr(ok12, mae12 <= -dist),
                       "r6": 0.0 if L == 1 else pr(ok6 & reg, mae6 <= -dist)}
    # spot plan stop: one step under rung 4, the dip reached in ~15% of six-month windows
    dep15 = 1 - math.exp(s6 * N.inv_cdf(0.15 / 2))
    stop15 = {"depth": dep15, "price": px * (1 - dep15), "emp_all": pr(ok6, mae6 <= -dep15), "emp_reg": pr(ok6 & reg, mae6 <= -dep15)}
    # first touch within 12 months: a stop 5..50% under the start close against a target (+50 / +100 / +200%)
    lows, highs, cl = d.l.values, d.h.values, c.values
    nfull = len(d) - h12
    stops = np.arange(5, 51) / 100.0
    tgs = np.array([0.5, 1.0, 2.0])
    ft = None
    if nfull > 60:
        ts = np.empty((nfull, len(stops)), dtype=np.int32)
        tt = np.empty((nfull, len(tgs)), dtype=np.int32)
        for i in range(nfull):
            lo = np.minimum.accumulate(lows[i + 1:i + 1 + h12]) / cl[i]
            hi = np.maximum.accumulate(highs[i + 1:i + 1 + h12]) / cl[i]
            ts[i] = np.searchsorted(-lo, -(1 - stops), side="left")      # h12 = never touched
            tt[i] = np.searchsorted(hi, 1 + tgs, side="left")
        endr = cl[h12:h12 + nfull] / cl[:nfull] - 1
        regv = reg.values[:nfull].astype(bool)
        ft = {"stops": [int(round(s * 100)) for s in stops], "t": {}}
        for j, u in enumerate(tgs):
            row = {}
            for nm, mk in (("all", np.ones(nfull, bool)), ("reg", regv)):
                n = int(mk.sum())
                if n < 60:
                    row[nm] = None
                    continue
                arr = []
                for k in range(len(stops)):
                    s_hit, t_hit = ts[:, k] < h12, tt[:, j] < h12
                    sf = mk & s_hit & (ts[:, k] <= tt[:, j])              # same-day tie counts as the stop
                    tf = mk & t_hit & (tt[:, j] < ts[:, k])
                    ne = mk & ~s_hit & ~t_hit
                    arr.append([round(tf.sum() / n, 3), round(sf.sum() / n, 3), round(ne.sum() / n, 3), nn(endr[ne].mean(), 3) if ne.sum() else None])
                row[nm] = arr
            ft["t"][f"{u:.2f}"] = row
    # add-up levels (price rises before it dips): the next landmarks above today's price, in order
    n90 = 63 if stock else 90
    hi90 = float(c.tail(n90).max())
    cands = [("50-day average", float(d.s50.iloc[-1])), ("200-day average", float(d.s200.iloc[-1]) if not math.isnan(d.s200.iloc[-1]) else None),
             ("90-day high", hi90), ("52-week high", hi52)]
    addups = []
    for nm_, v in sorted([x for x in cands if x[1] and x[1] > px * 1.03], key=lambda x: x[1]):
        if addups and v < addups[-1]["price"] * 1.03:
            addups[-1]["name"] += " / " + nm_
            continue
        addups.append({"name": nm_, "price": v, "up": v / px - 1})
    addups = addups[:3]
    tail = d.tail(730 if not stock else 504)
    wkl = wk.iloc[:-1] if len(wk) > 2 else wk
    return {"tk": tk, "name": NAMES[tk], "stock": stock, "px": px, "asof": int(d.t.iloc[-1]), "first": int(d.t.iloc[0]), "years": round(len(d) / ppy, 1),
            "ath": ath, "ath_t": ath_t, "dd_ath": px / ath - 1, "hi52": hi52, "lo52": lo52,
            "pos52": (px - lo52) / (hi52 - lo52) if hi52 > lo52 else None,
            "s50": nn(d.s50.iloc[-1], 6), "s200": nn(d.s200.iloc[-1], 6), "rsi_d": nn(d.rsi.iloc[-1], 1), "rsi_w": nn(rsi(wk).iloc[-1], 1),
            "vol_y": vol_y, "ret_1y": nn(px / c.iloc[-ppy] - 1) if len(c) > ppy else None, "ret_90d": nn(px / c.iloc[-(90 if not stock else 63)] - 1),
            "ret_30d": nn(px / c.iloc[-(30 if not stock else 21)] - 1),
            "maxdd_2y": nn((tail.c / tail.c.cummax() - 1).min()), "maxdd_all": nn(dd.min()),
            "reg_name": reg_name, "reg_now": bool(reg.iloc[-1]), "n6": int(ok6.sum()), "n6_reg": int((ok6 & reg).sum()),
            "n12": int(ok12.sum()), "n12_reg": int((ok12 & reg).sum()),
            "end12_med_all": nn(end12[ok12].median()) if ok12.sum() else None,
            "end12_med_reg": nn(end12[ok12 & reg].median()) if (ok12 & reg).sum() >= 60 else None,
            "end6_med_reg": nn(end6[end6.notna() & reg].median()) if (end6.notna() & reg).sum() >= 60 else None,
            "dip": dip, "rungs": rungs, "up": up, "liq": liq, "stop15": stop15, "ft": ft, "addups": addups, "hi90": hi90,
            "series": {"t": [int(x) for x in tail.t], "c": [nn(x, 6) for x in tail.c], "s50": [nn(x, 6) for x in tail.s50],
                       "s200": [nn(x, 6) for x in tail.s200], "rsi": [nn(x, 1) for x in tail.rsi]},
            "long": {"t": [int(x.timestamp()) for x in wkl.index], "c": [nn(x, 6) for x in wkl.values]}}


out = {"built": int(time.time()), "assets": {}, "picks": PICKS}
for tk in list(CRYPTO) + list(STOCKS):
    if tk in frames:
        try:
            out["assets"][tk] = measures(tk)
        except Exception as e:
            print("FAIL measures", tk, repr(e))

# ── correlations on weekly log returns over the common window (max 104 weeks) ──
wkc = {}
for tk in PICKS + ["BTC", "QQQ"]:
    if tk in frames:
        d = frames[tk]
        wkc[tk] = d.set_index(pd.to_datetime(d.t, unit="s")).c.resample("W-FRI").last()
W = np.log(pd.DataFrame(wkc)).diff().dropna().tail(104)
out["corr"] = {"order": list(W.columns), "weeks": int(len(W)), "m": [[nn(v, 3) for v in row] for row in W.corr().values]}
for tk in PICKS:
    if tk in W:
        ref = "QQQ" if tk in STOCKS else "BTC"
        cv = np.cov(W[tk], W[ref])
        out["assets"][tk]["beta_ref"] = ref
        out["assets"][tk]["beta"] = nn(cv[0, 1] / cv[1, 1], 2)
        out["assets"][tk]["corr_ref"] = nn(W[tk].corr(W[ref]), 2)

# ── adding on strength: what followed a reclaim of the 50-day / 200-day average or a fresh 90-day high ──
def add_events(tk):
    d = frames[tk]
    stock = tk in STOCKS
    ppy = 252 if stock else 365
    h6, h12 = ppy // 2, ppy
    c = d.c

    def first_cross(avg, minrun):
        below = (c < avg).astype(int)
        run = below.groupby((below != below.shift()).cumsum()).cumsum()
        prev = run.shift(1).where(below.shift(1) == 1, 0)
        return (c > avg) & (prev >= minrun)
    n90 = 63 if stock else 90
    hi = c.rolling(n90).max()
    newhi = (c >= hi) & hi.notna()
    ev = {"e50": first_cross(c.rolling(50).mean(), 20), "e200": first_cross(c.rolling(200).mean(), 30),
          "e90": newhi & (newhi.shift(1).rolling(60).sum() == 0)}
    f6, f12 = c.shift(-h6) / c - 1, c.shift(-h12) / c - 1
    mae6 = fwd_ext(d.l, h6, "min") / c - 1
    return ev, f6, f12, mae6


def pool_events(tks):
    acc = {k: {"f6": [], "f12": [], "mae6": []} for k in ("e50", "e200", "e90", "base")}
    for tk in tks:
        ev, f6, f12, mae6 = add_events(tk)
        for k in ("e50", "e200", "e90"):
            m = ev[k].fillna(False).astype(bool)
            acc[k]["f6"] += list(f6[m].dropna())
            acc[k]["f12"] += list(f12[m].dropna())
            acc[k]["mae6"] += list(mae6[m].dropna())
        acc["base"]["f6"] += list(f6.dropna())
        acc["base"]["f12"] += list(f12.dropna())
        acc["base"]["mae6"] += list(mae6.dropna())
    res = {}
    for k, v in acc.items():
        a6, a12, am = np.array(v["f6"]), np.array(v["f12"]), np.array(v["mae6"])
        res[k] = {"n6": int(len(a6)), "med6": nn(np.median(a6)) if len(a6) else None, "up6": nn((a6 > 0).mean()) if len(a6) else None,
                  "n12": int(len(a12)), "med12": nn(np.median(a12)) if len(a12) else None, "up12": nn((a12 > 0).mean()) if len(a12) else None,
                  "mae6": nn(np.median(am)) if len(am) else None}
    return res


out["addup_ev"] = {"coins": pool_events(["INJ", "SOL", "NEAR", "SUI", "AVAX", "UNI", "ARB"]), "stocks": pool_events(["NVDA", "AVGO", "MRVL"])}


# ── Nvidia / Broadcom / Marvell: which held up better ──
def episode(d, a, z):
    t = pd.to_datetime(d.t, unit="s")
    seg = d[(t >= a) & (t <= z)]
    if len(seg) < 5:
        return None
    dd = seg.c / seg.c.cummax() - 1
    i = dd.idxmin()
    pk = seg.c.loc[:i].idxmax()
    peak = float(d.c[pk])
    after = d[(d.index > i) & (d.c >= peak)]
    return {"dd": nn(dd.min()), "peak_t": int(d.t[pk]), "trough_t": int(d.t[i]), "rec": int((after.t.iloc[0] - d.t[i]) / 86400) if len(after) else None}


EPIS = [("Late 2018", "2018-09-01", "2018-12-31"), ("Covid crash, 2020", "2020-02-01", "2020-04-15"), ("2022 bear market", "2021-11-01", "2022-12-31"),
        ("Tariff shock, 2025", "2025-01-01", "2025-05-15"), ("2026 so far", "2026-01-01", "2030-01-01")]
qq = frames["QQQ"].set_index(pd.to_datetime(frames["QQQ"].t, unit="s")).c.resample("W-FRI").last().pct_change().dropna().tail(260)
cmp_ = {"episodes": [e[0] for e in EPIS], "rows": {}}
for tk in ("NVDA", "AVGO", "MRVL", "SOXX", "QQQ"):
    d = frames[tk]
    t = pd.to_datetime(d.t, unit="s")
    w = d.set_index(t).c.resample("W-FRI").last().pct_change().dropna()
    j = pd.concat([w, qq], axis=1, join="inner").dropna()
    j.columns = ["s", "q"]
    dn, up = j[j.q < 0], j[j.q > 0]
    dd_all = d.c / d.c.cummax() - 1
    pre = d[t <= "2026-11-04 23:59"]
    tl = d.tail(504)
    cmp_["rows"][tk] = {"name": NAMES[tk], "eps": [episode(d, a, z) for _, a, z in EPIS],
                        "down_cap": nn(dn.s.mean() / dn.q.mean(), 2), "up_cap": nn(up.s.mean() / up.q.mean(), 2),
                        "worst_week": nn(w.tail(260).min()), "weeks_m10": nn((w.tail(260) <= -0.10).mean()),
                        "under25": nn((dd_all.tail(1260) <= -0.25).mean()), "since_nov4": nn(float(d.c.iloc[-1] / pre.c.iloc[-1] - 1)),
                        "uw": {"t": [int(x) for x in tl.t], "v": [nn(x * 100, 1) for x in dd_all.tail(504)]}}
out["stk_cmp"] = cmp_

# ── BTC cycle clock ──
b = frames["BTC"]
bt = pd.to_datetime(b.t, unit="s")
cyc = []
for lab, a, z in (("2017 top", "2017-08-01", "2019-01-01"), ("2021 top", "2019-01-01", "2023-01-01"), ("2025 top", "2023-01-01", "2030-01-01")):
    m = (bt >= a) & (bt < z)
    i0 = int(b.h[m].idxmax())
    top = float(b.h[i0])
    seg = b.iloc[i0:i0 + 1100]
    ddc = (seg.c / top - 1).values
    imin = int(np.argmin(ddc[:800])) if lab != "2025 top" else int(np.argmin(ddc))
    cyc.append({"label": lab, "top_t": int(b.t[i0]), "top": top, "bottom_day": imin, "bottom_dd": nn(ddc[imin]), "days": int(len(ddc)),
                "after_bottom_365": nn(float(seg.c.iloc[imin + 365] / seg.c.iloc[imin] - 1)) if len(seg) > imin + 365 else None,
                "series": [[int(i), nn(v)] for i, v in enumerate(ddc) if i % 3 == 0 or i == len(ddc) - 1]})
out["cycle"] = cyc

# ── Fear & Greed: history + what followed extreme-fear episodes ──
try:
    fg = cached("fng", lambda: S.get("https://api.alternative.me/fng/", params={"limit": 0, "format": "json"}, timeout=25).json()["data"])
    F = pd.DataFrame([{"t": int(x["timestamp"]) // 86400 * 86400, "v": int(x["value"])} for x in fg]).sort_values("t").drop_duplicates("t").reset_index(drop=True)
    bb = b.set_index("t")
    F["btc"] = F.t.map(bb.c)
    F = F.dropna().reset_index(drop=True)
    idx = {int(t): i for i, t in enumerate(b.t)}
    eps, last = [], -10 ** 12
    for _, r in F.iterrows():
        if r.v <= 15:
            if r.t - last > 45 * 86400:
                eps.append(int(r.t))
            last = r.t
    rows = []
    for t in eps:
        i = idx.get(t)
        if i is None:
            continue
        p0 = float(b.c[i])

        def f(h):
            return nn(float(b.c[i + h] / p0 - 1)) if i + h < len(b) else None
        mae = nn(float(b.l[i + 1:i + 181].min() / p0 - 1)) if i + 30 < len(b) else None
        alts = {}
        for tk in PICKS:
            if tk in CRYPTO:
                a = frames[tk]
                j = a.index[a.t == t]
                if len(j) and j[0] + 365 < len(a):
                    alts[tk] = nn(float(a.c[j[0] + 365] / a.c[j[0]] - 1))
        rows.append({"t": t, "v": int(F.v[F.t == t].iloc[0]), "btc": p0, "f90": f(90), "f180": f(180), "f365": f(365), "mae180": mae, "alts": alts})
    Fx = F.copy()
    Fx["f365"] = [float(b.c[idx[t] + 365] / b.c[idx[t]] - 1) if t in idx and idx[t] + 365 < len(b) else np.nan for t in Fx.t]
    lo = Fx[(Fx.v <= 15) & Fx.f365.notna()]
    al = Fx[Fx.f365.notna()]
    out["fng"] = {"series": [[int(t), int(v)] for t, v in zip(F.t.tail(730), F.v.tail(730))], "now": int(F.v.iloc[-1]),
                  "today": int(max(fg, key=lambda x: int(x["timestamp"]))["value"]),
                  "avg30": nn(F.v.tail(30).mean(), 0), "episodes": rows,
                  "stats": {"n_low": int(len(lo)), "med_low": nn(lo.f365.median()), "up_low": nn((lo.f365 > 0).mean()),
                            "n_all": int(len(al)), "med_all": nn(al.f365.median()), "up_all": nn((al.f365 > 0).mean())}}
except Exception as e:
    print("FAIL fng", repr(e))
    out["fng"] = {"series": [], "episodes": [], "stats": {}}

# ── fundamentals (crypto): CoinGecko supply/valuation + DefiLlama TVL / fees / DEX volume / stablecoins ──
fund = {}
try:
    cg = cached("cg", lambda: S.get("https://api.coingecko.com/api/v3/coins/markets", params={"vs_currency": "usd", "ids": ",".join(CG.values())}, timeout=25).json())
    inv = {v: k for k, v in CG.items()}
    for x in cg:
        tk = inv.get(x.get("id"))
        if tk:
            fund[tk] = {"mcap": x.get("market_cap"), "rank": x.get("market_cap_rank"), "fdv": x.get("fully_diluted_valuation"), "circ": x.get("circulating_supply"),
                        "total": x.get("total_supply"), "max": x.get("max_supply"), "vol24": x.get("total_volume")}
except Exception as e:
    print("FAIL coingecko", repr(e))


def jget(url, **kw):
    r = S.get(url, timeout=30, **kw)
    r.raise_for_status()
    return r.json()


try:
    ch = cached("ll_chains", lambda: jget("https://api.llama.fi/v2/chains"))
    tv = {x["name"]: x.get("tvl") for x in ch}
    st = cached("ll_stables", lambda: jget("https://stablecoins.llama.fi/stablecoinchains"))
    sc = {x["name"]: (x.get("totalCirculatingUSD") or {}).get("peggedUSD") for x in st}
    for tk, nm in LLAMA_CHAIN.items():
        f = fund.setdefault(tk, {})
        f["tvl"], f["stables"] = tv.get(nm), sc.get(nm)
        try:
            hist = cached("ll_tvl_" + nm, lambda n=nm: jget(f"https://api.llama.fi/v2/historicalChainTvl/{n}"))
            f["tvl_1y"] = hist[-366]["tvl"] if len(hist) > 366 else None
        except Exception as e:
            print("  tvl hist", tk, repr(e)[:80])
        try:
            dx = cached("ll_dex_" + nm, lambda n=nm: jget(f"https://api.llama.fi/overview/dexs/{n}", params={"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true"}))
            f["dex30"] = dx.get("total30d")
        except Exception as e:
            print("  dex", tk, repr(e)[:80])
        try:
            af = cached("ll_appfees_" + nm, lambda n=nm: jget(f"https://api.llama.fi/overview/fees/{n}", params={"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true", "dataType": "dailyFees"}))
            f["appfees30"] = af.get("total30d")
        except Exception as e:
            print("  app fees", tk, repr(e)[:80])
        time.sleep(0.4)
    for tk, slug in LLAMA_FEES.items():
        f = fund.setdefault(tk, {})
        for key, dt in (("fees30", "dailyFees"), ("rev30", "dailyRevenue")):
            try:
                x = cached(f"ll_{key}_{slug}", lambda s=slug, d=dt: jget(f"https://api.llama.fi/summary/fees/{s}", params={"dataType": d}))
                f[key] = x.get("total30d")
                if key == "fees30":
                    f["fees1y"] = x.get("total1y")
            except Exception as e:
                print("  fees", tk, key, repr(e)[:80])
        time.sleep(0.4)
    try:
        fund["UNI"]["tvl"] = cached("ll_tvl_uniswap", lambda: jget("https://api.llama.fi/tvl/uniswap"))
        x = cached("ll_dex_uniswap", lambda: jget("https://api.llama.fi/summary/dexs/uniswap"))
        fund["UNI"]["dex30"] = x.get("total30d")
    except Exception as e:
        print("  uni", repr(e)[:80])
except Exception as e:
    print("FAIL llama", repr(e))
for tk, f in fund.items():
    if tk in out["assets"]:
        out["assets"][tk]["fund"] = f

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
