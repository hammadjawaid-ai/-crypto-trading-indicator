"""🔮 KRONOS — Tsinghua candlestick foundation model, wrapped for our stack.

Kronos (Shi et al., AAAI 2026, MIT license, github.com/shiyu-coder/Kronos)
is a decoder-only transformer pre-trained on raw OHLCV K-line sequences
from 45+ global exchanges. Feed it ~400 candles, it forecasts the next N
(price + volume) autoregressively.

House rules apply (user 2026-07-26 SURGE lesson: "don't deploy first,
test"): this wrapper gives the model a voice, NOT a vote — a labeled
paper-trading presence + silent desk tier until a walk-forward backtest
on OUR coins/timeframe earns it more. The creators say it themselves:
research tool, not a money printer — raw signals ignore fees/slippage,
which is exactly what our harness adds.

Runtime is optional by design: torch is NOT in requirements.txt, so the
deployed worker/app degrade gracefully when Kronos isn't installed
(available() -> False). Local install: pip install torch --index-url
https://download.pytorch.org/whl/cpu, plus einops huggingface_hub
safetensors tqdm; weights auto-download from Hugging Face on first use.
"""
from __future__ import annotations

import os
import sys

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
# Vendored copy first (deploy), local clone second (dev).
for _p in (os.path.join(_HERE, "kronos_vendor"),
           os.path.join(_HERE, ".kronos_repo")):
    if os.path.isdir(os.path.join(_p, "model")) and _p not in sys.path:
        sys.path.insert(0, _p)

MODEL_ID = os.environ.get("KRONOS_MODEL", "NeoQuasar/Kronos-small")
TOKENIZER_ID = os.environ.get("KRONOS_TOKENIZER",
                              "NeoQuasar/Kronos-Tokenizer-base")
DEVICE = os.environ.get("KRONOS_DEVICE", "cpu")
LOOKBACK = int(os.environ.get("KRONOS_LOOKBACK", "400"))   # candles in
MAX_CONTEXT = 512                                          # small/base cap
# Direction call threshold: predicted |move| below this is FLAT (noise).
FLAT_PCT = float(os.environ.get("KRONOS_FLAT_PCT", "0.5"))

_predictor = None
_import_err = None


def available() -> bool:
    """True when Kronos is enabled AND torch + the package import.

    KRONOS_ENABLED=0 is the ops kill switch (e.g. if the Render
    instance struggles with torch memory) — everything downstream
    degrades to '🔮 offline' without code changes."""
    global _import_err
    if (os.environ.get("KRONOS_ENABLED", "1") or "1").strip() == "0":
        _import_err = "disabled via KRONOS_ENABLED=0"
        return False
    try:
        import torch                                    # noqa: F401
        from model import Kronos, KronosTokenizer       # noqa: F401
        return True
    except Exception as exc:                            # torch missing etc.
        _import_err = exc
        return False


def _get_predictor():
    global _predictor
    if _predictor is None:
        from model import Kronos, KronosPredictor, KronosTokenizer
        tok = KronosTokenizer.from_pretrained(TOKENIZER_ID)
        mdl = Kronos.from_pretrained(MODEL_ID)
        _predictor = KronosPredictor(mdl, tok, device=DEVICE,
                                     max_context=MAX_CONTEXT)
    return _predictor


def forecast_window(x_df: pd.DataFrame, x_ts: pd.Series,
                    horizon: int = 24, freq: str = "1h",
                    samples: int = 1, temperature: float = 0.6,
                    top_p: float = 0.9) -> pd.DataFrame:
    """Raw forecast for a prepared window (no network; backtest-safe).

    x_df: columns open/high/low/close/volume[/amount], oldest first,
    <= LOOKBACK rows. x_ts: matching pd.Series of timestamps. Returns
    the predicted OHLCV DataFrame for the next `horizon` candles.
    """
    y_ts = pd.Series(pd.date_range(
        start=pd.Timestamp(x_ts.iloc[-1]) + pd.Timedelta(freq),
        periods=horizon, freq=freq))
    return _get_predictor().predict(
        df=x_df, x_timestamp=x_ts.reset_index(drop=True),
        y_timestamp=y_ts, pred_len=horizon, T=temperature,
        top_p=top_p, sample_count=samples, verbose=False)


def summarize(last_close: float, pred_df: pd.DataFrame) -> dict:
    """Turn a predicted OHLCV path into a signal-shaped verdict."""
    end_move = (float(pred_df["close"].iloc[-1]) / last_close - 1) * 100
    hi = (float(pred_df["high"].max()) / last_close - 1) * 100
    lo = (float(pred_df["low"].min()) / last_close - 1) * 100
    if end_move >= FLAT_PCT:
        direction = "UP"
    elif end_move <= -FLAT_PCT:
        direction = "DOWN"
    else:
        direction = "FLAT"
    return {"direction": direction,
            "exp_move_pct": round(end_move, 2),
            "path_high_pct": round(hi, 2),
            "path_low_pct": round(lo, 2),
            "horizon": len(pred_df)}


def forecast(symbol: str, interval: str = "1h", horizon: int = 24,
             samples: int = 1) -> dict | None:
    """Live forecast for a symbol. None when Kronos is unavailable."""
    if not available():
        return None
    import binance_client
    d = binance_client.get_klines(symbol, interval, limit=LOOKBACK)
    if d is None or len(d) < 64:
        return None
    x_df = pd.DataFrame({
        "open": d["open"].astype(float).to_numpy(),
        "high": d["high"].astype(float).to_numpy(),
        "low": d["low"].astype(float).to_numpy(),
        "close": d["close"].astype(float).to_numpy(),
        "volume": d["volume"].astype(float).to_numpy(),
        "amount": d["quote_volume"].astype(float).to_numpy(),
    })
    x_ts = pd.Series(pd.to_datetime(d.index))
    freq = {"1h": "1h", "30m": "30min", "15m": "15min",
            "4h": "4h", "1d": "1D"}.get(interval, "1h")
    pred = forecast_window(x_df, x_ts, horizon=horizon, freq=freq,
                           samples=samples)
    out = summarize(float(x_df["close"].iloc[-1]), pred)
    out["symbol"] = symbol
    out["interval"] = interval
    return out
