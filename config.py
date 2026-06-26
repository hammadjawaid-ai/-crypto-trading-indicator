"""Central configuration for the crypto trading indicator app."""

# Route TLS verification through the OS trust store so the app works behind
# corporate proxies that inject their own root CA (which `certifi` lacks).
try:
    import truststore as _truststore
    _truststore.inject_into_ssl()
except Exception:  # truststore missing or unsupported — fall back to certifi
    pass

import os
from pathlib import Path


def _load_dotenv() -> None:
    """Load KEY=VALUE pairs from a local .env file into the environment.

    Lets API keys (e.g. LunarCrush) live in an untracked .env file rather
    than in source. Existing environment variables always win.
    """
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(),
                              value.strip().strip('"').strip("'"))


_load_dotenv()


def _secret(key: str) -> str:
    """Read a secret from the environment (.env) or Streamlit Cloud secrets.

    Locally the key comes from the .env file; when deployed on Streamlit
    Community Cloud it is injected into st.secrets instead.
    """
    value = os.environ.get(key, "").strip()
    if value:
        return value
    try:  # Streamlit Cloud exposes deploy-time secrets here
        import streamlit as _st
        return str(_st.secrets.get(key, "")).strip()
    except Exception:
        return ""


# --- ntfy.sh push notifications (phone alerts via the standalone notifier) -
# Free, no account, no API key — just a unique topic name (treat it as a
# secret password since anyone with the topic can read your alerts).
# Set in .env or Streamlit Cloud secrets:
#   NTFY_TOPIC=your-private-topic-name-here
# Then install the ntfy.sh app on your phone, subscribe to that exact topic.
# Leave NTFY_TOPIC empty to disable phone push (Windows toasts still fire).
NTFY_TOPIC = _secret("NTFY_TOPIC")


# --- Bybit live-trading credentials & settings -----------------------------
# Set in .env (gitignored) or Streamlit Cloud secrets:
#   BYBIT_API_KEY=...
#   BYBIT_API_SECRET=...
#   BYBIT_TESTNET=true        # start on testnet, flip to false to go live
# The Live Trading tab gates itself when these are missing — no orders fire.
BYBIT_API_KEY = _secret("BYBIT_API_KEY")
BYBIT_API_SECRET = _secret("BYBIT_API_SECRET")
BYBIT_TESTNET = _secret("BYBIT_TESTNET").lower() in ("1", "true", "yes", "y")

# Live bot state file (created at runtime, gitignored).
LIVE_BOT_STATE_PATH = Path(__file__).with_name(".live_bot.json")

# --- Supabase: DURABLE closed-trade storage --------------------------------
# Streamlit Cloud's filesystem is ephemeral (redeploys wipe the .json bot
# state). Closed trades are mirrored to a Supabase Postgres table so the
# history is permanent + readable. Set in Streamlit secrets:
#   SUPABASE_URL = "https://<project>.supabase.co"
#   SUPABASE_KEY = "<service_role key>"   # server-side only, never exposed
# If unset, trade_store.py no-ops and the app runs on local state as before.
SUPABASE_URL = _secret("SUPABASE_URL")
SUPABASE_KEY = _secret("SUPABASE_KEY")

# Safety guardrails — every value enforced in live_broker.preflight()
# / auto_trade_gate() before any real order is placed.
LIVE_DEFAULTS = {
    "leverage_cap":      5,     # SAFE LAUNCH default (was 20). Fresh real
                                # account: cap at 5x until proven live, then
                                # raise via the Settings slider. Protects
                                # against liquidation on a losing streak.
    "daily_loss_pct":    8,     # halts auto-trade if equity drops X% in 24h
    "notional_cap_pct":  20,    # max % of balance on one trade (was 30)
    "max_concurrent":    3,     # max simultaneously open positions
    "slippage_tol_pct":  0.5,   # reject fills more than X% off expected
    "confirm_first_n":   10,    # first N live trades require manual confirm
    "auto_threshold":    85,    # combined-strength needed for auto-trade
    # Strict "sure-shot" gate for auto-trade. When True, auto-fire ONLY
    # if scanner conf>=90 AND forecast aligned 3/3 (direction matches)
    # AND radar stage COILED/FRESH AND live R:R>=1.3 AND not counter-
    # trend. With this on, expect 0-2 auto-fires per day at best.
    "auto_premium_only": True,
    # When a trade is flagged premium_tradeable (passes the strict gate
    # above), risk_per_trade_pct is multiplied by this factor for that
    # single position. Higher conviction = more capital deployed.
    # Conservative default 1.5 — on a $200 account, 4% base × 1.5 = 6%
    # risk on premium trades. Cap at 2.0 to avoid liquidation risk on
    # consecutive losses.
    "premium_risk_multiplier": 1.5,
}


# --- Market universe -------------------------------------------------------
QUOTE_ASSET = "USDT"          # only analyse pairs quoted in this asset
# Universe widened from 100 to 150 (2026-05-25) to catch mid-cap movers
# like DEXE / SAGA / ERA / similar that hover just outside the top 100
# by 24h volume but produce strong signal-engine reads.
TOP_N = 150                   # number of top coins (by 24h volume) to track
KLINE_LIMIT = 300             # candles fetched per symbol/timeframe

# Symbols to exclude: leveraged tokens and stablecoin-vs-stablecoin pairs that
# have no meaningful price action.
EXCLUDE_SUBSTRINGS = ("UP", "DOWN", "BULL", "BEAR")
EXCLUDE_BASES = ("USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "EUR", "GBP",
                 "USD1", "USDE", "USDD", "AEUR", "XUSD", "EURI", "RLUSD",
                 "USDG", "GUSD", "PYUSD",
                 # USD-pegged synthetics that slip through with single-char or
                 # non-obvious tickers. Always trade at ~$1.00 so they produce
                 # zero directional signal and just clog the scanner.
                 "U")

# --- Timeframes ------------------------------------------------------------
TIMEFRAMES = ["15m", "1h", "4h", "1d"]
DEFAULT_TIMEFRAME = "4h"

# --- Binance API -----------------------------------------------------------
# Multiple bases are tried in order; data-api.binance.vision is a public,
# key-free, geo-friendly market-data mirror.
BINANCE_BASES = [
    "https://api.binance.com",
    "https://data-api.binance.vision",
    "https://api1.binance.com",
    "https://api2.binance.com",
]
HTTP_TIMEOUT = 12             # seconds
SCAN_WORKERS = 16             # parallel threads for the market scanner
                              # Bumped 10 -> 16 to make the 150-coin
                              # Market Scanner load ~40% faster. Binance
                              # rate-limit retry in binance_client._get
                              # absorbs the modest extra concurrency.

# Live order-flow (recent trades + order-book depth).
ORDERFLOW_TRADES_LIMIT = 1000  # recent trades pulled per snapshot
ORDERFLOW_DEPTH_LIMIT = 100    # order-book levels per side
ORDERFLOW_CACHE_TTL = 60       # seconds — order flow is near-live
DEPTH_BAND_PCT = 1.0           # +/- % band around mid price for depth imbalance
LARGE_TRADE_QUANTILE = 0.97    # trades above this size quantile flagged "large"

# --- Caching ---------------------------------------------------------------
# Bumped 120 -> 300 (5 min) to match the new page-refresh cadence the
# user set. With the page reloading every 5 min, 2-min cache meant
# the cache expired every reload and the scanner re-fetched ~150
# coins every time. 5-min cache + 5-min refresh = at-most one cold
# scan per refresh cycle (page render hits warm cache most of the time).
MARKET_CACHE_TTL = 300        # seconds (klines / tickers)
NEWS_CACHE_TTL = 600          # seconds (news + sentiment)

# --- Indicator parameters --------------------------------------------------
RSI_PERIOD = 14
EMA_FAST = 20
EMA_SLOW = 50
EMA_TREND = 200
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2.0
ATR_PERIOD = 14
STOCH_PERIOD = 14
VOLUME_MA = 20
ADX_PERIOD = 14
VWAP_PERIOD = 20

# Market-regime thresholds (ADX — Average Directional Index).
ADX_TRENDING = 25   # ADX above this == a real trend; trend signals reliable
ADX_RANGING = 18    # ADX below this == chop; favour mean-reversion / fades

# --- Signal thresholds (composite score is -100..+100) ---------------------
SCORE_STRONG = 50
SCORE_MILD = 18

# --- Binance Futures (derivatives data — public, no API key) ---------------
BINANCE_FAPI_BASE = "https://fapi.binance.com"
DERIV_OI_LOOKBACK = 24    # periods of open-interest history used for the trend
DERIV_WEIGHT = 0.16       # weight of the derivatives vote when data is present

# Funding-rate thresholds (per-interval rate; 0.0005 == 0.05%).
FUNDING_HOT = 0.0005      # crowded longs/shorts above this — contrarian
FUNDING_WARM = 0.0001     # mild directional positioning
FUNDING_COLD = -0.0001    # shorts paying — contrarian bullish lean

# --- External data feeds (all free, no API key) ---------------------------
FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=30"
COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"

# --- Anthropic (Claude) API — Sure Shot Trader Agent 2 validator -----------
# Used ONLY by the hybrid validator in the 🎯 Sure Shot Trader section.
# The deterministic pre-filter does the heavy lifting for free; the LLM is
# called on just the top 2-3 survivors per scan for a final TRADE/SKIP
# verdict with reasoning (incorporating recent news headlines + BTC
# context). Cost ~$5-15/month at that volume.
# Set in .env or Streamlit Cloud secrets:  ANTHROPIC_API_KEY=sk-ant-...
# Leave empty → the validator runs deterministic-only (still fully
# functional, just no LLM second opinion).
ANTHROPIC_API_KEY = _secret("ANTHROPIC_API_KEY")
# Cheap, fast model for per-pick verdicts. Override in .env if desired.
ANTHROPIC_MODEL = _secret("ANTHROPIC_MODEL") or "claude-3-5-haiku-latest"

# Sure Shot Trader paper account — SEPARATE $10k state file, isolated from
# the regular Paper Trader (.paper_bot.json) and Live (.live_bot.json).
SURESHOT_BOT_STATE_PATH = Path(__file__).with_name(".sureshot_bot.json")
SURESHOT_STARTING_BALANCE = 10000.0

# --- Sure Shot Trader 2 — deep-analysis desk (9 agents) --------------------
# Isolated from SST1's account. The deep LLM verdict on finalists uses the
# most capable model (Fable 5) instead of the cheap haiku tier — it reads
# the full 7-analyst report per finalist and adjudicates. Called on at most
# 3 finalists per 3-min scan window, so cost stays modest despite the
# bigger model. Override the model in .env if desired.
SURESHOT2_BOT_STATE_PATH = Path(__file__).with_name(".sureshot2_bot.json")
SURESHOT2_STARTING_BALANCE = 10000.0
ANTHROPIC_MODEL_DEEP = _secret("ANTHROPIC_MODEL_DEEP") or "claude-fable-5"


# --- LunarCrush social intelligence (paid API — key set in .env) -----------
# Aggregates X/Twitter & other social data into Galaxy Score, AltRank and
# sentiment. Subscribe at lunarcrush.com, then put the key in a .env file.
LUNARCRUSH_BASE = "https://lunarcrush.com/api4/public"
LUNARCRUSH_API_KEY = _secret("LUNARCRUSH_API_KEY")

# RSS news feeds grouped by category. All are free, no-key, and validated to
# return parseable items. Categories span crypto, equities and geopolitics so
# the dashboard reflects the cross-asset drivers a trader actually watches.
NEWS_FEEDS = {
    "Crypto": [
        ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
        ("Cointelegraph", "https://cointelegraph.com/rss"),
        ("Decrypt", "https://decrypt.co/feed"),
        ("Bitcoin Magazine", "https://bitcoinmagazine.com/feed"),
        ("The Block", "https://www.theblock.co/rss.xml"),
        ("CryptoSlate", "https://cryptoslate.com/feed/"),
    ],
    "Stocks / Markets": [
        ("CNBC Markets", "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
        ("MarketWatch", "https://feeds.marketwatch.com/marketwatch/topstories/"),
        ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
        ("Investing.com", "https://www.investing.com/rss/news.rss"),
        ("ZeroHedge", "https://feeds.feedburner.com/zerohedge/feed"),
        ("Reuters Business",
         "https://www.reutersagency.com/feed/?best-topics=business-finance"),
    ],
    "Macro / Politics": [
        ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml"),
        ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
        ("NYT Economy", "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml"),
        ("Guardian Business", "https://www.theguardian.com/business/rss"),
        ("CNBC Finance", "https://www.cnbc.com/id/10000664/device/rss/rss.html"),
        # Trump Truth Social posts via the trumpstruth.org public archive.
        # High-noise but occasionally market-moving when he mentions Fed,
        # tariffs, regulation or crypto. The tier-2 impact filter (requires
        # crypto / market context) keeps the noise out of the impact panel.
        ("Trump (Truth Social)", "https://trumpstruth.org/feed"),
    ],
    "Geopolitics": [
        ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("NYT World", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
        ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
        ("Guardian World", "https://www.theguardian.com/world/rss"),
    ],
}

# --- Social sentiment (Reddit public JSON — free, no key) ------------------
# A Terms-of-Service-compliant stand-in for X/Twitter retail buzz. Subreddits
# are grouped by category so social mood lines up with the news categories.
SOCIAL_LIMIT = 30  # hot posts fetched per subreddit
SOCIAL_FEEDS = {
    "Crypto": ["CryptoCurrency", "Bitcoin", "ethereum", "CryptoMarkets"],
    "Stocks / Markets": ["stocks", "wallstreetbets", "investing"],
}
