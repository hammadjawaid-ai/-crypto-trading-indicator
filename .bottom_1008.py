"""Last night (2026-10-08) replayed through the bottom study's exact rule on fresh
15m candles: when each confirmation fired on BTC, and the basket result of the
higher-high rule (stop under the low - 0.25 ATR, TP 1.5R, 8h, fees) across the
top-150 alts — so we know where that night sits in the 13-month distribution."""
import calendar
import io
import sys
import time

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"F:\Trading Indicator")
import binance_client as bc

PK = 5 * 3600
FEE = 0.0011
T0 = calendar.timegm((2026, 10, 8, 14, 0, 0))     # 19:00 PKT


def ind(k):
    c = k["close"].astype(float)
    h, l, v = k["high"].astype(float), k["low"].astype(float), k["volume"].astype(float)
    ema20 = c.ewm(span=20, adjust=False).mean()
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    hist = macd - macd.ewm(span=9, adjust=False).mean()
    bbl = c.rolling(20).mean() - 2 * c.rolling(20).std()
    hi12 = h.rolling(48).max()
    return c, h, l, v, ema20, rsi, hist, bbl, hi12


btc = bc.get_klines("BTCUSDT", "15m", limit=600)
btc.index = pd.to_datetime(btc.index, utc=True)
c, h, l, v, ema20, rsi, hist, bbl, hi12 = ind(btc)
idx = list(btc.index)
i_cross = next(i for i, t in enumerate(idx) if t.timestamp() >= T0 and c.iloc[i] / hi12.iloc[i] - 1 <= -0.02)
pk = lambda i: time.strftime("%H:%M", time.gmtime(idx[i].timestamp() + PK))
print(f"BTC -2% crossing vs 12h high at {pk(i_cross)} PKT (close {c.iloc[i_cross]:.0f})")
runlow, lowbar = l.iloc[i_cross], i_cross
sig = {}
rsi_low = rsi.iloc[i_cross] < 30
trough = hist.iloc[i_cross]
for i in range(i_cross + 1, i_cross + 24):
    if l.iloc[i] < runlow:
        runlow, lowbar = l.iloc[i], i
    rsi_low = rsi_low or rsi.iloc[i] < 30
    trough = min(trough, hist.iloc[i])
    if "hh" not in sig and c.iloc[i] > h.iloc[i - 1] and l.iloc[i] >= runlow:
        sig["hh"] = i
    if "rsi" not in sig and rsi_low and rsi.iloc[i] > 30 and rsi.iloc[i - 1] <= 30:
        sig["rsi"] = i
    if "macd" not in sig and hist.iloc[i - 1] > trough and hist.iloc[i] > hist.iloc[i - 1] and hist.iloc[i] < 0:
        sig["macd"] = i
    if "ema" not in sig and c.iloc[i] > ema20.iloc[i] and c.iloc[i - 1] <= ema20.iloc[i - 1]:
        sig["ema"] = i
    if "bb" not in sig and c.iloc[i] > bbl.iloc[i] and c.iloc[i - 1] <= bbl.iloc[i - 1]:
        sig["bb"] = i
print(f"true low bar {pk(lowbar)} PKT ({runlow:.0f}) · RSI14 at the low {rsi.iloc[lowbar]:.0f}")
for k_, i in sig.items():
    print(f"  {k_:5s} confirmation at {pk(i)} PKT (entry at the next open, {pk(i + 1)})")
ie = sig.get("hh", lowbar + 1)
t_e = idx[ie]
syms = bc.get_top_symbols(150)["symbol"].tolist()
res = []
for s in syms:
    try:
        k = bc.get_klines(s, "15m", limit=600)
        k.index = pd.to_datetime(k.index, utc=True)
        kk = k[k.index >= idx[i_cross]]
        if len(kk) < 36:
            continue
        o_, h_, l_, c_ = (kk[x].astype(float) for x in ("open", "high", "low", "close"))
        tr = np.maximum(h_ - l_, np.maximum(abs(h_ - c_.shift()), abs(l_ - c_.shift())))
        atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
        pos = list(kk.index).index(t_e)
        e = o_.iloc[pos + 1]
        stop = l_.iloc[:pos + 1].min() - 0.25 * atr.iloc[pos]
        risk = e - stop
        if not (0.003 * e <= risk <= 0.15 * e):
            continue
        tp = e + 1.5 * risk
        px = c_.iloc[pos + 32] if pos + 32 < len(kk) else c_.iloc[-1]
        for j in range(pos + 1, min(pos + 33, len(kk))):
            if l_.iloc[j] <= stop:
                px = stop
                break
            if h_.iloc[j] >= tp:
                px = tp
                break
        res.append((s, px / e - 1 - FEE, (px - e) / risk - FEE * e / risk))
    except Exception:
        continue
r = pd.DataFrame(res, columns=["sym", "pct", "r"])
print(f"\nLAST NIGHT through the study's hh rule (entry {pk(ie + 1)} PKT, {len(r)} coins): basket {r.pct.mean() * 100:+.2f}% "
      f"· {r.r.mean():+.2f}R a coin · coin win {(r.pct > 0).mean() * 100:.0f}% · hit TP1 {(r.r > 1.4).mean() * 100:.0f}% · stopped {(r.r < -0.9).mean() * 100:.0f}%")
print("(13-month hh rule: -0.10% / -0.12R / 41% win · hindsight ceiling +0.41% / +0.28R / 58%)")
