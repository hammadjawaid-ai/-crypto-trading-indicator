"""📡 NEWS RADAR — coin catalysts, exchange listings, unusual moves, US macro.

User (2026-09-30): "if something big happened to any coin or some partnership
or anything that shows real strength for the coin we should have it as soon
as it lands on our telegram ... like if there is CPI data ... all the
important events".

What it watches (all fail-soft, ~10s timeouts, TLS-proxy tolerant):
  🏦/⚠️  official exchange notices — Binance (new listings + delistings
          catalogs), Upbit (Korean trade notices), OKX, Bybit
  📰     crypto RSS headlines (news.fetch_news() + EXTRA_FEEDS), coin-tagged
          with a strict tagger and a keyword catalyst classifier
  🚨     unusual coin-specific moves (4h ±8%, >=3 sigma, volume >=4x, BTC quiet)
  🗓     US high-impact macro prints (reminder ~30 min before, BTC reaction
          30-45 min after) + a 09:00 PKT morning digest

HONESTY (from our own studies — quoted in the bells, never softened):
  * coin-specific surges (810 events / 13 months): buying at the surge
    close -> 24h median -4.0%, only 35% keep rising; the best 5% gain +26%
    in a day (QNT 24 Sep: +116% in 72h). Surges of +14%+: 24h median -6.9%.
  * Upbit KRW listing notices: price already up a median +16% within 5-10
    min of the notice; buying when the alert lands: 24h median -6.9%, 16% win.
So every bell is INFORMATION or a risk / take-profit prompt — never "buy now".

Entry point: run(get_klines, symbols, send, record=None, now=None, fetch=None)
called every worker cycle; internal throttles decide what actually runs.
State: STATE_FILE (JSON on the durable state disk). The very first sight of
any source is absorbed silently (no flood on first deploy / feed recovery).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import requests

import config

try:  # the TLS-intercepting proxy forces verify=False retries — keep logs clean
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:  # pragma: no cover
    pass

# ---------------------------------------------------------------- constants
STATE_FILE: Path = config.state_path(".news_radar.json")
STREAM = "news_radar"

PKT = timezone(timedelta(hours=5), "PKT")      # Pakistan: UTC+5, no DST
HTTP_TIMEOUT = 10
MAX_MSG = 900
MAX_BELLS_PER_RUN = 8

EX_EVERY = 180            # exchange notices every 3 min
RSS_EVERY = 600           # RSS every 10 min
SURGE_EVERY = 900         # unusual-move scan every 15 min
CAL_EVERY = 6 * 3600      # economic calendar every 6 h
CAL_RETRY = 1800          # ...but retry after 30 min when the fetch failed

SEEN_CAP = 2000
MEMORY_HOURS = 48
EX_MAX_AGE_H = 24         # exchange notice older than this -> record, no bell
RSS_MAX_AGE_H = 6         # headline older than this -> record, no bell
NEWS_COOLDOWN_H = 6       # same coin + direction headline bell cooldown
EX_COOLDOWN_H = 24        # same exchange + coin + kind cooldown
SURGE_COOLDOWN_H = 24     # per coin per direction

DIGEST_UTC_HOURS = (4, 7)  # 04:00-07:00 UTC = 09:00-12:00 PKT

BINANCE_URL = ("https://www.binance.com/bapi/composite/v1/public/cms/"
               "article/list/query")
BINANCE_CATALOGS = (48, 161)   # 48 = new listings, 161 = delistings
UPBIT_URL = "https://api-manager.upbit.com/api/v1/announcements"
OKX_URL = "https://www.okx.com/api/v5/support/announcements"
OKX_TYPES = ("announcements-new-listings", "announcements-delistings")
BYBIT_URL = "https://api.bybit.com/v5/announcements/index"
BYBIT_TYPES = ("new_crypto", "delistings")     # verified live 2026-09-30
CAL_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

EXTRA_FEEDS: list[tuple[str, str]] = [
    ("Blockworks", "https://blockworks.co/feed"),
    ("The Defiant", "https://thedefiant.io/api/feed"),
    ("CoinGape", "https://coingape.com/feed/"),
    ("crypto.news", "https://crypto.news/feed/"),
    ("U.Today", "https://u.today/rss"),
]

# ---- honest lines (from our own studies; see module docstring)
LISTING_LINE_UPBIT = (
    "Upbit listing pumps are usually done within 5–10 min (median +16% by "
    "then); buying after the alert: 24h median −6.9%, 16% win — if you hold "
    "it, this is a take-profit moment, not a chase.")
LISTING_LINE_OTHER = (
    "Exchange listing pumps are usually done within 5–10 min (our Upbit "
    "study: median +16% by then); buying after the alert: 24h median −6.9%, "
    "16% win — if you hold it, this is a take-profit moment, not a chase.")
SURGE_LINE = (
    "Most surges like this fade: 24h median −4%, only 35% keep rising; the "
    "QNT-type runs are the rare 5%. Information, not a buy signal.")
SURGE_BIG_LINE = " Surges of +14% or more did worse: 24h median −6.9%."
DROP_LINE = (
    "Coin-specific dump while BTC is quiet — find the cause before acting; "
    "if you hold it, this is a risk check. We have no validated edge on "
    "buying these.")
DELIST_LINE = ("Risk prompt: if you hold it, plan your exit before liquidity "
               "thins. Information, not a trade signal.")
CAUTION_LINE = ("Upbit caution flags open a review that can end in "
                "delisting; if you hold it, tighten risk. Information, not a "
                "trade signal.")
NEWS_BULL_LINE = (
    "Information, not a buy signal — we have no validated edge on buying "
    "headlines, and coin-specific pops mostly fade (24h median −4% in our "
    "surge study).")
NEWS_BEAR_LINE = ("Risk prompt: if you hold it, check your stop now. "
                  "Information, not a trade signal.")
MACRO_TAIL = ("expect a volatile hour; avoid fresh entries right before the "
              "print")

# --------------------------------------------------------------- coin tagger
# Tickers that are English words / common acronyms, plus every ticker of two
# letters or fewer: they only count as "$TICKER" or via their project NAME.
AMBIGUOUS: set[str] = {
    "NEAR", "ONE", "GAS", "SUN", "HOT", "FUN", "MOVE", "BAND", "BOND", "ACE",
    "JOE", "COMP", "MASK", "PEOPLE", "USUAL", "ANIME", "TRUMP", "OP", "IO",
    "ZK", "AI", "ID", "S", "T", "W", "ME", "ACT", "GO", "UP", "IT", "US",
    "NOT", "CAT", "DOG", "DOGE", "MEME", "PUMP", "HIGH", "EDGE", "SAFE",
    "HOOK", "ALT", "PRIME", "ORDER", "LAYER", "SIGN", "SAGA", "MAGIC",
    "PORTAL", "HOME", "BIO", "RARE", "FORM", "KEY", "BIG", "NEW", "TOP",
    "CHESS", "TRUTH", "BANANA", "BLUR", "FLOW", "SKY", "AUCTION", "OPEN",
    "COOKIE", "TURBO", "GRASS", "RED", "GUN", "WIN", "COW", "GMT", "EPIC",
    "HIVE", "PROMPT", "SPELL", "SUPER", "TOKEN", "TREE", "SOON", "POWER",
    "BEAT", "ART", "SEC", "FED", "CPI", "GDP", "IPO", "DAO", "NFT", "API",
    "CEO", "ETF", "USD", "EU", "UK", "AT", "IN", "ON", "OR", "SO", "NO",
    "ALL", "ANY", "NOW", "FOR", "AND", "THE", "GOOD", "LIVE", "REAL", "DEEP",
    "SIREN", "TAG",
}

# (regex, ticker, case_sensitive). Wrapped in \b(?:...)\b at compile time.
_NAME_PATTERNS: list[tuple[str, str, bool]] = [
    (r"Bitcoin(?!\s+(?:Cash|SV|Gold))", "BTC", False),
    (r"Bitcoin Cash", "BCH", False),
    (r"Ethereum(?!\s+Classic)", "ETH", False),
    (r"Ether", "ETH", True),
    (r"Ethereum Classic", "ETC", False),
    (r"Ripple(?!\s+effects?\b)", "XRP", True),
    (r"Solana", "SOL", False),
    (r"Cardano", "ADA", False),
    (r"Polkadot", "DOT", False),
    (r"Avalanche(?!\s+of\b)", "AVAX", True),
    (r"Polygon", "POL", True),
    (r"Arbitrum", "ARB", False),
    (r"Optimism(?=\s+(?:network|Network|Foundation|mainnet|Mainnet|"
     r"Superchain|L2|layer|Collective))|OP Mainnet|on Optimism", "OP", True),
    (r"Sui(?=\s+(?:network|Network|blockchain|Blockchain|Foundation|"
     r"ecosystem|mainnet|Mainnet|DeFi|token|price|ETF|Labs))|Sui's|on Sui",
     "SUI", True),
    (r"Aptos", "APT", False),
    (r"Toncoin|TON Foundation|The Open Network|TON blockchain", "TON", False),
    (r"Dogecoin", "DOGE", False),
    (r"Shiba Inu", "SHIB", False),
    (r"Litecoin", "LTC", False),
    (r"Chainlink", "LINK", False),
    (r"Uniswap", "UNI", False),
    (r"Aave", "AAVE", False),
    (r"Filecoin", "FIL", False),
    (r"Render Network", "RENDER", False),
    (r"Injective", "INJ", False),
    (r"Celestia", "TIA", False),
    (r"Stellar", "XLM", True),
    (r"Hedera", "HBAR", False),
    (r"Algorand", "ALGO", False),
    (r"Cosmos(?=\s+(?:Hub|hub|network|Network|ecosystem|SDK|chain))",
     "ATOM", True),
    (r"Internet Computer", "ICP", False),
    (r"Sei Network|Sei Labs|Sei Foundation", "SEI", False),
    (r"Worldcoin|World Network", "WLD", False),
    (r"Ondo", "ONDO", False),
    (r"Pendle", "PENDLE", False),
    (r"Jupiter", "JUP", True),
    (r"Ethena", "ENA", False),
    (r"Hyperliquid", "HYPE", False),
    (r"Tron|TRON", "TRX", True),
    (r"Zcash", "ZEC", False),
    (r"Monero", "XMR", False),
    (r"Bittensor", "TAO", False),
    (r"Fetch\.ai", "FET", False),
    (r"Starknet", "STRK", False),
    (r"zkSync|ZKsync", "ZK", True),
    (r"Stacks(?=\s+(?:network|Network|blockchain|ecosystem|L2|Foundation))",
     "STX", True),
    (r"THORChain", "RUNE", False),
    (r"Lido", "LDO", True),
    (r"Curve Finance|Curve DAO", "CRV", False),
    (r"The Sandbox", "SAND", False),
    (r"Decentraland", "MANA", False),
    (r"Axie Infinity", "AXS", False),
    (r"ApeCoin", "APE", False),
    (r"Pepe", "PEPE", True),
    (r"Bonk", "BONK", True),
    (r"dogwifhat", "WIF", False),
    (r"Floki", "FLOKI", False),
    (r"Immutable", "IMX", True),
    (r"VeChain", "VET", False),
    (r"Plasma", "XPL", True),
    (r"Mantle", "MNT", True),
    (r"Berachain", "BERA", False),
    (r"Kaia", "KAIA", True),
    (r"EigenLayer|Eigen Layer", "EIGEN", False),
    (r"Movement Labs|Movement Network", "MOVE", False),
    (r"Story Protocol", "IP", False),
    (r"Virtuals Protocol", "VIRTUAL", False),
    (r"Raydium", "RAY", False),
    (r"Jito", "JTO", True),
    (r"Pyth", "PYTH", True),
    (r"Wormhole", "W", True),
    (r"Arweave", "AR", False),
    (r"Theta Network", "THETA", False),
    (r"IOTA", "IOTA", True),
    (r"Kaspa", "KAS", False),
    (r"NEAR Protocol|NEAR Foundation", "NEAR", False),
    (r"BNB Chain|Binance Coin", "BNB", False),
    (r"Tezos", "XTZ", False),
    (r"Cronos", "CRO", True),
    (r"Pi Network", "PI", False),
    (r"World Liberty Financial", "WLFI", False),
    (r"Sonic Labs", "S", False),
    (r"Chiliz", "CHZ", False),
    (r"Gala Games", "GALA", False),
    (r"Quant(?:\s+Network)?(?!\s+(?:fund|funds|firm|firms|trader|traders|"
     r"trading|strateg\w*|analyst\w*|model\w*|shop\w*|hedge|research|desk|"
     r"team|investing)\b)", "QNT", True),
]
# public view: name-pattern -> ticker (≈90 projects)
NAME_MAP: dict[str, str] = {p: t for p, t, _ in _NAME_PATTERNS}
_NAME_RES = [(re.compile(r"\b(?:" + p + r")\b", 0 if cs else re.IGNORECASE), t)
             for p, t, cs in _NAME_PATTERNS]
_TICKER_RE = re.compile(r"(?<![A-Za-z0-9$])(\$?)([A-Z0-9]{1,15})(?![A-Za-z0-9])")

TOP50: set[str] = {
    "BTC", "ETH", "XRP", "BNB", "SOL", "DOGE", "ADA", "TRX", "LINK", "AVAX",
    "SUI", "XLM", "TON", "HBAR", "SHIB", "DOT", "LTC", "BCH", "UNI", "NEAR",
    "APT", "ICP", "ETC", "POL", "XMR", "AAVE", "ENA", "ONDO", "TAO", "HYPE",
    "FIL", "ARB", "OP", "ATOM", "KAS", "RENDER", "INJ", "SEI", "TIA", "STX",
    "IMX", "VET", "ALGO", "WLD", "JUP", "MNT", "XPL", "FET", "PEPE", "BONK",
}


def tag_coins(text: str, bases) -> list[str]:
    """Strict coin tagger -> tickers (in order of first mention).

    * uppercase ticker, case-SENSITIVE, non-alphanumeric boundaries, optional
      leading "$" (so no ENA inside SENATE, no XPL inside EXPLOIT);
    * AMBIGUOUS tickers (English words / <=2 letters) only as "$TICKER" or
      via their project name (so "near $4,400" is not NEAR);
    * NAME_MAP project names (Quant -> QNT, NEAR Protocol -> NEAR, ...);
    * only tickers in `bases` are returned (BTC/ETH always allowed)."""
    if not text:
        return []
    allowed = {str(b).upper() for b in (bases or [])} | {"BTC", "ETH"}
    hits: dict[str, int] = {}
    for m in _TICKER_RE.finditer(text):
        dollar, tok = m.group(1), m.group(2)
        if tok not in allowed or not re.search(r"[A-Z]", tok):
            continue
        if (tok in AMBIGUOUS or len(tok) <= 2) and not dollar:
            continue
        hits.setdefault(tok, m.start())
    for rx, tick in _NAME_RES:
        if tick not in allowed:
            continue
        m = rx.search(text)
        if m:
            hits[tick] = min(hits.get(tick, m.start()), m.start())
    return [t for t, _ in sorted(hits.items(), key=lambda kv: kv[1])]


# ------------------------------------------------------- catalyst classifier
_I = re.IGNORECASE
_KINDS: list[tuple[str, str, float, re.Pattern]] = [
    # ---- bullish
    ("partnership", "bull", 0.80, re.compile(
        r"\bpartner(s|ed|ing)?\b|\bpartnerships?\b|\bteams? up\b|"
        r"\bcollaborat\w*", _I)),
    ("integration", "bull", 0.70, re.compile(r"\bintegrat\w*", _I)),
    ("adoption", "bull", 0.70, re.compile(r"\badopt\w*", _I)),
    ("listing", "bull", 0.80, re.compile(
        r"\blists\b|\bwill list\b|\bto list\b|\blisting on\b|\bnow listed\b|"
        r"\blisted on\b|\bgets listed\b", _I)),
    ("etf", "bull", 1.00, re.compile(
        r"\bETFs?\b.{0,60}\b(fil(e|es|ed|ing)|approv\w*|launch\w*|debut\w*|"
        r"S-1|19b-4|goes live|begins trading)\b|"
        r"\b(fil(e|es|ed|ing)|approv\w*|launch\w*|debut\w*)\b.{0,60}\bETFs?\b",
        _I)),
    ("mainnet", "bull", 0.80, re.compile(r"\bmainnet\b|\bgoes live\b|"
                                         r"\bwent live\b", _I)),
    ("launch", "bull", 0.40, re.compile(r"\blaunch(es|ed)?\b", _I)),
    ("upgrade", "bull", 0.80, re.compile(
        r"\bhard[- ]?fork\b|\b(network|protocol|mainnet|major|chain|"
        r"consensus)\s+upgrade\b|\bupgrade\s+(goes|went|is)\s+live\b|"
        r"\bupgrade\s+activat\w*", _I)),
    ("acquisition", "bull", 0.80, re.compile(
        r"\bacquir(e|es|ed|ing)\b|\bacquisitions?\b", _I)),
    ("treasury", "bull", 0.70, re.compile(
        r"(?<!U\.S\. )(?<!US )(?<!the )\btreasury\b(?!\s+(secretary|"
        r"department|yields?|bonds?|bills?|notes|urges|says|official\w*|"
        r"market))|\bbuys?\s+\$|\bbought\s+\$|\bpurchas(e|es|ed)\b", _I)),
    ("buyback", "bull", 0.70, re.compile(
        r"\bbuy-?backs?\b|\b(token )?burn(s|ed|ing)?\b", _I)),
    ("funding", "bull", 0.60, re.compile(
        r"\braise[sd]?\s+\$|\bfunding round\b|\bseries [A-E]\b|"
        r"\bseed round\b", _I)),
    ("regulatory", "bull", 0.80, re.compile(
        r"\blicen[cs]e[sd]?\b|\bapproval granted\b|\b(gets?|wins?|secures?|"
        r"receives?|granted|obtains?)\b.{0,40}\b(approval|licen[cs]e|"
        r"authori[sz]ation|registration)\b", _I)),
    ("record_high", "bull", 0.70, re.compile(
        r"\ball[- ]time highs?\b|\brecord highs?\b|\bnew highs?\b|\bATH\b|"
        r"\bhits? (a )?record\b|\brecord (inflows?|volume|TVL|revenue)\b", _I)),
    # ---- bearish
    ("hack", "bear", 1.20, re.compile(
        r"\bhack(ed|s|er|ers|ing)?\b|\bexploit(ed|s|er)?\b|"
        r"\bdrain(ed|s|ing)?\b|\bstolen\b|\bheist\b|\bcompromised\b|"
        r"\bsecurity breach\b", _I)),
    ("delist", "bear", 1.10, re.compile(r"\bdelist(s|ed|ing|ings)?\b", _I)),
    ("lawsuit", "bear", 1.00, re.compile(
        r"\blawsuits?\b|\bsues?\b|\bsued\b|\bcharged\b|\b(SEC|CFTC|DOJ|"
        r"prosecutors?)\s+charges?\b|\bindict(ed|ment)\b|\bclass[- ]action\b",
        _I)),
    ("investigation", "bear", 0.80, re.compile(
        r"\binvestigat(ion|ions|es|ing|ed)\b|\bprobes?\b|\bprobed\b|"
        r"\bsubpoena\w*", _I)),
    ("unlock", "bear", 0.60, re.compile(
        r"\b(token|cliff|vesting)\s+unlocks?\b|\bunlocks?\s+(worth\s+)?\$\s?\d|"
        r"\bunlock(s|ing)?\b.{0,40}\btokens\b", _I)),
    ("withdrawal_halt", "bear", 1.00, re.compile(
        r"\b(halts?|halted|halting|pauses?|paused|pausing|suspends?|suspended|"
        r"suspending|freezes?|froze|frozen|freezing)\s+(all\s+)?(withdrawals?|"
        r"deposits|trading)\b|\bwithdrawals?\s+(halted|paused|suspended|"
        r"frozen)\b", _I)),
    ("insolvent", "bear", 1.20, re.compile(
        r"\binsolven(t|cy)\b|\bbankrupt(cy|cies)?\b|\bchapter 11\b", _I)),
    ("outage", "bear", 0.70, re.compile(
        r"\boutage\b|\b(network|chain|blockchain|mainnet)\s+(halt|halts|"
        r"halted|stall|stalls|stalled|down|goes down)\b|"
        r"\bstops producing blocks\b", _I)),
    ("rug", "bear", 1.00, re.compile(
        r"\brug[- ]?pull(ed|s)?\b|\brugged\b|\bexit scam\b", _I)),
    ("regulatory_hit", "bear", 0.90, re.compile(
        r"\blicen[cs]e\b.{0,25}\b(revoked|suspended|rejected|denied)\b|"
        r"\b(revokes?|suspends?)\b.{0,30}\blicen[cs]e", _I)),
    ("etf_setback", "bear", 1.05, re.compile(
        r"\bETFs?\b.{0,60}\b(reject\w*|denied|denies|delay\w*|postpone\w*)\b|"
        r"\b(reject\w*|denied|denies|delay\w*|postpone\w*)\b.{0,60}\bETFs?\b",
        _I)),
]
# a hack mentioned as past context is not a new hack of the tagged coin
_RETRO_HACK_RE = re.compile(
    r"\b(after|since|following|in the wake of|post)\b.{0,40}"
    r"\b(hack|hacks|exploit|exploits|heist)\b", _I)
_ANALYSIS_RE = re.compile(
    r"\bprice (analysis|predictions?|forecast|outlook)\b|"
    r"\btechnical analysis\b|\bwhat'?s next\b", _I)
_DENIAL_RE = re.compile(
    r"\b(denies|denied|debunk\w*|fake|false|hoax|rumou?r(s|ed)?|no plans?)\b",
    _I)
_SPECULATIVE_RE = re.compile(
    r"\?\s*$|\bcould\b|\bmight\b|(?-i:\bmay\b)|\bexpected to\b|"
    r"\breportedly\b|"
    r"\bpotential(ly)?\b|\bpredicts?\b", _I)

BIG_NAMES: list[str] = [
    "SWIFT", "DTCC", "BlackRock", "Fidelity", "JPMorgan", "JP Morgan",
    "Goldman", "Visa", "Mastercard", "PayPal", "Stripe", "Google",
    "Microsoft", "Amazon", "AWS", "Nvidia", "Samsung", "Apple", "Meta",
    "Nasdaq", "CME", "Coinbase", "Binance", "Robinhood", "Deutsche Bank",
    "HSBC", "Citi", "Citigroup", "BNY", "State Street", "Franklin Templeton",
    "Grayscale", "Bitwise", "VanEck", "Circle", "Tether", "UBS", "Santander",
    "SoFi", "Revolut", "Telegram", "Shopify", "Sony", "Toyota",
    "central bank", "Federal Reserve", "Morgan Stanley", "Charles Schwab",
    "Standard Chartered", "Euroclear", "NYSE", "Cboe",
]
# English-word names are matched case-sensitively (no "swift recovery").
_BIG_CASE_SENSITIVE = {"SWIFT", "Visa", "Apple", "Meta", "Circle", "Amazon",
                       "Stripe", "Citi"}
_BIG_RES = [(n, re.compile(r"\b" + re.escape(n) + r"\b",
                           0 if n in _BIG_CASE_SENSITIVE else _I))
            for n in BIG_NAMES]

KIND_LABEL = {
    "partnership": "partnership", "integration": "integration",
    "adoption": "adoption", "listing": "exchange listing",
    "etf": "ETF", "mainnet": "mainnet / launch", "launch": "launch",
    "upgrade": "upgrade / hard fork", "acquisition": "acquisition",
    "treasury": "treasury buy", "buyback": "buyback / burn",
    "funding": "funding", "regulatory": "regulatory win",
    "record_high": "record high", "hack": "hack / exploit",
    "delist": "delisting", "lawsuit": "lawsuit / charges",
    "investigation": "investigation", "unlock": "token unlock",
    "withdrawal_halt": "withdrawals halted", "insolvent": "insolvency",
    "outage": "outage", "rug": "rug pull", "regulatory_hit": "licence hit",
    "etf_setback": "ETF setback", "analysis": "analysis", "denial": "denial",
    "none": "news",
    # exchange kinds
    "spot_listing": "spot listing", "delisting": "delisting",
    "caution": "caution flag", "caution_lifted": "caution lifted",
    "caution_extended": "caution extended", "market_add": "new market",
    "futures_launch": "futures launch", "futures_delist": "futures delist",
    "pair_removal": "pair removal", "listing_update": "listing update",
    "delisting_update": "delisting update", "other": "notice",
    "ignore": "ignored",
}


def classify(title: str) -> dict:
    """Keyword catalyst classifier for one headline.

    Returns {direction: bull|bear|neutral, kind, score, big_name} plus
    helper keys: names (matched big names), kinds (all matched kinds),
    speculative (question / could / reportedly ...)."""
    t = str(title or "")
    names = [n for n, rx in _BIG_RES if rx.search(t)]
    big_name = bool(names)
    speculative = bool(_SPECULATIVE_RE.search(t))
    if _ANALYSIS_RE.search(t):
        return {"direction": "neutral", "kind": "analysis", "score": 0.0,
                "big_name": big_name, "names": names, "kinds": [],
                "speculative": speculative}
    matched = [(k, d, w) for k, d, w, rx in _KINDS if rx.search(t)]
    if _RETRO_HACK_RE.search(t):      # "Months after the Kelp hack, X ..."
        matched = [m for m in matched if m[0] != "hack"]
    if any(k == "etf_setback" for k, _, _ in matched):
        matched = [m for m in matched if m[0] != "etf"]
    if any(k == "regulatory_hit" for k, _, _ in matched):
        matched = [m for m in matched if m[0] != "regulatory"]
    if not matched:
        return {"direction": "neutral", "kind": "none", "score": 0.0,
                "big_name": big_name, "names": names, "kinds": [],
                "speculative": speculative}
    kind, direction, weight = max(matched, key=lambda m: m[2])
    kinds = [k for k, _, _ in matched]
    if direction == "bull" and _DENIAL_RE.search(t):
        return {"direction": "neutral", "kind": "denial", "score": 0.1,
                "big_name": big_name, "names": names, "kinds": kinds,
                "speculative": speculative}
    same = sum(1 for _, d, _ in matched if d == direction) - 1
    score = weight + 0.15 * max(0, same) + (0.5 if big_name else 0.0)
    if speculative:
        score *= 0.6
    return {"direction": direction, "kind": kind, "score": round(score, 3),
            "big_name": big_name, "names": names, "kinds": kinds,
            "speculative": speculative}


def is_big_news(cls: dict, tickers) -> bool:
    """BIG rule for RSS headlines: coin-tagged AND (hack/delist/lawsuit/
    insolvent OR ETF OR (bullish AND big name) OR mainnet/major upgrade of a
    top-50 coin). Speculative headlines ("could", "?") never qualify."""
    if not tickers or not cls or cls.get("speculative"):
        return False
    kind, direction = cls.get("kind"), cls.get("direction")
    if direction == "bear" and kind in ("hack", "delist", "lawsuit",
                                         "insolvent"):
        return True
    if kind in ("etf", "etf_setback"):
        return True
    if direction == "bull" and cls.get("big_name"):
        return True
    if kind in ("mainnet", "upgrade") and any(t in TOP50 for t in tickers):
        return True
    return False


# ------------------------------------------------ exchange title classifiers
_QUOTES = {"USD", "USDT", "USDC", "EUR", "BTC", "ETH", "TRY", "BRL", "FDUSD",
           "KRW", "USDE", "USD1"}
_BELL_KINDS = {"spot_listing", "delisting", "caution"}


def _split_tickers(s: str) -> list[str]:
    out = []
    for tok in re.split(r",\s*|\s+and\s+|\s*&\s*|\s+", s or ""):
        tok = tok.strip().strip(".").upper()
        if re.fullmatch(r"[A-Z0-9]{2,15}", tok) and re.search(r"[A-Z]", tok) \
                and tok not in _QUOTES and tok not in {"TOKEN", "TOKENS"}:
            out.append(tok)
    return list(dict.fromkeys(out))


def _paren_tickers(title: str, ascii_only: bool = True) -> list[str]:
    pat = r"\(([A-Z0-9]{1,15})\)" if ascii_only else r"\(([^()\s,]{1,20})\)"
    out = []
    for tok in re.findall(pat, title or ""):
        if re.fullmatch(r"[\d\-/.:]+", tok):      # dates / numbers
            continue
        out.append(tok)
    return list(dict.fromkeys(out))


def _exc(kind: str, direction: str, tickers=None, markets=None) -> dict:
    bell = kind in _BELL_KINDS or (kind == "market_add"
                                   and "KRW" in (markets or []))
    return {"kind": kind, "direction": direction, "tickers": tickers or [],
            "markets": markets or [], "bell": bell, "big": bell}


_BN_IGNORE = re.compile(
    r"\bb?stocks?\b|\btokeni[sz]ed\b|\btradfi\b|\bsecurities\b|"
    r"\bcollateral\b|\bearn\b|\blaunchpool\b|\bmegadrop\b|\bhodler\b|"
    r"\bmargin\b|\btrading bots?\b|\bpre-?ipo\b|\bdividend\b|\bloans?\b|"
    r"\bbinance alpha\b", _I)


def classify_binance(title: str) -> dict:
    """Binance announcement title -> exchange kind (see module docstring)."""
    t = str(title or "")
    if _BN_IGNORE.search(t):
        return _exc("ignore", "neutral")
    if re.search(r"\bfutures\b|\bperpetual\b", t, _I):
        return _exc("futures_launch", "neutral")
    m = re.search(r"\bwill delist\s+(.+?)(?:\s+on\s+\d{4}-\d{2}-\d{2}|\s+on\s|"
                  r"\s*$)", t, _I)
    if m:
        return _exc("delisting", "bear", _split_tickers(m.group(1)))
    if re.search(r"\bremoval of (spot )?trading pairs?\b|\bdelist\b", t, _I):
        return _exc("pair_removal", "bear")
    if re.search(r"\bbinance will list\b|\bbinance lists\b", t, _I) or \
            re.search(r"\badds\b.*\btrading pairs? on binance spot\b", t, _I):
        ticks = _paren_tickers(t, ascii_only=False)
        if ticks:
            return _exc("spot_listing", "bull", ticks)
    return _exc("other", "neutral")


def classify_upbit(title: str) -> dict:
    """Upbit Korean trade-notice title -> exchange kind + tickers + markets."""
    t = str(title or "")
    ticks = _paren_tickers(t, ascii_only=True)
    mk = re.search(r"([A-Z]{3,4}(?:\s*,\s*[A-Z]{3,4})*)\s*마켓", t)
    markets = [x.strip() for x in mk.group(1).split(",")] if mk else []
    update = bool(re.search(r"(변경|취소|연기)\s*안내", t))
    if "거래지원 종료" in t:
        return _exc("delisting_update" if update else "delisting", "bear",
                    ticks, markets)
    if "신규 거래지원" in t:
        return _exc("listing_update" if update else "spot_listing",
                    "neutral" if update else "bull", ticks, markets)
    if "유의 종목" in t and "해제" in t:
        return _exc("caution_lifted", "neutral", ticks, markets)
    if "유의 종목" in t and "연장" in t:
        return _exc("caution_extended", "bear", ticks, markets)
    if "유의 종목 지정" in t:
        return _exc("caution", "bear", ticks, markets)
    if "마켓 디지털 자산 추가" in t or "마켓 추가" in t:
        return _exc("market_add", "bull", ticks, markets)
    return _exc("other", "neutral", ticks, markets)


def classify_okx(ann_type: str, title: str) -> dict:
    t = str(title or "")
    low = t.lower()
    at = str(ann_type or "")
    if at == "announcements-new-listings":
        if re.search(r"perp|futures|equity|pre-?ipo|pre-market|options|"
                     r"margin|earn", low):
            return _exc("futures_launch", "neutral")
        pairs = re.findall(r"\b([A-Z0-9]{1,15})/(?:USDT|USDC|USD|EUR|BTC)\b", t)
        ticks = [p for p in dict.fromkeys(pairs) if p not in _QUOTES]
        if "spot" in low and ticks:
            return _exc("spot_listing", "bull", ticks)
        return _exc("other", "neutral")
    if at == "announcements-delistings":
        if re.search(r"postpone|migration|swap|rebrand|redenominat", low):
            return _exc("other", "neutral")
        if re.search(r"perp|futures|x-perp|options|margin", low):
            return _exc("futures_delist", "bear")
        m = re.search(r"\bdelist\s+(.+?)\s+spot trading pairs?", t, _I)
        if m and "selected" not in m.group(1).lower():
            ticks = _split_tickers(m.group(1))
            if ticks:
                return _exc("delisting", "bear", ticks)
        return _exc("pair_removal", "bear")
    return _exc("ignore", "neutral")


def classify_bybit(type_key: str, title: str, tags=None) -> dict:
    t = str(title or "")
    low = t.lower()
    tags_l = {str(x).lower() for x in (tags or [])}
    key = str(type_key or "")
    if key == "new_crypto":
        if re.search(r"perpetual|futures|tradfi|pre-ipo|options|contract", low):
            return _exc("futures_launch", "neutral")
        if re.search(r"splash|launchpool|puzzle|campaign|airdrop|prize|"
                     r"giveaway|reward|earn", low):
            return _exc("ignore", "neutral")
        if re.search(r"\blist(s|ing|ed)?\b", low) and ("spot" in low
                                                      or "spot" in tags_l):
            ticks = _paren_tickers(t, ascii_only=True)
            if not ticks:
                ticks = [p for p in re.findall(r"\b([A-Z0-9]{2,15})/USDT\b", t)]
            if ticks:
                return _exc("spot_listing", "bull", ticks)
        return _exc("other", "neutral")
    if key == "delistings":
        if "alpha" in low or "web3" in tags_l:
            return _exc("ignore", "neutral")
        if re.search(r"perpetual|futures|contract|options", low):
            return _exc("futures_delist", "bear")
        if re.search(r"collateral|lending|loan|margin|savings|earn", low):
            return _exc("other", "neutral")
        if re.search(r"trading pair", low):
            return _exc("pair_removal", "bear")
        m = re.search(r"\b(?i:delisting of)\s+([A-Z0-9 ,&]+?)\s*$", t)
        if m:
            ticks = _split_tickers(m.group(1))
            if ticks:
                return _exc("delisting", "bear", ticks)
        if re.search(r"\bdelist\b.*\btokens?\b", low):
            return _exc("delisting", "bear", _paren_tickers(t))
        return _exc("other", "neutral")
    return _exc("ignore", "neutral")


# ------------------------------------------------------------- HTTP helpers
_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) news-radar/1.0",
    "Accept": "application/json, application/xml, text/xml, */*",
})
_INSECURE_HOSTS: set[str] = set()


def _http_get(url: str, params: dict | None = None,
              timeout: float = HTTP_TIMEOUT):
    """GET with a verify=False retry after an SSLError (TLS proxy). Never
    raises; returns the Response on HTTP 200 else None."""
    host = urlparse(url).netloc
    for verify in ((False,) if host in _INSECURE_HOSTS else (True, False)):
        try:
            r = _SESSION.get(url, params=params, timeout=timeout,
                             verify=verify)
            return r if r.status_code == 200 else None
        except requests.exceptions.SSLError:
            _INSECURE_HOSTS.add(host)
            continue
        except Exception:
            return None
    return None


def _get_json(url: str, params: dict | None = None):
    r = _http_get(url, params)
    if r is None:
        return None
    try:
        return r.json()
    except Exception:
        return None


def _hid(s: str) -> str:
    return hashlib.sha1(str(s).encode("utf-8", "ignore")).hexdigest()[:16]


def _item(source: str, src_key: str, iid: str, title: str, link: str,
          ts: float, cls: dict) -> dict:
    return {"source": source, "src_key": src_key, "id": iid,
            "title": str(title or "").strip(), "link": str(link or ""),
            "ts": float(ts or 0), **cls}


# ------------------------------------------------------------ payload parsers
def parse_binance(articles, catalog_id: int = 48) -> list[dict]:
    """Binance CMS articles (list of {id, code, title, releaseDate}) ->
    normalized items. Accepts the full JSON too."""
    if isinstance(articles, dict):
        try:
            articles = articles["data"]["catalogs"][0]["articles"]
        except Exception:
            return []
    out = []
    for a in articles or []:
        try:
            title = str(a.get("title") or "").strip()
            if not title:
                continue
            code = str(a.get("code") or "")
            aid = str(a.get("id") or code or _hid(title))
            link = (f"https://www.binance.com/en/support/announcement/detail/"
                    f"{code}" if code else "")
            ts = float(a.get("releaseDate") or 0) / 1000.0
            out.append(_item("Binance", f"binance{int(catalog_id)}",
                             f"bn:{aid}", title, link, ts,
                             classify_binance(title)))
        except Exception:
            continue
    return out


def _iso_ts(s) -> float:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")) \
            .astimezone(timezone.utc).timestamp()
    except Exception:
        return 0.0


def parse_upbit(payload) -> list[dict]:
    """Upbit announcements JSON (or its notices list) -> items."""
    notices = payload
    if isinstance(payload, dict):
        try:
            notices = payload["data"]["notices"]
        except Exception:
            return []
    out = []
    for n in notices or []:
        try:
            title = str(n.get("title") or "").strip()
            if not title:
                continue
            nid = str(n.get("id") or n.get("uuid") or _hid(title))
            ts = _iso_ts(n.get("first_listed_at") or n.get("listed_at"))
            link = f"https://upbit.com/service_center/notice?id={nid}"
            out.append(_item("Upbit", "upbit", f"upbit:{nid}", title, link,
                             ts, classify_upbit(title)))
        except Exception:
            continue
    return out


def parse_okx(payload) -> list[dict]:
    """OKX support/announcements JSON -> items."""
    details = []
    try:
        for page in (payload or {}).get("data") or []:
            details.extend(page.get("details") or [])
    except Exception:
        return []
    out = []
    for a in details:
        try:
            title = str(a.get("title") or "").strip()
            if not title:
                continue
            at = str(a.get("annType") or "")
            url = str(a.get("url") or "")
            ts = float(a.get("pTime") or 0) / 1000.0
            out.append(_item("OKX", f"okx:{at or 'all'}",
                             f"okx:{_hid(url or title)}", title, url, ts,
                             classify_okx(at, title)))
        except Exception:
            continue
    return out


def parse_bybit(payload) -> list[dict]:
    """Bybit v5 announcements JSON -> items."""
    try:
        rows = (payload or {}).get("result", {}).get("list") or []
    except Exception:
        return []
    out = []
    for a in rows:
        try:
            title = str(a.get("title") or "").strip()
            if not title:
                continue
            tkey = str((a.get("type") or {}).get("key") or "")
            url = str(a.get("url") or "")
            ts = float(a.get("dateTimestamp") or a.get("publishTime") or 0) \
                / 1000.0
            out.append(_item("Bybit", f"bybit:{tkey or 'all'}",
                             f"bybit:{_hid(url or title)}", title, url, ts,
                             classify_bybit(tkey, title, a.get("tags"))))
        except Exception:
            continue
    return out


# --------------------------------------------------------- network fetchers
def fetch_binance() -> list[dict]:
    out: list[dict] = []
    for cid in BINANCE_CATALOGS:
        j = _get_json(BINANCE_URL, {"type": 1, "pageNo": 1, "pageSize": 10,
                                    "catalogId": cid})
        try:
            arts = j["data"]["catalogs"][0]["articles"]
        except Exception:
            continue          # catalog missing / errored -> skip gracefully
        out.extend(parse_binance(arts, cid))
    return out


def fetch_upbit() -> list[dict]:
    j = _get_json(UPBIT_URL, {"os": "web", "page": 1, "per_page": 20,
                              "category": "trade"})
    return parse_upbit(j) if j else []


def fetch_okx() -> list[dict]:
    out, seen = [], set()
    for at in OKX_TYPES:
        j = _get_json(OKX_URL, {"page": 1, "annType": at})
        for it in parse_okx(j) if j else []:
            if it["id"] not in seen:
                seen.add(it["id"])
                out.append(it)
    return out


def fetch_bybit() -> list[dict]:
    out, seen = [], set()
    for tk in BYBIT_TYPES:
        j = _get_json(BYBIT_URL, {"locale": "en-US", "limit": 20, "type": tk})
        for it in parse_bybit(j) if j else []:
            if it["id"] not in seen:
                seen.add(it["id"])
                out.append(it)
    return out


def _parse_feed_soft(category: str, source: str, url: str) -> list[dict]:
    """news._parse_feed first; if it comes back empty (e.g. SSLError behind
    the TLS proxy) re-fetch with the verify=False retry and parse with
    news' own RSS/Atom extractors. Never raises."""
    try:
        import news
    except Exception:
        return []
    rows: list[dict] = []
    try:
        rows = news._parse_feed(category, source, url) or []
    except Exception:
        rows = []
    if not rows:
        try:
            r = _http_get(url)
            if r is not None:
                root = ET.fromstring(r.content)
                for title, link, _summary, date in news._extract_items(root)[:25]:
                    if title:
                        rows.append({"category": category, "source": source,
                                     "title": title, "link": link,
                                     "published": news._parse_date(date)})
        except Exception:
            rows = []
    return rows


def _row_ts(v) -> float:
    try:
        if isinstance(v, (int, float)):
            return float(v)
        return _as_dt(v).timestamp()
    except Exception:
        return 0.0


def fetch_rss() -> list[dict]:
    """news.fetch_news() + EXTRA_FEEDS -> [{source, title, link, published}]
    (published = epoch seconds)."""
    raw: list[dict] = []
    got: set[str] = set()
    try:
        import news
        df = news.fetch_news()
        if df is not None and len(df):
            for r in df.to_dict("records"):
                raw.append(r)
                got.add(str(r.get("source")))
    except Exception:
        pass
    jobs = [(cat, src, url)
            for cat, feeds in getattr(config, "NEWS_FEEDS", {}).items()
            for src, url in feeds if src not in got]
    jobs += [("Crypto", n, u) for n, u in EXTRA_FEEDS]
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for res in pool.map(lambda j: _parse_feed_soft(*j), jobs):
                raw.extend(res or [])
    except Exception:
        pass
    out = []
    for r in raw:
        try:
            out.append({"source": str(r.get("source") or "RSS"),
                        "title": str(r.get("title") or "").strip(),
                        "link": str(r.get("link") or ""),
                        "published": _row_ts(r.get("published"))})
        except Exception:
            continue
    return out


def fetch_calendar() -> list[dict]:
    j = _get_json(CAL_URL)
    return j if isinstance(j, list) else []


DEFAULT_FETCHERS = {
    "binance": fetch_binance, "upbit": fetch_upbit, "okx": fetch_okx,
    "bybit": fetch_bybit, "rss": fetch_rss, "calendar": fetch_calendar,
}


# ------------------------------------------------------------ time helpers
def _as_dt(now=None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if isinstance(now, (int, float)):
        return datetime.fromtimestamp(float(now), timezone.utc)
    if isinstance(now, pd.Timestamp):
        now = now.to_pydatetime()
    if isinstance(now, str):
        now = datetime.fromisoformat(now.replace("Z", "+00:00"))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def to_pkt(dt) -> datetime:
    return _as_dt(dt).astimezone(PKT)


def fmt_pkt(dt, with_utc: bool = True) -> str:
    """'17:30 PKT (12:30 UTC)'."""
    d = _as_dt(dt)
    s = f"{d.astimezone(PKT):%H:%M} PKT"
    return s + (f" ({d:%H:%M} UTC)" if with_utc else "")


def parse_cal_time(s: str) -> datetime:
    """Forex-Factory ISO time with offset -> aware UTC datetime."""
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")) \
        .astimezone(timezone.utc)


# ------------------------------------------------------------ calendar logic
_MACRO_RE = re.compile(r"\bFOMC\b|\bFed Chair\b|\bPowell\b|\bFederal Funds\b",
                       _I)


def filter_calendar(raw) -> list[dict]:
    """Keep USD High-impact events + FOMC / Fed Chair / Powell / Federal Funds
    titles regardless of impact. 'FOMC Member X Speaks' (a dozen a week, all
    Low/Medium) only counts when it is itself High impact."""
    out = []
    for e in raw or []:
        try:
            if str(e.get("country", "")).upper() != "USD":
                continue
            title = str(e.get("title") or "").strip()
            impact = str(e.get("impact") or "").strip()
            special = bool(_MACRO_RE.search(title)) and \
                not re.search(r"\bFOMC Member\b", title, _I)
            if impact.lower() != "high" and not special:
                continue
            dt = parse_cal_time(e["date"])
            out.append({"ts": dt.timestamp(), "title": title,
                        "impact": impact,
                        "forecast": str(e.get("forecast") or "").strip(),
                        "previous": str(e.get("previous") or "").strip()})
        except Exception:
            continue
    out.sort(key=lambda x: (x["ts"], x["title"]))
    return out


def reminder_due(event_ts: float, now) -> bool:
    """True when the event is 20-40 min away (the '30 min before' bell)."""
    mins = (float(event_ts) - _as_dt(now).timestamp()) / 60.0
    return 20.0 <= mins <= 40.0


def followup_due(event_ts: float, now) -> bool:
    """True 30-45 min after the print (the BTC-reaction follow-up)."""
    mins = (_as_dt(now).timestamp() - float(event_ts)) / 60.0
    return 30.0 <= mins <= 45.0


# ------------------------------------------------------------ text helpers
def clean(s, limit: int | None = None) -> str:
    """Telegram-Markdown-v1-safe text: drop * _ ` [ ] and squash spaces."""
    s = re.sub(r"[*_`\[\]]", "", str(s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    if limit and len(s) > limit:
        s = s[: max(1, limit - 1)].rstrip() + "…"
    return s


def _link(url: str, label: str = "open") -> str:
    u = str(url or "").strip()
    if not u.lower().startswith("http"):
        return ""
    for ch, enc in ((" ", "%20"), ("(", "%28"), (")", "%29"), ("_", "%5F"),
                    ("*", "%2A"), ("`", "%60"), ("[", "%5B"), ("]", "%5D")):
        u = u.replace(ch, enc)
    return f"[{label}]({u})"


def _fit(lines: list[str]) -> str:
    """Join lines; if over MAX_MSG drop middle lines (keeping header + the
    honest last line) until it fits."""
    lines = [ln for ln in lines if ln]
    msg = "\n".join(lines)
    while len(msg) > MAX_MSG and len(lines) > 2:
        lines.pop(-2)
        msg = "\n".join(lines)
    if len(msg) > MAX_MSG:
        msg = lines[0][:MAX_MSG]
    return msg


def _pct(x: float, nd: int = 1) -> str:
    v = round(float(x) * 100.0, nd)
    sign = "+" if v >= 0 else "−"
    return f"{sign}{abs(v):.{nd}f}%"


def _fmt_price(p: float) -> str:
    p = float(p)
    if p >= 1000:
        return f"{p:,.0f}"
    if p >= 1:
        return f"{p:,.4g}" if p < 100 else f"{p:,.2f}"
    return f"{p:.6g}"


# --------------------------------------------------------------- formatters
_EX_HEADER = {"spot_listing": "LISTING", "delisting": "DELISTING",
              "caution": "CAUTION FLAG", "market_add": "NEW KRW MARKET"}


def fmt_exchange(it: dict, bases=None) -> str:
    """🏦 listing / ⚠️ delisting-caution bell for one exchange notice."""
    kind = it.get("kind")
    src = clean(it.get("source") or "Exchange")
    ticks = [clean(t) for t in (it.get("tickers") or [])][:6]
    tick_s = ", ".join(ticks) if ticks else "see notice"
    bull = it.get("direction") == "bull"
    emoji = "🏦" if bull else "⚠️"
    head = f"{emoji} *{src.upper()} {_EX_HEADER.get(kind, 'NOTICE')} — {tick_s}*"
    lines = [head, clean(it.get("title"), 200)]
    meta = []
    if it.get("markets"):
        meta.append("markets: " + ", ".join(clean(m) for m in it["markets"]))
    if it.get("ts"):
        meta.append("posted " + fmt_pkt(it["ts"]))
    bset = {str(b).upper() for b in (bases or [])}
    inuni = [t for t in ticks if t in bset]
    if inuni:
        meta.append("in your universe: " + ", ".join(inuni))
    lk = _link(it.get("link"))
    if lk:
        meta.append(lk)
    lines.append(" · ".join(meta))
    if bull:
        line = LISTING_LINE_UPBIT if src.lower() == "upbit" else \
            LISTING_LINE_OTHER
    elif kind == "caution":
        line = CAUTION_LINE
    else:
        line = DELIST_LINE
    lines.append(f"_{line}_")
    return _fit(lines)


def fmt_news(it: dict) -> str:
    """📰 big coin-news bell."""
    ticks = [clean(t) for t in (it.get("tickers") or [])][:3]
    d = it.get("direction")
    dword = "BULLISH" if d == "bull" else ("BEARISH" if d == "bear"
                                           else "NEWS")
    kind = KIND_LABEL.get(it.get("kind"), clean(it.get("kind")))
    lines = [f"📰 *{' · '.join(ticks)} — {dword} {clean(kind)}*",
             clean(it.get("title"), 220)]
    meta = []
    if it.get("names"):
        meta.append("big name: " + ", ".join(clean(n) for n in
                                             it["names"][:3]))
    meta.append(clean(it.get("source"), 40))
    if it.get("ts"):
        meta.append(fmt_pkt(it["ts"]))
    lk = _link(it.get("link"))
    if lk:
        meta.append(lk)
    lines.append(" · ".join(m for m in meta if m))
    lines.append(f"_{NEWS_BEAR_LINE if d == 'bear' else NEWS_BULL_LINE}_")
    return _fit(lines)


def fmt_surge(ev: dict, headlines=None) -> str:
    """🚨 unusual move / drop bell. `headlines` = memory entries."""
    up = ev.get("direction") == "up"
    base = clean(ev.get("base"))
    what = "UNUSUAL MOVE" if up else "UNUSUAL DROP"
    lines = [f"🚨 *{what} — {base} {_pct(ev['r4'])} in 4h*",
             f"{ev['sigma']:.1f}σ vs its normal 4h swing · volume "
             f"{ev['vol_mult']:.1f}× normal · BTC {_pct(ev['btc_r4'])} (quiet)",
             f"now {_fmt_price(ev['price'])} · 4h window closed "
             f"{fmt_pkt(ev['window_end'])}"]
    heads = list(headlines or [])[:2]
    if heads:
        for h in heads:
            lines.append(f"news found: {clean(h.get('title'), 110)} "
                         f"({clean(h.get('src'), 30)})")
    else:
        lines.append("no headline found yet — something is moving it")
    if up:
        line = SURGE_LINE + (SURGE_BIG_LINE if ev["r4"] >= 0.14 else "")
    else:
        line = DROP_LINE
    lines.append(f"_{line}_")
    return _fit(lines)


def _group_titles(evs: list[dict]) -> str:
    return " + ".join(clean(e["title"], 60) for e in evs)


def fmt_macro_pre(evs: list[dict], now) -> str:
    """🗓 reminder ~30 min before a (group of) US print(s) at the same time."""
    ts = evs[0]["ts"]
    mins = max(1, int(round((ts - _as_dt(now).timestamp()) / 60.0)))
    head = f"🗓 *US {_group_titles(evs)} in {mins} min* — {fmt_pkt(ts)}"
    if len(evs) == 1:
        e = evs[0]
        parts = [head]
        if e.get("forecast"):
            parts.append(f"forecast {clean(e['forecast'])}")
        if e.get("previous"):
            parts.append(f"previous {clean(e['previous'])}")
        parts.append(MACRO_TAIL)
        return _fit([" · ".join(parts)])
    lines = [head]
    for e in evs[:6]:
        fp = []
        if e.get("forecast"):
            fp.append(f"forecast {clean(e['forecast'])}")
        if e.get("previous"):
            fp.append(f"previous {clean(e['previous'])}")
        lines.append(f"• {clean(e['title'], 60)}"
                     + (" — " + " · ".join(fp) if fp else ""))
    lines.append(MACRO_TAIL)
    return _fit(lines)


def fmt_macro_post(evs: list[dict], move: dict) -> str:
    """🗓 follow-up 30-45 min after the print with BTC's reaction."""
    ts = evs[0]["ts"]
    return _fit([
        f"🗓 *{_group_titles(evs)} released* — BTC moved "
        f"{_pct(move['move'])} since the print ({fmt_pkt(ts, False)}) · now "
        f"{_fmt_price(move['now'])} · range {_pct(move['lo'])} / "
        f"{_pct(move['hi'])}"])


def fmt_digest(st: dict, now) -> str:
    """🗞 09:00 PKT morning digest: today's US high-impact events, the top
    coin catalysts of the last 24h, and the last 24h's unusual moves."""
    now_dt = _as_dt(now)
    now_ts = now_dt.timestamp()
    today = now_dt.astimezone(PKT).date()
    head = [f"🗞 *NEWS RADAR — MORNING*",
            f"{now_dt.astimezone(PKT):%a %d %b} · {fmt_pkt(now_dt, False)}"]
    tail = "_Information only — none of this is a buy signal._"
    budget = MAX_MSG - len("\n".join(head)) - len(tail) - 4
    body: list[str] = []

    def add(line: str) -> bool:
        nonlocal budget
        if len(line) + 1 > budget:
            return False
        body.append(line)
        budget -= len(line) + 1
        return True

    evs = [e for e in st.get("cal_events") or []
           if to_pkt(e["ts"]).date() == today]
    add("*US high-impact today (PKT):*")
    if not evs:
        add("• none scheduled")
    for e in evs[:6]:
        fp = []
        if e.get("forecast"):
            fp.append(f"f {clean(e['forecast'])}")
        if e.get("previous"):
            fp.append(f"p {clean(e['previous'])}")
        add(f"• {to_pkt(e['ts']):%H:%M} {clean(e['title'], 45)}"
            + (" — " + " · ".join(fp) if fp else ""))

    mem = [m for m in st.get("memory") or []
           if now_ts - float(m.get("ts") or 0) <= 24 * 3600
           and m.get("dir") in ("bull", "bear") and m.get("kind") not in
           ("futures_launch", "futures_delist", "pair_removal", "other",
            "ignore", "listing_update", "delisting_update")]
    mem.sort(key=lambda m: (bool(m.get("big")), float(m.get("score") or 0),
                            float(m.get("ts") or 0)), reverse=True)
    picked, keys = [], set()
    for m in mem:
        k = (tuple(m.get("tickers") or []), m.get("kind"))
        if k in keys:
            continue
        keys.add(k)
        picked.append(m)
        if len(picked) >= 5:
            break
    add("*Coin catalysts, last 24h:*")
    if not picked:
        add("• nothing big")
    for m in picked:
        dot = "🟢" if m.get("dir") == "bull" else "🔴"
        tk = ",".join(clean(t) for t in (m.get("tickers") or [])[:2])
        add(f"• {dot} {tk} {clean(KIND_LABEL.get(m.get('kind'), m.get('kind')))}"
            f" — {clean(m.get('title'), 55)}")

    sg = [s for s in st.get("surges") or []
          if now_ts - float(s.get("ts") or 0) <= 24 * 3600]
    add("*Unusual moves, last 24h:*")
    if not sg:
        add("• none")
    for s in sg[-5:]:
        add(f"• 🚨 {clean(s.get('base'))} {_pct(s.get('r4', 0))} (4h) · "
            f"{fmt_pkt(s['ts'], False)}")
    return "\n".join(head + body + [tail])


# ----------------------------------------------------------- surge detector
def _base_of(sym: str) -> str:
    s = str(sym or "").upper().strip()
    b = s[:-4] if s.endswith("USDT") else s
    return re.sub(r"^1(?:0{3,})(?=[A-Z])", "", b)


def _kl_arrays(df, now_ts: float | None, step: int):
    """DataFrame (index = candle open time) -> dict of numpy arrays, sorted,
    with the still-forming candle dropped when now_ts is given."""
    if df is None or len(df) == 0:
        return None
    idx = df.index
    if not isinstance(idx, pd.DatetimeIndex):
        if "open_time" in getattr(df, "columns", []):
            idx = pd.DatetimeIndex(pd.to_datetime(df["open_time"], utc=True))
        else:
            idx = pd.DatetimeIndex(pd.to_datetime(idx, utc=True))
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    t = np.array([ts.timestamp() for ts in idx.tz_convert("UTC")],
                 dtype="float64")
    cols = {c.lower(): c for c in df.columns}
    try:
        arr = {k: np.asarray(df[cols[k]], dtype="float64")
               for k in ("open", "high", "low", "close", "volume")}
    except KeyError:
        return None
    order = np.argsort(t)
    t = t[order]
    arr = {k: v[order] for k, v in arr.items()}
    if now_ts is not None:
        keep = t + step <= now_ts + 1e-6
        t = t[keep]
        arr = {k: v[keep] for k, v in arr.items()}
    arr["t"] = t
    return arr


def _surge_one(sym: str, d: dict, btc: dict, now_ts: float) -> dict | None:
    t, c, v = d["t"], d["close"], d["volume"]
    n = len(c)
    if n < 4 * 20 + 5:
        return None
    # stale feed guard: last closed candle must be the latest (or one before)
    expected = (now_ts // 3600) * 3600 - 3600
    if t[-1] < expected - 3600:
        return None
    if t[-1] - t[-5] != 4 * 3600:
        return None                     # gap inside the window
    r4 = c[-1] / c[-5] - 1.0
    if abs(r4) < 0.08:
        return None
    qv = v * c
    q4 = float(qv[-4:].sum())
    rets, vols = [], []
    for k in range(1, 43):
        end = n - 1 - 4 * k
        start = end - 4
        if start < 0:
            break
        if c[start] > 0:
            rets.append(c[end] / c[start] - 1.0)
            vols.append(float(qv[end - 3:end + 1].sum()))
    if len(rets) < 20:
        return None
    sd = float(np.std(rets, ddof=1))
    med = float(np.median(vols))
    if sd <= 0 or med <= 0:
        return None
    sigma = abs(r4) / sd
    vol_mult = q4 / med
    bt = dict(zip(btc["t"].tolist(), btc["close"].tolist()))
    b1, b0 = bt.get(float(t[-1])), bt.get(float(t[-5]))
    if not b1 or not b0:
        return None
    btc_r4 = b1 / b0 - 1.0
    if sigma < 3.0 or vol_mult < 4.0 or abs(btc_r4) >= 0.015:
        return None
    return {"symbol": sym, "base": _base_of(sym),
            "direction": "up" if r4 > 0 else "down", "r4": float(r4),
            "sigma": float(sigma), "vol_mult": float(vol_mult),
            "btc_r4": float(btc_r4), "price": float(c[-1]),
            "window_start": float(t[-4]), "window_end": float(t[-1] + 3600)}


def scan_surges(get_klines, symbols, now=None, workers: int = 8) -> list[dict]:
    """Unusual coin-specific 4h moves on CLOSED 1h candles.

    Fires when r4 >= +8% (or <= -8%), |r4| >= 3x the std of the prior 42
    non-overlapping 4h block returns (~7 days), the 4 candles' quote volume
    (volume x close) >= 4x the median block volume, and BTC's same-window
    move |r| < 1.5%. Never raises; returns [] on any failure."""
    try:
        now_ts = _as_dt(now).timestamp()
        btc = _kl_arrays(get_klines("BTCUSDT", "1h", limit=200), now_ts, 3600)
        if btc is None or len(btc["t"]) < 6:
            return []
    except Exception:
        return []

    def one(sym):
        try:
            if str(sym).upper() == "BTCUSDT":
                return None
            d = _kl_arrays(get_klines(sym, "1h", limit=200), now_ts, 3600)
            return _surge_one(str(sym).upper(), d, btc, now_ts) if d else None
        except Exception:
            return None

    syms = list(dict.fromkeys(symbols or []))
    out: list[dict] = []
    try:
        if workers and workers > 1 and len(syms) > 1:
            with ThreadPoolExecutor(max_workers=min(workers, len(syms))) as p:
                res = list(p.map(one, syms))
        else:
            res = [one(s) for s in syms]
        out = [r for r in res if r]
    except Exception:
        out = []
    out.sort(key=lambda e: -abs(e["r4"]))
    return out


def _btc_since(get_klines, event_ts: float) -> dict | None:
    """BTC move from the open of the 5m candle containing the print to now."""
    try:
        d = _kl_arrays(get_klines("BTCUSDT", "5m", limit=24), None, 300)
        if d is None or not len(d["t"]):
            return None
        t = d["t"]
        hit = np.where((t <= event_ts) & (event_ts < t + 300))[0]
        if not len(hit):
            return None
        i = int(hit[0])
        p0 = float(d["open"][i])
        if p0 <= 0:
            return None
        now_p = float(d["close"][-1])
        return {"move": now_p / p0 - 1.0, "now": now_p,
                "hi": float(d["high"][i:].max()) / p0 - 1.0,
                "lo": float(d["low"][i:].min()) / p0 - 1.0}
    except Exception:
        return None


# ------------------------------------------------------------------- state
def _blank_state() -> dict:
    return {"v": 1, "seen": {}, "primed": [], "last_bell": {}, "memory": [],
            "surges": [], "surge_cd": {}, "cal_events": [], "macro_sent": {},
            "digest_date": "", "last_run": {}}


def _load_state() -> dict:
    st = _blank_state()
    try:
        p = Path(STATE_FILE)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k, v in data.items():
                    if k in st and isinstance(v, type(st[k])):
                        st[k] = v
    except Exception:
        pass
    return st


def _save_state(st: dict) -> None:
    """Atomic write (tmp + rename); falls back to a direct write where the
    filesystem refuses the rename. Never raises."""
    try:
        p = Path(STATE_FILE)
        p.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(st, ensure_ascii=False)
    except Exception:
        return
    tmp = p.with_name(p.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, p)
        return
    except Exception:
        pass
    try:
        p.write_text(text, encoding="utf-8")
    except Exception:
        pass
    try:
        if tmp.exists():
            tmp.unlink()
    except Exception:
        pass


def _due(st: dict, key: str, every: float, now_ts: float) -> bool:
    last = float(st["last_run"].get(key, 0) or 0)
    if now_ts - last >= every - 5:
        st["last_run"][key] = now_ts
        return True
    return False


def _prune(st: dict, now_ts: float) -> None:
    cut = now_ts - MEMORY_HOURS * 3600
    st["memory"] = [m for m in st["memory"]
                    if max(float(m.get("ts") or 0),
                           float(m.get("seen") or 0)) >= cut][-400:]
    st["surges"] = [s for s in st["surges"]
                    if float(s.get("ts") or 0) >= cut][-200:]
    for k in ("last_bell", "surge_cd", "macro_sent"):
        st[k] = {a: b for a, b in st[k].items()
                 if now_ts - float(b or 0) <= 3 * 86400}
    for src in list(st["seen"]):
        st["seen"][src] = st["seen"][src][-SEEN_CAP:]


# ------------------------------------------------------------------ helpers
def _call(fn) -> list:
    if fn is None:
        return []
    try:
        r = fn()
        return list(r or [])
    except Exception:
        return []


def _safe_record(record):
    def rec(payload: dict):
        if record is None:
            return
        try:
            record(STREAM, payload)
        except Exception:
            pass
    return rec


def _safe_send(send, text: str) -> bool:
    if send is None:
        return False
    try:
        r = send(text)
    except Exception:
        return False
    if r is False:
        return False
    if isinstance(r, tuple) and r and r[0] is False:
        return False
    return True


def _iso(ts: float) -> str:
    try:
        return datetime.fromtimestamp(float(ts), timezone.utc).isoformat()
    except Exception:
        return ""


def _remember(st: dict, it: dict, now_ts: float) -> None:
    if not it.get("tickers"):
        return
    st["memory"].append({
        "ts": float(it.get("ts") or now_ts), "seen": now_ts,
        "src": it.get("source"), "title": str(it.get("title") or "")[:200],
        "link": it.get("link") or "", "tickers": list(it["tickers"])[:6],
        "dir": it.get("direction"), "kind": it.get("kind"),
        "big": bool(it.get("big")), "score": float(it.get("score") or
                                                   (1.5 if it.get("big")
                                                    else 0.5))})


def _headlines_for(st: dict, base: str, now_ts: float) -> list[dict]:
    hs = [m for m in st.get("memory") or []
          if base in (m.get("tickers") or [])
          and now_ts - float(m.get("ts") or 0) <= 24 * 3600
          and m.get("kind") not in ("ignore",)]
    hs.sort(key=lambda m: float(m.get("ts") or 0), reverse=True)
    out, seen = [], set()
    for h in hs:
        k = str(h.get("title"))[:60].lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(h)
    return out[:2]


def _mark_seen(st: dict, src_key: str, iid: str, seen_sets: dict) -> bool:
    """Returns True when the id was NEW (and marks it)."""
    s = seen_sets.setdefault(src_key, set(st["seen"].get(src_key, [])))
    if iid in s:
        return False
    s.add(iid)
    st["seen"].setdefault(src_key, []).append(iid)
    return True


def _payload(it: dict) -> dict:
    return {"source": it.get("source"), "kind": it.get("kind"),
            "direction": it.get("direction"), "big": bool(it.get("big")),
            "tickers": list(it.get("tickers") or []),
            "title": it.get("title"), "link": it.get("link"),
            "ts": _iso(it.get("ts") or 0)}


# ------------------------------------------------------------- processors
def _process_exchange(items, st, now_ts, bases, rec) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    seen_sets: dict = {}
    by_src: dict[str, list] = {}
    for it in items:
        if isinstance(it, dict) and it.get("id") and it.get("src_key"):
            by_src.setdefault(it["src_key"], []).append(it)
    for src_key, its in by_src.items():
        priming = src_key not in st["primed"]
        for it in its:
            if not _mark_seen(st, src_key, it["id"], seen_sets):
                continue
            if it.get("kind") == "ignore":
                continue
            rec(_payload(it))
            _remember(st, it, now_ts)
            if priming or not it.get("bell"):
                continue
            ts = float(it.get("ts") or now_ts)
            if now_ts - ts > EX_MAX_AGE_H * 3600:
                continue
            ticks = it.get("tickers") or []
            keys = [f"ex|{it.get('source')}|{t}|{it.get('kind')}"
                    for t in ticks]
            if keys and all(now_ts - float(st["last_bell"].get(k, 0))
                            < EX_COOLDOWN_H * 3600 for k in keys):
                continue
            for k in keys:
                st["last_bell"][k] = now_ts
            out.append((1, fmt_exchange(it, bases)))
        if priming:
            st["primed"].append(src_key)
    return out


def _process_rss(rows, st, now_ts, bases, rec) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    seen_sets: dict = {}
    primed_now: set[str] = set()
    for r in rows:
        try:
            title = str(r.get("title") or "").strip()
            if not title:
                continue
            source = str(r.get("source") or "RSS")
            link = str(r.get("link") or "")
            src_key = "rss:" + source
            iid = "rss:" + _hid(link or (source + "|" + title))
            priming = src_key not in st["primed"] or src_key in primed_now
            if src_key not in st["primed"]:
                st["primed"].append(src_key)
                primed_now.add(src_key)
            if not _mark_seen(st, src_key, iid, seen_sets):
                continue
            tickers = tag_coins(title, bases)
            cls = classify(title)
            big = is_big_news(cls, tickers)
            ts = _row_ts(r.get("published")) or now_ts
            it = {"source": source, "title": title, "link": link, "ts": ts,
                  "tickers": tickers, "big": big, **cls}
            if tickers or cls["direction"] != "neutral":
                rec(_payload(it))
            _remember(st, it, now_ts)
            if priming or not big:
                continue
            if now_ts - ts > RSS_MAX_AGE_H * 3600:
                continue
            key = f"news|{tickers[0]}|{cls['direction']}"
            if now_ts - float(st["last_bell"].get(key, 0)) < \
                    NEWS_COOLDOWN_H * 3600:
                continue
            st["last_bell"][key] = now_ts
            out.append((3, fmt_news(it)))
        except Exception:
            continue
    return out


def _process_surges(evs, st, now_ts, rec) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for ev in evs or []:
        try:
            key = f"{ev['base']}|{ev['direction']}"
            if now_ts - float(st["surge_cd"].get(key, 0)) < \
                    SURGE_COOLDOWN_H * 3600:
                continue
            st["surge_cd"][key] = now_ts
            heads = _headlines_for(st, ev["base"], now_ts)
            msg = fmt_surge(ev, heads)
            st["surges"].append({"ts": now_ts, "base": ev["base"],
                                 "r4": ev["r4"], "dir": ev["direction"]})
            rec({"source": "surge_scan",
                 "kind": "unusual_move" if ev["direction"] == "up"
                 else "unusual_drop",
                 "direction": "bull" if ev["direction"] == "up" else "bear",
                 "big": True, "tickers": [ev["base"]],
                 "title": f"{ev['base']} {_pct(ev['r4'])} in 4h",
                 "link": "", "ts": _iso(now_ts), "r4": ev["r4"],
                 "sigma": ev["sigma"], "vol_mult": ev["vol_mult"],
                 "btc_r4": ev["btc_r4"], "price": ev["price"],
                 "headlines": [h.get("title") for h in heads]})
            out.append((2, msg))
        except Exception:
            continue
    return out


def _process_macro(st, now_dt, get_klines) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    now_ts = now_dt.timestamp()
    groups: dict[float, list] = {}
    for e in st.get("cal_events") or []:
        try:
            groups.setdefault(float(e["ts"]), []).append(e)
        except Exception:
            continue
    for ts, evs in sorted(groups.items()):
        pre, post = f"pre|{int(ts)}", f"post|{int(ts)}"
        if reminder_due(ts, now_dt) and pre not in st["macro_sent"]:
            st["macro_sent"][pre] = now_ts
            out.append((0, fmt_macro_pre(evs, now_dt)))
        if followup_due(ts, now_dt) and post not in st["macro_sent"] \
                and get_klines is not None:
            mv = _btc_since(get_klines, ts)
            if mv is not None:
                st["macro_sent"][post] = now_ts
                out.append((0, fmt_macro_post(evs, mv)))
    return out


_RUN_LOCK = threading.Lock()


def run(get_klines, symbols, send, record=None, now=None,
        fetch=None) -> list[str]:
    """One NEWS RADAR cycle. Call every worker cycle (~2-5 min); internal
    throttles: exchanges 3 min, RSS 10 min, surge scan 15 min, calendar 6 h,
    digest once a day 04:00-07:00 UTC. Never raises. Returns the messages
    that `send` accepted."""
    if not _RUN_LOCK.acquire(blocking=False):
        return []
    sent: list[str] = []
    st = None
    try:
        now_dt = _as_dt(now)
        now_ts = now_dt.timestamp()
        st = _load_state()
        fetchers = dict(DEFAULT_FETCHERS)
        fetchers.update(fetch or {})
        bases = {_base_of(s) for s in (symbols or [])} | {"BTC", "ETH"}
        rec = _safe_record(record)
        outbox: list[tuple[int, str]] = []

        # 1) calendar refresh (time-gated bells below)
        try:
            if _due(st, "cal", CAL_EVERY, now_ts):
                raw = _call(fetchers.get("calendar"))
                if raw:
                    st["cal_events"] = filter_calendar(raw)
                else:
                    st["last_run"]["cal"] = now_ts - CAL_EVERY + CAL_RETRY
        except Exception:
            pass

        # 2) exchange notices (parallel)
        try:
            if _due(st, "ex", EX_EVERY, now_ts):
                keys = ("binance", "upbit", "okx", "bybit")
                with ThreadPoolExecutor(max_workers=4) as pool:
                    res = list(pool.map(lambda k: _call(fetchers.get(k)),
                                        keys))
                items = [it for r in res for it in r]
                outbox += _process_exchange(items, st, now_ts, bases, rec)
        except Exception:
            pass

        # 3) RSS headlines
        try:
            if _due(st, "rss", RSS_EVERY, now_ts):
                outbox += _process_rss(_call(fetchers.get("rss")), st,
                                       now_ts, bases, rec)
        except Exception:
            pass

        # 4) unusual moves
        try:
            if get_klines is not None and symbols and \
                    _due(st, "surge", SURGE_EVERY, now_ts):
                evs = scan_surges(get_klines, symbols, now_dt)
                outbox += _process_surges(evs, st, now_ts, rec)
        except Exception:
            pass

        # 5) macro reminders / follow-ups
        try:
            outbox += _process_macro(st, now_dt, get_klines)
        except Exception:
            pass

        # 6) morning digest
        try:
            lo, hi = DIGEST_UTC_HOURS
            day = now_dt.date().isoformat()
            if lo <= now_dt.hour < hi and st.get("digest_date") != day:
                st["digest_date"] = day
                outbox.append((4, fmt_digest(st, now_dt)))
        except Exception:
            pass

        outbox.sort(key=lambda x: x[0])
        for _pri, text in outbox[:MAX_BELLS_PER_RUN]:
            if _safe_send(send, text):
                sent.append(text)
        try:
            _prune(st, now_ts)
        except Exception:
            pass
    except Exception:
        pass
    finally:
        if st is not None:
            _save_state(st)
        _RUN_LOCK.release()
    return sent


# ---------------------------------------------------------------- dry run
if __name__ == "__main__":      # python news_radar.py  -> live parse, no sends
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    for name in ("binance", "upbit", "okx", "bybit"):
        its = DEFAULT_FETCHERS[name]()
        print(f"== {name}: {len(its)} items")
        for it in its[:12]:
            print(f"   [{it['kind']:<16}] bell={it['bell']!s:<5} "
                  f"{it['tickers']} {it['title'][:90]}")
    rows = fetch_rss()
    print(f"== rss: {len(rows)} rows from "
          f"{len({r['source'] for r in rows})} feeds")
    demo_bases = {"BTC", "ETH", "SOL", "XRP", "QNT", "NEAR", "ENA", "UNI",
                  "LINK", "DOGE", "ADA", "AVAX", "SUI", "HYPE", "XPL"}
    for r in rows:
        tk = tag_coins(r["title"], demo_bases)
        c = classify(r["title"])
        if is_big_news(c, tk):
            print(f"   BIG {tk} {c['direction']}/{c['kind']} "
                  f"{r['source']}: {r['title'][:90]}")
    cal = filter_calendar(fetch_calendar())
    print(f"== calendar: {len(cal)} kept")
    for e in cal:
        print(f"   {fmt_pkt(e['ts'])} {e['title']} ({e['impact']})")
