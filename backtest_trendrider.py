"""TREND RIDER — the documented edge, tested on YEARS of daily data.

Every deep-history test agrees: 1h price patterns = breakeven noise. The
edge with decades of documentation (and our own 'momentum persists' finding)
is DAILY-scale trend following. This validates the classic spec on 2-3
YEARS x 40 coins, WITH FEES:

  ENTRY  (long):  close breaks the prior 20-day high AND close > EMA50(1d)
  ENTRY  (short): close breaks the prior 20-day low  AND close < EMA50(1d)
  INITIAL STOP:   2.5 x ATR(14d) from entry
  TRAIL:          chandelier — peak -/+ 3 x ATR(14d), never loosens
  EXIT:           trail hit. No fixed TP — winners run for weeks.
  ONE position per coin at a time; fees 0.055% per side (Bybit taker).

Metrics per trade: R after fees (risk = initial stop distance), hold days.
Aggregates: win%, avg win R / avg loss R, expectancy/trade, R per month per
coin, and the whole-portfolio monthly R if each signal risks 1%.
Long-run daily data via deep_history (1d paginates to listing start).
"""
from __future__ import annotations
import io, json, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import os
import binance_client
import deep_history as dh

N_COINS = int(os.environ.get("TR_N", "40"))
SKIP = int(os.environ.get("TR_SKIP", "0"))
DAYS = 1100                  # ~3 years where listing history allows
BREAK_N = 20
EMA_N = 50
ATR_N = 14
STOP_ATR = 2.5
TRAIL_ATR = 3.0
FEE = 0.00055                # per side
ROWS_FILE = ".trend_rows.jsonl"


def _atr(h, l, c, n=ATR_N):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(n).mean().to_numpy()


def _one(sym):
    try:
        d = dh.get_klines_deep(sym, "1d", DAYS)
    except Exception:
        return []
    if d is None or len(d) < 120:
        return []
    o = d["open"].to_numpy(); h = d["high"].to_numpy()
    l = d["low"].to_numpy(); c = d["close"].to_numpy()
    e50 = d["close"].ewm(span=EMA_N, adjust=False).mean().to_numpy()
    atr = _atr(h, l, c)
    n = len(d)
    trades = []
    pos = None                       # dict(side, entry, stop, peak, risk, i0)
    for t in range(max(BREAK_N, EMA_N) + 5, n):
        a = float(atr[t-1]) if atr[t-1] == atr[t-1] else 0.0
        if a <= 0:
            continue
        if pos is None:
            hi_prev = float(np.max(h[t-BREAK_N:t]))
            lo_prev = float(np.min(l[t-BREAK_N:t]))
            if c[t] > hi_prev and c[t] > e50[t]:
                risk = STOP_ATR * a
                pos = {"side": "LONG", "entry": float(c[t]),
                       "stop": float(c[t]) - risk, "peak": float(c[t]),
                       "risk": risk, "i0": t}
            elif c[t] < lo_prev and c[t] < e50[t]:
                risk = STOP_ATR * a
                pos = {"side": "SHORT", "entry": float(c[t]),
                       "stop": float(c[t]) + risk, "peak": float(c[t]),
                       "risk": risk, "i0": t}
            continue
        # manage open position on bar t
        long = pos["side"] == "LONG"
        # exit check FIRST against today's extreme (conservative: stop
        # touched intraday closes the trade at the stop)
        stopped = (l[t] <= pos["stop"]) if long else (h[t] >= pos["stop"])
        if stopped:
            exit_px = pos["stop"]
            g = (exit_px - pos["entry"]) if long else (pos["entry"] - exit_px)
            fees_r = 2 * FEE * pos["entry"] / pos["risk"]
            trades.append({
                "year": str(d.index[t].year),
                "side": pos["side"],
                "r": g / pos["risk"] - fees_r,
                "days": t - pos["i0"],
            })
            pos = None
            continue
        # update peak + chandelier trail (never loosens)
        pos["peak"] = max(pos["peak"], float(h[t])) if long \
            else min(pos["peak"], float(l[t]))
        trail = pos["peak"] - TRAIL_ATR * a if long \
            else pos["peak"] + TRAIL_ATR * a
        pos["stop"] = max(pos["stop"], trail) if long \
            else min(pos["stop"], trail)
    span_days = n
    return [{"sym": sym, "span": span_days, **tr} for tr in trades]


syms = binance_client.get_top_symbols(SKIP + N_COINS)["symbol"].tolist()[SKIP:SKIP + N_COINS]
rows = []
spans = {}
t0 = time.time()
with ThreadPoolExecutor(max_workers=6) as pool:
    futs = {pool.submit(_one, s): s for s in syms}
    for fut in as_completed(futs):
        s = futs[fut]
        try:
            rr = fut.result()
        except Exception:
            rr = []
        if rr:
            spans[s] = rr[0]["span"]
        rows.extend(rr)
        print(f"  done {s:12} +{len(rr)} trades", flush=True)
print(f"total trades: {len(rows)} in {time.time()-t0:.0f}s")
with open(ROWS_FILE, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")

print("=" * 70)
print(f"TREND RIDER (daily, 20d breakout + EMA50, chandelier 3xATR, fees in)")
print(f"universe: {len(spans)} coins · avg history "
      f"{np.mean(list(spans.values())):.0f} days")
print("=" * 70)


def rep(label, seg):
    if not seg:
        print(f"  {label}: no trades")
        return
    rs = [t["r"] for t in seg]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    wr = len(wins) / len(rs) * 100
    exp = float(np.mean(rs))
    aw = float(np.mean(wins)) if wins else 0.0
    al = float(np.mean(losses)) if losses else 0.0
    hold = float(np.median([t["days"] for t in seg]))
    print(f"  {label:12} | n={len(rs):5} | win {wr:5.1f}% | avg win "
          f"{aw:+.2f}R · avg loss {al:+.2f}R | EXP {exp:+.3f}R/trade | "
          f"hold med {hold:.0f}d")


rep("ALL", rows)
rep("LONG", [t for t in rows if t["side"] == "LONG"])
rep("SHORT", [t for t in rows if t["side"] == "SHORT"])
for y in sorted({t["year"] for t in rows}):
    rep(f"LONG {y}", [t for t in rows if t["side"] == "LONG" and t["year"] == y])
# portfolio view: trades per coin-month and monthly expectancy at 1% risk
months = sum(spans.values()) / 30.44
tpm = len(rows) / months if months else 0
exp = float(np.mean([t["r"] for t in rows])) if rows else 0.0
print("-" * 70)
print(f"portfolio: {tpm:.2f} trades per coin-month -> across 40 coins "
      f"~{tpm*40:.0f} trades/month")
print(f"at 1% risk/trade: expected ~{tpm*40*exp:+.1f}% account per month "
      f"(before compounding, after fees)")
print("=" * 70)
print("Positive EXP with big avg-win/avg-loss asymmetry = the documented "
      "trend edge is real on OUR universe. That becomes the system's core.")
