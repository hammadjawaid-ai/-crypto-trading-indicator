# Crypto Trading Indicator — Project Resume

> One file to get back into this project. If your Claude session isn't
> showing, open Claude Code in this folder (`F:\Trading Indicator`) — your
> memory auto-loads — or just read this file.

## What it is

A Streamlit dashboard that analyses the top 100 Binance USDT pairs and turns
live technical, derivatives, order-flow, social and news data into concrete,
actionable trading signals (entry / stop / targets) with one clear verdict.

## Run it

- **Locally:** double-click **`run.bat`** in this folder → opens at
  `http://localhost:8501`.
- **Live (cloud):** https://lzvswzxrr2dpnkhmckncuk.streamlit.app/
- **Code (GitHub):** https://github.com/hammadjawaid-ai/-crypto-trading-indicator

## The six tabs

1. **Market Scanner** — every coin scored, ranked, with a Live Trade Signals
   table (entry / stop / targets).
2. **Breakout Radar** — the flagship. Predicts which coins are about to blow
   out. See below.
3. **Ask the Oracle** — a plain-English chat box answering questions like
   "which coin is next for a bullish/bearish blowout?", coin lookups,
   "safest long" and "volume igniting" — straight from the live radar, no
   LLM. Below it, a **Bullish Buy Zones** board: accumulation ranges,
   triggers, stops and targets for bullish coins, read against circulating
   supply and the worldwide market backdrop.
4. **Coin Analysis** — deep per-coin read: "Bottom Line" verdict, Action
   Plan, order flow, history, TradingView chart.
5. **News & Sentiment** — RSS news, Reddit buzz, LunarCrush social leaderboard.
6. **Decision Mode** — buy / hold / sell calls for the top 30 coins.

## Breakout Radar — how it works

A self-contained intelligence engine (`breakout.py`). It scans every coin
across three timeframes and fuses ~11 signals — volume + a volume-ignition
detector, volatility coil, momentum, range break, order flow, quiet
accumulation (OBV), multi-timeframe trend, strength vs Bitcoin, futures
funding, social attention and news catalysts — inside the broad market
backdrop (Fear & Greed + BTC trend + total market cap).

- **Two horizons:** *Imminent* (15m/1h/4h charts, microstructure-driven) and
  *Next 24 hours* (1h/4h/1d charts, news/catalyst-driven). Each uses its own
  signal weighting.
- **Stage grading:** *Building Up* (coiled, hasn't moved — earliest, safest
  entry) · *Just Started* (early breakout) · *Already Ran* (move spent —
  flagged a chasing risk).
- **Trend respect:** every coin's own EMA structure across all three charts
  forms a chart-trend backbone. A call that rides a strong trend is firmed
  up; one that fights it is halved, flagged and confidence-docked — so the
  radar no longer calls a coin bullish while it sits in a clear downtrend.
- **Output:** top 30 coins on a long/short decision board, each with a plain
  verdict ("LIKELY TO GO UP SOON"), entry, target, confidence, 24h volume,
  and a written prediction. Ranked by an Opportunity score.

## Tech / files

- `app.py` — the Streamlit UI (all 6 tabs).
- `breakout.py` — the Breakout Radar engine.
- `oracle.py` — the Ask the Oracle Q&A engine + bullish buy-zone finder.
- `binance_client.py`, `derivatives.py`, `indicators.py`, `signals.py`,
  `orderflow.py`, `tv_analysis.py`, `lunarcrush.py`, `news.py`,
  `sentiment.py`, `social.py`, `market_context.py` — data + analysis modules.
- `config.py` — central config. Reads the LunarCrush API key from `.env`
  (untracked) locally, or Streamlit secrets when deployed.
- Python 3.12, virtualenv in `.venv`.

## Deployment

Streamlit Community Cloud **auto-redeploys on every push to `main`**. To ship
a change: commit and push to GitHub — the live app rebuilds in ~1-2 minutes.
The LunarCrush key lives in Streamlit secrets (quoted TOML:
`LUNARCRUSH_API_KEY = "..."`).

## Status

Built, code-audited and live. The Breakout Radar (both horizons, plain
labels, long/short decision board, volume display, trend-respect) is
complete, and the Ask the Oracle tab — chat box plus Bullish Buy Zones board
— is live. Binance data loads fine on the cloud (the Market Scanner confirms
it).
