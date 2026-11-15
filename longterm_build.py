"""📈 Long Term Investment — the research workbook's data build (user 2026-11-14: "yes add the daily
automatic rebuild on the render").

compute() gathers daily history for the sixteen names + BTC + Marvell / QQQ / SOXX + Fear & Greed and derives
every measure the workbook shows: dip map, ladder rungs by one volatility rule, upside map, isolated-leverage
liquidation odds, first-touch history, add-up levels, the BTC cycle clock, extreme-fear episodes,
correlations, the chip-stock comparison and on-chain fundamentals.
build_server() renders the workbook page from the template into the state directory;
maybe_rebuild() is the worker's once-a-day trigger. Research only: nothing here places or sizes a trade,
and the tracked plan (longterm_data/plan.json) is never touched.

Every source is fail-soft: a source that is down falls back to its last good copy; the three stocks fall
back to a seed history extended with their tokenized candles. A build that would be incomplete raises, and
the previous workbook stays in place.
"""
import json
import math
import os
import sys
import time
from statistics import NormalDist

import threading
import numpy as np
import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "research_meta", "portfolio_1114", "template.html")
SEED_DIR = os.path.join(HERE, "longterm_data", "seed")
RAW = None                               # cache directory, set by compute()
STALE: list = []                         # sources served from their last good copy in this run
FALLBACK: list = []                      # stocks built from the seed (+ tokenized candles) in this run
TOKENIZED = {"SNDK": "SNDKBUSDT", "NVDA": "NVDABUSDT", "AVGO": "AVGOBUSDT", "MRVL": "MRVLBUSDT"}
S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (research script)"})
N = NormalDist()
CRYPTO = {"INJ": "INJUSDT", "SOL": "SOLUSDT", "NEAR": "NEARUSDT", "SUI": "SUIUSDT", "AVAX": "AVAXUSDT", "UNI": "UNIUSDT", "ARB": "ARBUSDT",
          "WLD": "WLDUSDT", "TAO": "TAOUSDT", "HYPE": "HYPEUSDT", "ONDO": "ONDOUSDT", "LINK": "LINKUSDT", "QNT": "QNTUSDT",   # added 2026-11-15
          "BTC": "BTCUSDT"}
PERP_HISTORY = {"HYPEUSDT", "ONDOUSDT"}   # the perpetual feed goes back further than spot for these (May 2025 / Jan 2024)
STOCKS = {"SNDK": "SNDK", "NVDA": "NVDA", "AVGO": "AVGO", "MRVL": "MRVL", "QQQ": "QQQ", "SOXX": "SOXX"}
NAMES = {"INJ": "Injective", "SOL": "Solana", "NEAR": "NEAR Protocol", "SUI": "Sui", "AVAX": "Avalanche", "UNI": "Uniswap", "ARB": "Arbitrum",
         "WLD": "Worldcoin", "TAO": "Bittensor", "HYPE": "Hyperliquid", "ONDO": "Ondo", "LINK": "Chainlink", "QNT": "Quant",
         "SNDK": "SanDisk", "NVDA": "Nvidia", "AVGO": "Broadcom", "MRVL": "Marvell", "BTC": "Bitcoin", "QQQ": "Nasdaq 100 (QQQ)", "SOXX": "Semiconductors (SOXX)"}
PICKS = ["INJ", "SOL", "NEAR", "SNDK", "NVDA", "AVGO", "SUI", "AVAX", "UNI", "ARB", "WLD", "TAO", "HYPE", "ONDO", "LINK", "QNT"]
CG = {"INJ": "injective-protocol", "SOL": "solana", "NEAR": "near", "SUI": "sui", "AVAX": "avalanche-2", "UNI": "uniswap", "ARB": "arbitrum", "BTC": "bitcoin",
      "WLD": "worldcoin-wld", "TAO": "bittensor", "HYPE": "hyperliquid", "ONDO": "ondo-finance", "LINK": "chainlink", "QNT": "quant-network"}
LLAMA_CHAIN = {"INJ": "Injective", "SOL": "Solana", "NEAR": "Near", "SUI": "Sui", "AVAX": "Avalanche", "ARB": "Arbitrum", "HYPE": "Hyperliquid L1"}
LLAMA_FEES = {"INJ": "injective", "SOL": "solana", "NEAR": "near", "SUI": "sui", "AVAX": "avalanche", "ARB": "arbitrum", "UNI": "uniswap",
              "HYPE": "hyperliquid", "LINK": "chainlink", "ONDO": "ondo-finance"}
RUNG_P = [2 / 3, 1 / 3]                # three tranches (user 2026-11-14): today, then the dips reached in about two in three and one in three six-month windows
DIPS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70]
UPS = [0.25, 0.50, 1.00, 2.00, 4.00]
LEV = [1, 2, 3, 5, 10]
MM = 0.02                               # maintenance margin used for the isolated-liquidation distance


def cached(name, fn, max_age=6 * 3600):
    """Fresh copy from the cache, else fetch and store; if the fetch fails, the last good copy (any age)."""
    p = f"{RAW}/{name}.json"
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < max_age:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    try:
        v = fn()
    except Exception:
        if os.path.exists(p):
            STALE.append(name)
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        raise
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(v, f)
    os.replace(p + ".tmp", p)
    return v


def _bn_get(path, params):
    """Binance through the app's own client (mirrors + rate-limit handling) when it is importable."""
    fut = path.startswith("/fapi/")
    try:
        import binance_client
    except Exception:
        return S.get(("https://fapi.binance.com" if fut else "https://api.binance.com") + path, params=params, timeout=25).json()
    return binance_client._get(path, params, bases=binance_client.FUTURES_BASES) if fut else binance_client._get(path, params)


def _klines_all(path, sym):
    """Every completed daily candle of a symbol from one Binance endpoint, as [open_ts, o, h, l, c]."""
    rows, start = [], 1501545600000          # 1 Aug 2017
    while True:
        k = _bn_get(path, {"symbol": sym, "interval": "1d", "limit": 1000, "startTime": start})
        if not isinstance(k, list) or not k:
            break
        rows += [[int(x[0]) // 1000, float(x[1]), float(x[2]), float(x[3]), float(x[4])] for x in k]
        if len(k) < 1000:
            break
        start = int(k[-1][0]) + 86400000
        time.sleep(0.25)
    return rows[:-1]                         # drop the bar still in progress


def bn_seed_rows(sym):
    """The perpetual history shipped with the code for a PERP_HISTORY symbol (longterm_data/seed), or []."""
    try:
        with open(os.path.join(SEED_DIR, f"bn_{sym}.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def binance_daily(sym):
    """Daily history from the spot feed; for a PERP_HISTORY symbol from the perpetual feed, and when that
    feed cannot be reached, the shipped perpetual history followed by the spot candles after it."""
    if sym not in PERP_HISTORY:
        return _klines_all("/api/v3/klines", sym)
    try:
        rows = _klines_all("/fapi/v1/klines", sym)
    except Exception:
        rows = []
    if len(rows) >= 250:
        return rows
    seed, spot = bn_seed_rows(sym), _klines_all("/api/v3/klines", sym)
    if not seed:
        return spot
    STALE.append("bn_" + sym + "_perp")
    return seed + [r for r in spot if r[0] > seed[-1][0]]


def yahoo_daily(sym):
    r = S.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", params={"range": "10y", "interval": "1d"}, timeout=25)
    j = r.json()["chart"]["result"][0]
    q = j["indicators"]["quote"][0]
    return [[int(t), o, h, l, c] for t, o, h, l, c in zip(j["timestamp"], q["open"], q["high"], q["low"], q["close"]) if None not in (o, h, l, c)]


def seed_rows(sym):
    """The committed 10-year history for a stock (longterm_data/seed), or [] when there is none."""
    try:
        with open(os.path.join(SEED_DIR, f"yh_{sym}.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def tokenized_rows(sym, limit=400):
    """Completed daily candles of a tokenized ticker as [open_ts, o, h, l, c]; [] on any failure."""
    try:
        import binance_client
        df = binance_client.get_klines(sym, "1d", limit=limit)
        rows = [[int(pd.Timestamp(i).timestamp()), float(o), float(h), float(l), float(c)]
                for i, o, h, l, c in zip(df.index, df["open"], df["high"], df["low"], df["close"])]
        return rows[:-1]                     # drop the bar still in progress
    except Exception:
        return []


def extend_tokenized(tk, rows, now=None, fetch=tokenized_rows):
    """When a stock's history stops more than four days back (its feed is down), append the weekday
    candles of its tokenized ticker after the last row. Rows that are already current pass through."""
    now = time.time() if now is None else now
    if not rows or tk not in TOKENIZED or now - rows[-1][0] < 4 * 86400:
        return rows
    last_day = int(rows[-1][0] // 86400)
    add = [[r[0] + 52200] + r[1:] for r in fetch(TOKENIZED[tk])
           if int(r[0] // 86400) > last_day and time.gmtime(r[0]).tm_wday < 5]
    if add:
        FALLBACK.append(tk)
    return rows + add


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



def compute(raw_dir, log=print):
    """Fetch everything and return the workbook's data dict. Raises when a required series is missing."""
    global RAW
    RAW = raw_dir
    os.makedirs(RAW, exist_ok=True)
    del STALE[:]
    del FALLBACK[:]
    frames = {}
    for tk, sym in CRYPTO.items():
        try:
            frames[tk] = frame(cached("bn_" + sym, lambda s=sym: binance_daily(s)))
        except Exception as e:
            log("FAIL", tk, e)
    for tk, sym in STOCKS.items():
        try:
            rows = cached("yh_" + sym, lambda s=sym: yahoo_daily(s))
        except Exception as e:                   # no feed and no earlier copy: the committed seed
            rows = seed_rows(sym)
            STALE.append("yh_" + sym)
            log("stock feed down, using the seed for", tk, repr(e)[:80])
        rows = extend_tokenized(tk, rows)
        if rows:
            frames[tk] = frame(rows)

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
        dip50 = 1 - math.exp(s6 * N.inv_cdf(0.50 / 2))          # the isolated plan's default stop
        dip75 = 1 - math.exp(s6 * N.inv_cdf(0.75 / 2))          # its tight stop
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
                "dip": dip, "rungs": rungs, "up": up, "liq": liq, "stop15": stop15, "ft": ft, "addups": addups, "hi90": hi90, "dip50": dip50, "dip75": dip75,
                "series": {"t": [int(x) for x in tail.t], "c": [nn(x, 6) for x in tail.c], "s50": [nn(x, 6) for x in tail.s50],
                           "s200": [nn(x, 6) for x in tail.s200], "rsi": [nn(x, 1) for x in tail.rsi]},
                "long": {"t": [int(x.timestamp()) for x in wkl.index], "c": [nn(x, 6) for x in wkl.values]}}


    out = {"built": int(time.time()), "assets": {}, "picks": PICKS}
    for tk in list(CRYPTO) + list(STOCKS):
        if tk in frames:
            try:
                out["assets"][tk] = measures(tk)
            except Exception as e:
                log("FAIL measures", tk, repr(e))

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


    out["addup_ev"] = {"coins": pool_events([t for t in PICKS if t in CRYPTO]), "stocks": pool_events(["NVDA", "AVGO", "MRVL"])}


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
        log("FAIL fng", repr(e))
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
        log("FAIL coingecko", repr(e))


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
                log("  tvl hist", tk, repr(e)[:80])
            try:
                dx = cached("ll_dex_" + nm, lambda n=nm: jget(f"https://api.llama.fi/overview/dexs/{n}", params={"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true"}))
                f["dex30"] = dx.get("total30d")
            except Exception as e:
                log("  dex", tk, repr(e)[:80])
            try:
                af = cached("ll_appfees_" + nm, lambda n=nm: jget(f"https://api.llama.fi/overview/fees/{n}", params={"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true", "dataType": "dailyFees"}))
                f["appfees30"] = af.get("total30d")
            except Exception as e:
                log("  app fees", tk, repr(e)[:80])
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
                    log("  fees", tk, key, repr(e)[:80])
            time.sleep(0.4)
        try:
            fund["UNI"]["tvl"] = cached("ll_tvl_uniswap", lambda: jget("https://api.llama.fi/tvl/uniswap"))
            x = cached("ll_dex_uniswap", lambda: jget("https://api.llama.fi/summary/dexs/uniswap"))
            fund["UNI"]["dex30"] = x.get("total30d")
        except Exception as e:
            log("  uni", repr(e)[:80])
    except Exception as e:
        log("FAIL llama", repr(e))
    for tk, f in fund.items():
        if tk in out["assets"]:
            out["assets"][tk]["fund"] = f


    missing = [tk for tk in PICKS + ["BTC", "MRVL", "QQQ", "SOXX"] if tk not in out["assets"]]
    if missing:
        raise RuntimeError("no data for " + ", ".join(missing))
    if not (out.get("fng") or {}).get("series"):
        raise RuntimeError("no Fear & Greed history")
    out["sources"] = {"stale": sorted(set(STALE)), "stock_fallback": sorted(set(FALLBACK))}
    return out


def render_html(out, template_text):
    """The workbook page: the template with the data dropped in."""
    assert template_text.count("/*DATA*/null") == 1, "template has no single data slot"
    return template_text.replace("/*DATA*/null", json.dumps(out, separators=(",", ":")).replace("</", "<\\/"))


# ───────────────────────── the server's daily rebuild ─────────────────────────
ENABLED = os.environ.get("LONGTERM_REBUILD", "1") != "0"      # set LONGTERM_REBUILD=0 in the environment to switch it off
BUILD_VER = 3                    # bump when the workbook's shape changes: the server rebuilds at once, the page ignores older copies
AFTER_CLOSE_S = 20 * 60          # build once the 00:00 UTC daily close is 20 minutes old
RETRY_S = 2 * 3600               # after a failed try, wait this long before the next
WARMUP_S = 15 * 60               # never during the first minutes after a start (the scanner's first pass)
_BOOT = time.time()
_LOCK = threading.Lock()
_RUNNING = {"on": False}
BANNER = ("<b>Rebuilt automatically every day</b> after the 00:00 UTC close. This copy uses prices to the close of {asof}. "
          "The buy levels inside this workbook restart from that close; the tracked plan on the Long Term Investment page "
          "stays fixed at its {plan} levels. The news notes and quarterly figures were written on 14 Nov 2026 and are not refreshed.{stale}")


def live_dir() -> str:
    """Where the rebuilt workbook lives: <STATE_DIR>/longterm on the server, longterm_data/_live beside the code otherwise."""
    sd = ""
    try:
        import config
        sd = (getattr(config, "STATE_DIR", "") or "").strip()
    except Exception:
        sd = (os.environ.get("STATE_DIR") or "").strip()
    d = os.path.join(sd, "longterm") if sd and os.path.isdir(sd) else os.path.join(HERE, "longterm_data", "_live")
    os.makedirs(d, exist_ok=True)
    return d


def live_workbook() -> str:
    return os.path.join(live_dir(), "workbook.html")


def read_status() -> dict:
    try:
        with open(os.path.join(live_dir(), "build.json"), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _write_status(st: dict) -> None:
    try:
        p = os.path.join(live_dir(), "build.json")
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(st, f)
        os.replace(p + ".tmp", p)
    except Exception:
        pass


def _day_label(ts) -> str:
    return time.strftime("%d %b %Y", time.gmtime(float(ts))).lstrip("0")


def build_server(log=print, now=None) -> dict:
    """Rebuild the workbook into the live directory. Never raises; returns (and stores) the status."""
    now = time.time() if now is None else now
    st = read_status()
    st["last_try"] = now
    _write_status(st)
    try:
        d = live_dir()
        out = compute(os.path.join(d, "raw"), log=log)
        plan_label = "13 Nov 2026"
        try:
            with open(os.path.join(HERE, "longterm_data", "plan.json"), encoding="utf-8") as f:
                plan_label = json.load(f).get("plan_date_label") or plan_label
        except Exception:
            pass
        src = out.get("sources") or {}
        stale = ""
        if src.get("stale") or src.get("stock_fallback"):
            bits = []
            if src.get("stock_fallback"):
                bits.append("stock prices for " + ", ".join(src["stock_fallback"]) + " come from their tokenized tickers")
            if src.get("stale"):
                bits.append(str(len(src["stale"])) + " data feed(s) were unavailable and show their last good copy")
            stale = " Today: " + "; ".join(bits) + "."
        asof = out["assets"]["BTC"]["asof"]
        out["banner"] = BANNER.format(asof=_day_label(asof), plan=plan_label, stale=stale)
        with open(TEMPLATE, encoding="utf-8") as f:
            page = render_html(out, f.read())
        tmp = live_workbook() + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(page)
        os.replace(tmp, live_workbook())
        st.update(ver=BUILD_VER, last_ok=time.time(), asof=asof, asof_label=_day_label(asof), secs=round(time.time() - now, 1),
                  sources=src, error=None)
        log(f"longterm workbook rebuilt: prices to {_day_label(asof)}, {st['secs']}s, stale {src.get('stale')}, fallback {src.get('stock_fallback')}")
    except Exception as exc:
        st["error"] = repr(exc)[:300]
        log("longterm workbook rebuild FAILED (the previous copy stays):", st["error"])
    _write_status(st)
    return st


def due(st: dict, now: float, boot: float) -> bool:
    """True when today's rebuild has not run yet: past the warm-up, past the retry gap, and the last good
    build belongs to an earlier UTC day (days turn over 20 minutes after the 00:00 close)."""
    if now - boot < WARMUP_S:
        return False
    if now - float(st.get("last_try") or 0) < RETRY_S:
        return False
    if st.get("ver") != BUILD_VER:
        return True
    day = lambda t: int((float(t) - AFTER_CLOSE_S) // 86400)
    return day(now) != day(st.get("last_ok") or 0)


def maybe_rebuild(now=None, log=print) -> bool:
    """The worker calls this every cycle. Starts the day's rebuild in its own thread when it is due and
    returns at once. True when a build was started."""
    if not ENABLED:
        return False
    now = time.time() if now is None else now
    with _LOCK:
        if _RUNNING["on"] or not due(read_status(), now, _BOOT):
            return False
        _RUNNING["on"] = True

    def _run():
        try:
            build_server(log=log)
        finally:
            _RUNNING["on"] = False

    threading.Thread(target=_run, name="longterm-rebuild", daemon=True).start()
    return True
