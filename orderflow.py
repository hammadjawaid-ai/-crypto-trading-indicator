"""Live order-flow analysis: recent-trade buy/sell pressure and book depth.

Uses Binance's public market-data endpoints (no key). Order flow is the most
'live' layer of the dashboard — it reflects what is happening right now,
independent of candle close — so the app caches it only briefly.
"""
from __future__ import annotations

import pandas as pd

import binance_client
import config


def _pressure_word(buy_pct: float) -> str:
    if buy_pct >= 58:
        return "Buyers in control"
    if buy_pct <= 42:
        return "Sellers in control"
    return "Balanced"


def trade_flow(symbol: str) -> dict | None:
    """Aggressive buy vs sell volume from the most recent executed trades."""
    try:
        df = binance_client.get_recent_trades(symbol)
    except Exception:
        return None
    if df.empty:
        return None

    # is_buyer_maker True  -> taker SOLD into the bid   (aggressive sell)
    # is_buyer_maker False -> taker BOUGHT from the ask (aggressive buy)
    buys = df[~df["is_buyer_maker"]]
    sells = df[df["is_buyer_maker"]]
    buy_quote = float(buys["quote_qty"].sum())
    sell_quote = float(sells["quote_qty"].sum())
    total_quote = buy_quote + sell_quote
    buy_pct = (buy_quote / total_quote * 100) if total_quote else 50.0

    threshold = df["quote_qty"].quantile(config.LARGE_TRADE_QUANTILE)
    large = df[df["quote_qty"] >= threshold].nlargest(8, "quote_qty")
    large_trades = [
        {
            "side": "SELL" if row["is_buyer_maker"] else "BUY",
            "price": float(row["price"]),
            "qty": float(row["qty"]),
            "quote": float(row["quote_qty"]),
            "time": row["time"],
        }
        for _, row in large.iterrows()
    ]

    span = (df["time"].max() - df["time"].min()).total_seconds()
    return {
        "trades": int(len(df)),
        "buy_volume": float(buys["qty"].sum()),
        "sell_volume": float(sells["qty"].sum()),
        "buy_quote": buy_quote,
        "sell_quote": sell_quote,
        "total_quote": total_quote,
        "buy_pct": buy_pct,
        "net_quote": buy_quote - sell_quote,
        "pressure": _pressure_word(buy_pct),
        "large_trades": large_trades,
        "window_seconds": span,
        "last_price": float(df["price"].iloc[-1]),
    }


def book_imbalance(symbol: str) -> dict | None:
    """Order-book bid/ask imbalance and the nearest large walls."""
    try:
        book = binance_client.get_depth(symbol)
    except Exception:
        return None
    bids, asks = book["bids"], book["asks"]
    if bids.empty or asks.empty:
        return None

    best_bid = bids["price"].iloc[0]
    best_ask = asks["price"].iloc[0]
    mid = (best_bid + best_ask) / 2
    band = config.DEPTH_BAND_PCT / 100 * mid
    near_bids = bids[bids["price"] >= mid - band]
    near_asks = asks[asks["price"] <= mid + band]

    bid_quote = float((near_bids["price"] * near_bids["qty"]).sum())
    ask_quote = float((near_asks["price"] * near_asks["qty"]).sum())
    total = bid_quote + ask_quote
    imbalance = ((bid_quote - ask_quote) / total) if total else 0.0

    def _wall(side: pd.DataFrame) -> dict | None:
        if side.empty:
            return None
        row = side.loc[side["qty"].idxmax()]
        return {"price": float(row["price"]), "qty": float(row["qty"]),
                "quote": float(row["price"] * row["qty"])}

    if imbalance > 0.12:
        verdict = "Bid-heavy book — buy-side support"
    elif imbalance < -0.12:
        verdict = "Ask-heavy book — sell-side pressure"
    else:
        verdict = "Balanced order book"

    return {
        "mid_price": mid,
        "spread_pct": (best_ask - best_bid) / mid * 100 if mid else 0.0,
        "bid_quote": bid_quote,
        "ask_quote": ask_quote,
        "imbalance": imbalance,
        "imbalance_pct": (bid_quote / total * 100) if total else 50.0,
        "support": _wall(near_bids),
        "resistance": _wall(near_asks),
        "verdict": verdict,
    }


def snapshot(symbol: str) -> dict:
    """Combined live order-flow snapshot: {'flow': ..., 'book': ...}."""
    return {"flow": trade_flow(symbol), "book": book_imbalance(symbol)}
