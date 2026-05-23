"""Crypto Trading Indicator — Streamlit dashboard.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from plotly.subplots import make_subplots

import alerts
import binance_client
import breakout
import btc_outlook
import config
import derivatives
import forecast
import indicators
import lunarcrush
import market_context
import news as news_mod
import news_impact
import oracle
import orderflow
import paper_bot
import sentiment as sentiment_mod
import signals
import social as social_mod
import tv_analysis

st.set_page_config(
    page_title="Crypto Trading Indicator",
    page_icon="📈",
    layout="wide",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, .stApp, [class*="css"], [data-testid="stMarkdownContainer"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* --- canvas: near-black with one restrained accent wash -------------- */
    .stApp {
        background:
          radial-gradient(1100px 520px at 50% -16%,
                          rgba(110,139,255,0.06), transparent),
          #0b0c10;
    }
    [data-testid="stHeader"] { background: transparent; }
    div.block-container { padding-top: 2.4rem; max-width: 1500px; }

    /* --- typography ------------------------------------------------------- */
    h1, h2, h3, h4 { letter-spacing: -0.018em; color: #f1f2f5; }
    h1 { font-weight: 800; }
    h2, h3, h4 { font-weight: 700; }
    h3 {
        margin-top: 0.9rem; font-size: 1.05rem;
        border-left: 2px solid #6e8bff; padding-left: 12px;
    }
    h4 { margin-top: 0.4rem; font-size: 0.98rem; color: #c9cbd4; }

    /* --- metric cards: flat, calm, refined -------------------------------- */
    [data-testid="stMetric"] {
        background: #15161c;
        border: 1px solid rgba(255,255,255,0.055);
        border-radius: 12px;
        padding: 14px 18px;
        transition: border-color .18s ease;
    }
    [data-testid="stMetric"]:hover {
        border-color: rgba(110,139,255,0.40);
    }
    [data-testid="stMetricValue"] {
        font-size: 1.5rem; font-weight: 700; color: #f4f5f7;
    }
    [data-testid="stMetricLabel"] {
        opacity: 0.55; text-transform: uppercase;
        font-size: 0.67rem; letter-spacing: 0.08em; font-weight: 600;
    }
    [data-testid="stMetricDelta"] { font-size: 0.78rem; }

    /* --- panels ----------------------------------------------------------- */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: #121319;
        border-radius: 14px;
    }

    /* --- tabs ------------------------------------------------------------- */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        gap: 4px; border-bottom: 1px solid rgba(255,255,255,0.06);
    }
    [data-testid="stTabs"] [data-baseweb="tab"] {
        border-radius: 9px 9px 0 0; padding: 9px 20px;
    }
    [data-testid="stTabs"] [data-baseweb="tab"] p {
        font-weight: 600; font-size: 0.92rem;
    }
    [data-testid="stTabs"] [aria-selected="true"] {
        background: rgba(110,139,255,0.10);
        border-bottom: 2px solid #6e8bff;
    }

    /* --- sidebar ---------------------------------------------------------- */
    [data-testid="stSidebar"] {
        background: #0d0e13;
        border-right: 1px solid rgba(255,255,255,0.05);
    }

    /* --- buttons ---------------------------------------------------------- */
    .stButton button {
        border-radius: 9px; font-weight: 600;
        border: 1px solid rgba(255,255,255,0.09);
        transition: all .15s ease;
    }
    .stButton button:hover {
        border-color: #6e8bff; color: #6e8bff;
        background: rgba(110,139,255,0.07);
    }

    /* --- expanders, dataframes ------------------------------------------- */
    [data-testid="stExpander"] {
        border: 1px solid rgba(255,255,255,0.055);
        border-radius: 11px; background: #121319;
    }
    [data-testid="stDataFrame"] {
        border-radius: 11px; border: 1px solid rgba(255,255,255,0.055);
    }

    /* --- progress accent -------------------------------------------------- */
    [data-testid="stProgress"] div[role="progressbar"] > div {
        background: #6e8bff;
    }

    hr { border-color: rgba(255,255,255,0.06); opacity: 1; margin: 1rem 0; }

    /* --- scrollbars ------------------------------------------------------- */
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-thumb { background: #262833; border-radius: 6px; }
    ::-webkit-scrollbar-thumb:hover { background: #343748; }
    ::-webkit-scrollbar-track { background: transparent; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Paper trading bot state file (lives next to app.py, gitignored) ------
PAPER_BOT_FILE = Path(__file__).resolve().parent / ".paper_bot.json"


# --- Colour palette for signal labels --------------------------------------
LABEL_COLORS = {
    "STRONG LONG": "#0b8a3e", "LONG": "#34c759",
    "STRONG BUY": "#0b8a3e", "BUY": "#34c759",
    "NEUTRAL": "#8e8e93",
    "SHORT": "#ff6b5b", "STRONG SHORT": "#c1121f",
    "SELL": "#ff6b5b", "STRONG SELL": "#c1121f",
}
MOOD_COLORS = {"Bullish": "#34c759", "Bearish": "#ff6b5b", "Neutral": "#8e8e93"}


# --- Cached data services --------------------------------------------------
@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def load_top_symbols(n: int) -> pd.DataFrame:
    return binance_client.get_top_symbols(n)


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def load_klines(symbol: str, interval: str) -> pd.DataFrame:
    return binance_client.get_klines(symbol, interval)


def _scan_one(symbol: str, interval: str, funding: float | None = None,
              social: dict | None = None,
              mode: str = "futures") -> dict | None:
    try:
        df = binance_client.get_klines(symbol, interval)
        deriv = {"funding": funding} if funding is not None else None
        result = signals.analyze(df, deriv, social, mode)
        result["symbol"] = symbol
        result["funding"] = funding
        return result
    except Exception:  # skip a symbol that fails rather than break the scan
        return None


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def scan_market(symbols: tuple[str, ...], interval: str,
                mode: str = "futures") -> pd.DataFrame:
    try:
        funding = derivatives.all_funding_rates()
    except Exception:
        funding = {}
    # {} when LunarCrush is not configured; one shared list fetch.
    social_map = lunarcrush.top_coins(
        load_lunarcrush_list() if lunarcrush.is_configured() else [])
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=config.SCAN_WORKERS) as pool:
        for res in pool.map(
                lambda s: _scan_one(s, interval, funding.get(s),
                                    social_map.get(s.replace("USDT", "")),
                                    mode),
                symbols):
            if res:
                rows.append(res)
    return pd.DataFrame(rows)


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def forecast_market(symbols: tuple[str, ...]) -> pd.DataFrame:
    """Per-coin multi-horizon forecast — blends the per-timeframe technical
    read with the comprehensive Breakout Radar read (news catalysts, the
    macro / geopolitical backdrop, volume ignition, social heat and funding).
    See forecast.py."""
    tfs = [tf for tf, _ in forecast.HORIZONS]
    try:
        radar_df, backdrop = scan_breakouts(symbols, "imminent")
        radar_by_sym = ({r["symbol"]: r.to_dict()
                         for _, r in radar_df.iterrows()}
                        if radar_df is not None and not radar_df.empty
                        else {})
    except Exception:
        radar_by_sym, backdrop = {}, {}

    def one(sym: str):
        try:
            per_tf = {tf: signals.analyze(binance_client.get_klines(sym, tf))
                      for tf in tfs}
            pred = forecast.predict_one(
                per_tf, radar_by_sym.get(sym), backdrop)
            pred["symbol"] = sym
            pred["base"] = sym[:-4] if sym.endswith("USDT") else sym
            pred["price"] = per_tf[tfs[0]]["price"]
            return pred
        except Exception:  # skip a coin that fails rather than break the scan
            return None

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=config.SCAN_WORKERS) as pool:
        for res in pool.map(one, symbols):
            if res:
                rows.append(res)
    return pd.DataFrame(rows)


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def btc_outlook_now(btc_change_24h: float, alt_median_24h: float) -> dict:
    """Build the BTC 24h Outlook (see btc_outlook.py). The caller supplies
    BTC's own 24h % change and the median alt 24h % so the divergence
    detector has the latest tape; everything else is fetched fresh here."""
    try:
        btc_4h = signals.analyze(load_klines("BTCUSDT", "4h"))
    except Exception:
        btc_4h = None
    try:
        btc_1d = signals.analyze(load_klines("BTCUSDT", "1d"))
    except Exception:
        btc_1d = None
    try:
        btc_1w = signals.analyze(load_klines("BTCUSDT", "1w"))
    except Exception:
        btc_1w = None
    try:
        deriv = load_derivatives("BTCUSDT", "4h")
    except Exception:
        deriv = None
    try:
        fg = load_fear_greed().get("value")
    except Exception:
        fg = None
    try:
        mcap_change = load_global_market().get("market_cap_change_24h")
    except Exception:
        mcap_change = None

    # News fusion — BTC-specific + macro/political + general crypto mood.
    news_payload = None
    try:
        nd = load_news()
        if nd is not None and not nd.empty:
            btc_mask = nd["title"].str.contains(
                r"\b(?:bitcoin|btc)\b", case=False, na=False, regex=True)
            btc_news = nd[btc_mask]
            news_payload = {
                "btc": {
                    "count": int(len(btc_news)),
                    "sentiment": (float(btc_news["sentiment"].mean())
                                  if not btc_news.empty else 0.0),
                },
                "macro": news_mod.category_mood(nd, "Macro / Politics"),
                "crypto": news_mod.category_mood(nd, "Crypto"),
            }
    except Exception:
        news_payload = None

    return btc_outlook.compute(
        btc_4h, btc_1d, deriv, fg, mcap_change,
        btc_change_24h, alt_median_24h,
        btc_1w=btc_1w, news=news_payload)


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def scan_breakouts(symbols: tuple[str, ...],
                   horizon: str = "imminent") -> tuple[pd.DataFrame, dict]:
    """Scan symbols for blowout candidates on a horizon ("imminent" or "24h"),
    wiring in funding, social, news and the broad-market backdrop. Returns
    (radar DataFrame, backdrop dict)."""
    try:
        funding = derivatives.all_funding_rates()
    except Exception:
        funding = {}
    lc_rows: list = []
    if lunarcrush.is_configured():
        try:
            lc_rows = load_lunarcrush_list()
        except Exception:
            lc_rows = []
    try:
        news_df = load_news()
    except Exception:
        news_df = pd.DataFrame()
    try:
        fg_val = load_fear_greed().get("value")
    except Exception:
        fg_val = None
    try:
        mcap_change = load_global_market().get("market_cap_change_24h")
    except Exception:
        mcap_change = None
    return breakout.scan(list(symbols), funding, lc_rows, news_df,
                         fg_val, mcap_change, horizon)


@st.cache_data(ttl=config.NEWS_CACHE_TTL, show_spinner=False)
def load_news() -> pd.DataFrame:
    return news_mod.fetch_news()


@st.cache_data(ttl=config.NEWS_CACHE_TTL, show_spinner=False)
def load_impactful_news() -> list[dict]:
    """The headlines that are MOVING the tape right now — used by the BTC
    banner's 'Why this is happening' panel and the live news notifications."""
    try:
        return news_impact.detect_impactful(load_news())
    except Exception:
        return []


@st.cache_data(ttl=config.NEWS_CACHE_TTL, show_spinner=False)
def load_social() -> pd.DataFrame:
    return social_mod.fetch_social()


@st.cache_data(ttl=config.NEWS_CACHE_TTL, show_spinner=False)
def load_fear_greed() -> dict:
    return sentiment_mod.fear_greed()


@st.cache_data(ttl=config.NEWS_CACHE_TTL, show_spinner=False)
def load_global_market() -> dict:
    return market_context.global_market()


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def load_derivatives(symbol: str, interval: str) -> dict | None:
    return derivatives.get_derivatives(symbol, interval)


@st.cache_data(ttl=5, show_spinner=False)
def live_price(symbol: str) -> float | None:
    """Fast 5-second-cached live price for one symbol — used by the Paper
    Trader so open-position cards reflect near-real-time price between
    full scanner refreshes. Falls back to None if the endpoint fails."""
    return binance_client.get_ticker_price(symbol)


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def load_tv_ratings(symbols: tuple[str, ...], interval: str) -> dict:
    return tv_analysis.get_ratings(list(symbols), interval)


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def load_tv_rating(symbol: str, interval: str) -> dict | None:
    return tv_analysis.get_rating(symbol, interval)


@st.cache_data(ttl=config.ORDERFLOW_CACHE_TTL, show_spinner=False)
def load_orderflow(symbol: str) -> dict:
    return orderflow.snapshot(symbol)


@st.cache_data(ttl=config.NEWS_CACHE_TTL, show_spinner=False)
def load_lunarcrush_list() -> list:
    return lunarcrush.coin_list()


@st.cache_data(ttl=config.NEWS_CACHE_TTL, show_spinner=False)
def load_lunarcrush_coin(base_asset: str) -> dict | None:
    return lunarcrush.coin_metrics(base_asset, load_lunarcrush_list())


@st.cache_data(ttl=config.NEWS_CACHE_TTL, show_spinner=False)
def load_lunarcrush_top() -> dict:
    return lunarcrush.top_coins(load_lunarcrush_list())


@st.cache_data(ttl=config.NEWS_CACHE_TTL, show_spinner=False)
def load_crypto_social() -> dict | None:
    return lunarcrush.crypto_social(load_lunarcrush_list())


@st.cache_data(ttl=config.NEWS_CACHE_TTL, show_spinner=False)
def load_stock_social() -> dict | None:
    return lunarcrush.stock_social()


# --- Formatting helpers ----------------------------------------------------
def fmt_price(value: float) -> str:
    if value is None:
        return "—"
    if value >= 100:
        return f"${value:,.2f}"
    if value >= 1:
        return f"${value:,.4f}"
    return f"${value:.8f}".rstrip("0").rstrip(".")


def fmt_volume(value: float) -> str:
    """Human-readable money amount — billions / millions / thousands.

    Avoids the '$0.0B' problem where dividing every coin by a billion hides
    anything that does not trade in the billions.
    """
    if value is None or value != value:   # None or NaN
        return "—"
    if value >= 1e9:
        return f"${value / 1e9:.2f}B"
    if value >= 1e6:
        return f"${value / 1e6:.1f}M"
    if value >= 1e3:
        return f"${value / 1e3:.0f}K"
    return f"${value:,.0f}"


def md_safe(text: str) -> str:
    """Escape `$` so Streamlit markdown does not parse price text as LaTeX."""
    return str(text).replace("$", "\\$")


def label_badge(label: str) -> str:
    color = LABEL_COLORS.get(label, "#8e8e93")
    return (f"<span style='background:{color};color:#fff;padding:3px 12px;"
            f"border-radius:7px;font-weight:700;font-size:0.78rem;"
            f"letter-spacing:0.04em;display:inline-block'>{label}</span>")


def tradingview_chart(symbol: str, interval: str, height: int = 540) -> None:
    """Embed TradingView's interactive Advanced Chart widget for a symbol."""
    tv_interval = {"15m": "15", "1h": "60", "4h": "240",
                   "1d": "D"}.get(interval, "240")
    components.html(
        f"""
        <div class="tradingview-widget-container" style="height:{height}px">
          <div id="tv_chart" style="height:100%;width:100%"></div>
          <script src="https://s3.tradingview.com/tv.js"></script>
          <script>
          new TradingView.widget({{
            "autosize": true,
            "symbol": "BINANCE:{symbol}",
            "interval": "{tv_interval}",
            "timezone": "Etc/UTC",
            "theme": "dark",
            "style": "1",
            "locale": "en",
            "hide_side_toolbar": false,
            "allow_symbol_change": true,
            "studies": ["RSI@tv-basicstudies", "MACD@tv-basicstudies"],
            "container_id": "tv_chart"
          }});
          </script>
        </div>
        """,
        height=height + 12,
    )


def style_scan(df: pd.DataFrame):
    def color_label(val):
        return f"background-color:{LABEL_COLORS.get(val, '#8e8e93')};color:white;"

    def color_change(val):
        try:
            return "color:#34c759;" if float(val) >= 0 else "color:#ff6b5b;"
        except (TypeError, ValueError):
            return ""

    return (df.style
            .map(color_label, subset=["Bias", "Action", "TradingView"])
            .map(color_change, subset=["24h %"]))


def confidence_gauge(value: float, suffix: str = "%"):
    """Plotly gauge for a 0-100 score (confidence, Galaxy Score, etc.)."""
    color = ("#0b8a3e" if value >= 70
             else "#f5a623" if value >= 45 else "#ff6b5b")
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"suffix": suffix, "font": {"size": 30}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#888"},
            "bar": {"color": color, "thickness": 0.32},
            "borderwidth": 0,
            "steps": [
                {"range": [0, 45], "color": "rgba(255,107,91,0.18)"},
                {"range": [45, 70], "color": "rgba(245,166,35,0.18)"},
                {"range": [70, 100], "color": "rgba(11,138,62,0.22)"},
            ],
        }))
    fig.update_layout(height=200, margin=dict(l=26, r=26, t=14, b=8),
                      template="plotly_dark")
    return fig


def pressure_bar(buy_pct: float, height: int = 30) -> str:
    """HTML horizontal buy-vs-sell pressure bar."""
    buy = max(0.0, min(100.0, buy_pct))
    sell = 100 - buy
    return (
        f"<div style='display:flex;height:{height}px;border-radius:7px;"
        f"overflow:hidden;font-weight:700;font-size:0.82rem'>"
        f"<div style='width:{buy}%;background:#34c759;color:#04331a;"
        f"display:flex;align-items:center;justify-content:center'>"
        f"BUY {buy:.0f}%</div>"
        f"<div style='width:{sell}%;background:#ff6b5b;color:#3d0a05;"
        f"display:flex;align-items:center;justify-content:center'>"
        f"SELL {sell:.0f}%</div></div>")


def _analysis_sections(agg: dict, detail: dict, per_tf: dict,
                       tv_rating: dict | None, flow_snap: dict,
                       lc_metrics: dict | None) -> list[tuple[str, str]]:
    """Build the detailed written analysis as (heading, prose) sections."""
    secs: list[tuple[str, str]] = []
    bd = {b["indicator"]: b for b in detail["breakdown"]}

    t = (f"Directional bias is {agg['bias_label']} "
         f"(score {agg['bias_score']:+.0f}). {detail.get('trend', '')}. ")
    adx, regime = detail.get("adx"), detail["regime"]
    if adx is not None:
        if regime == "Trending":
            t += (f"ADX at {adx:.0f} confirms a genuine trend — "
                  f"trend-following signals are reliable and targets can be "
                  f"held toward the second take-profit.")
        elif regime == "Ranging":
            t += (f"ADX at {adx:.0f} is low: the market is ranging and "
                  f"choppy, so favour mean-reversion, bank profit earlier "
                  f"and distrust breakouts.")
        else:
            t += (f"ADX at {adx:.0f} shows a developing — not yet "
                  f"established — trend; wait for confirmation.")
    secs.append(("Trend & market structure", t))

    r = detail["rsi"]
    m = (f"Entry timing reads {agg['action_label']} "
         f"(score {agg['action_score']:+.0f}). RSI at {r:.0f} is "
         + ("overbought — a pullback is increasingly likely" if r >= 70
            else "oversold — a bounce is increasingly likely" if r <= 30
            else "in positive-momentum territory" if r >= 55
            else "in weak-momentum territory" if r <= 45 else "neutral")
         + ". ")
    for ind in ("MACD", "Stochastic", "Volume"):
        if ind in bd:
            m += bd[ind]["detail"] + ". "
    secs.append(("Momentum & entry timing", m))

    flow = flow_snap.get("flow")
    if flow:
        o = (f"Right now {flow['pressure'].lower()} — {flow['buy_pct']:.0f}% "
             f"of the last {flow['trades']:,} trades by value were aggressive "
             f"buys (${flow['buy_quote']:,.0f} bought vs "
             f"${flow['sell_quote']:,.0f} sold). ")
        book = flow_snap.get("book")
        if book:
            o += book["verdict"] + "."
        secs.append(("Live order flow", o))

    dv = detail.get("derivatives")
    if dv and dv.get("funding") is not None:
        f = dv["funding"]
        d = (f"Perpetual funding is {f * 100:+.3f}% — "
             + ("longs are crowded and over-paying, a contrarian warning"
                if f >= config.FUNDING_HOT
                else "shorts are crowded — squeeze fuel for a move higher"
                if f <= -config.FUNDING_HOT
                else "balanced, with no leverage extreme") + ". ")
        if dv.get("long_short_ratio") is not None:
            d += f"Trader long/short ratio is {dv['long_short_ratio']:.2f}. "
        if dv.get("oi_change_pct") is not None:
            d += f"Open interest has moved {dv['oi_change_pct']:+.1f}%."
        secs.append(("Derivatives & positioning", d))

    if lc_metrics and lc_metrics.get("sentiment") is not None:
        sv = lc_metrics["sentiment"]
        s = (f"LunarCrush social: Galaxy Score "
             f"{lc_metrics.get('galaxy_score', '—')}, sentiment {sv:.0f}% "
             f"positive")
        if lc_metrics.get("alt_rank") is not None:
            s += f", AltRank #{lc_metrics['alt_rank']:,.0f}"
        s += (". Social attention is "
              + ("supportive of the move." if sv >= 55
                 else "weak or negative — a headwind." if sv <= 45
                 else "neutral."))
        secs.append(("Social sentiment", s))

    if tv_rating:
        secs.append((
            "TradingView cross-check",
            f"TradingView's independent engine rates this "
            f"{tv_rating['recommendation']} — {tv_rating['buy']} buy, "
            f"{tv_rating['neutral']} neutral and {tv_rating['sell']} sell "
            f"indicators (oscillators {tv_rating['oscillators']}, moving "
            f"averages {tv_rating['moving_averages']})."))

    longs = sum(1 for a in per_tf.values() if a["bias_score"] > 5)
    shorts = sum(1 for a in per_tf.values() if a["bias_score"] < -5)
    tf_list = ", ".join(f"{tf} {a['bias_label']}"
                        for tf, a in per_tf.items())
    aligned = longs == len(per_tf) or shorts == len(per_tf)
    secs.append((
        "Across timeframes",
        f"{longs} of {len(per_tf)} timeframes lean long and {shorts} lean "
        f"short ({tf_list}). " + (
            "All timeframes agree — this is a higher-conviction setup."
            if aligned else
            "Timeframes disagree — lower conviction; trade smaller or wait "
            "for them to align.")))
    return secs


def _action_steps(plan: dict | None, agg: dict,
                  nearest_sup: float | None,
                  nearest_res: float | None) -> list[str]:
    """Concrete, numbered trading actions for the current setup."""
    if not plan:
        steps = [
            "The composite signal is NEUTRAL — there is no high-probability "
            "trade right now, so do not force one.",
            "Wait for the directional bias and entry timing to agree — both "
            "clearly bullish, or both clearly bearish.",
        ]
        if nearest_sup:
            steps.append(f"Watch support at {fmt_price(nearest_sup)} — a "
                         f"clean bounce there could set up a long.")
        if nearest_res:
            steps.append(f"Watch resistance at {fmt_price(nearest_res)} — a "
                         f"clear rejection there could set up a short.")
        return steps

    side = plan["side"]
    other = "short" if side == "LONG" else "long"
    steps = [
        f"Trade {side} only — ignore {other} setups while this bias holds.",
        f"Place a limit {side} order in the entry zone "
        f"{fmt_price(plan['entry_low'])} – {fmt_price(plan['entry_high'])}; "
        f"do not chase price outside that zone.",
    ]
    if side == "LONG" and nearest_sup:
        steps.append(f"Best entries are near support {fmt_price(nearest_sup)} "
                     f"— a pullback there gives a tighter, safer stop.")
    if side == "SHORT" and nearest_res:
        steps.append(f"Best entries are near resistance "
                     f"{fmt_price(nearest_res)}.")
    steps += [
        f"As soon as you are filled, set a stop-loss at "
        f"{fmt_price(plan['stop_loss'])} ({plan['risk_pct']:.2f}% away, placed "
        f"on {plan.get('stop_basis', 'volatility')}). A candle close beyond it "
        f"invalidates the trade — exit, no exceptions.",
        f"Scale out: ~40% at Target 1 {fmt_price(plan['take_profit'])} "
        f"({plan['risk_reward']:.1f}R), ~35% at Target 2 "
        f"{fmt_price(plan['take_profit_2'])} ({plan['risk_reward_2']:.1f}R), "
        f"the rest at Target 3 {fmt_price(plan['take_profit_3'])} "
        f"({plan['risk_reward_3']:.1f}R). Each target is a real swing level.",
        "Once Target 1 fills, move the stop to your entry price "
        "(break-even) — the rest of the trade is then risk-free.",
    ]
    if plan.get("mode") == "spot":
        steps.append(
            f"Spot sizing — buy ≈{plan.get('position_pct', 0):.0f}% of your "
            f"account capital so a stop-out costs only "
            f"~{signals.RISK_PER_TRADE_PCT:g}% of the account (no leverage).")
    else:
        steps.append(
            f"Futures sizing — ≈{plan.get('leverage', 1):g}× leverage on a "
            f"≈{plan.get('position_pct', 0):.0f}% margin allocation; a stop-out "
            f"then costs ~{signals.RISK_PER_TRADE_PCT:g}% of the account.")
    return steps


def _trade_decision(row, timeframe: str) -> dict:
    """Derive a buy/hold/sell decision, hold horizon and entry timing."""
    score = row["score"]
    plan = row.get("trade_plan")
    regime = row.get("regime", "Unknown")

    if score >= 40:
        decision, color = "BUY", "#2ed47a"
    elif score >= 15:
        decision, color = "ACCUMULATE", "#7bd88f"
    elif score > -15:
        decision, color = "HOLD / WAIT", "#c9a227"
    elif score > -40:
        decision, color = "REDUCE", "#ff8a7a"
    else:
        decision, color = "SELL / AVOID", "#ff5c5c"

    base = {"15m": "a few hours (intraday)", "1h": "1–3 days",
            "4h": "several days to ~2 weeks",
            "1d": "several weeks to months"}.get(timeframe, "a few days")
    if regime == "Trending":
        hold = f"{base} — trend intact; hold while the structure holds"
    elif regime == "Ranging":
        hold = f"shorter than {base} — ranging market, bank profit quickly"
    else:
        hold = base

    if decision in ("BUY", "ACCUMULATE") and isinstance(plan, dict):
        when = (f"Enter on a pullback into {fmt_price(plan['entry_low'])}–"
                f"{fmt_price(plan['entry_high'])}, stop "
                f"{fmt_price(plan['stop_loss'])}.")
    elif decision == "BUY":
        when = "Momentum is live — enter now or on the first shallow dip."
    elif decision == "HOLD / WAIT":
        when = "No clean setup — wait for a stronger signal before buying."
    else:
        when = "Avoid new longs; trim or exit existing exposure."

    if score >= 15 and isinstance(plan, dict):
        outlook = (f"Bullish bias — scope toward "
                   f"{fmt_price(plan['take_profit'])} while price holds "
                   f"above {fmt_price(plan['stop_loss'])}.")
    elif score <= -15 and isinstance(plan, dict):
        outlook = (f"Bearish bias — downside risk toward "
                   f"{fmt_price(plan['take_profit'])} while price stays "
                   f"below {fmt_price(plan['stop_loss'])}.")
    else:
        outlook = ("Rangebound / no directional edge — wait for a breakout "
                   "or a stronger signal before acting.")
    return {"decision": decision, "color": color, "hold": hold,
            "when": when, "outlook": outlook}


def render_action_plan(plan: dict, regime: str, confidence: int,
                       symbol: str, agg: dict,
                       nearest_sup: float | None,
                       nearest_res: float | None) -> None:
    """Render the prominent trade action-plan card."""
    side = plan["side"]
    accent = "#34c759" if side == "LONG" else "#ff6b5b"
    coin = symbol.replace("USDT", "")
    mode = plan.get("mode", "futures")
    mat = plan.get("maturity") or {}
    mat_color = {"EARLY": "#34c759", "RE-RUN": "#6e8bff",
                 "EXTENDED": "#ff8a3d"}.get(mat.get("stage"), "#8e8e93")
    mat_label = {"EARLY": "EARLY — room to run",
                 "RE-RUN": "RE-RUN SETUP — second-leg entry",
                 "EXTENDED": "EXTENDED — move already ran"}.get(
                     mat.get("stage"), "MOVE STAGE UNKNOWN")
    risk_unit = signals.RISK_PER_TRADE_PCT
    with st.container(border=True):
        st.markdown(
            f"<h4 style='margin:0 0 6px 0'>📋 Action Plan &nbsp;"
            f"<span style='color:{accent}'>{side} {coin}</span>"
            f"<span style='float:right;color:#888;font-size:0.8rem'>"
            f"{mode.upper()} · regime: {regime}</span></h4>",
            unsafe_allow_html=True)
        if mat:
            st.markdown(
                f"<div style='background:{mat_color}1f;border-left:3px solid "
                f"{mat_color};padding:6px 11px;border-radius:4px;"
                f"margin:2px 0 12px 0'>"
                f"<b style='color:{mat_color}'>{mat_label}</b>"
                f"<span style='color:#888'> · {mat.get('confidence', 0)}% "
                f"confidence</span><br><span style='font-size:0.85rem;"
                f"color:#bbb'>{mat.get('note', '')}</span></div>",
                unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Entry zone", fmt_price(plan["entry"]),
                  f"{fmt_price(plan['entry_low'])} – "
                  f"{fmt_price(plan['entry_high'])}")
        c2.metric("Stop loss", fmt_price(plan["stop_loss"]),
                  f"-{plan['risk_pct']:.2f}% · {plan.get('stop_basis', '')}")
        c3.metric("Target 1", fmt_price(plan["take_profit"]),
                  f"{plan['risk_reward']:.1f}R")
        c4.metric("Target 2", fmt_price(plan["take_profit_2"]),
                  f"{plan['risk_reward_2']:.1f}R")
        t1, t2 = st.columns([1, 3])
        t1.metric("Target 3", fmt_price(plan["take_profit_3"]),
                  f"{plan['risk_reward_3']:.1f}R")
        pos = plan.get("position_pct", 0.0)
        lev = plan.get("leverage", 1.0)
        if mode == "spot":
            t2.markdown(
                f"**Position sizing** — risking **{risk_unit:g}%** of your "
                f"account: with the stop **{plan['risk_pct']:.2f}%** away, buy "
                f"**≈{pos:.0f}%** of account capital (spot, no leverage). "
                f"R:R is built from real swing structure, so a wider stop "
                f"gives a smaller position — that is why every coin differs.")
        else:
            t2.markdown(
                f"**Position sizing** — risking **{risk_unit:g}%** of account: "
                f"suggested **{lev:g}× leverage** on a margin allocation of "
                f"**≈{pos:.0f}%** of account. Leverage scales with signal "
                f"confidence and is capped on volatile (wide-stop) coins, so "
                f"each coin gets its own size — never a copy-paste.")
        st.caption(plan["regime_fit"])
        st.progress(int(confidence), text=f"Signal confidence · {confidence}%")

        market = ("tradeable on Spot or Futures" if side == "LONG"
                  else "tradeable on Futures / Margin only — you cannot "
                       "short on a spot account")
        st.caption(f"This is a {side} setup, {market}.")
        st.markdown("**✅ Trading actions — follow in order**")
        for _i, _step in enumerate(
                _action_steps(plan, agg, nearest_sup, nearest_res), 1):
            st.markdown(f"{_i}. {_step}")
        st.caption("Educational walkthrough — not financial advice. Price "
                   "can gap straight through stops in fast markets.")


def render_orderflow(snap: dict) -> None:
    """Render the live order-flow panel (recent trades + book depth)."""
    flow, book = snap.get("flow"), snap.get("book")
    with st.container(border=True):
        st.markdown("#### 🟢🔴 Live Order Flow")
        if flow:
            st.markdown(pressure_bar(flow["buy_pct"]), unsafe_allow_html=True)
            f1, f2, f3 = st.columns(3)
            f1.metric("Aggressive buys", f"${flow['buy_quote']:,.0f}")
            f2.metric("Aggressive sells", f"${flow['sell_quote']:,.0f}")
            f3.metric("Net flow", f"${flow['net_quote']:,.0f}",
                      flow["pressure"])
            st.caption(f"Last {flow['trades']:,} executed trades over "
                       f"~{flow['window_seconds'] / 60:.1f} min · "
                       f"{flow['pressure']}.")
            if flow["large_trades"]:
                lt = pd.DataFrame([
                    {"Side": t["side"], "Price": fmt_price(t["price"]),
                     "Size (USDT)": f"${t['quote']:,.0f}",
                     "Time": t["time"].strftime("%H:%M:%S")}
                    for t in flow["large_trades"]])
                st.dataframe(
                    lt.style.map(
                        lambda v: ("color:#34c759;font-weight:700;"
                                   if v == "BUY" else
                                   "color:#ff6b5b;font-weight:700;"
                                   if v == "SELL" else ""),
                        subset=["Side"]),
                    use_container_width=True, hide_index=True)
        else:
            st.caption("Live trade feed unavailable for this symbol.")
        if book:
            st.markdown(f"**Order book** · ±{config.DEPTH_BAND_PCT:.1f}% band")
            b1, b2, b3 = st.columns(3)
            b1.metric("Bid depth", f"${book['bid_quote']:,.0f}")
            b2.metric("Ask depth", f"${book['ask_quote']:,.0f}")
            b3.metric("Book imbalance", f"{book['imbalance_pct']:.0f}% bid")
            sup, res = book.get("support"), book.get("resistance")
            if sup and res:
                st.caption(
                    f"{book['verdict']} · nearest support wall "
                    f"{fmt_price(sup['price'])} (${sup['quote']:,.0f}) · "
                    f"resistance wall {fmt_price(res['price'])} "
                    f"(${res['quote']:,.0f}).")


def render_history(symbol: str, df1d, ticker_row, detail: dict,
                   levels: tuple) -> None:
    """Render the price-history, key-levels and trend-context panel."""
    with st.container(border=True):
        st.markdown("#### 📜 Price History & Key Levels")
        price = detail["price"]
        cols = st.columns(4)
        if ticker_row is not None:
            hi, lo = ticker_row["highPrice"], ticker_row["lowPrice"]
            pos = (price - lo) / (hi - lo) * 100 if hi > lo else 50.0
            cols[0].metric("24h change",
                           f"{ticker_row['priceChangePercent']:+.2f}%")
            cols[1].metric("24h range position", f"{pos:.0f}%",
                           help="0% = at the 24h low, 100% = at the 24h high")
        if df1d is not None and len(df1d) >= 30:
            d30 = df1d.tail(30)
            h30, l30 = d30["high"].max(), d30["low"].min()
            pos30 = (price - l30) / (h30 - l30) * 100 if h30 > l30 else 50.0
            cols[2].metric("30d range position", f"{pos30:.0f}%")
        if df1d is not None and len(df1d) >= 90:
            perf90 = (price / df1d["close"].iloc[-90] - 1) * 100
            cols[3].metric("90d performance", f"{perf90:+.1f}%")

        nearest_sup, nearest_res = levels
        lv = st.columns(2)
        lv[0].metric(
            "Nearest support",
            fmt_price(nearest_sup) if nearest_sup else "—",
            f"{(nearest_sup / price - 1) * 100:+.2f}% away"
            if nearest_sup else None, delta_color="off")
        lv[1].metric(
            "Nearest resistance",
            fmt_price(nearest_res) if nearest_res else "—",
            f"{(nearest_res / price - 1) * 100:+.2f}% away"
            if nearest_res else None, delta_color="off")

        bits = [f"Market regime **{detail['regime']}**"]
        if detail.get("adx") is not None:
            bits.append(f"ADX {detail['adx']} (+DI {detail['plus_di']} / "
                        f"-DI {detail['minus_di']})")
        if detail.get("vwap"):
            bits.append("price "
                        + ("above" if price >= detail["vwap"] else "below")
                        + " VWAP")
        if df1d is not None and not pd.isna(df1d["ema_trend"].iloc[-1]):
            above = price >= df1d["ema_trend"].iloc[-1]
            bits.append(("above" if above else "below")
                        + " the 200-day EMA — long-term "
                        + ("uptrend" if above else "downtrend"))
        if detail.get("atr_pct"):
            bits.append(f"volatility {detail['atr_pct']}% ATR")
        st.caption(" · ".join(bits))


def render_lunarcrush(metrics: dict | None, base_asset: str) -> None:
    """Render the LunarCrush social-intelligence panel."""
    with st.container(border=True):
        st.markdown("#### 🌙 LunarCrush Social Intelligence")
        if metrics is None:
            if not lunarcrush.is_configured():
                st.info(
                    "LunarCrush is not configured. It is a paid API that "
                    "aggregates X/Twitter and other social platforms into "
                    "Galaxy Score, AltRank and sentiment. To enable it: "
                    "subscribe at lunarcrush.com, copy `.env.example` to "
                    "`.env`, add your `LUNARCRUSH_API_KEY`, then restart.")
            else:
                st.caption(
                    f"No LunarCrush data for {base_asset}. Your API key is "
                    f"loaded, but the LunarCrush API needs an **active "
                    f"Individual (or higher) subscription** — a free account "
                    f"returns no data. Activate a plan at lunarcrush.com.")
            return

        gs = metrics.get("galaxy_score")
        col1, col2 = st.columns([1, 2])
        with col1:
            if gs is not None:
                st.plotly_chart(
                    confidence_gauge(float(gs), suffix=""),
                    use_container_width=True,
                    config={"displayModeBar": False})
                st.caption("Galaxy Score — combined social + market "
                           "health (0-100)")
            else:
                st.caption("Galaxy Score unavailable")
        with col2:
            mc = st.columns(2)
            ar = metrics.get("alt_rank")
            ar_prev = metrics.get("alt_rank_prev")
            if ar is not None:
                delta = (f"{ar_prev - ar:+.0f} vs prev"
                         if ar_prev is not None else None)
                mc[0].metric(
                    "AltRank", f"#{ar:,.0f}", delta,
                    help="Combined price + social rank — lower is better")
            sent = metrics.get("sentiment")
            if sent is not None:
                mc[1].metric("Social sentiment", f"{sent:.0f}%",
                             help="Share of social posts that are positive")
            sd = metrics.get("social_dominance")
            if sd is not None:
                mc[0].metric("Social dominance", f"{sd:.2f}%")
            iv = metrics.get("interactions_24h")
            if iv is not None:
                mc[1].metric("Interactions 24h", f"{iv:,.0f}")
        st.caption("Source: LunarCrush — social data aggregated from "
                   "X/Twitter and other platforms.")


def render_bottom_line(agg: dict, detail: dict, per_tf: dict,
                       tv_rating: dict | None, flow_snap: dict,
                       lc_metrics: dict | None) -> None:
    """Synthesise every data source into one expert bottom-line verdict."""
    reads: list[tuple[str, str, str]] = []
    reads.append((
        "Trend & momentum",
        "bull" if agg["bias_score"] > 8
        else "bear" if agg["bias_score"] < -8 else "neutral",
        f"{agg['bias_label']} bias · {agg['action_label']} timing"))
    if tv_rating:
        reads.append((
            "TradingView", "bull" if tv_rating["score"] > 10
            else "bear" if tv_rating["score"] < -10 else "neutral",
            tv_rating["recommendation"]))
    flow = flow_snap.get("flow")
    if flow:
        reads.append((
            "Live order flow", "bull" if flow["buy_pct"] >= 55
            else "bear" if flow["buy_pct"] <= 45 else "neutral",
            f"{flow['buy_pct']:.0f}% aggressive buys"))
    dv = detail.get("derivatives")
    if dv and dv.get("long_short_ratio") is not None:
        ls = dv["long_short_ratio"]
        reads.append((
            "Derivatives positioning",
            "bear" if ls >= 2.2 else "bull" if ls <= 0.9 else "neutral",
            f"long/short ratio {ls:.2f}"))
    if lc_metrics and lc_metrics.get("sentiment") is not None:
        s = lc_metrics["sentiment"]
        reads.append((
            "Social (LunarCrush)", "bull" if s >= 60
            else "bear" if s <= 40 else "neutral",
            f"Galaxy {lc_metrics.get('galaxy_score', '—')} · "
            f"sentiment {s:.0f}%"))

    bulls = sum(1 for _, s, _ in reads if s == "bull")
    bears = sum(1 for _, s, _ in reads if s == "bear")
    score, conf = agg["score"], detail["confidence"]

    if score >= 30 and bulls >= bears:
        head, col = "Bullish — the edge favours longs", "#2ed47a"
    elif score <= -30 and bears >= bulls:
        head, col = "Bearish — the edge favours shorts", "#ff5c5c"
    elif abs(score) < 15 or abs(bulls - bears) <= 1:
        head, col = "Mixed / Neutral — no clear edge, stand aside", "#c9a227"
    elif score > 0:
        head, col = "Leaning bullish — partial confirmation only", "#7bd88f"
    else:
        head, col = "Leaning bearish — partial confirmation only", "#ff8a7a"

    dot = {"bull": "#2ed47a", "bear": "#ff5c5c", "neutral": "#8b8d98"}
    with st.container(border=True):
        st.markdown(
            f"<div style='font-size:0.72rem;letter-spacing:0.09em;"
            f"color:#8b8d98;font-weight:700'>THE BOTTOM LINE</div>"
            f"<div style='font-size:1.35rem;font-weight:800;color:{col};"
            f"margin:3px 0 4px 0'>{head}</div>"
            f"<div style='color:#8b8d98;font-size:0.85rem'>"
            f"{bulls} bullish · {bears} bearish signals · composite score "
            f"{score:+.0f} · {conf}% confidence</div>",
            unsafe_allow_html=True)
        rows = "".join(
            f"<div style='display:flex;gap:9px;align-items:center;"
            f"margin:5px 0'><span style='width:8px;height:8px;border-radius:"
            f"50%;background:{dot[s]};display:inline-block;flex:none'></span>"
            f"<span style='color:#c9cbd4;font-weight:600;min-width:185px'>"
            f"{src}</span><span style='color:#8b8d98'>{note}</span></div>"
            for src, s, note in reads)
        st.markdown(rows, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("**🔬 Detailed analysis**")
        for _heading, _text in _analysis_sections(
                agg, detail, per_tf, tv_rating, flow_snap, lc_metrics):
            st.markdown(f"**{_heading}.** {_text}")
        st.markdown("---")

        plan = detail.get("trade_plan")
        if plan and abs(score) >= 15:
            st.caption(
                f"Expert read — act on the {plan['side']} plan below only "
                f"once price reaches the entry zone and the timing signal "
                f"agrees; otherwise wait. Always keep the stop.")
        else:
            st.caption(
                "Expert read — signals conflict or are weak; the "
                "highest-probability action right now is to wait for "
                "alignment rather than force a trade.")


def render_lunarcrush_leaderboard(rows: list) -> None:
    """Render a LunarCrush social leaderboard across the major coins."""
    with st.container(border=True):
        st.markdown("#### 🌙 LunarCrush Social Leaderboard")
        if not rows:
            if not lunarcrush.is_configured():
                st.info("LunarCrush is not configured — add your API key to "
                        "the `.env` file to enable social intelligence.")
            else:
                st.caption("LunarCrush data is unavailable right now.")
            return

        coins = [r for r in rows
                 if r.get("market_cap_rank")
                 and r.get("galaxy_score") is not None]
        coins = sorted(coins, key=lambda r: r["market_cap_rank"])[:150]
        if not coins:
            st.caption("No ranked LunarCrush coins available.")
            return

        sents = [r["sentiment"] for r in coins
                 if r.get("sentiment") is not None]
        top = max(coins, key=lambda r: r["galaxy_score"])
        c1, c2, c3 = st.columns(3)
        c1.metric("Coins tracked", len(coins))
        c2.metric("Top Galaxy Score",
                  f"{top['symbol']} · {top['galaxy_score']:.0f}")
        if sents:
            c3.metric("Avg social sentiment",
                      f"{sum(sents) / len(sents):.0f}%")

        board = sorted(coins, key=lambda r: r["galaxy_score"],
                       reverse=True)[:25]
        df = pd.DataFrame([{
            "Coin": r["symbol"],
            "Galaxy": r["galaxy_score"],
            "Galaxy Δ": (round(r["galaxy_score"] - r["galaxy_score_previous"],
                               1)
                         if r.get("galaxy_score_previous") is not None
                         else None),
            "AltRank": r.get("alt_rank"),
            "Sentiment": r.get("sentiment"),
            "Social Dom %": (round(r["social_dominance"], 2)
                             if r.get("social_dominance") is not None
                             else None),
            "24h %": (round(r["percent_change_24h"], 2)
                      if r.get("percent_change_24h") is not None else None),
        } for r in board])
        st.dataframe(
            df, use_container_width=True, hide_index=True, height=460,
            column_config={
                "Galaxy": st.column_config.ProgressColumn(
                    "Galaxy", min_value=0, max_value=100, format="%d"),
                "Sentiment": st.column_config.ProgressColumn(
                    "Sentiment", min_value=0, max_value=100, format="%d%%"),
                "24h %": st.column_config.NumberColumn(
                    "24h %", format="%.2f%%"),
                "Galaxy Δ": st.column_config.NumberColumn(
                    "Galaxy Δ", format="%+.1f"),
            })
        st.caption("Ranked by Galaxy Score — LunarCrush's 0-100 social + "
                   "market health metric — among the top 150 coins by market "
                   "cap. AltRank: lower is better. Galaxy Δ is the change vs "
                   "the previous reading.")


def breakout_accent(row: dict) -> str:
    """Pick the accent colour for a Breakout Radar card."""
    if row["chasing_risk"]:
        return "#e0a92b"                       # amber — extended / chasing risk
    if row["dir_word"] == "BULLISH":
        return "#2ed47a"
    if row["dir_word"] == "BEARISH":
        return "#ff5c5c"
    return "#8b8d98"


def render_breakout_card(row: dict, rank: int) -> None:
    """Render one Breakout Radar candidate card."""
    accent = breakout_accent(row)
    idea = row["idea"]
    strength = oracle.signal_strength(row)
    ignite = (
        "&nbsp;<span style='background:rgba(255,138,43,0.16);"
        "border:1px solid rgba(255,138,43,0.55);color:#ff9d3d;padding:3px 9px;"
        "border-radius:7px;font-size:0.68rem;font-weight:800'>🔥 VOLUME "
        "SURGING</span>" if row.get("ignited") else "")
    with st.container(border=True):
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;"
            f"align-items:baseline;flex-wrap:wrap;gap:6px'>"
            f"<div style='font-size:1.16rem;font-weight:800'>"
            f"<span style='color:#6b7080'>#{rank}</span>&nbsp; "
            f"{row['emoji']} {row['base']} / USDT &nbsp;"
            f"<span style='background:{accent};color:#06121f;padding:3px 12px;"
            f"border-radius:7px;font-size:0.72rem;font-weight:800;"
            f"letter-spacing:0.03em'>{row['verdict']}</span>{ignite}</div>"
            f"<div style='color:#8b8d98;font-size:0.82rem;font-weight:600'>"
            f"radar score {row['opportunity']:.0f}/100 · "
            f"{row['confidence']}% confidence · "
            f"signal {strength['label'].lower()} ({strength['score']})"
            f"</div></div>",
            unsafe_allow_html=True)

        if row["chasing_risk"]:
            st.markdown(
                "<div style='background:rgba(224,169,43,0.12);"
                "border:1px solid rgba(224,169,43,0.45);border-radius:9px;"
                "padding:7px 12px;margin:8px 0;font-size:0.84rem;"
                "color:#e9c66b;font-weight:600'>⚠️ This coin has already made "
                "its big move — it is too late to enter safely. Don't chase "
                "it: wait for it to pull back, or just manage a position you "
                "already hold.</div>",
                unsafe_allow_html=True)

        m = st.columns(6)
        m[0].metric("Price", fmt_price(row["price"]))
        m[1].metric("1h", f"{row['chg_1h']:+.2f}%")
        m[2].metric("24h", f"{row['chg_24h']:+.2f}%")
        m[3].metric("24h Vol", fmt_volume(row.get("quoteVolume")),
                    help="24h traded value — a liquidity check")
        m[4].metric("Surge", f"{row['vol_peak']:.1f}x",
                    help="Peak recent volume vs its 20-candle average")
        m[5].metric("RSI", f"{row['rsi']:.0f}")

        st.progress(min(int(row["opportunity"]), 100),
                    text=f"🎯 Radar score {row['opportunity']:.0f}/100  ·  "
                         f"{_STAGE_WORD.get(row['stage'], row['stage'])}")

        st.markdown(f"**Why it's on the radar** — {md_safe(row['summary'])}")
        st.markdown(f"**📰 News** — {md_safe(row['news_read'])}")
        st.caption(f"⏱️ Timing — {row['window']} · {row['regime_4h']} backdrop")

        # --- Entry & exit plan, shown prominently in the card body ---------
        st.markdown(f"**🎯 The play** — {md_safe(idea['play'])}")
        if idea["side"] != "EITHER":
            tc = st.columns(4)
            tc[0].metric("Entry zone", md_safe(
                f"{fmt_price(idea['entry_low'])} – "
                f"{fmt_price(idea['entry_high'])}"))
            tc[1].metric("Stop loss", fmt_price(idea["stop"]))
            tc[2].metric("Exit 1", fmt_price(idea["target_1"]))
            tc[3].metric("Exit 2", fmt_price(idea["target_2"]))
        else:
            tc = st.columns(3)
            tc[0].metric("Long trigger", fmt_price(row["win_high"]))
            tc[1].metric("Short trigger", fmt_price(row["win_low"]))
            tc[2].metric("Stay flat inside", md_safe(
                f"{fmt_price(row['win_low'])} – "
                f"{fmt_price(row['win_high'])}"))
        st.caption(f"Exit plan — {md_safe(idea['exit_note'])}")

        chips = ""
        for d in row["drivers"]:
            sc = d["score"]
            if d["signed"]:
                col = ("#2ed47a" if sc >= 15 else "#ff5c5c" if sc <= -15
                       else "#8b8d98")
                val = f"{sc:+d}"
            else:
                col = ("#6e8bff" if sc >= 55 else "#9aa0b4" if sc >= 25
                       else "#5b5f6e")
                val = f"{sc}"
            chips += (f"<span style='display:inline-block;margin:3px 6px 3px 0;"
                      f"padding:4px 10px;border-radius:7px;font-size:0.76rem;"
                      f"background:#1a1c24;border:1px solid {col}55'>"
                      f"<span style='color:#c9cbd4;font-weight:600'>"
                      f"{d['force']}</span> "
                      f"<span style='color:{col};font-weight:800'>{val}</span>"
                      f"</span>")
        st.markdown(chips, unsafe_allow_html=True)

        with st.expander("🔬 Full breakdown — every signal explained"):
            for d in row["drivers"]:
                tag = (f"{d['score']:+d}" if d["signed"]
                       else f"{d['score']} / 100")
                st.markdown(f"- **{d['force']}** ({tag}) — "
                            f"{md_safe(d['note'])}")
        st.caption("Educational — algorithmic detection, not financial "
                   "advice. Fast moves can gap straight through stops.")


_STAGE_WORD = {"COILED": "Building Up", "FRESH": "Just Started",
               "EXTENDED": "Already Ran"}


def breakout_side_table(df_side: pd.DataFrame, side: str) -> None:
    """Render a compact ranked table for one side — 'UP' (long) or 'DOWN'
    (short). Entry and Target are computed for that side's trade."""
    if df_side.empty:
        st.caption("No coins on this side right now.")
        return

    def _entry(r: dict) -> float:
        idea = r["idea"]
        if idea["side"] != "EITHER":
            return idea["entry_low"]
        return r["win_high"] if side == "UP" else r["win_low"]

    def _target(r: dict) -> float:
        idea = r["idea"]
        if idea["side"] != "EITHER":
            return idea["target_1"]
        return idea["target_1"] if side == "UP" else idea["target_2"]

    tbl = pd.DataFrame({
        "Coin": df_side["base"],
        "Status": df_side.apply(
            lambda r: ("🔥 " if r["ignited"] else "")
            + _STAGE_WORD.get(r["stage"], r["stage"]), axis=1),
        "Score": df_side["opportunity"],
        "Confidence": df_side["confidence"],
        "Entry": df_side.apply(lambda r: fmt_price(_entry(r)), axis=1),
        "Target": df_side.apply(lambda r: fmt_price(_target(r)), axis=1),
        "24h Vol": (df_side["quoteVolume"].map(fmt_volume)
                    if "quoteVolume" in df_side.columns else "—"),
    })
    st.dataframe(
        tbl, use_container_width=True, hide_index=True,
        height=min((len(tbl) + 1) * 36 + 3, 760),
        column_config={
            "Score": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%d",
                help="0-100 radar rank — higher is a stronger setup"),
            "Confidence": st.column_config.NumberColumn(
                "Confidence", format="%d%%",
                help="How sure the engine is of the direction"),
        })


def render_oracle_answer(result: dict) -> None:
    """Render the Oracle's answer — a headline panel plus matching cards."""
    accent = {"bullish": "#2ed47a", "bearish": "#ff5c5c",
              "mixed": "#e0a92b", "empty": "#8b8d98"}.get(
                  result.get("tone", "mixed"), "#6e8bff")
    with st.container(border=True):
        st.markdown(
            f"<div style='font-size:0.72rem;letter-spacing:0.09em;"
            f"color:#8b8d98;font-weight:700'>🤖 THE ORACLE SAYS</div>"
            f"<div style='font-size:1.22rem;font-weight:800;color:{accent};"
            f"margin:4px 0 6px 0'>{md_safe(result['headline'])}</div>"
            f"<div style='color:#c9cbd4;font-size:0.9rem'>"
            f"{md_safe(result['detail'])}</div>",
            unsafe_allow_html=True)
    coins = result.get("coins")
    if coins is not None and not coins.empty:
        for _i, (_, _r) in enumerate(coins.iterrows(), 1):
            render_breakout_card(_r.to_dict(), _i)


def render_buy_zone_board(radar: pd.DataFrame, backdrop: dict,
                          mcap_map: dict) -> None:
    """Render the bullish-accumulation buy-zone board."""
    st.markdown("### 🟢 Bullish Buy Zones — where to accumulate")
    zones = oracle.buy_zones(radar, mcap_map)
    if zones is None or zones.empty:
        st.info("No clean bullish accumulation setups on the radar right "
                "now — nothing is coiled or freshly breaking to the upside. "
                "Try the other horizon, or check back after the next "
                "candles close.")
        return

    if backdrop:
        score = backdrop.get("score", 0) or 0
        tape = ("a tailwind for these longs" if score >= 22
                else "a headwind — size these down" if score <= -22
                else "broadly neutral for these longs")
        st.caption(f"🌍 **Worldwide backdrop** — {backdrop.get('label', '—')}: "
                   f"{backdrop.get('note', '')}. That is {tape}.")

    table = pd.DataFrame({
        "Coin": zones["base"],
        "Signal": zones.apply(
            lambda r: f"{r['strength_label']} · {r['strength']:.0f}", axis=1),
        "Status": zones.apply(
            lambda r: ("🔥 " if r["ignited"] else "")
            + _STAGE_WORD.get(r["stage"], r["stage"]), axis=1),
        "Buy zone": zones.apply(
            lambda r: f"{fmt_price(r['buy_low'])} – {fmt_price(r['buy_high'])}",
            axis=1),
        "Trigger": zones["trigger"].map(fmt_price),
        "Stop": zones["bz_stop"].map(
            lambda v: fmt_price(v) if v is not None and v == v else "—"),
        "Target 1": zones.apply(
            lambda r: f"{fmt_price(r['bz_t1'])}  (+{r['bz_gain1']:.1f}%)",
            axis=1),
        "Target 2": zones.apply(
            lambda r: f"{fmt_price(r['bz_t2'])}  (+{r['bz_gain2']:.1f}%)",
            axis=1),
        "Target 3": zones.apply(
            lambda r: f"{fmt_price(r['bz_t3'])}  (+{r['bz_gain3']:.1f}%)",
            axis=1),
        "R : R": zones.apply(
            lambda r: (f"{r['bz_rr1']:.1f}–{r['bz_rr3']:.1f}"
                       if r['bz_rr1'] > 0 else "—"), axis=1),
        "Score": zones["opportunity"],
        "Conf": zones["confidence"],
        "Cap tier": zones["cap_tier"],
        "Circulating": zones["circ_pct"].map(
            lambda v: f"{v:.0f}%" if v is not None and v == v else "—"),
    })
    st.dataframe(
        table, use_container_width=True, hide_index=True,
        height=min((len(table) + 1) * 36 + 3, 520),
        column_config={
            "Score": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%d",
                help="Radar opportunity rank — rewards early, coiled setups."),
            "Conf": st.column_config.NumberColumn(
                "Conf", format="%d%%",
                help="How sure the engine is of the bullish direction."),
            "Signal": st.column_config.TextColumn(
                "Signal",
                help="Signal strength — the breadth and force of the ~11 "
                     "detection signals backing this breakout "
                     "(Weak / Moderate / Strong / Very Strong, 0-100). "
                     "Trade the strongest rows first."),
            "R : R": st.column_config.TextColumn(
                "R : R",
                help="Reward-to-risk from the buy zone, Target 1 through "
                     "Target 3 — e.g. '1.8–5.4' means Target 1 pays 1.8x "
                     "the risked amount and Target 3 pays 5.4x."),
            "Circulating": st.column_config.TextColumn(
                "Circulating",
                help="Circulating supply as a % of max supply — a high % "
                     "means little future dilution; a low % means many "
                     "tokens are still to be unlocked."),
        })
    st.caption(
        "**How to use this** — **Signal** is how forcefully the breakout is "
        "backed: how many of the ~11 detection forces (volume, momentum, "
        "order flow, trend, strength vs BTC, social, news…) pull the same "
        "way, and how hard — trade the **Strong** and **Very Strong** rows "
        "first. The **Buy zone** is where to accumulate: inside the range "
        "for *Building Up* coins (positioned **before** the break), the "
        "retest of the broken level for *Just Started* coins. A clean "
        "candle close above the **Trigger** confirms the move; always set "
        "the **Stop**. **R : R** is reward-to-risk measured from the buy "
        "zone — the three targets carry +% gains; only take rows where "
        "Target 1 already pays more than 1.0x the risk. A low "
        "**Circulating** % flags dilution as more tokens unlock. "
        "Educational only — not financial advice.")

    st.markdown("#### 📋 Top 3 — full read & trade plan")
    for _i, (_, _r) in enumerate(zones.head(3).iterrows(), 1):
        render_breakout_card(_r.to_dict(), _i)


def _render_alert_setup(s: dict, is_new: bool) -> None:
    """One high-confidence setup line inside the Trade Alerts strip."""
    color = "#2ed47a" if s["side"] == "LONG" else "#ff5c5c"
    word = "BULLISH" if s["side"] == "LONG" else "BEARISH"
    proof = " · ".join(s["proof"]) if s["proof"] else "multiple signals aligned"
    new_tag = " 🆕" if is_new else ""
    st.markdown(
        f"<div style='border-left:3px solid {color};padding:6px 11px;"
        f"margin:6px 0;background:{color}14;border-radius:5px'>"
        f"<span style='font-weight:800'>{s['base']}</span> "
        f"<span style='color:{color};font-weight:800'>{word}</span> · "
        f"{s['confidence']}% confidence · R:R {s['rr']:.1f}{new_tag}<br>"
        f"<span style='font-size:0.8rem;color:#aab'>proof — "
        f"{md_safe(proof)}</span><br>"
        f"<span style='font-size:0.8rem;color:#889'>entry "
        f"{fmt_price(s['entry_low'])}–{fmt_price(s['entry_high'])} · stop "
        f"{fmt_price(s['stop'])} · target {fmt_price(s['target'])}</span>"
        f"</div>",
        unsafe_allow_html=True)


def _render_alert_surge(s: dict, is_new: bool) -> None:
    """One volume-surge line inside the Trade Alerts strip."""
    chg = s.get("change_24h")
    chg_txt = (f" · {chg:+.1f}% 24h" if chg is not None and chg == chg else "")
    lab = s["label"]
    lab_col = ("#2ed47a" if "LONG" in lab else "#ff5c5c" if "SHORT" in lab
               else "#8b8d98")
    new_tag = " 🆕" if is_new else ""
    st.markdown(
        f"<div style='padding:5px 11px;margin:6px 0;background:#1a1c24;"
        f"border-radius:5px;border:1px solid #ff8a3d44'>"
        f"🔥 <span style='font-weight:800'>{s['base']}</span> — volume "
        f"<span style='color:#ff9d3d;font-weight:800'>{s['vol_ratio']:.1f}×</span>"
        f" average{chg_txt} · <span style='color:{lab_col};font-weight:700'>"
        f"{lab}</span>{new_tag}</div>",
        unsafe_allow_html=True)


_BROWSER_ALERT_JS = """
<script>
(function(){
  try {
    var P = window.parent || window;
    var N = P.Notification || window.Notification;
    var items = __PAYLOAD__;
    var KEY = '__KEY__';
    function fire(){
      var raw = null;
      try { raw = P.localStorage.getItem(KEY); } catch(e){}
      var firstEver = (raw === null);
      var prev = {};
      if (!firstEver) {
        try { (JSON.parse(raw) || []).forEach(function(id){ prev[id]=1; }); }
        catch(e){}
      }
      items.forEach(function(a){
        if (!firstEver && !prev[a.id]) {
          try { new N(a.title, {body:a.body, tag:a.id, renotify:true}); }
          catch(e){}
        }
      });
      try {
        P.localStorage.setItem(KEY,
          JSON.stringify(items.map(function(a){ return a.id; })));
      } catch(e){}
    }
    if (N) {
      if (N.permission === 'granted') { fire(); }
      else if (N.permission !== 'denied') {
        N.requestPermission().then(function(p){ if(p==='granted') fire(); });
      }
    }
    var secs = __REFRESH__;
    if (secs > 0 && !P.__tiAutoReload) {
      P.__tiAutoReload = 1;
      setTimeout(function(){ try { P.location.reload(); } catch(e){} },
                 secs * 1000);
    }
  } catch(e){}
})();
</script>
"""


def _inject_browser_alerts(items: list[dict], refresh_secs: int,
                           key: str = "ti_notified_alerts") -> None:
    """Inject the JS that fires browser desktop notifications for new alerts
    and (when refresh_secs > 0) auto-refreshes the page so scanning continues
    in the background.

    De-duplication is client-side (localStorage under `key`), so it survives
    the auto-refresh — a full page reload resets Python state, but the
    browser remembers what it has already notified about and never repeats
    itself. The very first load only seeds that memory; it never fires a
    burst. A distinct `key` keeps separate alert streams independent."""
    html = (_BROWSER_ALERT_JS
            .replace("__PAYLOAD__", json.dumps(items))
            .replace("__REFRESH__", str(int(refresh_secs)))
            .replace("__KEY__", key))
    components.html(html, height=0)


def render_alerts(merged: pd.DataFrame, timeframe: str) -> None:
    """Global Trade Alerts strip — the few high-confidence setups and volume
    surges worth acting on for the *currently selected* timeframe, each shown
    with its proof, plus toast pop-ups when a brand-new one appears."""
    data = alerts.build_alerts(merged, timeframe)
    setups, surges = data["setups"], data["surges"]

    # New-since-last-view tracking, kept separately per timeframe.
    seen_all = st.session_state.setdefault("alert_seen", {})
    first_visit = timeframe not in seen_all
    prev = seen_all.get(timeframe, set())
    new_setup_syms = {s["symbol"] for s in setups
                      if s["symbol"] not in prev}
    new_surge_syms = {s["symbol"] for s in surges
                      if ("vol:" + s["symbol"]) not in prev}
    seen_all[timeframe] = ({s["symbol"] for s in setups}
                           | {"vol:" + s["symbol"] for s in surges})

    # Toast only genuinely new alerts — never on the first visit (which would
    # pop the whole board at once).
    if not first_visit:
        for s in [x for x in setups if x["symbol"] in new_setup_syms][:3]:
            st.toast(f"{s['base']} — {s['side']} setup, "
                     f"{s['confidence']}% confidence", icon="🚨")
        for s in [x for x in surges if x["symbol"] in new_surge_syms][:2]:
            st.toast(f"{s['base']} — volume surging {s['vol_ratio']:.1f}×",
                     icon="🔊")

    with st.container(border=True):
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;"
            f"align-items:baseline'><span style='font-size:1.06rem;"
            f"font-weight:800'>🚨 Trade Alerts</span>"
            f"<span style='color:#8b8d98;font-size:0.8rem;font-weight:600'>"
            f"{timeframe} timeframe · {trade_mode.upper()} mode</span></div>",
            unsafe_allow_html=True)

        if not setups and not surges:
            st.info(
                f"No high-confidence setup on the **{timeframe}** timeframe "
                f"right now — nothing crosses the bar to act on. That is a "
                f"valid, useful answer: wait, don't force a trade.")
        else:
            ac1, ac2 = st.columns(2)
            with ac1:
                st.markdown(f"**🟢 High-confidence setups** ({len(setups)})")
                if not setups:
                    st.caption("None clear the confidence bar right now.")
                for s in setups[:5]:
                    _render_alert_setup(s, s["symbol"] in new_setup_syms)
            with ac2:
                st.markdown(f"**🔥 Volume surging** ({len(surges)})")
                if not surges:
                    st.caption("No coin's volume is surging right now.")
                for s in surges[:6]:
                    _render_alert_surge(s, s["symbol"] in new_surge_syms)

        st.caption(
            f"Alerts are built only from **{timeframe}** data — 15m, 1h, 4h "
            f"and 1d each have their own setups, so a coin can be a buy on "
            f"one timeframe and not another; that is expected, not a glitch. "
            f"A setup that stays on this list across refreshes is more "
            f"trustworthy than one that just appeared. 🆕 marks alerts new "
            f"since you last looked; pop-ups fire when a fresh one lands.")

    # Browser desktop notifications + background auto-refresh (opt-in).
    if alerts_on:
        notify_items: list[dict] = []
        for s in setups:
            bullish = s["side"] == "LONG"
            notify_items.append({
                "id": f"{s['symbol']}:{s['side']}",
                "title": (f"{'🟢' if bullish else '🔴'} {s['base']} "
                          f"{'BULLISH' if bullish else 'BEARISH'} setup"),
                "body": (f"{s['confidence']}% confidence · R:R "
                         f"{s['rr']:.1f} · {timeframe} · entry "
                         f"{fmt_price(s['entry_low'])}–"
                         f"{fmt_price(s['entry_high'])}"),
            })
        for s in surges:
            notify_items.append({
                "id": f"vol:{s['symbol']}",
                "title": f"🔥 {s['base']} volume surge",
                "body": (f"Volume {s['vol_ratio']:.1f}× average · "
                         f"{timeframe} timeframe"),
            })
        _inject_browser_alerts(notify_items, alert_every * 60)


def render_forecast(fc_df: pd.DataFrame) -> None:
    """Render the multi-timeframe forecast board with its alert callout."""
    st.subheader("🔮 Multi-Timeframe Forecast")
    st.caption(
        "Where each coin is projected to head over the next 15m, 1h and 4h "
        "candle. Each call fuses that timeframe's own technicals with the "
        "Breakout Radar read — news catalysts, the macro / geopolitical "
        "backdrop, volume ignition, social heat and funding. A forecast is "
        "a probabilistic lean with an expected move sized from the "
        "timeframe's ATR — not a guaranteed price.")
    if fc_df is None or fc_df.empty:
        st.warning("No forecast data right now — try refreshing.")
        return

    # --- Forecast alerts — aligned, high-conviction calls ------------------
    fa = alerts.build_forecast_alerts(fc_df)
    prev = st.session_state.get("forecast_seen")
    first_visit = prev is None
    new_syms = {a["symbol"] for a in fa
                if not first_visit and a["symbol"] not in prev}
    st.session_state["forecast_seen"] = {a["symbol"] for a in fa}
    for a in [x for x in fa if x["symbol"] in new_syms][:3]:
        st.toast(f"Forecast: {a['base']} {a['outlook'].lower()} across "
                 f"15m / 1h / 4h ({a['confidence']}%)", icon="🔮")

    with st.container(border=True):
        st.markdown("**🚨 Forecast Alerts** — coins projected the same way "
                    "across all three horizons with strong confidence")
        if not fa:
            st.caption("No coin is aligned across 15m, 1h and 4h with strong "
                       "confidence right now — the tape is mixed; wait.")
        else:
            for a in fa[:6]:
                color = "#2ed47a" if a["outlook"] == "Bullish" else "#ff5c5c"
                fire = " &nbsp;🔥 volume igniting" if a["ignited"] else ""
                tag = " 🆕" if a["symbol"] in new_syms else ""
                st.markdown(
                    f"<div style='border-left:3px solid {color};"
                    f"padding:5px 11px;margin:5px 0;background:{color}14;"
                    f"border-radius:5px'><b>{a['base']}</b> "
                    f"<span style='color:{color};font-weight:800'>"
                    f"{a['outlook'].upper()}</span> across 15m / 1h / 4h · "
                    f"{a['confidence']}% confidence · 4h move "
                    f"<b>{a['proj_4h_pct']:+.2f}%</b>{fire}{tag}</div>",
                    unsafe_allow_html=True)

    # Browser desktop notifications for forecast alerts — only when the user
    # has Desktop alerts switched on. Own localStorage key, no extra refresh.
    if alerts_on and fa:
        _inject_browser_alerts(
            [{"id": f"fc:{a['symbol']}:{a['outlook']}",
              "title": f"🔮 {a['base']} — {a['outlook']} forecast",
              "body": (f"Aligned across 15m / 1h / 4h · {a['confidence']}% "
                       f"confidence · 4h move {a['proj_4h_pct']:+.2f}%")}
             for a in fa],
            0, key="ti_notified_forecast")

    aligned_up = int(((fc_df["outlook_word"] == "Bullish")
                      & fc_df["aligned"]).sum())
    aligned_down = int(((fc_df["outlook_word"] == "Bearish")
                        & fc_df["aligned"]).sum())
    st.markdown(
        f"**{aligned_up}** coin(s) projected **up across all three "
        f"horizons**, **{aligned_down}** projected **down across all "
        f"three**. The full board is below, ranked by total expected move.")

    arrow = {"Up": "▲", "Down": "▼", "Sideways": "▬"}

    def cell(h: dict | None) -> str:
        if not h:
            return "—"
        return f"{arrow.get(h['direction'], '·')} {h['move_pct']:+.2f}%"

    rows = []
    for _, r in fc_df.iterrows():
        hz = r["horizons"] or {}
        h4 = hz.get("4h")
        rows.append({
            "Coin": ("🔥 " if r["ignited"] else "") + r["base"],
            "Price now": fmt_price(r["price"]),
            "Next 15m": cell(hz.get("15m")),
            "Next 1h": cell(hz.get("1h")),
            "Next 4h": cell(hz.get("4h")),
            "Projected 4h": fmt_price(h4["projected"]) if h4 else "—",
            "Outlook": r["outlook_word"],
            "Conf": int(r["confidence"]),
            "_lean": float(r["net_lean"]),
        })
    table = pd.DataFrame(rows).sort_values(
        "_lean", ascending=False).drop(columns=["_lean"])

    def _cell_color(v):
        if isinstance(v, str):
            if v.startswith("▲"):
                return "color:#2ed47a;font-weight:700"
            if v.startswith("▼"):
                return "color:#ff5c5c;font-weight:700"
            if v.startswith("▬"):
                return "color:#8b8d98"
        return ""

    def _outlook_color(v):
        return {"Bullish": "color:#2ed47a;font-weight:700",
                "Bearish": "color:#ff5c5c;font-weight:700"}.get(
                    v, "color:#8b8d98")

    styled = (table.style
              .map(_cell_color, subset=["Next 15m", "Next 1h", "Next 4h"])
              .map(_outlook_color, subset=["Outlook"]))
    st.dataframe(
        styled, use_container_width=True, hide_index=True,
        height=min((len(table) + 1) * 36 + 3, 720),
        column_config={
            "Conf": st.column_config.NumberColumn(
                "Conf", format="%d%%",
                help="Average confidence across the three horizons, with a "
                     "bonus when all three agree."),
        })

    with st.expander("📋 Why these forecasts — news, key drivers & backdrop"):
        bd = fc_df.iloc[0].get("backdrop_label", "")
        if bd:
            st.markdown(f"🌍 **Macro / geopolitical backdrop** — {md_safe(bd)}")
        ranked = fc_df.reindex(
            fc_df["net_lean"].abs().sort_values(ascending=False).index)
        for _, r in ranked.head(6).iterrows():
            drivers = " · ".join(r["drivers"]) if r["drivers"] else "—"
            news = r["news_read"] or "no specific news catalyst"
            fire = " · 🔥 volume igniting" if r["ignited"] else ""
            st.markdown(
                f"**{r['base']}** — {r['outlook_word']} "
                f"({r['confidence']}%){fire}  \n"
                f"Key drivers: {md_safe(drivers)}  \n"
                f"News: {md_safe(news)}")

    st.caption(
        "Each cell shows the projected direction (▲ up · ▼ down · ▬ "
        "sideways) and the expected NET move for that candle. The call "
        "fuses the timeframe's technicals with news, the macro backdrop, "
        "volume ignition, social heat and funding — every input tilts the "
        "read within bounds, none overrides it. 'Projected 4h' applies the "
        "4h expected move to the current price. Probabilistic projections, "
        "not guarantees. Educational only, not financial advice.")


def _inject_autorefresh(seconds: int) -> None:
    """Reload the whole app after `seconds` — used for the live forecast."""
    components.html(
        "<script>(function(){var P=window.parent||window;"
        "if(!P.__tiFcReload){P.__tiFcReload=1;setTimeout(function(){"
        "try{P.location.reload();}catch(e){}}," + str(int(seconds * 1000))
        + ");}})();</script>", height=0)


def render_btc_outlook(o: dict,
                       impactful_news: list[dict] | None = None) -> None:
    """Prominent BTC 24h Outlook banner — shown above every tab. BTC leads the
    market; the banner tells the user which way it leans, with the evidence
    and the caution flags surfaced so they can size accordingly. When
    `impactful_news` is supplied, a 'Why this is happening' panel shows the
    headlines moving the tape — and new ones fire toasts and desktop
    notifications when Desktop alerts is enabled."""
    if not o:
        return
    direction = o.get("direction", "Neutral")
    color = {"Up": "#2ed47a", "Down": "#ff5c5c",
             "Neutral": "#e0a92b"}.get(direction, "#8b8d98")
    label = {"Up": "LEANING UP", "Down": "LEANING DOWN",
             "Neutral": "NEUTRAL"}.get(direction, direction.upper())
    with st.container(border=True):
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;"
            f"align-items:center;flex-wrap:wrap;gap:8px'>"
            f"<div><span style='font-size:1.08rem;font-weight:800'>"
            f"₿ BTC — Next 24 Hours</span> &nbsp;"
            f"<span style='background:{color};color:#06121f;padding:4px 13px;"
            f"border-radius:7px;font-size:0.78rem;font-weight:800;"
            f"letter-spacing:0.04em'>{label}</span></div>"
            f"<div style='color:#8b8d98;font-size:0.85rem;font-weight:600'>"
            f"{o.get('confidence', 0)}% confidence · "
            f"{o.get('aligned_categories', 0)}/"
            f"{o.get('total_categories', 0)} categories agree · "
            f"expected range ±{o.get('expected_range_pct', 0):.1f}%"
            f"</div></div>"
            f"<div style='color:{color};font-size:0.94rem;font-weight:700;"
            f"margin:6px 0 4px 0'>{md_safe(o.get('takeaway', ''))}</div>",
            unsafe_allow_html=True)

        # --- Trading-desk briefing: synthesis + concrete next steps -------
        briefing = o.get("briefing") or {}
        if briefing.get("summary"):
            st.markdown(
                f"<div style='background:#11141c;border-radius:6px;"
                f"padding:11px 14px;margin:10px 0 6px 0;"
                f"border:1px solid #1f2330'>"
                f"<div style='font-size:0.74rem;letter-spacing:0.10em;"
                f"color:#8b8d98;font-weight:800;margin-bottom:5px'>"
                f"🧭 WHAT THIS MEANS</div>"
                f"<div style='color:#d8dae3;font-size:0.9rem;"
                f"line-height:1.55'>{md_safe(briefing['summary'])}</div>"
                + (f"<div style='font-size:0.78rem;color:#9aa0b4;"
                   f"margin-top:7px;font-style:italic'>"
                   f"{md_safe(briefing.get('conviction_note', ''))}</div>"
                   if briefing.get("conviction_note") else "")
                + "</div>",
                unsafe_allow_html=True)
        if briefing.get("next_steps"):
            steps_html = "".join(
                f"<div style='color:#cfd2dc;font-size:0.86rem;"
                f"margin:5px 0;padding-left:18px;text-indent:-18px;"
                f"line-height:1.5'>"
                f"<span style='color:#6e8bff;font-weight:800'>→</span> "
                f"{md_safe(step)}</div>"
                for step in briefing["next_steps"])
            st.markdown(
                f"<div style='background:#0e1118;border-left:3px solid "
                f"#6e8bff;padding:9px 14px;margin:6px 0 10px 0;"
                f"border-radius:5px'>"
                f"<div style='font-size:0.74rem;letter-spacing:0.10em;"
                f"color:#6e8bff;font-weight:800;margin-bottom:6px'>"
                f"📋 NEXT STEPS — HOW TO TRADE IT</div>"
                f"{steps_html}</div>",
                unsafe_allow_html=True)

        # --- WHY THIS IS HAPPENING — high-impact headlines moving the tape
        if impactful_news:
            # Toast + browser-notification dedup tracking.
            prev_titles = st.session_state.get("impactful_seen")
            first_visit = prev_titles is None
            current_titles = {it["title"] for it in impactful_news}
            new_items = ([it for it in impactful_news
                          if it["title"] not in prev_titles]
                         if not first_visit else [])
            st.session_state["impactful_seen"] = current_titles
            for it in new_items[:3]:
                icon = ("📈" if it["direction"] == "Bullish"
                        else "📉" if it["direction"] == "Bearish"
                        else "📰")
                st.toast(f"{it['direction'].upper()} impact news — "
                         f"{it['title'][:90]}", icon=icon)

            items_html = ""
            for it in impactful_news[:6]:
                dir_color = {"Bullish": "#2ed47a",
                             "Bearish": "#ff5c5c"}.get(
                                 it["direction"], "#e0a92b")
                fresh_tag = (" 🆕" if it["title"] in
                             {x["title"] for x in new_items} else "")
                kw_chip = ""
                if it.get("keywords"):
                    kw_chip = (f"<span style='background:#1a1c24;"
                               f"color:#aab;padding:1px 6px;border-radius:4px;"
                               f"font-size:0.7rem;margin-left:6px'>"
                               f"{it['keywords'][0]}</span>")
                items_html += (
                    f"<div style='border-left:3px solid {dir_color};"
                    f"padding:6px 12px;margin:5px 0;background:{dir_color}10;"
                    f"border-radius:4px;font-size:0.86rem'>"
                    f"<span style='color:{dir_color};font-weight:800'>"
                    f"{it['direction'].upper()}</span>{kw_chip} "
                    f"<span style='color:#9aa0b4;font-size:0.76rem'>"
                    f"· {md_safe(it.get('source', ''))} "
                    f"· impact {it['score']:.2f}</span>{fresh_tag}<br>"
                    f"<span style='color:#d5d7e0'>"
                    f"{md_safe(it['title'])}</span></div>")
            st.markdown(
                f"<div style='background:#0e1118;border-left:3px solid "
                f"#e0a92b;padding:10px 14px;margin:6px 0 10px 0;"
                f"border-radius:5px'>"
                f"<div style='font-size:0.74rem;letter-spacing:0.10em;"
                f"color:#e0a92b;font-weight:800;margin-bottom:6px'>"
                f"📰 WHY THIS IS HAPPENING — high-impact news right now</div>"
                f"{items_html}</div>",
                unsafe_allow_html=True)

            # Live browser notifications for impactful news (only when the
            # user has Desktop alerts switched on). Own localStorage key so
            # it never duplicates with the trade-alert stream.
            if alerts_on:
                _inject_browser_alerts(
                    [{"id": f"news:{it['title'][:80]}",
                      "title": f"📰 {it['direction']} impact news",
                      "body": (f"{it['title']} — "
                               f"{it.get('source', '')}")}
                     for it in impactful_news[:8]],
                    0, key="ti_notified_news")

        for flag in o.get("flags", []):
            st.markdown(
                f"<div style='background:#e0a92b1f;border-left:3px solid "
                f"#e0a92b;padding:5px 11px;margin:4px 0;border-radius:4px;"
                f"font-size:0.85rem'>⚠️ {md_safe(flag)}</div>",
                unsafe_allow_html=True)
        if o.get("strategies"):
            with st.expander("🎯 Trading strategies currently firing on BTC"):
                st.caption(
                    "Classic technical patterns the engine sees right now. "
                    "Confirming patterns add a small confidence bonus; "
                    "contradicting ones flag uncertainty.")
                for s in o["strategies"]:
                    direction = s.get("direction", "")
                    sc = ("#2ed47a" if direction == "Bullish"
                          else "#ff5c5c" if direction == "Bearish"
                          else "#8b8d98")
                    st.markdown(
                        f"- **{md_safe(s.get('name', ''))}** on "
                        f"<span style='color:#bbb'>"
                        f"{md_safe(s.get('tf', ''))}</span> — "
                        f"<span style='color:{sc};font-weight:700'>"
                        f"{direction}</span>", unsafe_allow_html=True)
        if o.get("drivers"):
            with st.expander("Full drivers — what's pulling BTC each way"):
                for d in o["drivers"]:
                    lean = float(d.get("lean", 0))
                    lc = ("#2ed47a" if lean > 0.05
                          else "#ff5c5c" if lean < -0.05
                          else "#8b8d98")
                    st.markdown(
                        f"- **{d.get('force', '')}** "
                        f"<span style='color:{lc}'>(category "
                        f"{d.get('category', '—')}, lean {lean:+.2f}, "
                        f"weight {d.get('weight', 0)})</span> — "
                        f"{md_safe(d.get('note', ''))}",
                        unsafe_allow_html=True)


# ===========================================================================
# Sidebar
# ===========================================================================
st.sidebar.title("📈 Crypto Indicator")
st.sidebar.caption("Live technical analysis & sentiment — Binance USDT pairs")

# --- Persistent state — survives full page refresh via URL query params --
_qp = st.query_params
_qp_tf = _qp.get("tf", config.DEFAULT_TIMEFRAME)
if _qp_tf not in config.TIMEFRAMES:
    _qp_tf = config.DEFAULT_TIMEFRAME
_qp_mode = _qp.get("mode", "Futures")
if _qp_mode not in ("Futures", "Spot"):
    _qp_mode = "Futures"

# Section navigation lives on the LEFT side as the user requested.
SECTIONS = [
    "🔍 Market Scanner", "🔮 Forecast", "🚀 Breakout Radar",
    "🤖 Ask the Oracle", "🪙 Coin Analysis", "📰 News & Sentiment",
    "🧭 Decision Mode", "🧪 Paper Trader",
]
_qp_section = _qp.get("section", SECTIONS[0])
if _qp_section not in SECTIONS:
    _qp_section = SECTIONS[0]
active_section = st.sidebar.radio(
    "📂 Section", SECTIONS, index=SECTIONS.index(_qp_section),
    help="Switch between the dashboard's sections. Your choice persists "
         "across page refreshes.")

st.sidebar.divider()

timeframe = st.sidebar.selectbox(
    "Timeframe", config.TIMEFRAMES,
    index=config.TIMEFRAMES.index(_qp_tf),
)
trade_mode_label = st.sidebar.radio(
    "Trade mode", ["Futures", "Spot"], horizontal=True,
    index=["Futures", "Spot"].index(_qp_mode),
    help="Futures — trades both long & short, sizes leverage from "
         "conviction. Spot — long-only (no shorting), no leverage, "
         "wider swing-horizon targets and stops.")
trade_mode = trade_mode_label.lower()

# Persist current choices back to the URL so they survive a refresh.
st.query_params["tf"] = timeframe
st.query_params["mode"] = trade_mode_label
st.query_params["section"] = active_section

top_n = st.sidebar.slider("Coins to track", 10, config.TOP_N, config.TOP_N, 5)

alerts_on = st.sidebar.checkbox(
    "🔔 Desktop alerts", value=False,
    help="Browser desktop notifications for new high-confidence setups and "
         "volume surges. Keep this dashboard tab open and allow "
         "notifications when the browser asks — the page auto-refreshes so "
         "it keeps scanning in the background.")
alert_every = 5
if alerts_on:
    alert_every = st.sidebar.selectbox(
        "Check for new signals every", [3, 5, 10], index=1,
        format_func=lambda m: f"{m} minutes")
    st.sidebar.caption(
        f"🔔 Desktop alerts ON — re-scanning every {alert_every} min. Keep "
        f"this tab open (a background tab is fine); allow notifications when "
        f"the browser prompts.")

if st.sidebar.button("🔄 Refresh data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption(
    f"Updated {datetime.now(timezone.utc):%H:%M:%S} UTC · "
    f"market cache {config.MARKET_CACHE_TTL}s")
st.sidebar.info(
    "Educational tool. Signals are algorithmic, not financial advice. "
    "Always manage your own risk.")


# ===========================================================================
# Header — global market sentiment
# ===========================================================================
st.markdown(
    """
    <div style='display:flex;align-items:center;gap:14px;margin:0 0 14px 0'>
      <div style='font-size:2.2rem;line-height:1'>📈</div>
      <div>
        <div style='font-size:1.95rem;font-weight:800;letter-spacing:-0.025em;
             background:linear-gradient(90deg,#6e8bff,#9d8bff);
             -webkit-background-clip:text;background-clip:text;
             -webkit-text-fill-color:transparent;line-height:1.15'>
          Crypto Trading Indicator</div>
        <div style='color:#8a93a6;font-size:0.9rem;margin-top:2px'>
          Live technical, derivatives &amp; social analysis across the top
          Binance USDT pairs</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    fg = load_fear_greed()
except Exception:
    fg = None

try:
    glob = load_global_market()
except Exception:
    glob = None

try:
    news_df = load_news()
except Exception:
    news_df = pd.DataFrame()

# Columns 3-4 adapt: LunarCrush social mood when available, else news mood.
crypto_soc = stock_soc = None
if lunarcrush.is_configured():
    try:
        crypto_soc = load_crypto_social()
    except Exception:
        crypto_soc = None
    try:
        stock_soc = load_stock_social()
    except Exception:
        stock_soc = None

hcol1, hcol2, hcol3, hcol4 = st.columns(4)

if fg:
    delta = fg["value"] - (fg["yesterday"] or fg["value"])
    hcol1.metric("Fear & Greed", f"{fg['value']} · {fg['label']}",
                 f"{delta:+d} vs yesterday")
else:
    hcol1.metric("Fear & Greed", "unavailable")

if glob:
    hcol2.metric("BTC Dominance", f"{glob['btc_dominance']:.1f}%",
                 f"{glob['market_cap_change_24h']:+.2f}% total cap 24h")
else:
    hcol2.metric("BTC Dominance", "unavailable")

if crypto_soc:
    hcol3.metric("Crypto Social Mood", crypto_soc["mood"],
                 f"{crypto_soc['sentiment']:.0f}% positive · LunarCrush")
elif not news_df.empty:
    _cm = news_mod.category_mood(news_df, "Crypto")
    hcol3.metric("Crypto News Mood", _cm["mood"], f"{_cm['score']:+.2f} avg")
else:
    hcol3.metric("Crypto Mood", "unavailable")

if stock_soc:
    hcol4.metric("Equities Social Mood", stock_soc["mood"],
                 f"{stock_soc['sentiment']:.0f}% positive · LunarCrush")
elif not news_df.empty:
    _mm = news_mod.category_mood(news_df, "Macro / Politics")
    hcol4.metric("Macro News Mood", _mm["mood"], f"{_mm['score']:+.2f} avg")
else:
    hcol4.metric("Macro Mood", "unavailable")

if glob:
    _eth = glob.get("eth_dominance") or 0.0
    _eth_txt = f" / ETH {_eth:.1f}%" if _eth else ""
    st.caption(
        f"Total crypto market cap ${glob['market_cap_usd'] / 1e12:.2f}T · "
        f"24h volume ${glob['volume_usd'] / 1e9:.0f}B · "
        f"BTC {glob['btc_dominance']:.1f}%{_eth_txt} dominance · "
        f"via {glob.get('source', '—')}")

# --- BTC 24h Outlook — the headline directional read above every tab --------
try:
    _bo_tickers = load_top_symbols(top_n)
    _btc_row = _bo_tickers[_bo_tickers["symbol"] == "BTCUSDT"]
    _btc_change = (float(_btc_row["priceChangePercent"].iloc[0])
                   if not _btc_row.empty else 0.0)
    _alts = _bo_tickers[~_bo_tickers["symbol"].isin(
        ["BTCUSDT", "ETHUSDT"])]
    _alt_median = (float(_alts["priceChangePercent"].head(30).median())
                   if not _alts.empty else 0.0)
    try:
        _impactful_news = load_impactful_news()
    except Exception:
        _impactful_news = []
    render_btc_outlook(btc_outlook_now(_btc_change, _alt_median),
                       impactful_news=_impactful_news)
except Exception:
    pass  # never let the BTC banner block the rest of the dashboard

# --- Global Trade Alerts strip — high-confidence setups & volume surges,
# computed for the selected timeframe and shown above every tab. -------------
_alert_merged = pd.DataFrame()    # so later tabs can rely on it being defined
try:
    _alert_tickers = load_top_symbols(top_n)
    with st.spinner(f"Scanning {len(_alert_tickers)} coins for alerts…"):
        _alert_scan = scan_market(
            tuple(_alert_tickers["symbol"]), timeframe, trade_mode)
    _alert_merged = _alert_scan.merge(
        _alert_tickers[["symbol", "priceChangePercent", "quoteVolume"]],
        on="symbol", how="left")
    render_alerts(_alert_merged, timeframe)
except Exception:
    pass  # never let the alerts strip block the rest of the dashboard

# Section is selected from the sidebar radio above — no horizontal tab bar.


# ===========================================================================
# Tab 1 — Market Scanner
# ===========================================================================
if active_section == "🔍 Market Scanner":
    st.subheader(f"Market Scanner · {timeframe} timeframe")
    st.caption(f"Top {top_n} USDT pairs by 24h volume, ranked by signal score.")

    try:
        tickers = load_top_symbols(top_n)
    except Exception as exc:
        st.error(f"Could not load Binance market data: {exc}")
        st.stop()

    with st.spinner(f"Analysing {len(tickers)} coins on {timeframe}…"):
        scan_df = scan_market(tuple(tickers["symbol"]), timeframe, trade_mode)

    if scan_df.empty:
        st.warning("No analysis results — try refreshing.")
    else:
        merged = scan_df.merge(
            tickers[["symbol", "priceChangePercent", "quoteVolume"]],
            on="symbol", how="left")
        merged = merged.sort_values("score", ascending=False)

        # TradingView ratings for all scanned coins in one batched request.
        try:
            tv_map = load_tv_ratings(tuple(merged["symbol"]), timeframe)
        except Exception:
            tv_map = {}
        merged["tv"] = merged["symbol"].map(
            lambda s: tv_map.get(s, {}).get("recommendation", "—").upper())

        # LunarCrush Galaxy Score for every coin (one request; skipped when
        # no API key is configured).
        lc_top: dict = {}
        if lunarcrush.is_configured():
            try:
                lc_top = load_lunarcrush_top()
            except Exception:
                lc_top = {}

        # Summary counts on the actionable BUY / SELL verdict.
        counts = merged["action_label"].value_counts()
        s1, s2, s3, s4, s5 = st.columns(5)
        for col, lbl in zip(
                [s1, s2, s3, s4, s5],
                ["STRONG BUY", "BUY", "NEUTRAL", "SELL", "STRONG SELL"]):
            col.metric(lbl.title(), int(counts.get(lbl, 0)))

        table = pd.DataFrame({
            "Coin": merged["symbol"].str.replace("USDT", "", regex=False),
            "Bias": merged["bias_label"],
            "Action": merged["action_label"],
            "TradingView": merged["tv"],
            "Score": merged["score"],
            "Confidence": merged["confidence"],
            "Price": merged["price"].map(fmt_price),
            "24h %": merged["priceChangePercent"].round(2),
            "RSI": merged["rsi"],
            "Regime": merged["regime"],
            "Funding": merged["funding"].map(
                lambda f: f"{f * 100:+.3f}%" if pd.notna(f) else "—"),
        })
        if lc_top:
            table["Galaxy"] = merged["symbol"].map(
                lambda s: lc_top.get(s.replace("USDT", ""), {}).get(
                    "galaxy_score"))

        col_cfg = {
            "Score": st.column_config.ProgressColumn(
                "Score", min_value=-100, max_value=100, format="%d"),
            "Confidence": st.column_config.NumberColumn(
                "Confidence", format="%d%%"),
            "24h %": st.column_config.NumberColumn("24h %", format="%.2f%%"),
        }
        if "Galaxy" in table.columns:
            col_cfg["Galaxy"] = st.column_config.ProgressColumn(
                "Galaxy", min_value=0, max_value=100, format="%d")

        st.dataframe(
            style_scan(table),
            use_container_width=True, hide_index=True, height=560,
            column_config=col_cfg,
        )
        st.caption(
            "Bias = directional positioning (LONG / SHORT). "
            "Action = entry timing (BUY / SELL / NEUTRAL). "
            "TradingView = TradingView's own rating, an independent "
            "cross-check. Score blends bias & action: -100 bearish → "
            "+100 bullish. Funding positive means longs pay shorts.")

        st.markdown("### 🎯 Live Trade Signals")
        st.caption(f"High-conviction setups on the {timeframe} timeframe — "
                   f"entry zone, protective stop and scale-out targets.")
        sig = merged[merged["trade_plan"].apply(
            lambda p: isinstance(p, dict))]
        sig = sig[sig["confidence"] >= 55].sort_values(
            "confidence", ascending=False)
        if sig.empty:
            st.info("No high-conviction setups right now — the market is "
                    "mostly neutral on this timeframe. Try another timeframe "
                    "or check back after the next candles close.")
        else:
            sig_table = pd.DataFrame([{
                "Coin": r["symbol"].replace("USDT", ""),
                "Direction": r["trade_plan"]["side"],
                "Move": (r["trade_plan"].get("maturity") or {}).get(
                    "stage", "—"),
                "Entry zone": f"{fmt_price(r['trade_plan']['entry_low'])} – "
                              f"{fmt_price(r['trade_plan']['entry_high'])}",
                "Stop loss": fmt_price(r["trade_plan"]["stop_loss"]),
                "Target 1": fmt_price(r["trade_plan"]["take_profit"]),
                "Target 2": fmt_price(r["trade_plan"]["take_profit_2"]),
                "Target 3": fmt_price(r["trade_plan"]["take_profit_3"]),
                "R : R": f"{r['trade_plan']['risk_reward']:.1f}–"
                         f"{r['trade_plan']['risk_reward_3']:.1f}R",
                "Confidence": r["confidence"],
            } for _, r in sig.head(20).iterrows()])
            st.dataframe(
                sig_table.style.map(
                    lambda v: f"background-color:"
                              f"{LABEL_COLORS.get(v, '#8e8e93')};"
                              f"color:#fff;font-weight:700;",
                    subset=["Direction"]),
                use_container_width=True, hide_index=True, height=420,
                column_config={
                    "Confidence": st.column_config.NumberColumn(
                        "Confidence", format="%d%%"),
                })
            st.caption(
                "How to trade a signal — place a **limit order** in the "
                "entry zone, set a **stop-market** order at the stop loss, "
                "and exit in two parts: close ~50% at Target 1, the rest at "
                "Target 2, moving the stop to break-even once Target 1 fills. "
                "Open the Coin Analysis tab for the full plan and "
                "step-by-step order guide. Educational only — not financial "
                "advice.")


# ===========================================================================
# Tab 2 — Forecast
# ===========================================================================
if active_section == "🔮 Forecast":
    _fc_live = st.checkbox(
        "🔴 Live forecast — keep it auto-refreshing every 5 min",
        value=False, key="forecast_live",
        help="Re-runs the forecast on an interval so the predictions and "
             "their alerts stay current without you refreshing the page.")
    try:
        _fc_tickers = load_top_symbols(top_n)
        _fc_syms = tuple(_fc_tickers["symbol"].head(40))
        with st.spinner(f"Forecasting {len(_fc_syms)} coins across "
                        f"15m / 1h / 4h with full news & macro context…"):
            _fc_df = forecast_market(_fc_syms)
        render_forecast(_fc_df)
    except Exception as exc:
        st.error(f"Could not build the forecast right now: {exc}")
    if _fc_live:
        _inject_autorefresh(300)


# ===========================================================================
# Tab 3 — Breakout Radar
# ===========================================================================
if active_section == "🚀 Breakout Radar":
    st.subheader("🚀 Breakout Radar — predict the next coins to blow out")
    st.caption(
        "A self-contained intelligence engine. It scans every coin across "
        "three charts and fuses price action, volume surges, volatility, "
        "live buying/selling, the bigger trend, strength versus Bitcoin, "
        "futures funding, social attention and fresh news into one plain "
        "verdict — set inside the overall market mood. It tells you which "
        "coins look ready to move and **how early you are**: coins that "
        "haven't moved yet (the safest entries), coins just starting to move, "
        "and coins that have already run (too late to chase).")

    hz_label = st.radio(
        "Horizon", ["⚡ Imminent — next 15m–4h move  (scans 15m · 1h · 4h)",
                    "📅 Next 24 hours  (scans 1h · 4h · 1d)"],
        horizontal=True, label_visibility="collapsed")
    horizon = "24h" if hz_label.startswith("📅") else "imminent"
    tf_note = ("1h · 4h · 1d charts" if horizon == "24h"
               else "15m · 1h · 4h charts")

    try:
        b_tickers = load_top_symbols(top_n)
    except Exception as exc:
        st.error(f"Could not load Binance market data: {exc}")
        st.stop()

    try:
        with st.spinner(f"Scanning {len(b_tickers)} coins across {tf_note}…"):
            radar, backdrop = scan_breakouts(
                tuple(b_tickers["symbol"]), horizon)
    except Exception as exc:
        import traceback as _tb
        st.error(f"The Breakout Radar hit an error — "
                 f"{type(exc).__name__}: {exc}")
        with st.expander("Technical details"):
            st.code(_tb.format_exc())
        radar, backdrop = pd.DataFrame(), {}

    # Attach each coin's 24h USDT volume for a liquidity read on the cards.
    if not radar.empty:
        radar = radar.merge(
            b_tickers[["symbol", "quoteVolume"]], on="symbol", how="left")

    if radar.empty:
        st.warning("No analysis available right now — try refreshing.")
    else:
        bd_color = {"Risk-on": "#2ed47a", "Risk-off": "#ff5c5c"}.get(
            backdrop["label"], "#e0a92b")
        st.markdown(
            f"<div style='background:rgba(110,139,255,0.05);border:1px solid "
            f"rgba(255,255,255,0.07);border-left:3px solid {bd_color};"
            f"border-radius:10px;padding:10px 15px;margin:2px 0 14px 0'>"
            f"<span style='font-size:0.7rem;letter-spacing:0.09em;"
            f"color:#8b8d98;font-weight:700'>MARKET BACKDROP — THE TAPE EVERY "
            f"SETUP SITS INSIDE</span><br>"
            f"<span style='font-size:1.08rem;font-weight:800;color:{bd_color}'>"
            f"{backdrop['label']}</span>"
            f"<span style='color:#8b8d98;font-size:0.84rem'> &nbsp;·&nbsp; "
            f"score {backdrop['score']:+.0f} &nbsp;·&nbsp; "
            f"{backdrop['note']}</span><br>"
            f"<span style='color:#9aa0b4;font-size:0.79rem'>Bullish setups get "
            f"a small tailwind when the tape is risk-on and a headwind when "
            f"it is risk-off — and the reverse for shorts. It tilts the "
            f"scores, never overrides them.</span></div>",
            unsafe_allow_html=True)

        # Decision board: the top 30 coins by radar score.
        shortlist = radar.head(30)

        loading = int((shortlist["stage"] == "COILED").sum())
        fresh = int((shortlist["stage"] == "FRESH").sum())
        extended = int((shortlist["stage"] == "EXTENDED").sum())
        # Split by the direction score's sign so every coin is a long or a
        # short call — no coin is left without a decision.
        up_df = shortlist[shortlist["direction"] >= 0]
        down_df = shortlist[shortlist["direction"] < 0]

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("🔋 Building Up", loading,
                  help="Hasn't moved yet — the earliest, safest entries")
        k2.metric("🚀 Just Started", fresh,
                  help="Already moving but still early — room to run")
        k3.metric("⚠️ Already Ran", extended,
                  help="Move mostly done — too late, risky to chase")
        k4.metric("🟢 Long / 🔴 Short", f"{len(up_df)} / {len(down_df)}")

        st.caption(
            "**The summary above counts the 30 coins by status.** "
            "🔋 **Building Up** = coiled, has not moved yet — the earliest and "
            "safest entry. 🚀 **Just Started** = the move just began, still "
            "early. ⚠️ **Already Ran** = the move is mostly done — too late, "
            "risky to chase.")

        # --- The decision board: LONG vs SHORT ----------------------------
        st.markdown("### 🎯 Top 30 coins — your long / short decision board")
        bc, sc = st.columns(2)
        with bc:
            st.markdown(
                f"<h4 style='color:#2ed47a;border-color:#2ed47a'>🟢 GO LONG "
                f"&nbsp;<span style='font-size:0.8rem;color:#8b8d98'>"
                f"buy — price likely to rise ({len(up_df)})</span></h4>",
                unsafe_allow_html=True)
            breakout_side_table(up_df, "UP")
        with sc:
            st.markdown(
                f"<h4 style='color:#ff5c5c;border-color:#ff5c5c'>🔴 GO SHORT "
                f"&nbsp;<span style='font-size:0.8rem;color:#8b8d98'>"
                f"sell — price likely to fall ({len(down_df)})</span></h4>",
                unsafe_allow_html=True)
            breakout_side_table(down_df, "DOWN")
        st.caption(
            "**How to read this:** coins on the **left → open a LONG** (buy, "
            "betting price goes up); coins on the **right → open a SHORT** "
            "(sell, betting price goes down). **Entry** = the price to act at, "
            "**Target** = the first place to take profit. Prefer high "
            "**Score** and high **Confidence**; **Building Up** is the safest "
            "timing, **Already Ran** is the riskiest. 🔥 = volume surging. "
            "Full plan and reasoning for every coin below.")

        st.divider()

        # --- Full read & trade plan per coin ------------------------------
        st.markdown("### 📋 Full read & trade plan for each coin")
        fc1, fc2 = st.columns([3, 2])
        stage_flt = fc1.radio(
            "Status", ["All", "🔋 Building up", "🚀 Just started",
                       "⚠️ Already ran"],
            horizontal=True, label_visibility="collapsed")
        dir_flt = fc2.radio(
            "Direction", ["Long & short", "🟢 Long only", "🔴 Short only"],
            horizontal=True, label_visibility="collapsed")

        view = shortlist
        if stage_flt.startswith("🔋"):
            view = view[view["stage"] == "COILED"]
        elif stage_flt.startswith("🚀"):
            view = view[view["stage"] == "FRESH"]
        elif stage_flt.startswith("⚠️"):
            view = view[view["stage"] == "EXTENDED"]
        if dir_flt.startswith("🟢"):
            view = view[view["direction"] >= 0]
        elif dir_flt.startswith("🔴"):
            view = view[view["direction"] < 0]

        if view.empty:
            st.info("No coins match that filter right now.")
        else:
            for _, r in view.iterrows():
                render_breakout_card(r.to_dict(), int(r.name) + 1)

        st.caption("The radar is algorithmic — it flags where the conditions "
                   "for a violent move are stacking up; it does not promise "
                   "one will happen. Educational only, not financial advice.")


# ===========================================================================
# Tab 4 — Ask the Oracle
# ===========================================================================
if active_section == "🤖 Ask the Oracle":
    st.subheader("🤖 Ask the Oracle — your trading-desk analyst")
    st.caption(
        "Ask in plain English which coin is next to blow out — up or down — "
        "and the Oracle answers straight from the live Breakout Radar. Below, "
        "a curated board of bullish coins with concrete buy zones, read "
        "against circulating supply and the worldwide market backdrop.")

    o_hz_label = st.radio(
        "Horizon",
        ["⚡ Imminent — next 15m–4h move", "📅 Next 24 hours"],
        horizontal=True, label_visibility="collapsed", key="oracle_horizon")
    o_horizon = "24h" if o_hz_label.startswith("📅") else "imminent"

    try:
        o_tickers = load_top_symbols(top_n)
        with st.spinner("Scanning the market for the Oracle…"):
            o_radar, o_backdrop = scan_breakouts(
                tuple(o_tickers["symbol"]), o_horizon)
        if not o_radar.empty:
            o_radar = o_radar.merge(
                o_tickers[["symbol", "quoteVolume"]], on="symbol", how="left")
    except Exception as exc:
        st.error(f"Could not load the radar: {exc}")
        o_radar, o_backdrop = pd.DataFrame(), {}

    # Market-cap / circulating-supply context for the buy zones.
    o_mcap_map: dict = {}
    if lunarcrush.is_configured():
        try:
            o_mcap_map = oracle.market_cap_map(load_lunarcrush_list())
        except Exception:
            o_mcap_map = {}

    st.markdown("#### 💬 Ask anything")
    o_question = st.text_input(
        "Your question", value="",
        placeholder="e.g. Which coin is about to blow out?",
        label_visibility="collapsed", key="oracle_question")
    st.caption("Try: “which coin is next for a bullish blowout?” · "
               "“safest long right now” · “what about SOL?” · "
               "“show me the next breakdown” · “volume igniting”")

    o_presets = ["Next bullish blowout", "Next bearish blowout",
                 "Safest long now", "Volume igniting"]
    o_cols = st.columns(len(o_presets))
    for _col, _preset in zip(o_cols, o_presets):
        if _col.button(_preset, use_container_width=True,
                       key=f"oracle_preset_{_preset}"):
            o_question = _preset

    if o_question:
        render_oracle_answer(oracle.answer(o_question, o_radar, o_backdrop))
    else:
        st.caption("Ask a question above, or tap a quick button — the Oracle "
                   "replies instantly from the live radar.")

    st.divider()
    render_buy_zone_board(o_radar, o_backdrop, o_mcap_map)
    st.caption("The Oracle reads only the live Breakout Radar — no "
               "predictions beyond what the engine sees. Educational only, "
               "not financial advice.")


# ===========================================================================
# Tab 5 — Coin Analysis
# ===========================================================================
if active_section == "🪙 Coin Analysis":
    try:
        tickers = load_top_symbols(top_n)
    except Exception as exc:
        st.error(f"Could not load Binance market data: {exc}")
        st.stop()

    symbols = list(tickers["symbol"])
    default_idx = symbols.index("BTCUSDT") if "BTCUSDT" in symbols else 0
    symbol = st.selectbox(
        "Select a coin", symbols, index=default_idx,
        format_func=lambda s: s.replace("USDT", " / USDT"))

    base_asset = symbol.replace("USDT", "")
    try:
        lc_metrics = load_lunarcrush_coin(base_asset)
    except Exception:
        lc_metrics = None

    # Multi-timeframe analysis — derivatives and social sentiment feed every
    # timeframe's signal.
    per_tf: dict[str, dict] = {}
    enriched_by_tf: dict[str, pd.DataFrame] = {}
    for tf in config.TIMEFRAMES:
        try:
            raw = load_klines(symbol, tf)
            enriched = indicators.enrich(raw)
            enriched_by_tf[tf] = enriched
            try:
                deriv = load_derivatives(symbol, tf)
            except Exception:
                deriv = None
            per_tf[tf] = signals.analyze(
                enriched, deriv, lc_metrics, trade_mode)
        except Exception:
            continue

    if not per_tf:
        st.error("Could not analyse this coin right now. Try refreshing.")
        st.stop()

    agg = signals.aggregate(per_tf)
    detail = per_tf.get(timeframe) or next(iter(per_tf.values()))
    detail_tf = timeframe if timeframe in per_tf else next(iter(per_tf))
    edf = enriched_by_tf[detail_tf]

    try:
        tv_rating = load_tv_rating(symbol, detail_tf)
    except Exception:
        tv_rating = None

    # ---- Verdict row: bias, action, TradingView, confidence gauge --------
    try:
        flow_snap = load_orderflow(symbol)
    except Exception:
        flow_snap = {"flow": None, "book": None}

    _trow = tickers[tickers["symbol"] == symbol]
    ticker_row = _trow.iloc[0] if not _trow.empty else None
    df1d = enriched_by_tf.get("1d")
    plan = detail.get("trade_plan")

    sup_levels, res_levels = indicators.swing_levels(edf)
    nearest_sup = max((s for s in sup_levels if s < detail["price"]),
                      default=None)
    nearest_res = min((r for r in res_levels if r > detail["price"]),
                      default=None)

    render_bottom_line(agg, detail, per_tf, tv_rating, flow_snap, lc_metrics)

    st.markdown(
        f"### {symbol.replace('USDT', ' / USDT')} — multi-timeframe verdict")
    vc1, vc2, vc3, vc4 = st.columns([1.1, 1.1, 1.1, 1.3])
    with vc1:
        st.caption("DIRECTIONAL BIAS — which side to hold")
        st.markdown(label_badge(agg["bias_label"]), unsafe_allow_html=True)
        st.caption(f"Score {agg['bias_score']:+.0f} · trend · MACD · derivatives")
    with vc2:
        st.caption("ENTRY ACTION — whether to act now")
        st.markdown(label_badge(agg["action_label"]), unsafe_allow_html=True)
        st.caption(f"Score {agg['action_score']:+.0f} · RSI · Stoch · Bollinger")
    with vc3:
        st.caption(f"TRADINGVIEW — independent rating ({detail_tf})")
        if tv_rating:
            st.markdown(label_badge(tv_rating["recommendation"].upper()),
                        unsafe_allow_html=True)
            st.caption(f"{tv_rating['buy']} buy · {tv_rating['neutral']} "
                       f"neutral · {tv_rating['sell']} sell")
        else:
            st.markdown(label_badge("NEUTRAL"), unsafe_allow_html=True)
            st.caption("rating unavailable")
    with vc4:
        st.caption(f"SIGNAL CONFIDENCE — {detail_tf}")
        st.plotly_chart(confidence_gauge(detail["confidence"]),
                        use_container_width=True,
                        config={"displayModeBar": False})

    _tf_long = sum(1 for a in per_tf.values() if a["bias_score"] > 5)
    _tf_short = sum(1 for a in per_tf.values() if a["bias_score"] < -5)
    _bd_bull = sum(1 for b in detail["breakdown"] if b["signal"] == "Bullish")
    _bd_bear = sum(1 for b in detail["breakdown"] if b["signal"] == "Bearish")
    st.caption(
        f"🔗 **Confluence** — {_tf_long}/{len(per_tf)} timeframes lean long, "
        f"{_tf_short} lean short · on {detail_tf}: {_bd_bull} bullish / "
        f"{_bd_bear} bearish across {len(detail['breakdown'])} indicators. "
        f"Bias and timing are scored separately, so a long bias can still "
        f"pair with a 'wait' on entry.")

    # ---- Action plan -----------------------------------------------------
    if plan:
        render_action_plan(plan, detail["regime"], detail["confidence"],
                            symbol, agg, nearest_sup, nearest_res)
    else:
        with st.container(border=True):
            if trade_mode == "spot" and "SHORT" in detail["label"]:
                st.markdown("#### 📋 Action Plan — NO SPOT TRADE")
                st.info(
                    f"The {detail_tf} bias is bearish ({detail['label']}). "
                    f"Spot is long-only — there is no trade to take here. "
                    f"Switch to Futures mode to see the short setup, or wait "
                    f"for the bias to turn bullish for a spot buy.")
            else:
                st.markdown("#### 📋 Action Plan — STAND ASIDE")
                st.info(
                    f"No high-conviction setup on the {detail_tf} timeframe — "
                    f"the composite signal is NEUTRAL. Wait for directional "
                    f"bias and entry timing to align before committing risk.")

    # ---- Live order flow + price history ---------------------------------
    oc1, oc2 = st.columns(2)
    with oc1:
        render_orderflow(flow_snap)
    with oc2:
        render_history(symbol, df1d, ticker_row, detail,
                       (nearest_sup, nearest_res))

    # ---- LunarCrush social intelligence ----------------------------------
    render_lunarcrush(lc_metrics, base_asset)

    # ---- Live, interactive TradingView chart -----------------------------
    st.markdown(f"#### 📈 Live TradingView chart · {detail_tf}")
    tradingview_chart(symbol, detail_tf)

    # ---- Per-timeframe signal cards --------------------------------------
    st.markdown("#### Signal by timeframe")
    tf_cols = st.columns(len(config.TIMEFRAMES))
    for col, tf in zip(tf_cols, config.TIMEFRAMES):
        with col:
            if tf in per_tf:
                a = per_tf[tf]
                st.markdown(f"**{tf}** · _{a['regime']}_")
                st.markdown(f"Bias {label_badge(a['bias_label'])}",
                            unsafe_allow_html=True)
                st.markdown(f"Action {label_badge(a['action_label'])}",
                            unsafe_allow_html=True)
                st.progress(int(a["confidence"]),
                            text=f"{a['confidence']}% confidence")
            else:
                st.markdown(f"**{tf}**")
                st.caption("no data")

    st.divider()

    left, right = st.columns([2, 1])

    with left:
        st.markdown(f"#### Indicator chart · {detail_tf}")
        plot = edf.tail(120)
        fig = make_subplots(
            rows=3, cols=1, shared_xaxes=True,
            row_heights=[0.6, 0.2, 0.2], vertical_spacing=0.03,
            subplot_titles=("", "RSI", "Volume"))

        fig.add_trace(go.Candlestick(
            x=plot.index, open=plot["open"], high=plot["high"],
            low=plot["low"], close=plot["close"], name="Price"),
            row=1, col=1)
        for col_name, color in [("ema_fast", "#f5a623"),
                                ("ema_slow", "#4a90d9")]:
            fig.add_trace(go.Scatter(
                x=plot.index, y=plot[col_name], name=col_name,
                line=dict(color=color, width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=plot.index, y=plot["vwap"], name="VWAP",
            line=dict(color="#e056fd", width=1.2, dash="dash")), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=plot.index, y=plot["bb_upper"], name="BB upper",
            line=dict(color="#999", width=1, dash="dot")), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=plot.index, y=plot["bb_lower"], name="BB lower",
            line=dict(color="#999", width=1, dash="dot"),
            fill="tonexty", fillcolor="rgba(150,150,150,0.08)"), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=plot.index, y=plot["rsi"], name="RSI",
            line=dict(color="#9b59b6", width=1.5)), row=2, col=1)
        fig.add_hline(y=70, line=dict(color="#ff6b5b", width=1, dash="dash"),
                      row=2, col=1)
        fig.add_hline(y=30, line=dict(color="#34c759", width=1, dash="dash"),
                      row=2, col=1)

        vol_colors = ["#34c759" if c >= o else "#ff6b5b"
                      for c, o in zip(plot["close"], plot["open"])]
        fig.add_trace(go.Bar(
            x=plot.index, y=plot["volume"], name="Volume",
            marker_color=vol_colors), row=3, col=1)

        fig.update_layout(
            height=620, margin=dict(l=10, r=10, t=20, b=10),
            xaxis_rangeslider_visible=False, showlegend=False,
            template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Price panel: candles · EMA fast/slow · VWAP (dashed "
                   "magenta) · Bollinger Bands. Lower panels: RSI & volume.")

    with right:
        st.markdown(f"#### Signal detail · {detail_tf}")
        b1, b2 = st.columns(2)
        b1.caption("Directional bias")
        b1.markdown(label_badge(detail["bias_label"]), unsafe_allow_html=True)
        b2.caption("Entry action")
        b2.markdown(label_badge(detail["action_label"]), unsafe_allow_html=True)

        m1, m2 = st.columns(2)
        m1.metric("Bias score", f"{detail['bias_score']:+.0f}")
        m2.metric("Action score", f"{detail['action_score']:+.0f}")
        m1.metric("ADX · trend strength",
                  f"{detail['adx']}" if detail["adx"] is not None else "—",
                  detail["regime"])
        m2.metric("Volatility (ATR)",
                  f"{detail['atr_pct']}%" if detail['atr_pct'] else "—")

        bd = pd.DataFrame(detail["breakdown"])
        bd_view = pd.DataFrame({
            "Group": bd["group"],
            "Indicator": bd["indicator"],
            "Signal": bd["signal"],
            "Score": bd["score"],
            "Notes": bd["detail"],
        })
        st.dataframe(
            bd_view.style.map(
                lambda v: f"color:{MOOD_COLORS.get(v, '#888')};font-weight:600;",
                subset=["Signal"]),
            use_container_width=True, hide_index=True,
            column_config={
                "Score": st.column_config.ProgressColumn(
                    "Score", min_value=-100, max_value=100, format="%d"),
            })

        if tv_rating:
            st.markdown("#### TradingView cross-check")
            t1, t2 = st.columns(2)
            t1.metric("Oscillators", tv_rating["oscillators"])
            t2.metric("Moving averages", tv_rating["moving_averages"])
            st.caption(
                f"TradingView consensus **{tv_rating['recommendation']}** — "
                f"{tv_rating['buy']} buy / {tv_rating['neutral']} neutral / "
                f"{tv_rating['sell']} sell indicators.")

        dv = detail.get("derivatives")
        if dv:
            st.markdown("#### Derivatives positioning")
            d1, d2 = st.columns(2)
            d1.metric("Funding rate", f"{dv['funding'] * 100:+.4f}%")
            if dv.get("long_short_ratio") is not None:
                d2.metric("Long / Short ratio", f"{dv['long_short_ratio']:.2f}")
            if dv.get("oi_change_pct") is not None:
                d1.metric("Open interest trend", f"{dv['oi_change_pct']:+.1f}%")
            st.caption("Perpetual funding, trader long/short ratio and "
                       "open-interest trend — leverage & positioning context.")


# ===========================================================================
# Tab 6 — News & Sentiment
# ===========================================================================
if active_section == "📰 News & Sentiment":
    st.subheader("Market Sentiment & Live News")

    sleft, sright = st.columns([1, 2])

    with sleft:
        if fg:
            gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=fg["value"],
                title={"text": f"Fear & Greed<br><sup>{fg['label']}</sup>"},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": "#222"},
                    "steps": [
                        {"range": [0, 25], "color": "#c1121f"},
                        {"range": [25, 45], "color": "#ff6b5b"},
                        {"range": [45, 55], "color": "#8e8e93"},
                        {"range": [55, 75], "color": "#34c759"},
                        {"range": [75, 100], "color": "#0b8a3e"},
                    ],
                }))
            gauge.update_layout(height=260, margin=dict(l=20, r=20, t=50, b=10),
                                template="plotly_dark")
            st.plotly_chart(gauge, use_container_width=True)
        else:
            st.warning("Fear & Greed index unavailable.")

    with sright:
        if fg is not None and not fg["history"].empty:
            hist = fg["history"]
            line = go.Figure(go.Scatter(
                x=hist["timestamp"], y=hist["value"],
                mode="lines", line=dict(color="#4a90d9", width=2),
                fill="tozeroy", fillcolor="rgba(74,144,217,0.15)"))
            line.update_layout(
                height=260, margin=dict(l=10, r=10, t=30, b=10),
                title="Fear & Greed — last 30 days",
                template="plotly_dark", yaxis_range=[0, 100])
            st.plotly_chart(line, use_container_width=True)

    st.divider()
    try:
        lc_rows = load_lunarcrush_list()
    except Exception:
        lc_rows = []
    render_lunarcrush_leaderboard(lc_rows)
    st.divider()

    if news_df.empty:
        st.warning("News feeds are unavailable right now. Try refreshing.")
    else:
        # Per-category mood strip.
        cats = list(config.NEWS_FEEDS.keys())
        mcols = st.columns(len(cats))
        for col, cat in zip(mcols, cats):
            mood = news_mod.category_mood(news_df, cat)
            col.metric(cat, mood["mood"],
                       f"{mood['score']:+.2f} · {mood['count']} stories")

        st.divider()

        fcol1, fcol2 = st.columns([2, 1])
        chosen = fcol1.multiselect(
            "Categories", cats, default=cats)
        mood_filter = fcol2.selectbox(
            "Sentiment", ["All", "Bullish", "Bearish", "Neutral"])

        view = news_df[news_df["category"].isin(chosen)]
        if mood_filter != "All":
            view = view[view["mood"] == mood_filter]

        st.caption(f"{len(view)} stories · newest first")
        for _, row in view.head(60).iterrows():
            color = MOOD_COLORS.get(row["mood"], "#888")
            when = row["published"].strftime("%b %d %H:%M UTC")
            st.markdown(
                f"<div style='border-left:3px solid {color};"
                f"padding:4px 12px;margin-bottom:8px'>"
                f"<a href='{row['link']}' target='_blank' "
                f"style='font-weight:600;text-decoration:none;color:inherit'>"
                f"{row['title']}</a><br>"
                f"<span style='color:#888;font-size:0.8rem'>"
                f"{row['source']} · {row['category']} · {when} · "
                f"<span style='color:{color}'>{row['mood']} "
                f"({row['sentiment']:+.2f})</span></span></div>",
                unsafe_allow_html=True)

    # --- Social buzz (Reddit) — free, ToS-compliant stand-in for X --------
    st.divider()
    st.subheader("Social Buzz · Reddit")
    st.caption("Retail/social sentiment from Reddit — a free, "
               "Terms-of-Service-compliant alternative to X/Twitter, which no "
               "longer offers free data access. Mood is upvote-weighted.")

    try:
        social_df = load_social()
    except Exception:
        social_df = pd.DataFrame()

    if social_df.empty:
        st.warning("Reddit social feed is unavailable right now. Try refreshing.")
    else:
        scats = list(config.SOCIAL_FEEDS.keys())
        sm_cols = st.columns(len(scats))
        for col, cat in zip(sm_cols, scats):
            mood = social_mod.social_mood(social_df, cat)
            col.metric(f"{cat} buzz", mood["mood"],
                       f"{mood['score']:+.2f} · {mood['count']} posts")

        st.caption(f"{len(social_df)} hot posts · most-upvoted first")
        for _, row in social_df.sort_values(
                "upvotes", ascending=False).head(40).iterrows():
            color = MOOD_COLORS.get(row["mood"], "#888")
            when = row["published"].strftime("%b %d %H:%M UTC")
            st.markdown(
                f"<div style='border-left:3px solid {color};"
                f"padding:4px 12px;margin-bottom:8px'>"
                f"<a href='{row['link']}' target='_blank' "
                f"style='font-weight:600;text-decoration:none;color:inherit'>"
                f"{row['title']}</a><br>"
                f"<span style='color:#888;font-size:0.8rem'>"
                f"{row['source']} · ▲{row['upvotes']:,} · "
                f"{row['comments']:,} comments · {when} · "
                f"<span style='color:{color}'>{row['mood']} "
                f"({row['sentiment']:+.2f})</span></span></div>",
                unsafe_allow_html=True)


# ===========================================================================
# Tab 7 — Decision Mode
# ===========================================================================
if active_section == "🧭 Decision Mode":
    st.subheader("🧭 Decision Mode — Top 30 Coins")
    st.caption(f"Buy / hold / sell calls for the 30 strongest opportunities "
               f"right now — ranked on a blend of signal strength, social "
               f"sentiment, recent performance and market size, on the "
               f"{timeframe} timeframe. Each call includes entry timing, "
               f"hold horizon, an outlook and the data behind it.")

    try:
        d_tickers = load_top_symbols(top_n)
        d_scan = scan_market(tuple(d_tickers["symbol"]), timeframe, trade_mode)
    except Exception as exc:
        st.error(f"Could not load market data: {exc}")
        d_scan = pd.DataFrame()

    if d_scan.empty:
        st.warning("No analysis available right now — try refreshing.")
    else:
        d_merged = d_scan.merge(
            d_tickers[["symbol", "priceChangePercent", "quoteVolume"]],
            on="symbol", how="left")

        # LunarCrush social data feeds the ranking, so fetch it first.
        d_lc = load_lunarcrush_top() if lunarcrush.is_configured() else {}

        # Blended rank: signal strength (dominant) + confidence + social
        # sentiment + 24h performance + a small market-size factor.
        _bases = d_merged["symbol"].str.replace("USDT", "", regex=False)
        d_merged["_sent"] = [
            float(d_lc.get(b, {}).get("sentiment") or 50.0) for b in _bases]
        d_merged["_perf"] = (
            d_merged["priceChangePercent"].clip(-15, 15) + 15) / 30 * 100
        d_merged["_size"] = (
            d_merged["quoteVolume"].rank(pct=True).fillna(0) * 100)
        d_merged["rank_score"] = (
            d_merged["score"].abs() * 0.40
            + d_merged["confidence"] * 0.20
            + d_merged["_sent"] * 0.20
            + d_merged["_perf"] * 0.15
            + d_merged["_size"] * 0.05)
        d_merged = d_merged.sort_values(
            "rank_score", ascending=False).head(30)

        try:
            d_tv = load_tv_ratings(tuple(d_merged["symbol"]), timeframe)
        except Exception:
            d_tv = {}

        decisions = [_trade_decision(r, timeframe)
                     for _, r in d_merged.iterrows()]
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Buy / Accumulate", sum(
            1 for d in decisions if d["decision"] in ("BUY", "ACCUMULATE")))
        s2.metric("Hold / Wait", sum(
            1 for d in decisions if d["decision"] == "HOLD / WAIT"))
        s3.metric("Reduce / Sell", sum(
            1 for d in decisions
            if d["decision"] in ("REDUCE", "SELL / AVOID")))
        s4.metric("Timeframe", timeframe)
        st.divider()

        for (_, r), dec in zip(d_merged.iterrows(), decisions):
            base_sym = r["symbol"].replace("USDT", "")
            tv = d_tv.get(r["symbol"], {})
            lc = d_lc.get(base_sym, {})
            with st.container(border=True):
                st.markdown(
                    f"<h4 style='margin:0 0 4px 0'>{base_sym} / USDT "
                    f"&nbsp;<span style='background:{dec['color']};"
                    f"color:#06121f;padding:3px 13px;border-radius:7px;"
                    f"font-size:0.8rem;font-weight:800'>{dec['decision']}"
                    f"</span><span style='float:right;color:#8b8d98;"
                    f"font-size:0.8rem;font-weight:600'>composite "
                    f"{r['score']:+.0f} · {r['confidence']}% confidence"
                    f"</span></h4>", unsafe_allow_html=True)

                m = st.columns(6)
                m[0].metric("Price", fmt_price(r["price"]))
                m[1].metric("24h", f"{r['priceChangePercent']:+.2f}%")
                m[2].metric("24h volume", fmt_volume(r["quoteVolume"]))
                m[3].metric("RSI", r["rsi"])
                m[4].metric("TradingView", tv.get("recommendation", "—"))
                _sent = lc.get("sentiment")
                m[5].metric("Social sentiment",
                            f"{_sent:.0f}%" if _sent is not None else "—")

                st.markdown(f"**Decision:** {dec['decision']} · "
                            f"**when to open:** {dec['when']}")
                st.markdown(f"**Hold duration:** {dec['hold']}")
                st.markdown(f"**Read:** {r['bias_label']} bias · "
                            f"{r['action_label']} timing · {r['regime']} "
                            f"market regime")
                _plan = r.get("trade_plan")
                if isinstance(_plan, dict):
                    st.markdown(
                        f"**Trade levels:** entry "
                        f"{fmt_price(_plan['entry_low'])}–"
                        f"{fmt_price(_plan['entry_high'])} · stop "
                        f"{fmt_price(_plan['stop_loss'])} · targets "
                        f"{fmt_price(_plan['take_profit'])} / "
                        f"{fmt_price(_plan['take_profit_2'])} · "
                        f"R:R {_plan['risk_reward']:.1f}")
                st.caption("📈 Prediction — " + dec["outlook"])

        st.caption("Decisions are algorithmic — derived from technicals, "
                   "derivatives, live order flow and social data. "
                   "Educational only, not financial advice.")


# ===========================================================================
# Tab 8 — Paper Trader (bot that tests the signals with virtual money)
# ===========================================================================
if active_section == "🧪 Paper Trader":
    st.subheader("🧪 Paper Trading Bot")
    st.caption(
        "Open trades on any coin from the left panel, or let the bot "
        "auto-trade from high-confidence alerts. The bot manages stops "
        "and targets every scan and tracks every trade. State persists "
        "to `.paper_bot.json` so a run survives refreshes and full app "
        "restarts.")

    pb_state = paper_bot.load_state(PAPER_BOT_FILE)

    # ---- Settings (collapsed so the trade UI is the focus) ---------------
    with st.expander("⚙️ Settings — balance, risk, auto-trade, live, reset"):
        c1, c2, c3, c4, c5 = st.columns([1.2, 1.2, 1.3, 1.1, 1.1])
        new_balance = c1.number_input(
            "Starting balance ($)", min_value=100.0, max_value=1_000_000.0,
            value=float(pb_state.get("starting_balance") or 10000.0),
            step=500.0, key="pb_start_balance")
        new_risk = c2.slider(
            "Risk per trade (%)", 0.25, 5.0,
            float(pb_state.get("risk_per_trade_pct") or 1.0), 0.25,
            key="pb_risk")
        auto_trade = c3.checkbox(
            "🟢 Auto-trade from alerts", value=False, key="pb_auto",
            help="When on, each scan the agent opens new positions for "
                 "every high-confidence trade alert (>= 70% confidence), "
                 "long and short.")
        live_mode = c4.checkbox(
            "🔴 Live", value=False, key="pb_live",
            help="Auto-refresh every 5 min so the bot actively manages "
                 "positions and watches for new alerts without you "
                 "reloading the page.")
        if c5.button("🔄 Reset", type="secondary",
                     use_container_width=True):
            paper_bot.reset(PAPER_BOT_FILE, new_balance, new_risk)
            st.rerun()

    # ---- Helpers used in this section ------------------------------------
    def _hold_horizon(tf):
        """Suggested holding period — capped at 1-2 days per user preference.

        The agent is a short-term swing/intraday trader; positions are not
        intended to be held longer than ~2 days regardless of timeframe."""
        return {"15m": "a few hours",
                "1h": "1 day",
                "4h": "1-2 days",
                "1d": "1-2 days"}.get(tf, "1-2 days")

    def _strength_label(conf):
        """Confidence → (label, colour) for a signal-strength badge."""
        if conf >= 80:
            return ("Very Strong", "#0b8a3e")
        if conf >= 70:
            return ("Strong", "#2ed47a")
        if conf >= 60:
            return ("Moderate", "#e0a92b")
        return ("Weak", "#8b8d98")

    def _enrich_position(pos, conf, tf, label_override=None):
        """Stamp a position with the metadata the UI shows back."""
        if pos is None:
            return None
        pos["hold_horizon"] = _hold_horizon(tf)
        pos["strength_label"] = (label_override
                                 if label_override is not None
                                 else _strength_label(conf)[0])
        pos["timeframe"] = tf
        return pos

    def _render_position_chart(symbol, side, entry, stop, target, cur_price):
        """Mini chart for one open position — recent 1h price line with
        Entry / Stop / Target levels and a live-price dot."""
        try:
            kdf = load_klines(symbol, "1h").tail(72)
        except Exception:
            return
        if kdf is None or kdf.empty:
            return
        line_color = "#2ed47a" if side == "LONG" else "#ff5c5c"
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=kdf.index, y=kdf["close"], mode="lines",
            line=dict(color=line_color, width=2),
            showlegend=False, name="Price"))
        # Live price dot at the right edge.
        fig.add_trace(go.Scatter(
            x=[kdf.index[-1]], y=[cur_price], mode="markers",
            marker=dict(color="#fff", size=9,
                        line=dict(color=line_color, width=2)),
            showlegend=False, name="Now"))
        for level, lcol, name in (
                (entry,  "#6e8bff", f"Entry {fmt_price(entry)}"),
                (stop,   "#ff5c5c", f"Stop {fmt_price(stop)}"),
                (target, "#2ed47a", f"Target {fmt_price(target)}")):
            fig.add_hline(
                y=level, line_color=lcol,
                line_dash="dot" if name.startswith("Entry") else "dash",
                annotation_text=name, annotation_position="right",
                annotation=dict(font=dict(size=10, color=lcol)))
        fig.update_layout(
            height=180, margin=dict(l=0, r=90, t=10, b=10),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=False, color="#888"),
            yaxis=dict(showgrid=False, color="#888"))
        st.plotly_chart(
            fig, use_container_width=True,
            config={"displayModeBar": False})

    # ------------------------------------------------------------------
    # Live-updating fragments — these refresh IN PLACE every 10 seconds
    # without reloading the whole page. They each re-read paper-bot state
    # from disk so a Close action or weekly reset is reflected immediately.
    # ------------------------------------------------------------------
    @st.fragment(run_every=10)
    def _live_paper_stats():
        """Bank + trade stats row, live-updating."""
        state = paper_bot.load_state(PAPER_BOT_FILE)
        live_p: dict[str, float] = {}
        for _p in state["open"]:
            _lp = live_price(_p["symbol"])
            live_p[_p["symbol"]] = (
                float(_lp) if _lp is not None and _lp > 0
                else float(_p["entry"]))

        bal = float(state["balance"])
        start_bal = float(state.get("starting_balance") or bal)
        margin_used = paper_bot.open_margin_used(state)
        unreal = paper_bot.unrealized_pnl(state, live_p)
        available = bal - margin_used
        equity = bal + unreal
        realized = bal - start_bal
        realized_pct = ((realized / start_bal * 100)
                        if start_bal else 0.0)

        bc = st.columns(5)
        bc[0].metric(
            "💰 Bank balance", f"${bal:,.2f}",
            f"{realized_pct:+.2f}% since start",
            help="Realised cash. Updates only when a trade closes.")
        bc[1].metric(
            "Available", f"${available:,.2f}",
            f"-${margin_used:,.0f} in trades" if margin_used > 0
            else "all free",
            help="Free to deploy — bank balance minus locked margin.")
        unr_arrow = "↑" if unreal >= 0 else "↓"
        bc[2].metric(
            "Unrealised P&L", f"${unreal:+,.2f}",
            f"{unr_arrow} from open positions",
            help="Live mark-to-market across open positions.")
        bc[3].metric(
            "📊 Equity", f"${equity:,.2f}",
            f"${realized:+,.0f} realised",
            help="Bank balance + unrealised P&L.")
        bc[4].metric(
            "Realised P&L", f"${realized:+,.2f}",
            f"{realized_pct:+.2f}% of start",
            help="Total realised since the period started.")

        st_stats = paper_bot.stats(state)
        _elapsed = max(0.0, time.time() - float(
            state.get("started_at") or time.time()))
        _days_left = (paper_bot.WEEKLY_RESET_DAYS
                      - _elapsed / 86400.0)
        _reset_txt = (f"{_days_left:.1f} days"
                      if _days_left > 0 else "next refresh")
        sc = st.columns(5)
        sc[0].metric("Trades closed", st_stats["trades"])
        sc[1].metric("Win rate",
                     f"{st_stats['win_rate']:.0f}%"
                     if st_stats["trades"] else "—")
        sc[2].metric("Best trade",
                     f"{st_stats['best_trade']:+.2f}%"
                     if st_stats["trades"] else "—")
        sc[3].metric("Worst trade",
                     f"{st_stats['worst_trade']:+.2f}%"
                     if st_stats["trades"] else "—")
        sc[4].metric("⏰ Resets in", _reset_txt,
                     f"to ${start_bal:,.0f}",
                     help=(f"Auto-restores to ${start_bal:,.0f} every "
                           f"{paper_bot.WEEKLY_RESET_DAYS} days."))

    @st.fragment(run_every=10)
    def _live_paper_positions():
        """Open-position cards, live-updating. Also re-runs the stop/target
        evaluator on every tick so a hit fires in seconds, not minutes."""
        state = paper_bot.load_state(PAPER_BOT_FILE)
        live_p: dict[str, float] = {}
        for _p in state["open"]:
            _lp = live_price(_p["symbol"])
            live_p[_p["symbol"]] = (
                float(_lp) if _lp is not None and _lp > 0
                else float(_p["entry"]))

        # Evaluate stops/targets on every fragment tick with live prices.
        closed_now = paper_bot.evaluate(state, live_p)
        for c in closed_now:
            emoji = "✅" if c["pnl_usd"] > 0 else "❌"
            st.toast(
                f"{emoji} {c['base']} closed at {c['exit_reason']} · "
                f"{c['pnl_pct']:+.2f}%", icon="🧪")
        if closed_now:
            paper_bot.save_state(PAPER_BOT_FILE, state)

        st.markdown(f"### 📂 Open positions ({len(state['open'])})")
        if not state["open"]:
            st.info(
                "No open positions. Use the panel on the left to open a "
                "trade, or toggle **Auto-trade** in Settings to let the "
                "bot trade alerts automatically.")
            return

        for p in state["open"]:
            cur = live_p.get(p["symbol"], p["entry"])
            long = (p["side"] == "LONG")
            entry_v = float(p["entry"])
            stop_v = float(p["stop"])
            target_v = float(p["target"])
            qty_v = float(p["qty"])
            notional_v = float(p.get("notional") or (qty_v * entry_v))
            lev_v = int(p.get("leverage") or 1)
            unreal_pos = (((cur - entry_v) if long
                           else (entry_v - cur)) * qty_v)
            unreal_pct_pos = (unreal_pos / state["balance"] * 100
                              if state["balance"] else 0.0)
            if entry_v > 0:
                pct_from_entry = ((cur - entry_v) / entry_v * 100)
                if not long:
                    pct_from_entry = -pct_from_entry
            else:
                pct_from_entry = 0.0
            color = "#2ed47a" if unreal_pos >= 0 else "#ff5c5c"
            side_color = "#2ed47a" if long else "#ff5c5c"
            if long:
                if cur >= entry_v:
                    prog = (((cur - entry_v) / (target_v - entry_v)
                             * 50 + 50)
                            if target_v != entry_v else 50)
                else:
                    prog = ((50 - (entry_v - cur) / (entry_v - stop_v)
                             * 50)
                            if entry_v != stop_v else 50)
            else:
                if cur <= entry_v:
                    prog = (((entry_v - cur) / (entry_v - target_v)
                             * 50 + 50)
                            if entry_v != target_v else 50)
                else:
                    prog = ((50 - (cur - entry_v) / (stop_v - entry_v)
                             * 50)
                            if stop_v != entry_v else 50)
            health = int(max(0, min(100, prog)))
            hold_txt = p.get("hold_horizon") or "—"
            str_label = p.get("strength_label", "")
            be_badge = (" · ✓ break-even"
                        if p.get("break_even_set") else "")
            lev_txt = f" · {lev_v}× lev" if lev_v > 1 else ""

            with st.container(border=True):
                info_col, pnl_col, btn_col = st.columns([2.4, 1.8, 0.8])
                info_col.markdown(
                    f"<div style='font-size:1.05rem;font-weight:800;"
                    f"margin-bottom:2px'>{p['base']} "
                    f"<span style='background:{side_color};color:#06121f;"
                    f"padding:2px 10px;border-radius:5px;font-size:"
                    f"0.72rem;font-weight:800;margin-left:6px'>"
                    f"{p['side']}</span></div>"
                    f"<div style='color:#d5d7e0;font-size:0.84rem;"
                    f"margin:3px 0'>"
                    f"<b>{qty_v:.6f} {p['base']}</b> · "
                    f"notional <b>${notional_v:,.2f}</b>{lev_txt}</div>"
                    f"<div style='color:#8b8d98;font-size:0.78rem'>"
                    f"Entry {fmt_price(entry_v)} · Stop "
                    f"{fmt_price(stop_v)} · Target {fmt_price(target_v)}"
                    f" · hold: {hold_txt}"
                    + (f" · {str_label}" if str_label else "")
                    + be_badge + "</div>",
                    unsafe_allow_html=True)
                pnl_col.markdown(
                    f"<div style='text-align:right;font-size:1.15rem;"
                    f"font-weight:800;color:#fff'>{fmt_price(cur)}</div>"
                    f"<div style='text-align:right;color:{color};"
                    f"font-size:1.1rem;font-weight:800;margin-top:2px'>"
                    f"${unreal_pos:+,.2f}</div>"
                    f"<div style='text-align:right;color:{color};"
                    f"font-size:0.78rem;font-weight:700;margin-top:1px'>"
                    f"{pct_from_entry:+.2f}% from entry · "
                    f"{unreal_pct_pos:+.2f}% balance</div>",
                    unsafe_allow_html=True)
                if btn_col.button(
                        "Close", key=f"pb_close_{p['symbol']}",
                        use_container_width=True):
                    cl = paper_bot.close_position_at(
                        state, p["symbol"], cur, reason="manual")
                    if cl:
                        paper_bot.save_state(PAPER_BOT_FILE, state)
                        emoji = "✅" if cl["pnl_usd"] > 0 else "❌"
                        st.toast(
                            f"{emoji} Closed {cl['base']} · "
                            f"{cl['pnl_pct']:+.2f}%", icon="🧪")
                        st.rerun(scope="fragment")
                st.progress(health, text=(
                    f"🎯 {health}% toward target"
                    if health >= 50
                    else f"⚠️ {100 - health}% toward stop"))
                _render_position_chart(
                    p["symbol"], p["side"],
                    entry_v, stop_v, target_v, cur)

    # Apply latest settings — only adopt new balance on a fresh book.
    pb_state["risk_per_trade_pct"] = float(new_risk)
    if not pb_state.get("closed") and not pb_state.get("open"):
        pb_state["starting_balance"] = float(new_balance)
        pb_state["balance"] = float(new_balance)

    # ---- Live price map for every open position ---------------------------
    # Start with the cached scanner prices, then OVERRIDE each open
    # position's price with a fresh live fetch (5-second cache). That way
    # the position cards, P&L and chart dot reflect a near-real-time price
    # even when the 120-second scanner cache is still warm.
    prices: dict[str, float] = {}
    if not _alert_merged.empty:
        prices = dict(zip(_alert_merged["symbol"], _alert_merged["price"]))
    for _p in pb_state["open"]:
        _lp = live_price(_p["symbol"])
        if _lp is not None and _lp > 0:
            prices[_p["symbol"]] = float(_lp)

    # ---- ALWAYS evaluate stops/targets first (with live prices) ----------
    just_closed = paper_bot.evaluate(pb_state, prices)
    for c in just_closed:
        emoji = "✅" if c["pnl_usd"] > 0 else "❌"
        st.toast(
            f"{emoji} {c['base']} closed at {c['exit_reason']} · "
            f"{c['pnl_pct']:+.2f}%", icon="🧪")

    # ---- Auto-trade from alerts ------------------------------------------
    auto_ad = (alerts.build_alerts(_alert_merged, timeframe)
               if not _alert_merged.empty else {"setups": []})
    if auto_trade:
        for setup in auto_ad["setups"]:
            if setup.get("confidence", 0) >= 70:
                opened = paper_bot.open_position(
                    pb_state, setup,
                    prices.get(setup["symbol"]) or setup.get("entry_low"))
                if opened:
                    _enrich_position(opened,
                                     setup.get("confidence", 0), timeframe)
                    st.toast(
                        f"📥 Auto-opened {opened['side']} {opened['base']} "
                        f"@ {fmt_price(opened['entry'])}", icon="🧪")

    # ---- Track persistence of bot suggestions ----------------------------
    # An alert that stays on the board for many minutes is more trustworthy
    # than one that just flickered in; show 'alive for X min' on each pick.
    now_ts = time.time()
    sp = pb_state.setdefault("suggestion_persistence", {})
    current_setup_ids: set[str] = set()
    for _s in auto_ad["setups"]:
        _sid = f"{_s['symbol']}:{_s['side']}"
        current_setup_ids.add(_sid)
        if _sid not in sp:
            sp[_sid] = now_ts
    for _sid in list(sp.keys()):
        if _sid not in current_setup_ids:
            del sp[_sid]

    # ---- Weekly auto-reset to the starting balance -----------------------
    _reset_info = paper_bot.check_weekly_reset(pb_state, prices)
    if _reset_info["reset"]:
        st.success(
            f"⏰ Weekly reset! Balance restored to "
            f"${pb_state['starting_balance']:,.0f}. "
            f"{len(_reset_info['closed_at_reset'])} open position(s) "
            f"were closed at market — the closed-trades history is "
            f"preserved so you can review the previous period.")

    paper_bot.save_state(PAPER_BOT_FILE, pb_state)

    # ---- Bank + trade stats — LIVE fragment (updates in place every 10s)
    _live_paper_stats()

    st.divider()

    # ---- Main two-column layout: LEFT = open new trade, RIGHT = positions
    left_col, right_col = st.columns([1, 2])

    with left_col:
        st.markdown("### 📥 Open a trade")
        if _alert_merged.empty:
            st.info("Scan data not ready — refresh and try again.")
        else:
            _syms = sorted(_alert_merged["symbol"].unique().tolist())
            _open_syms = {p["symbol"] for p in pb_state["open"]}
            _avail = [s for s in _syms if s not in _open_syms]
            if not _avail:
                st.warning("You already have a position in every tracked "
                           "coin — close one before opening another.")
            else:
                _sel = st.selectbox(
                    "Coin", _avail,
                    format_func=lambda s: s.replace("USDT", ""),
                    key="pb_open_sym")
                _side = st.radio(
                    "Side", ["LONG", "SHORT"], horizontal=True,
                    key="pb_open_side")
                _row_match = _alert_merged[_alert_merged["symbol"] == _sel]
                _row = (_row_match.iloc[0]
                        if not _row_match.empty else None)
                _cur = (float(_row["price"])
                        if _row is not None else 0.0)
                _chg = (float(_row.get("priceChangePercent") or 0.0)
                        if _row is not None else 0.0)
                _plan = (_row.get("trade_plan")
                         if _row is not None
                         and isinstance(_row.get("trade_plan"), dict)
                         else None)

                # ---- Live price card --------------------------------------
                _ch_color = "#2ed47a" if _chg >= 0 else "#ff5c5c"
                st.markdown(
                    f"<div style='background:#11141c;padding:10px 14px;"
                    f"border-radius:6px;margin:6px 0 10px 0;"
                    f"border:1px solid #1f2330'>"
                    f"<div style='font-size:0.7rem;color:#8b8d98;"
                    f"letter-spacing:0.08em;font-weight:700'>LIVE PRICE · "
                    f"{_sel.replace('USDT','')}/USDT</div>"
                    f"<div style='display:flex;align-items:baseline;"
                    f"gap:10px;flex-wrap:wrap'>"
                    f"<span style='font-size:1.4rem;font-weight:800;"
                    f"color:#fff'>{fmt_price(_cur)}</span>"
                    f"<span style='color:{_ch_color};font-size:0.85rem;"
                    f"font-weight:700'>{_chg:+.2f}% (24h)</span>"
                    f"</div></div>", unsafe_allow_html=True)

                # ---- Order type + entry -----------------------------------
                _order_type = st.radio(
                    "Order type", ["Market", "Limit"],
                    horizontal=True, key="pb_open_order_type")
                _combo = f"{_sel}_{_side}_{_order_type}"
                _step = (_cur * 0.001) if _cur > 0 else 0.01
                if _order_type == "Market":
                    _entry = _cur
                    st.caption(
                        f"Entry: **{fmt_price(_entry)}** (market price)")
                else:
                    _entry = st.number_input(
                        "Limit entry price", value=float(_cur),
                        format="%.8f", step=_step,
                        key=f"pb_entry_{_combo}")

                # ---- Stop & take-profit (editable) ------------------------
                if _plan and _plan.get("side") == _side:
                    _def_stop = float(_plan["stop_loss"])
                    _def_target = float(_plan["take_profit"])
                else:
                    _def_stop = _entry * (0.98 if _side == "LONG" else 1.02)
                    _def_target = _entry * (1.04 if _side == "LONG" else 0.96)
                _sc1, _sc2 = st.columns(2)
                _stop = _sc1.number_input(
                    "Stop loss", value=float(_def_stop), format="%.8f",
                    step=_step, key=f"pb_stop_{_combo}")
                _target = _sc2.number_input(
                    "Take profit", value=float(_def_target), format="%.8f",
                    step=_step, key=f"pb_target_{_combo}")

                if _entry > 0 and _stop != _entry:
                    _stop_pct = abs((_entry - _stop) / _entry * 100)
                    _target_pct = abs((_target - _entry) / _entry * 100)
                    _rr = abs(_target - _entry) / abs(_entry - _stop)
                else:
                    _stop_pct = _target_pct = _rr = 0.0
                st.caption(
                    f"Stop **{_stop_pct:.2f}%** away · Target "
                    f"**{_target_pct:.2f}%** away · R:R **{_rr:.2f}**")

                # ---- Leverage (futures only) ------------------------------
                if trade_mode == "futures":
                    _leverage = st.slider(
                        "Leverage", 1, 10, 1, key="pb_open_leverage")
                else:
                    _leverage = 1
                    st.caption("Spot mode — no leverage (1×)")

                # ---- Sizing method ----------------------------------------
                _sizing = st.radio(
                    "How to size", ["Risk-based", "Dollar amount",
                                    "Quantity", "% of balance"],
                    key="pb_sizing")
                _balance = float(pb_state["balance"])

                if _sizing == "Risk-based":
                    _risk_pct_in = st.slider(
                        "Account risk per trade (%)", 0.25, 5.0,
                        float(pb_state.get("risk_per_trade_pct", 1.0)), 0.25,
                        key="pb_risk_pct_slider")
                    _risk_dollars = _balance * _risk_pct_in / 100
                    _risk_pu = (abs(_entry - _stop)
                                if _entry != _stop else 0.0)
                    _qty = (_risk_dollars / _risk_pu
                            if _risk_pu > 0 else 0.0)
                elif _sizing == "Dollar amount":
                    _max_notional = max(_balance * _leverage, _balance)
                    _notional_in = st.number_input(
                        "Notional ($) to deploy",
                        min_value=10.0, max_value=float(_max_notional),
                        value=float(min(1000.0, _balance)),
                        step=100.0, key="pb_notional_in")
                    _qty = _notional_in / _entry if _entry > 0 else 0.0
                elif _sizing == "Quantity":
                    _qty = st.number_input(
                        f"Quantity ({_sel.replace('USDT','')})",
                        min_value=0.0, value=1.0, step=0.001,
                        format="%.6f", key="pb_qty_in")
                else:                       # % of balance
                    _pct = st.slider(
                        "% of balance to allocate", 1, 100, 10,
                        key="pb_pct_alloc")
                    _qty = ((_balance * _pct / 100 * _leverage) / _entry
                            if _entry > 0 else 0.0)

                _qty = float(_qty)
                _notional_val = _qty * _entry
                _margin = (_notional_val / _leverage
                           if _leverage > 0 else _notional_val)
                _risk_dollars_final = _qty * abs(_entry - _stop)
                _risk_pct_final = (_risk_dollars_final / _balance * 100
                                   if _balance > 0 else 0.0)
                _potential_profit = _qty * abs(_target - _entry)
                _profit_pct = (_potential_profit / _balance * 100
                               if _balance > 0 else 0.0)

                # ---- Live order summary -----------------------------------
                _summary_lines = [
                    f"Position size: <b>{_qty:.6f} "
                    f"{_sel.replace('USDT','')}</b>",
                    f"Notional value: <b>${_notional_val:,.2f}</b>",
                ]
                if trade_mode == "futures" and _leverage > 1:
                    _summary_lines.append(
                        f"Margin required: <b>${_margin:,.2f}</b> "
                        f"(at {_leverage}× leverage)")
                _summary_lines.extend([
                    f"Risk if stopped: <b style='color:#ff5c5c'>"
                    f"${_risk_dollars_final:,.2f}</b> "
                    f"({_risk_pct_final:.2f}% of balance)",
                    f"Reward if target: <b style='color:#2ed47a'>"
                    f"${_potential_profit:,.2f}</b> "
                    f"({_profit_pct:.2f}% of balance)",
                    f"R:R = <b>{_rr:.2f}R</b> · Suggested hold: "
                    f"<b>{_hold_horizon(timeframe)}</b>",
                ])
                st.markdown(
                    f"<div style='background:#0e1118;border-left:3px solid "
                    f"#6e8bff;padding:10px 14px;border-radius:5px;"
                    f"margin:8px 0'>"
                    f"<div style='font-size:0.7rem;color:#6e8bff;"
                    f"letter-spacing:0.08em;font-weight:800;"
                    f"margin-bottom:6px'>📊 LIVE ORDER SUMMARY</div>"
                    f"<div style='color:#d5d7e0;font-size:0.85rem;"
                    f"line-height:1.6'>" + "<br>".join(_summary_lines)
                    + "</div></div>", unsafe_allow_html=True)

                # ---- Validation warnings ----------------------------------
                _warnings = []
                if _side == "LONG" and _stop >= _entry:
                    _warnings.append(
                        "Stop must be BELOW entry for a LONG trade.")
                if _side == "SHORT" and _stop <= _entry:
                    _warnings.append(
                        "Stop must be ABOVE entry for a SHORT trade.")
                if _side == "LONG" and _target <= _entry:
                    _warnings.append(
                        "Take profit must be ABOVE entry for a LONG trade.")
                if _side == "SHORT" and _target >= _entry:
                    _warnings.append(
                        "Take profit must be BELOW entry for a SHORT trade.")
                if _qty <= 0:
                    _warnings.append(
                        "Position size is zero — adjust sizing inputs.")
                if _margin > _available:
                    _warnings.append(
                        f"Margin required (${_margin:,.0f}) exceeds your "
                        f"AVAILABLE cash (${_available:,.0f}). Close a "
                        f"trade or size down.")
                if _risk_pct_final > 10:
                    _warnings.append(
                        f"Risking {_risk_pct_final:.1f}% of balance — that "
                        "is aggressive; size down.")
                for _w in _warnings:
                    st.warning(f"⚠️ {_w}")

                # ---- Open button ------------------------------------------
                _can_open = (not _warnings) and _qty > 0
                _btn_label = (
                    f"📥 Open {_side} {_sel.replace('USDT','')} "
                    f"@ {fmt_price(_entry)}")
                if st.button(_btn_label, use_container_width=True,
                             type="primary", key="pb_open_btn",
                             disabled=not _can_open):
                    _manual_alert = {
                        "symbol": _sel,
                        "base": _sel.replace("USDT", ""),
                        "side": _side,
                        "stop": _stop,
                        "target": _target,
                        "entry_low": _entry,
                        "confidence": 0,
                        "rr": _rr,
                    }
                    _opened = paper_bot.open_position(
                        pb_state, _manual_alert, _entry)
                    if _opened:
                        # Override the engine's risk-based qty with the
                        # user's chosen sizing.
                        _opened["qty"] = float(_qty)
                        _opened["notional"] = float(_notional_val)
                        _opened["leverage"] = int(_leverage)
                        _opened["margin"] = float(_margin)
                        _opened["order_type"] = _order_type
                        _enrich_position(_opened, 0, timeframe,
                                         label_override="Manual")
                        paper_bot.save_state(PAPER_BOT_FILE, pb_state)
                        st.toast(
                            f"📥 Opened {_side} {_opened['base']} @ "
                            f"{fmt_price(_opened['entry'])} · qty "
                            f"{_qty:.6f}", icon="🧪")
                        st.rerun()
                    else:
                        st.error(
                            "Could not open — already have a position in "
                            "this coin.")

    with right_col:
        # ---- 🤖 Bot's top picks — what the agent would open right now ---
        st.markdown("### 🤖 Bot's top picks")
        st.caption(
            "Strongest long & short setups the agent sees right now, "
            "ranked by a COMBINED signal that fuses the Market Scanner "
            "alert with the Forecast tab's multi-horizon read. A setup "
            "where the Scanner AND the Forecast agree across all three "
            "horizons scores highest. Click 📥 to open one.")

        # Pull the live forecast data (cached so it is cheap) — used to
        # confirm or contradict each scanner setup.
        _fc_by_sym: dict[str, dict] = {}
        try:
            _fc_tickers_bot = load_top_symbols(top_n)
            _fc_syms_bot = tuple(
                _fc_tickers_bot["symbol"].head(40))
            _fc_df_bot = forecast_market(_fc_syms_bot)
            if _fc_df_bot is not None and not _fc_df_bot.empty:
                _fc_by_sym = {r["symbol"]: r.to_dict()
                              for _, r in _fc_df_bot.iterrows()}
        except Exception:
            pass

        def _combined_score(setup, fc):
            """Combined strength score: scanner confidence + forecast bonus
            when the forecast confirms, minus a penalty when it disagrees."""
            score = float(setup.get("confidence") or 0)
            if not fc:
                return score, "no forecast"
            fc_word = fc.get("outlook_word")
            fc_conf = float(fc.get("confidence") or 0)
            aligned = bool(fc.get("aligned"))
            side = setup["side"]
            confirms = ((side == "LONG" and fc_word == "Bullish")
                        or (side == "SHORT" and fc_word == "Bearish"))
            disagrees = ((side == "LONG" and fc_word == "Bearish")
                         or (side == "SHORT" and fc_word == "Bullish"))
            if confirms:
                score += 10
                if aligned:
                    score += 8        # all three horizons agree
                if fc_conf >= 70:
                    score += 5        # high-confidence forecast
                label = (f"forecast confirms · aligned 3/3"
                         if aligned else f"forecast confirms")
            elif disagrees:
                score -= 8
                label = "forecast disagrees"
            else:
                label = "forecast neutral"
            return min(99.0, score), label

        _open_syms = {p["symbol"] for p in pb_state["open"]}
        _all_picks = [s for s in auto_ad["setups"]
                      if s["symbol"] not in _open_syms]
        # Score every candidate then re-rank by the combined score.
        _scored = [
            (*_combined_score(s, _fc_by_sym.get(s["symbol"])), s)
            for s in _all_picks
        ]
        _scored.sort(key=lambda t: t[0], reverse=True)
        _bot_picks = _scored[:5]

        if not _bot_picks:
            st.info("No high-confidence setups for the agent to recommend "
                    "right now. Watch the alerts strip or switch the "
                    "timeframe.")
        else:
            for combined, fc_label, s in _bot_picks:
                side = s["side"]
                side_color = "#2ed47a" if side == "LONG" else "#ff5c5c"
                conf = int(s.get("confidence", 0) or 0)
                str_label, str_color = _strength_label(int(combined))
                sid = f"{s['symbol']}:{side}"
                alive_min = (now_ts - sp.get(sid, now_ts)) / 60.0
                alive_txt = (f"alive {alive_min:.0f} min"
                             if alive_min >= 1 else "just appeared")
                hold = _hold_horizon(timeframe)
                proof = (" · ".join(s.get("proof", [])[:2])
                         if s.get("proof") else "multiple signals align")
                rr = float(s.get("rr") or 0.0)
                fc = _fc_by_sym.get(s["symbol"]) or {}

                # Forecast confirmation chip
                fc_chip = ""
                if fc_label == "forecast confirms · aligned 3/3":
                    fc_chip = (
                        f"<span style='background:#2ed47a33;color:#2ed47a;"
                        f"padding:2px 8px;border-radius:5px;font-size:0.7rem;"
                        f"font-weight:700;margin-left:4px'>"
                        f"✓ Forecast aligned 3/3</span>")
                elif fc_label == "forecast confirms":
                    fc_chip = (
                        f"<span style='background:#6e8bff33;color:#6e8bff;"
                        f"padding:2px 8px;border-radius:5px;font-size:0.7rem;"
                        f"font-weight:700;margin-left:4px'>"
                        f"✓ Forecast confirms</span>")
                elif fc_label == "forecast disagrees":
                    fc_chip = (
                        f"<span style='background:#e0a92b33;color:#e0a92b;"
                        f"padding:2px 8px;border-radius:5px;font-size:0.7rem;"
                        f"font-weight:700;margin-left:4px'>"
                        f"⚠ Forecast disagrees</span>")

                # Forecast per-horizon line
                fc_line = ""
                if fc.get("horizons"):
                    horizon_bits = []
                    arrow = {"Up": "▲", "Down": "▼", "Sideways": "▬"}
                    for _tf in ("15m", "1h", "4h"):
                        h = fc["horizons"].get(_tf)
                        if not h:
                            continue
                        ac = ("#2ed47a" if h["direction"] == "Up"
                              else "#ff5c5c" if h["direction"] == "Down"
                              else "#8b8d98")
                        horizon_bits.append(
                            f"<span style='color:#aab'>{_tf}</span> "
                            f"<span style='color:{ac};font-weight:700'>"
                            f"{arrow.get(h['direction'], '·')} "
                            f"{h['move_pct']:+.2f}%</span>")
                    if horizon_bits:
                        fc_line = (
                            f"<div style='color:#9aa0b4;font-size:0.76rem;"
                            f"margin-top:2px'>📈 forecast — "
                            + " · ".join(horizon_bits) + "</div>")

                with st.container(border=True):
                    pa, pb = st.columns([6, 1])
                    pa.markdown(
                        f"<div style='display:flex;align-items:center;"
                        f"gap:8px;flex-wrap:wrap'>"
                        f"<span style='font-weight:800;font-size:1rem'>"
                        f"{s['base']}</span>"
                        f"<span style='background:{side_color};color:#06121f;"
                        f"padding:2px 10px;border-radius:5px;font-size:"
                        f"0.72rem;font-weight:800'>{side}</span>"
                        f"<span style='background:{str_color}33;"
                        f"color:{str_color};padding:2px 8px;border-radius:"
                        f"5px;font-size:0.72rem;font-weight:700'>"
                        f"{str_label} · {int(combined)}</span>"
                        f"{fc_chip}"
                        f"<span style='color:#8b8d98;font-size:0.78rem'>"
                        f"scanner {conf}% · R:R {rr:.1f} · "
                        f"{alive_txt}</span></div>"
                        f"<div style='color:#aab;font-size:0.78rem;"
                        f"margin-top:4px'>"
                        f"hold: <b>{hold}</b> · entry "
                        f"{fmt_price(s.get('entry_low', 0))} · stop "
                        f"{fmt_price(s.get('stop', 0))} · target "
                        f"{fmt_price(s.get('target', 0))}</div>"
                        f"<div style='color:#9aa0b4;font-size:0.78rem;"
                        f"margin-top:2px'>proof — {md_safe(proof)}</div>"
                        f"{fc_line}",
                        unsafe_allow_html=True)
                    if pb.button("📥", key=f"pb_pick_{sid}",
                                 help=f"Open this {side} {s['base']} trade",
                                 use_container_width=True):
                        _opened = paper_bot.open_position(
                            pb_state, s,
                            prices.get(s["symbol"])
                            or s.get("entry_low"))
                        if _opened:
                            _enrich_position(_opened, int(combined),
                                             timeframe)
                            paper_bot.save_state(PAPER_BOT_FILE, pb_state)
                            st.toast(
                                f"📥 Opened {side} {_opened['base']} @ "
                                f"{fmt_price(_opened['entry'])}",
                                icon="🧪")
                            st.rerun()

        st.divider()
        # Open positions — LIVE fragment (updates in place every 10s).
        _live_paper_positions()

    st.divider()

    # ---- Equity curve ----------------------------------------------------
    if pb_state["closed"]:
        cs_sorted = sorted(pb_state["closed"],
                           key=lambda c: c.get("exit_at", 0))
        bal = float(pb_state["starting_balance"])
        eq_rows = [{"Time": datetime.fromtimestamp(
                        cs_sorted[0].get("exit_at", 0),
                        tz=timezone.utc),
                    "Equity": bal}]
        for c in cs_sorted:
            bal += float(c.get("pnl_usd") or 0.0)
            eq_rows.append({
                "Time": datetime.fromtimestamp(
                    c.get("exit_at", 0), tz=timezone.utc),
                "Equity": round(bal, 2),
            })
        st.markdown("#### 📈 Equity curve")
        st.line_chart(pd.DataFrame(eq_rows).set_index("Time"),
                      use_container_width=True, height=240)

    # ---- Closed trades history -------------------------------------------
    st.markdown(f"#### 📜 Closed trades ({len(pb_state['closed'])})")
    if pb_state["closed"]:
        cs_recent = sorted(pb_state["closed"],
                           key=lambda c: c.get("exit_at", 0),
                           reverse=True)[:80]
        closed_rows = [{
            "Coin": c.get("base", ""),
            "Side": c.get("side", ""),
            "Entry": fmt_price(c.get("entry", 0)),
            "Exit": fmt_price(c.get("exit", 0)),
            "Qty": round(c.get("qty", 0) or 0, 6),
            "Notional $": round(
                (c.get("notional")
                 or (c.get("qty", 0) or 0) * (c.get("entry", 0) or 0)),
                2),
            "Reason": c.get("exit_reason", ""),
            "PnL $": c.get("pnl_usd", 0.0),
            "PnL %": c.get("pnl_pct", 0.0),
            "Conf": c.get("confidence", 0),
            "Closed (UTC)": datetime.fromtimestamp(
                c.get("exit_at", 0), tz=timezone.utc).strftime(
                    "%Y-%m-%d %H:%M"),
        } for c in cs_recent]
        st.dataframe(pd.DataFrame(closed_rows),
                     use_container_width=True, hide_index=True)
    else:
        st.caption("No closed trades yet — they appear here once a position "
                   "hits a stop, target, or you close it manually.")

    st.caption("Paper trading idealises execution — no slippage, fees or "
               "partial fills. Use it to gauge whether the signals tend to "
               "win in the current regime; real-money results will be a "
               "little worse. Educational only, not financial advice.")

    # ---- Live mode — only the 10-min hard refresh now -------------------
    # The Bank stats and Open positions sections already update in place
    # every 10s via st.fragment — no full page reload needed for live P&L.
    # Live mode still triggers a hard 10-minute refresh to clear caches
    # (scanner, news, forecast) so fresh signals can land.
    if live_mode:
        _inject_autorefresh(600)
