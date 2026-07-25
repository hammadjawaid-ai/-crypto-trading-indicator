"""⏱ FAST CONFIRM (30m) — user 2026-07-25: "remove 1h, 30 mins to
confirm entries."

The PROVEN tiers, desk records and live executor stay on 1h
confirmation — the user's own two head-to-head tests this week measured
30m confirmation as the loser (68.3%/-0.024R vs 76.8%/+0.054R scaled;
65.3%/-0.009R vs 69.1%/+0.033R on his same-levels spec), and the green
records + real money must not be silently moved onto a measured
negative. THIS stream is the sanctioned outlet (the IGNITION pattern):
the same qualified setups, confirmed on the 30m candle instead of 1h —
roughly 30 minutes earlier — as a LABELED Telegram stream + silent desk
tier "fast30" that must earn its own green light forward.

Signal: ELITE MAX/HIGH/STRONG watch rows (plans already structural-
stopped by scan_core) that pass the 🚀 approval gate, whose latest
CLOSED 30m candle prints the full confirmation: pullback touched the
plan entry within the last 8x30m bars, then close>open, close>prev,
close>EMA20(30m), volume>1.2x its 20-bar average. In-zone gating is
applied by the worker at push time.
"""
from __future__ import annotations

import numpy as np

import binance_client
import velocity_burst as _vb


def _approved(df1h, side: str) -> bool:
    try:
        c = df1h["close"].to_numpy()
        roc6 = np.abs(c / np.roll(c, 6) - 1.0)
        roc6[:6] = 0.0
        ref = roc6[-100:-1]
        roc_hot = (len(ref) > 0
                   and float((ref < roc6[-1]).mean() * 100) >= 60)
        bs, bside, _ = _vb.lane_velocity_burst(df1h)
        return roc_hot or (bs >= 78 and (bside or "").upper() == side)
    except Exception:
        return False


def scan(elite_watch: list) -> list[dict]:
    """30m-confirmed picks among approved qualified setups. Fail-soft."""
    out: list[dict] = []
    for p in elite_watch or []:
        if (p.get("tier") or "").upper() not in ("MAX", "HIGH", "STRONG"):
            continue
        side = (p.get("side") or "").upper()
        sym = p.get("symbol")
        entry = float(p.get("entry") or 0)
        stop = float(p.get("stop") or 0)
        if not sym or side not in ("LONG", "SHORT") or entry <= 0 \
                or stop <= 0 or not p.get("tp1"):
            continue
        try:
            df1h = binance_client.get_klines(sym, "1h", limit=120)
            if not _approved(df1h, side):
                continue
            d30 = binance_client.get_klines(sym, "30m", limit=60)
        except Exception:
            continue
        if d30 is None or len(d30) < 30:
            continue
        o = d30["open"].to_numpy(); h = d30["high"].to_numpy()
        l = d30["low"].to_numpy(); c = d30["close"].to_numpy()
        v = d30["volume"].to_numpy()
        ema20 = d30["close"].ewm(span=20, adjust=False).mean().to_numpy()
        vma = float(np.mean(v[-21:-1]))
        # use the last CLOSED 30m candle (index -2; -1 may be forming)
        i = len(d30) - 2
        if i < 22 or vma <= 0:
            continue
        if side == "LONG":
            pulled = bool(np.min(l[i - 8:i + 1]) <= entry)
            conf = (pulled and c[i] > o[i] and c[i] > c[i - 1]
                    and c[i] > ema20[i] and v[i] > 1.2 * vma
                    and c[i] > stop)
        else:
            pulled = bool(np.max(h[i - 8:i + 1]) >= entry)
            conf = (pulled and c[i] < o[i] and c[i] < c[i - 1]
                    and c[i] < ema20[i] and v[i] > 1.2 * vma
                    and c[i] < stop)
        if not conf:
            continue
        q = dict(p)
        q["fast30"] = True
        out.append(q)
    return out[:5]
