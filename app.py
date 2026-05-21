"""Crypto Trading Indicator — Streamlit dashboard.

Run with:  streamlit run app.py
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from plotly.subplots import make_subplots

import binance_client
import breakout
import config
import derivatives
import indicators
import lunarcrush
import market_context
import news as news_mod
import oracle
import orderflow
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
            f"{row['confidence']}% confidence</div></div>",
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
        "Status": zones.apply(
            lambda r: ("🔥 " if r["ignited"] else "")
            + _STAGE_WORD.get(r["stage"], r["stage"]), axis=1),
        "Buy zone": zones.apply(
            lambda r: f"{fmt_price(r['buy_low'])} – {fmt_price(r['buy_high'])}",
            axis=1),
        "Breakout trigger": zones["trigger"].map(fmt_price),
        "Stop": zones["bz_stop"].map(fmt_price),
        "Target 1": zones["bz_t1"].map(fmt_price),
        "Target 2": zones["bz_t2"].map(fmt_price),
        "Score": zones["opportunity"],
        "Confidence": zones["confidence"],
        "Market cap": zones["market_cap"].map(
            lambda v: fmt_volume(v) if v and v == v else "—"),
        "Cap tier": zones["cap_tier"],
        "Circulating": zones["circ_pct"].map(
            lambda v: f"{v:.0f}%" if v is not None and v == v else "—"),
    })
    st.dataframe(
        table, use_container_width=True, hide_index=True,
        height=min((len(table) + 1) * 36 + 3, 520),
        column_config={
            "Score": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%d"),
            "Confidence": st.column_config.NumberColumn(
                "Confidence", format="%d%%"),
            "Circulating": st.column_config.TextColumn(
                "Circulating",
                help="Circulating supply as a % of max supply — a high % "
                     "means little future dilution; a low % means many "
                     "tokens are still to be unlocked."),
        })
    st.caption(
        "**How to use this** — the **Buy zone** is the price band to "
        "accumulate in: for *Building Up* coins it sits inside the range so "
        "you get positioned **before** the breakout, for *Just Started* "
        "coins it is the retest of the level just broken. A clean candle "
        "close above the **Breakout trigger** confirms the move; always set "
        "the **Stop**. Larger-cap coins move more slowly but reverse less "
        "violently; a low **Circulating** % flags dilution risk as more "
        "tokens unlock. Educational only — not financial advice.")

    st.markdown("#### 📋 Top 3 — full read & trade plan")
    for _i, (_, _r) in enumerate(zones.head(3).iterrows(), 1):
        render_breakout_card(_r.to_dict(), _i)


# ===========================================================================
# Sidebar
# ===========================================================================
st.sidebar.title("📈 Crypto Indicator")
st.sidebar.caption("Live technical analysis & sentiment — Binance USDT pairs")

timeframe = st.sidebar.selectbox(
    "Timeframe", config.TIMEFRAMES,
    index=config.TIMEFRAMES.index(config.DEFAULT_TIMEFRAME),
)
trade_mode = st.sidebar.radio(
    "Trade mode", ["Futures", "Spot"], horizontal=True,
    help="Futures — trades both long & short, sizes leverage from "
         "conviction. Spot — long-only (no shorting), no leverage, "
         "wider swing-horizon targets and stops.").lower()
top_n = st.sidebar.slider("Coins to track", 10, config.TOP_N, config.TOP_N, 5)

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
    st.caption(
        f"Total crypto market cap ${glob['market_cap_usd'] / 1e12:.2f}T · "
        f"24h volume ${glob['volume_usd'] / 1e9:.0f}B · "
        f"BTC {glob['btc_dominance']:.1f}% / "
        f"ETH {glob['eth_dominance']:.1f}% dominance")

(tab_scan, tab_breakout, tab_oracle, tab_coin, tab_news,
 tab_decision) = st.tabs(
    ["🔍 Market Scanner", "🚀 Breakout Radar", "🤖 Ask the Oracle",
     "🪙 Coin Analysis", "📰 News & Sentiment", "🧭 Decision Mode"])


# ===========================================================================
# Tab 1 — Market Scanner
# ===========================================================================
with tab_scan:
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
# Tab 2 — Breakout Radar
# ===========================================================================
with tab_breakout:
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
# Tab 3 — Ask the Oracle
# ===========================================================================
with tab_oracle:
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
# Tab 4 — Coin Analysis
# ===========================================================================
with tab_coin:
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
# Tab 5 — News & Sentiment
# ===========================================================================
with tab_news:
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
# Tab 6 — Decision Mode
# ===========================================================================
with tab_decision:
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
