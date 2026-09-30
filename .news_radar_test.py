"""NEWS RADAR fixture tests — no network.

Run:  .venv\\Scripts\\python.exe .news_radar_test.py
Prints "NEWS RADAR: ALL PASS" when everything passes (exit 1 otherwise).
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np
import pandas as pd

import news_radar as nr

UTC = timezone.utc
KST = timezone(timedelta(hours=9))
TMP = Path(tempfile.mkdtemp(prefix="news_radar_test_"))

# ---------------------------------------------------------------- no network
NET_CALLS: list[str] = []


def _no_net(*a, **k):
    NET_CALLS.append("session.get")
    raise RuntimeError("network used in a test")


nr._SESSION.get = _no_net
for _k in list(nr.DEFAULT_FETCHERS):
    nr.DEFAULT_FETCHERS[_k] = (lambda k=_k: NET_CALLS.append(k) or [])

ALL_MSGS: list[str] = []
SAMPLES: dict[str, str] = {}
TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def fresh_state(name: str) -> Path:
    p = TMP / f"{name}.json"
    if p.exists():
        p.unlink()
    nr.STATE_FILE = p
    return p


class Outbox:
    def __init__(self):
        self.msgs: list[str] = []

    def __call__(self, text: str):
        self.msgs.append(text)
        ALL_MSGS.append(text)
        return (True, "sent")


class Recorder:
    def __init__(self):
        self.rows: list[tuple[str, dict]] = []

    def __call__(self, stream, payload):
        self.rows.append((stream, payload))


def md_ok(msg: str) -> bool:
    """Telegram Markdown v1 sanity: link targets aside, * _ ` are balanced
    and no stray [ ] remains."""
    body = re.sub(r"\[[^\[\]]*\]\(https?://[^)\s]*\)", "LINK", msg)
    return (body.count("*") % 2 == 0 and body.count("_") % 2 == 0
            and body.count("`") % 2 == 0 and "[" not in body
            and "]" not in body)


def dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


# ------------------------------------------------------------------ fixtures
BASES = {"BTC", "ETH", "QNT", "NEAR", "ENA", "UNI", "XPL", "LINK", "SOL"}

UPBIT_JSON = {"success": True, "data": {"total_pages": 1, "notices": [
    {"listed_at": "2026-09-28T14:27:04+09:00",
     "first_listed_at": "2026-09-28T14:27:04+09:00", "id": 6618,
     "uuid": "u6618", "category": "거래",
     "title": "캐시캣(CASHCAT) 신규 거래지원 안내 (KRW, BTC, USDT 마켓)"},
    {"listed_at": "2026-09-22T16:00:00+09:00",
     "first_listed_at": "2026-09-22T16:00:00+09:00", "id": 6605,
     "uuid": "u6605", "category": "거래",
     "title": "인젝티브(INJ) 거래 유의 종목 지정 해제 안내"},
    {"listed_at": "2026-09-22T15:00:08+09:00",
     "first_listed_at": "2026-09-22T15:00:08+09:00", "id": 6604,
     "uuid": "u6604", "category": "거래",
     "title": "소폰(SOPH) 거래 유의 종목 지정 안내"},
    {"listed_at": "2026-09-18T16:30:00+09:00",
     "first_listed_at": "2026-09-18T16:30:00+09:00", "id": 6591,
     "uuid": "u6591", "category": "거래",
     "title": "아이콘(ICX) 거래지원 종료 안내 (10/19 15:00)"},
]}}

BINANCE_48 = [
    {"id": 285492, "code": "d49de208bb6d4a26b02677d7c3d89b5d", "type": 1,
     "title": "Binance Will List Hyperliquid (HYPE) with Seed Tag Applied",
     "releaseDate": 1790235038608},
    {"id": 285915, "code": "172e44302d6143578e40acc48570a2e5", "type": 1,
     "title": "Binance Exchange Adds Adobe (ADBEB), Zoom (ZMB) bStocks Trading "
              "Pairs on Binance Spot/Convert - 2026-09-30",
     "releaseDate": 1790737204692},
    {"id": 285396, "code": "8bd2b3a7684749bba472e71fc3ad8043", "type": 1,
     "title": "Binance Futures Will Launch USDⓈ-Margined PONSUSDT Perpetual "
              "Contract (2026-09-06)", "releaseDate": 1790147746848},
]
BINANCE_161 = [
    {"id": 284259, "code": "8e6fd91b79a34bddbd7643ef002db47e", "type": 1,
     "title": "Binance Will Delist USDP on 2026-09-24",
     "releaseDate": 1789020012727},
    {"id": 285827, "code": "63415de54a164619aaaf245850349654", "type": 1,
     "title": "Notice of Removal of Spot Trading Pairs - 2026-10-02",
     "releaseDate": 1790673300000},
]

OKX_JSON = {"code": "0", "msg": "", "data": [{"totalPage": 1, "details": [
    {"annType": "announcements-new-listings",
     "title": "OKX to list CT/USDT (Concrete) for spot trading",
     "url": "https://www.okx.com/help/okx-to-list-ct-usdt",
     "pTime": "1790740812658"},
    {"annType": "announcements-new-listings",
     "title": "OKX to list PURRUSD Equity X-Perps",
     "url": "https://www.okx.com/help/okx-to-list-purrusd",
     "pTime": "1790740812490"},
    {"annType": "announcements-new-listings",
     "title": "OKX to list ONEUSD X-Perp",
     "url": "https://www.okx.com/help/okx-to-list-oneusd",
     "pTime": "1790739012058"},
    {"annType": "announcements-delistings",
     "title": "OKX to delist DORA, ICX, STORJ, ZEUS and ELF spot trading pairs",
     "url": "https://www.okx.com/help/okx-to-delist-dora",
     "pTime": "1790157613684"},
    {"annType": "announcements-delistings",
     "title": "OKX to delist perpetual futures for ONEUSDT",
     "url": "https://www.okx.com/help/okx-to-delist-oneusdt-perp",
     "pTime": "1789524011039"},
    {"annType": "latest-events",
     "title": "OKX × CT Trade-to-Earn: Trade to Share 1,000,000 CT",
     "url": "https://www.okx.com/help/ct-trade-to-earn",
     "pTime": "1790757117955"},
]}]}

BYBIT_JSON = {"retCode": 0, "retMsg": "OK", "result": {"total": 7, "list": [
    {"title": "Bybit to List Pons (PONS) on Spot",
     "description": "We are excited to announce the upcoming listing of Pons",
     "type": {"key": "new_crypto", "title": "New Listings"},
     "tags": ["Spot", "Spot Listings"],
     "url": "https://announcements.bybit.com/en-US/article/bybit-to-list-pons/",
     "dateTimestamp": 1790253232000},
    {"title": "New listing: XDPUSDT Perpetual Contract in Innovation Zone, "
              "with up to 25x leverage", "description": "",
     "type": {"key": "new_crypto", "title": "New Listings"},
     "tags": ["Derivatives"],
     "url": "https://announcements.bybit.com/en-US/article/xdpusdt-perp/",
     "dateTimestamp": 1790675090000},
    {"title": "KII Alpha Token Splash— Grab a share of the 2,000,000 KII prize "
              "pool .", "description": "",
     "type": {"key": "new_crypto", "title": "New Listings"},
     "tags": ["Spot", "Spot Listings"],
     "url": "https://announcements.bybit.com/en-US/article/kii-splash/",
     "dateTimestamp": 1790253232001},
    {"title": "Delisting of L3,VIC", "description": "",
     "type": {"key": "delistings", "title": "Delistings"},
     "tags": ["Delistings", "Institutions", "VIP"],
     "url": "https://announcements.bybit.com/en-US/article/delisting-of-l3-vic/",
     "dateTimestamp": 1789900000000},
    {"title": "Bybit to Delist 4 Token(s) on Sep 24, 2026", "description": "",
     "type": {"key": "delistings", "title": "Delistings"},
     "tags": ["Delistings"],
     "url": "https://announcements.bybit.com/en-US/article/bybit-to-delist-4/",
     "dateTimestamp": 1789800000000},
    {"title": "Delisting of ICXUSDT Perpetual Contract", "description": "",
     "type": {"key": "delistings", "title": "Delistings"},
     "tags": ["Derivatives", "Delistings"],
     "url": "https://announcements.bybit.com/en-US/article/icx-perp/",
     "dateTimestamp": 1789700000000},
    {"title": "Bybit AI Now Supports Main Account Operations", "description": "",
     "type": {"key": "latest_bybit_news", "title": "Latest Bybit News"},
     "tags": ["News"],
     "url": "https://announcements.bybit.com/en-US/article/bybit-ai/",
     "dateTimestamp": 1790568000000},
]}}

CAL_RAW = [
    {"title": "Core PCE Price Index m/m", "country": "USD",
     "date": "2026-09-30T08:30:00-04:00", "impact": "High",
     "forecast": "0.3%", "previous": "0.2%"},
    {"title": "Final GDP q/q", "country": "USD",
     "date": "2026-09-30T08:30:00-04:00", "impact": "High",
     "forecast": "1.5%", "previous": "1.5%"},
    {"title": "FOMC Member Barkin Speaks", "country": "USD",
     "date": "2026-09-30T13:30:00-04:00", "impact": "Low",
     "forecast": "", "previous": ""},
    {"title": "Unemployment Claims", "country": "USD",
     "date": "2026-10-01T08:30:00-04:00", "impact": "Medium",
     "forecast": "201K", "previous": "197K"},
    {"title": "Federal Funds Rate", "country": "USD",
     "date": "2026-10-01T14:00:00-04:00", "impact": "Medium",
     "forecast": "3.75%", "previous": "3.75%"},
    {"title": "CPI Flash Estimate y/y", "country": "EUR",
     "date": "2026-09-30T05:00:00-04:00", "impact": "High",
     "forecast": "2.1%", "previous": "2.0%"},
]


def ex_fetchers(extra_upbit=None):
    ub = json.loads(json.dumps(UPBIT_JSON))
    if extra_upbit:
        ub["data"]["notices"] = extra_upbit + ub["data"]["notices"]
    return {
        "binance": lambda: nr.parse_binance(BINANCE_48, 48)
        + nr.parse_binance(BINANCE_161, 161),
        "upbit": lambda: nr.parse_upbit(ub),
        "okx": lambda: nr.parse_okx(OKX_JSON),
        "bybit": lambda: nr.parse_bybit(BYBIT_JSON),
    }


def quiet_klines(clock: dict, overrides: dict | None = None):
    """Deterministic quiet market: 1h / 5m candles ending at clock['now'],
    last row = the still-forming candle."""
    def gk(sym, interval, limit=200):
        if overrides and (sym, interval) in overrides:
            return overrides[(sym, interval)](clock, limit)
        step = 3600 if interval == "1h" else 300
        now = clock["now"].timestamp()
        end = (now // step) * step
        t = end - step * np.arange(limit - 1, -1, -1)
        rng = np.random.default_rng(sum(map(ord, sym)) + step)
        close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.003, limit)))
        opn = np.r_[close[0], close[:-1]]
        return pd.DataFrame(
            {"open": opn, "high": np.maximum(opn, close) * 1.001,
             "low": np.minimum(opn, close) * 0.999, "close": close,
             "volume": np.full(limit, 1000.0)},
            index=pd.to_datetime(t, unit="s", utc=True))
    return gk


def no_fetch(**over):
    base = {k: (lambda: []) for k in ("binance", "upbit", "okx", "bybit",
                                      "rss", "calendar")}
    base.update(over)
    return base


# --------------------------------------------------------------------- tests
@test
def tagger():
    cases = [
        ("Gold holds near $4,400", []),
        ("NEAR Protocol partners with Google Cloud", ["NEAR"]),
        ("Treasury urges Senate to pass Clarity Act", []),
        ("Ethena (ENA) TVL hits record", ["ENA"]),
        ("Exploit drains $5M from bridge", []),
        ("Quant partners with SWIFT on tokenised deposits", ["QNT"]),
        ("$UNI surges 12%", ["UNI"]),
        # extras
        ("NEAR price rises 5%", []),                 # ambiguous, no $ / name
        ("$NEAR rallies after upgrade", ["NEAR"]),
        ("SENATE BANKING COMMITTEE DELAYS VOTE", []),
        ("EXPLOIT HITS DEFI PROTOCOL", []),
        ("Quant funds pile into Bitcoin", ["BTC"]),  # 'Quant funds' != QNT
        ("Bitcoin and Ethereum ETFs see outflows", ["BTC", "ETH"]),
        ("QNT jumps 20% as Quant Network signs bank deal", ["QNT"]),
        ("Solana (SOL) and Cardano (ADA) rally", ["SOL"]),  # ADA not in bases
        ("Plasma (XPL) mainnet goes live", ["XPL"]),
        ("Chainlink CCIP now live on 60 chains", ["LINK"]),
    ]
    for text, want in cases:
        got = nr.tag_coins(text, BASES)
        assert got == want, f"{text!r}: got {got} want {want}"


@test
def classifier():
    c = nr.classify("Quant partners with SWIFT on tokenised deposits")
    assert c["direction"] == "bull" and c["kind"] == "partnership", c
    assert c["big_name"] is True and "SWIFT" in c["names"], c
    assert nr.is_big_news(c, ["QNT"]) is True
    assert nr.is_big_news(c, []) is False           # untagged -> never big
    c = nr.classify("X protocol hacked for $40M")
    assert c["direction"] == "bear" and c["kind"] == "hack", c
    assert nr.is_big_news(c, ["UNI"]) is True
    c = nr.classify("Bitcoin price analysis")
    assert c["direction"] == "neutral", c
    # extras
    c = nr.classify("SEC delays decision on XRP ETF")
    assert c["direction"] == "bear" and c["kind"] == "etf_setback", c
    c = nr.classify("SEC approves spot Solana ETF")
    assert c["direction"] == "bull" and c["kind"] == "etf", c
    c = nr.classify("Coinbase lists Quant")
    assert c["kind"] == "listing" and c["big_name"], c
    c = nr.classify("Months After the $292M Kelp Hack, Chainlink Lets "
                    "Institutions Add Their Own Bridge Checks")
    assert c["kind"] != "hack", c                  # retrospective context
    c = nr.classify("Treasury urges Senate to pass Clarity Act")
    assert c["kind"] != "treasury", c
    c = nr.classify("Could XRP partner with Visa?")
    assert c["speculative"] and not nr.is_big_news(c, ["XRP"]), c
    c = nr.classify("Exchange halts withdrawals after insolvency fears")
    assert c["direction"] == "bear", c
    c = nr.classify("Ethena (ENA) TVL hits record")
    assert c["direction"] == "bull" and c["kind"] == "record_high", c
    c = nr.classify("Swift recovery for markets")    # lowercase-ish swift
    assert not c["big_name"], c


@test
def upbit_titles():
    items = {it["id"]: it for it in nr.parse_upbit(UPBIT_JSON)}
    a = items["upbit:6618"]
    assert a["kind"] == "spot_listing" and a["direction"] == "bull", a
    assert a["tickers"] == ["CASHCAT"] and a["markets"] == ["KRW", "BTC",
                                                            "USDT"], a
    assert a["bell"] and a["big"]
    b = items["upbit:6591"]
    assert b["kind"] == "delisting" and b["direction"] == "bear" and \
        b["tickers"] == ["ICX"] and b["bell"], b
    c = items["upbit:6604"]
    assert c["kind"] == "caution" and c["direction"] == "bear" and \
        c["tickers"] == ["SOPH"] and c["bell"], c
    d = items["upbit:6605"]
    assert d["kind"] == "caution_lifted" and d["direction"] == "neutral" and \
        not d["bell"] and d["tickers"] == ["INJ"], d
    # extras: title-edit notices never re-bell
    e = nr.classify_upbit("렌조(REZ) 신규 거래지원 안내 (USDT 마켓) "
                          "(거래지원 개시 시점 추가 변경 안내)")
    assert e["kind"] == "listing_update" and not e["bell"], e
    f = nr.classify_upbit("바이프로스트(BFC) KRW, USDT 마켓 디지털 자산 추가")
    assert f["kind"] == "market_add" and f["bell"] and f["tickers"] == ["BFC"]
    assert abs(a["ts"] - dt("2026-09-28 05:27:04").timestamp()) < 1


@test
def binance_titles():
    cb = nr.classify_binance
    x = cb("Binance Will List Hyperliquid (HYPE) with Seed Tag Applied")
    assert x["kind"] == "spot_listing" and x["tickers"] == ["HYPE"] and \
        x["bell"], x
    x = cb("Binance Exchange Adds Adobe (ADBEB), Zoom (ZMB) bStocks Trading "
           "Pairs on Binance Spot/Convert - 2026-09-30")
    assert x["kind"] == "ignore" and not x["bell"], x
    x = cb("Binance Will Add 7 bStocks Tokenized Securities as Collateral "
           "Asset - 2026-09-30")
    assert x["kind"] == "ignore", x
    x = cb("Binance Futures Will Launch USDⓈ-Margined PONSUSDT Perpetual "
           "Contract (2026-09-06)")
    assert x["kind"] == "futures_launch" and not x["bell"], x
    x = cb("Binance Will Delist USDP on 2026-09-24")
    assert x["kind"] == "delisting" and x["direction"] == "bear" and \
        x["tickers"] == ["USDP"] and x["bell"], x
    x = cb("Binance Will Delist BADGER, BAL, BETA and CREAM on 2026-04-16")
    assert x["tickers"] == ["BADGER", "BAL", "BETA", "CREAM"], x
    x = cb("Binance Will Add Hyperliquid (HYPE) on Earn, Buy Crypto, Convert, "
           "VIP Loan & Margin")
    assert x["kind"] == "ignore", x
    x = cb("Notice of Removal of Spot Trading Pairs - 2026-10-02")
    assert x["kind"] == "pair_removal" and not x["bell"], x
    x = cb("Binance Adds Foo Network (FOO) Trading Pairs on Binance Spot")
    assert x["kind"] == "spot_listing" and x["tickers"] == ["FOO"], x
    items = nr.parse_binance(BINANCE_48, 48) + nr.parse_binance(BINANCE_161,
                                                                161)
    assert {i["src_key"] for i in items} == {"binance48", "binance161"}
    assert items[0]["link"].endswith(BINANCE_48[0]["code"])


@test
def okx_bybit_parse():
    ok = {i["title"]: i for i in nr.parse_okx(OKX_JSON)}
    a = ok["OKX to list CT/USDT (Concrete) for spot trading"]
    assert a["kind"] == "spot_listing" and a["tickers"] == ["CT"] and \
        a["bell"], a
    assert ok["OKX to list PURRUSD Equity X-Perps"]["kind"] == "futures_launch"
    assert ok["OKX to list ONEUSD X-Perp"]["bell"] is False
    d = ok["OKX to delist DORA, ICX, STORJ, ZEUS and ELF spot trading pairs"]
    assert d["kind"] == "delisting" and d["tickers"] == \
        ["DORA", "ICX", "STORJ", "ZEUS", "ELF"] and d["bell"], d
    p = ok["OKX to delist perpetual futures for ONEUSDT"]
    assert p["kind"] == "futures_delist" and not p["bell"], p
    assert ok["OKX × CT Trade-to-Earn: Trade to Share 1,000,000 CT"]["kind"] \
        == "ignore"
    assert abs(a["ts"] - 1790740812.658) < 1e-3
    by = {i["title"]: i for i in nr.parse_bybit(BYBIT_JSON)}
    b = by["Bybit to List Pons (PONS) on Spot"]
    assert b["kind"] == "spot_listing" and b["tickers"] == ["PONS"] and \
        b["bell"], b
    assert by["New listing: XDPUSDT Perpetual Contract in Innovation Zone, "
              "with up to 25x leverage"]["kind"] == "futures_launch"
    assert by["KII Alpha Token Splash— Grab a share of the 2,000,000 KII "
              "prize pool ."]["kind"] == "ignore"
    v = by["Delisting of L3,VIC"]
    assert v["kind"] == "delisting" and v["tickers"] == ["L3", "VIC"], v
    w = by["Bybit to Delist 4 Token(s) on Sep 24, 2026"]
    assert w["kind"] == "delisting" and w["bell"] and w["tickers"] == [], w
    assert by["Delisting of ICXUSDT Perpetual Contract"]["kind"] == \
        "futures_delist"
    assert by["Bybit AI Now Supports Main Account Operations"]["kind"] == \
        "ignore"
    assert b["src_key"] == "bybit:new_crypto"


@test
def calendar_pkt_and_windows():
    ev = nr.filter_calendar(CAL_RAW)
    titles = [e["title"] for e in ev]
    assert titles == ["Core PCE Price Index m/m", "Final GDP q/q",
                      "Federal Funds Rate"], titles
    t = nr.parse_cal_time("2026-09-30T08:30:00-04:00")
    assert t == dt("2026-09-30 12:30"), t
    assert nr.to_pkt(t).strftime("%H:%M") == "17:30"
    assert nr.fmt_pkt(t) == "17:30 PKT (12:30 UTC)", nr.fmt_pkt(t)
    ts = t.timestamp()
    assert nr.reminder_due(ts, t - timedelta(minutes=30))
    assert nr.reminder_due(ts, t - timedelta(minutes=20))
    assert nr.reminder_due(ts, t - timedelta(minutes=40))
    assert not nr.reminder_due(ts, t - timedelta(minutes=45))
    assert not nr.reminder_due(ts, t - timedelta(minutes=15))
    assert nr.followup_due(ts, t + timedelta(minutes=35))
    assert not nr.followup_due(ts, t + timedelta(minutes=20))
    assert not nr.followup_due(ts, t + timedelta(minutes=50))


def _btc5m(clock, limit):
    """BTC 5m: flat 99,900 before the 12:30 print, then 100,000 -> 100,500."""
    now = clock["now"].timestamp()
    end = (now // 300) * 300
    t = end - 300 * np.arange(limit - 1, -1, -1)
    ev = dt("2026-09-30 12:30").timestamp()
    close = np.where(t < ev, 99900.0, 0.0)
    after = t >= ev
    k = int(after.sum())
    close[after] = np.linspace(100000.0, 100500.0, k + 1)[1:]
    opn = np.r_[close[0], close[:-1]]
    opn[np.argmax(after)] = 100000.0
    return pd.DataFrame({"open": opn, "high": np.maximum(opn, close) + 20,
                         "low": np.minimum(opn, close) - 20, "close": close,
                         "volume": np.full(limit, 10.0)},
                        index=pd.to_datetime(t, unit="s", utc=True))


@test
def macro_reminder_and_followup():
    fresh_state("macro")
    clock = {"now": dt("2026-09-30 12:00")}
    gk = quiet_klines(clock, {("BTCUSDT", "5m"): _btc5m})
    fx = no_fetch(calendar=lambda: CAL_RAW)
    out = Outbox()
    sent = nr.run(gk, ["BTCUSDT", "ETHUSDT"], out, now=clock["now"], fetch=fx)
    assert len(sent) == 1, sent
    m = sent[0]
    assert m.startswith("🗓 *US Core PCE Price Index m/m + Final GDP q/q in "
                        "30 min* — 17:30 PKT (12:30 UTC)"), m
    assert "forecast 0.3%" in m and "previous 1.5%" in m
    assert "avoid fresh entries right before the print" in m
    SAMPLES["macro reminder (2 prints at once)"] = m
    single = nr.fmt_macro_pre([nr.filter_calendar(CAL_RAW)[0]],
                              dt("2026-09-30 12:00"))
    assert "in 30 min* — 17:30 PKT (12:30 UTC) · forecast 0.3% · " \
        "previous 0.2% · expect a volatile hour" in single, single
    SAMPLES["macro reminder (single)"] = single
    ALL_MSGS.append(single)
    clock["now"] = dt("2026-09-30 12:05")
    assert nr.run(gk, ["BTCUSDT"], out, now=clock["now"], fetch=fx) == []
    clock["now"] = dt("2026-09-30 13:05")
    sent = nr.run(gk, ["BTCUSDT"], out, now=clock["now"], fetch=fx)
    assert len(sent) == 1, sent
    m = sent[0]
    assert "released* — BTC moved +0.5% since the print (17:30 PKT)" in m, m
    assert "now 100,500" in m, m
    SAMPLES["macro follow-up"] = m
    clock["now"] = dt("2026-09-30 13:10")
    assert nr.run(gk, ["BTCUSDT"], out, now=clock["now"], fetch=fx) == []


@test
def first_run_no_flood_then_one_bell():
    fresh_state("firstrun")
    clock = {"now": dt("2026-09-30 09:00")}
    gk = quiet_klines(clock)
    rss_rows = [{"source": "CoinDesk", "title": "Quant partners with SWIFT on "
                 "tokenised deposits", "link": "https://x.test/qnt-swift",
                 "published": clock["now"].timestamp() - 600}]
    fx = ex_fetchers()
    fx.update(rss=lambda: rss_rows, calendar=lambda: [])
    out, rec = Outbox(), Recorder()
    sent = nr.run(gk, ["BTCUSDT", "QNTUSDT", "NEARUSDT"], out, record=rec,
                  now=clock["now"], fetch=fx)
    assert sent == [], f"first run flooded: {sent}"
    st = json.loads(Path(nr.STATE_FILE).read_text(encoding="utf-8"))
    for k in ("upbit", "binance48", "binance161", "rss:CoinDesk"):
        assert k in st["primed"], (k, st["primed"])
    assert "upbit:6618" in st["seen"]["upbit"]
    assert rec.rows and all(s == "news_radar" for s, _ in rec.rows)
    keys = {"source", "kind", "direction", "big", "tickers", "title", "link",
            "ts"}
    assert all(keys <= set(p) for _, p in rec.rows), rec.rows[0]
    # a genuinely NEW Upbit listing lands 4 minutes later -> exactly one bell
    clock["now"] = dt("2026-09-30 09:04")
    new = [{"listed_at": clock["now"].astimezone(KST).isoformat(),
            "first_listed_at": clock["now"].astimezone(KST).isoformat(),
            "id": 6620, "uuid": "u6620", "category": "거래",
            "title": "퀀트(QNT) 신규 거래지원 안내 (KRW, USDT 마켓)"}]
    fx.update(ex_fetchers(extra_upbit=new))
    sent = nr.run(gk, ["BTCUSDT", "QNTUSDT", "NEARUSDT"], out, record=rec,
                  now=clock["now"], fetch=fx)
    assert len(sent) == 1, sent
    m = sent[0]
    assert m.startswith("🏦 *UPBIT LISTING — QNT*"), m
    assert "markets: KRW, USDT" in m and "in your universe: QNT" in m, m
    assert nr.LISTING_LINE_UPBIT in m, m
    SAMPLES["exchange listing"] = m
    # same notice again (dedup) -> no bell
    clock["now"] = dt("2026-09-30 09:08")
    assert nr.run(gk, ["BTCUSDT", "QNTUSDT"], out, now=clock["now"],
                  fetch=fx) == []


@test
def dedup_and_rss_big_news():
    fresh_state("rss")
    clock = {"now": dt("2026-09-30 09:00")}
    gk = quiet_klines(clock)
    old = [{"source": "CoinDesk", "title": "Bitcoin price analysis",
            "link": "https://x.test/a", "published": 0},
           {"source": "Decrypt", "title": "Ethereum gas fees fall",
            "link": "https://x.test/b", "published": 0}]
    rows = list(old)
    fx = no_fetch(rss=lambda: rows)
    out = Outbox()
    assert nr.run(gk, ["QNTUSDT"], out, now=clock["now"], fetch=fx) == []
    now2 = dt("2026-09-30 09:11")
    rows += [
        {"source": "CoinDesk", "title": "Quant partners with SWIFT on "
         "tokenised deposits", "link": "https://x.test/qnt_swift(1)",
         "published": now2.timestamp() - 300},
        {"source": "Decrypt", "title": "Quant teams up with SWIFT for "
         "tokenised deposit pilot", "link": "https://x.test/qnt2",
         "published": now2.timestamp() - 200},
        {"source": "Decrypt", "title": "Chainlink launches new docs portal",
         "link": "https://x.test/link", "published": now2.timestamp()},
        {"source": "CoinDesk", "title": "Uniswap hacked for $40M",
         "link": "https://x.test/uni", "published":
         now2.timestamp() - 10 * 3600},           # too old to bell
    ]
    clock["now"] = now2
    sent = nr.run(gk, ["QNTUSDT", "LINKUSDT", "UNIUSDT"], out, now=now2,
                  fetch=fx)
    assert len(sent) == 1, sent                  # 2 outlets, 1 bell
    m = sent[0]
    assert m.startswith("📰 *QNT — BULLISH partnership*"), m
    assert "big name: SWIFT" in m and nr.NEWS_BULL_LINE in m, m
    assert "qnt%5Fswift%281%29" in m              # link sanitised (_ and parens encoded), clickable
    SAMPLES["big coin news"] = m
    clock["now"] = dt("2026-09-30 09:22")
    assert nr.run(gk, ["QNTUSDT"], out, now=clock["now"], fetch=fx) == []


@test
def message_sanitation():
    nasty = "Evil *bold* _it_ `code` [link](x) title"
    it = {"source": "Upbit", "title": nasty, "link": "https://a.test/x_y",
          "ts": dt("2026-09-30 09:00").timestamp(), "kind": "spot_listing",
          "direction": "bull", "tickers": ["AB_C"], "markets": ["KRW"]}
    msgs = [nr.fmt_exchange(it, {"ABC"}),
            nr.fmt_exchange({**it, "kind": "delisting", "direction": "bear"}),
            nr.fmt_exchange({**it, "kind": "caution", "direction": "bear"}),
            nr.fmt_news({**it, "kind": "hack", "direction": "bear",
                         "names": ["Nasdaq"], "source": "Co*in_Desk"}),
            nr.fmt_surge({"base": "Q_NT", "direction": "down", "r4": -0.12,
                          "sigma": 4.2, "vol_mult": 6.1, "btc_r4": -0.002,
                          "price": 0.012345, "window_end": 1790000000},
                         [{"title": nasty, "src": "x_y"}]),
            nr.fmt_macro_pre([{"ts": 1790000000, "title": "C*P_I y/y",
                               "forecast": "3_%", "previous": "*"}],
                             1790000000 - 1800),
            nr.fmt_macro_post([{"ts": 1790000000, "title": "C*P_I y/y"}],
                              {"move": 0.004, "now": 1.5, "hi": 0.01,
                               "lo": -0.02})]
    for m in msgs:
        assert md_ok(m), m
        assert "Evil bold it code link(x) title" in m or "C" in m
        assert len(m) <= nr.MAX_MSG
    assert nr.clean("a*b_c`d[e]f") == "abcdef"
    long = {**it, "title": "x" * 5000}
    assert len(nr.fmt_exchange(long)) <= nr.MAX_MSG
    ALL_MSGS.extend(msgs)


@test
def fail_soft():
    def boom(*a, **k):
        raise RuntimeError("boom")
    fresh_state("failsoft")
    fx = {k: boom for k in ("binance", "upbit", "okx", "bybit", "rss",
                            "calendar")}
    r = nr.run(boom, ["BTCUSDT", "QNTUSDT"], boom, record=boom,
               now=dt("2026-09-30 05:00"), fetch=fx)
    assert isinstance(r, list), r
    # corrupt state file + send that reports failure
    Path(nr.STATE_FILE).write_text("{not json", encoding="utf-8")
    r = nr.run(boom, ["BTCUSDT"], lambda t: (False, "tg down"),
               now=dt("2026-09-30 05:30"), fetch=fx)
    assert r == [], r
    # garbage payloads never raise
    assert nr.parse_upbit({"x": 1}) == [] and nr.parse_okx(None) == []
    assert nr.parse_bybit("junk") == [] and nr.parse_binance(None) == []
    assert nr.filter_calendar([{"country": "USD", "impact": "High"}]) == []
    assert nr.scan_surges(boom, ["QNTUSDT"], dt("2026-09-30 05:00")) == []
    assert nr.tag_coins(None, None) == [] and nr.classify(None)["direction"] \
        == "neutral"


def _load15(sym: str) -> pd.DataFrame:
    return pd.read_csv(HERE / ".dip_kl" / f"{sym}USDT.csv",
                       usecols=["ot", "o", "h", "l", "c", "v"])


def csv_klines(frames: dict, clock: dict):
    """1h candles rebuilt from the 15m CSVs as of clock['now'] — including
    the still-forming hour, exactly like a live exchange."""
    def gk(sym, interval, limit=200):
        d = frames[sym]
        now_ms = int(clock["now"].timestamp() * 1000)
        lo = now_ms - (limit + 2) * 3_600_000
        sub = d[(d.ot >= lo) & (d.ot < now_ms)]
        h = (sub.ot // 3_600_000) * 3_600_000
        g = sub.groupby(h).agg(open=("o", "first"), high=("h", "max"),
                               low=("l", "min"), close=("c", "last"),
                               volume=("v", "sum"))
        g.index = pd.to_datetime(g.index, unit="ms", utc=True)
        return g.tail(limit)
    return gk


@test
def surge_replay_qnt_real_data():
    frames = {"QNTUSDT": _load15("QNT"), "BTCUSDT": _load15("BTC")}
    clock = {"now": dt("2026-09-24 12:00")}
    gk = csv_klines(frames, clock)
    fired = []
    t = dt("2026-09-24 12:00")
    while t <= dt("2026-09-24 18:00"):
        clock["now"] = t
        for ev in nr.scan_surges(gk, ["QNTUSDT", "BTCUSDT"], t):
            fired.append((t, ev))
        t += timedelta(minutes=15)
    q = [(t, e) for t, e in fired if e["base"] == "QNT"]
    assert q, "QNT 24-Sep surge not detected"
    t0, e0 = q[0]
    assert e0["direction"] == "up" and e0["r4"] >= 0.08 and \
        e0["sigma"] >= 3 and e0["vol_mult"] >= 4 and abs(e0["btc_r4"]) < 0.015
    print(f"      replay: QNT first fires at {t0:%Y-%m-%d %H:%M} UTC — "
          f"r4 {e0['r4']*100:+.1f}%, {e0['sigma']:.1f}σ, vol "
          f"{e0['vol_mult']:.1f}×, BTC {e0['btc_r4']*100:+.2f}%; "
          f"fires at {len(q)} of 25 checks")
    assert not [e for _, e in fired if e["base"] == "BTC"]
    # end-to-end through run(): radar already holds a QNT headline
    fresh_state("replay")
    clock["now"] = t0
    rows = [{"source": "CoinDesk", "title": "Quant partners with SWIFT on "
             "tokenised deposits", "link": "https://x.test/q",
             "published": (t0 - timedelta(hours=3)).timestamp()}]
    out, rec = Outbox(), Recorder()
    sent = nr.run(gk, ["QNTUSDT", "BTCUSDT"], out, record=rec, now=t0,
                  fetch=no_fetch(rss=lambda: rows))
    assert len(sent) == 1 and sent[0].startswith(
        "🚨 *UNUSUAL MOVE — QNT +"), sent
    assert "news found: Quant partners with SWIFT" in sent[0], sent[0]
    assert nr.SURGE_LINE in sent[0]
    assert any(p.get("kind") == "unusual_move" for _, p in rec.rows)
    SAMPLES["unusual move (QNT replay)"] = sent[0]
    # 24h cooldown: an hour later, no second bell
    clock["now"] = t0 + timedelta(hours=1)
    assert nr.run(gk, ["QNTUSDT", "BTCUSDT"], out, now=clock["now"],
                  fetch=no_fetch()) == []


def _synthetic(now: datetime, last4: float, vol_mult: float, btc4: float):
    """200 1h candles: quiet noise, then the last 4 closed candles move
    `last4` total on `vol_mult`x volume; BTC moves `btc4` in the window."""
    n = 200
    end = int(now.timestamp() // 3600 * 3600)          # forming candle
    t = end - 3600 * np.arange(n - 1, -1, -1)
    rng = np.random.default_rng(3)
    r = rng.normal(0, 0.004, n)
    r[-5:-1] = np.log1p(last4) / 4                     # 4 closed candles
    close = 50 * np.exp(np.cumsum(r))
    vol = np.full(n, 1000.0)
    vol[-5:-1] *= vol_mult
    br = np.zeros(n)
    br[-5:-1] = np.log1p(btc4) / 4
    bclose = 80000 * np.exp(np.cumsum(br))
    mk = lambda c, v: pd.DataFrame(
        {"open": np.r_[c[0], c[:-1]], "high": c * 1.002, "low": c * 0.998,
         "close": c, "volume": v}, index=pd.to_datetime(t, unit="s", utc=True))
    return {"XYZUSDT": mk(close, vol), "BTCUSDT": mk(bclose, vol)}


@test
def surge_synthetic_rules():
    now = dt("2026-09-30 10:07")
    def run_case(last4, vm, b4):
        fr = _synthetic(now, last4, vm, b4)
        return nr.scan_surges(lambda s, i, limit=200: fr[s], ["XYZUSDT"], now)
    d = run_case(-0.12, 6.0, 0.002)
    assert len(d) == 1 and d[0]["direction"] == "down", d
    assert run_case(-0.12, 6.0, -0.03) == []      # BTC not quiet
    assert run_case(0.12, 2.0, 0.0) == []         # volume not unusual
    assert run_case(0.05, 8.0, 0.0) == []         # under +8%
    u = run_case(0.16, 6.0, 0.0)
    assert len(u) == 1 and u[0]["direction"] == "up", u
    m = nr.fmt_surge(u[0], [])
    assert nr.SURGE_BIG_LINE.strip() in m and "no headline found yet" in m, m
    ALL_MSGS.append(m)
    md = nr.fmt_surge(d[0], [])
    assert md.startswith("🚨 *UNUSUAL DROP — XYZ −") and nr.DROP_LINE in md
    SAMPLES["unusual drop (synthetic)"] = md
    ALL_MSGS.append(md)


@test
def morning_digest_once():
    p = fresh_state("digest")
    now = dt("2026-09-30 04:30")
    st = nr._blank_state()
    st["primed"] = ["rss:CoinDesk"]
    st["memory"] = [
        {"ts": now.timestamp() - 3600, "seen": now.timestamp(),
         "src": "CoinDesk", "title": "Quant partners with SWIFT on "
         "tokenised deposits", "link": "", "tickers": ["QNT"], "dir": "bull",
         "kind": "partnership", "big": True, "score": 1.3},
        {"ts": now.timestamp() - 7200, "seen": now.timestamp(),
         "src": "Upbit", "title": "아이콘(ICX) 거래지원 종료 안내 (10/19 15:00)",
         "link": "", "tickers": ["ICX"], "dir": "bear", "kind": "delisting",
         "big": True, "score": 1.5},
        {"ts": now.timestamp() - 90000, "seen": now.timestamp(),
         "src": "old", "title": "too old", "link": "", "tickers": ["BTC"],
         "dir": "bull", "kind": "etf", "big": True, "score": 2},
    ]
    st["surges"] = [{"ts": now.timestamp() - 5000, "base": "QNT",
                     "r4": 0.106, "dir": "up"}]
    p.write_text(json.dumps(st), encoding="utf-8")
    out = Outbox()
    fx = no_fetch(calendar=lambda: CAL_RAW)
    sent = nr.run(quiet_klines({"now": now}), ["QNTUSDT"], out, now=now,
                  fetch=fx)
    assert len(sent) == 1, sent
    m = sent[0]
    assert m.startswith("🗞 *NEWS RADAR — MORNING*"), m
    assert "• 17:30 Core PCE Price Index m/m — f 0.3% · p 0.2%" in m, m
    assert "Federal Funds" not in m                 # that one is tomorrow
    assert "🟢 QNT partnership" in m and "🔴 ICX delisting" in m, m
    assert "too old" not in m and "🚨 QNT +10.6% (4h)" in m, m
    SAMPLES["morning digest"] = m
    assert nr.run(quiet_klines({"now": now}), ["QNTUSDT"], out,
                  now=dt("2026-09-30 05:10"), fetch=fx) == []


@test
def zz_all_messages_clean():
    assert ALL_MSGS, "no messages captured"
    for m in ALL_MSGS:
        assert md_ok(m), f"unbalanced markdown:\n{m}"
        assert len(m) <= nr.MAX_MSG, (len(m), m)
    assert NET_CALLS == [], f"network touched: {NET_CALLS}"


def main() -> int:
    fails = 0
    for fn in TESTS:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception:
            fails += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print("\n---- rendered samples ----")
    for k, v in SAMPLES.items():
        print(f"\n[{k}] ({len(v)} chars)\n{v}")
    print()
    if fails:
        print(f"NEWS RADAR: {fails} FAILED")
        return 1
    print("NEWS RADAR: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
