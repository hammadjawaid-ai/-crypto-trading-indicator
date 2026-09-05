"""🎯 SNIPER — the flagship construct. Born 2026-09-06.

THE ONLY construct in this system that survived full adversarial
verification at every stage (multi-agent study, 2026-09-05/06,
wf_9292ecc5 + wf_a2211920, 19 research agents, 208 cells measured):

  ENTRY (short only — no long cell survived):
    - the coin was COILED: mean HEAT of the prior 12 closed bars < 35
    - price BREAKS the prior 24h LOW (24 closed 1h bars)
    - HEAT is 55-90 evaluated INTRABAR at the break (waiting for bar
      close degrades the edge to +0.10R with a negative third)
    - accrued bar volume >= 1.5x its 20-bar mean (conservative subset
      of the verified full-bar gate)
    - fill AT the level (resting-stop style — the 60s clock). Next-bar
      -open entries collapse the edge to +0.085R.
  EXIT: structural SL from PRE-BREAK bars only (swing high +
    0.25*ATR14, 4*ATR cap, 1.5*ATR fallback), FIXED TP at 1.5R.
    No BE move (verified: collapses win rate to 28.7%), no trail,
    48-bar time stop. The desk manages records; this module only
    defines plans.

  VERIFIED NUMBERS (independent adversarial re-implementation, 366d,
  15 midcaps, fees 0.00055/side, stop-before-target):
    n=306-327 · win 57.5-59.5% · +0.27 to +0.34R/trade · ALL thirds
    positive · drop-best-3-coins still +0.25-0.30R · 13-15/15 coins
    individually positive · ~0.9 fires/day (clustered in cascades)
  HONEST FLOOR: the fully-causal variant measures +0.085R — SIZE TO
  THE FLOOR. Live truth lands between the floor and the ceiling
  depending on fill quality at the level.

  REFUTED at universe scale (2026-09-06): every long cell and every
  universe-wide short — middle third negative in all configurations.
  The edge is LOCAL to this midcap class. Do not widen the coin list
  without a fresh adversarial pass.
"""
from __future__ import annotations

import binance_client

# The verified coin class — the exact 15-midcap slice the construct
# was confirmed on. Dead/renamed symbols simply never arm (fail-soft).
SNIPER_COINS = [
    "LINKUSDT", "INJUSDT", "TIAUSDT", "SEIUSDT", "ARBUSDT",
    "SUIUSDT", "WLDUSDT", "PYTHUSDT", "JUPUSDT", "STRKUSDT",
    "ENAUSDT", "ORDIUSDT", "FETUSDT", "RNDRUSDT", "GALAUSDT",
]
HEAT_LO, HEAT_HI = 55.0, 90.0
COIL_MAX = 35.0
VOL_X = 1.5
TP_R = 1.5


def _heat_series(h, l, upto: int) -> float | None:
    """HEAT at index `upto` (inclusive): percentile of the current
    14-bar ATR within the trailing 100 such ATRs. bars <= upto only."""
    tr = h - l
    if upto + 1 < 45:
        return None
    atr_now = float(tr[upto - 13:upto + 1].mean())
    hist = [float(tr[j - 14:j].mean())
            for j in range(max(15, upto - 99), upto + 1)]
    if len(hist) < 30:
        return None
    return sum(1 for x in hist if x < atr_now) / len(hist) * 100.0


def arm_check(symbol: str) -> dict | None:
    """Cycle-clock pass (5 min): is this coin COILED with a level to
    arm? Returns {symbol, level, coil, heat_closed} or None.
    Uses CLOSED bars only — arming never peeks at the live bar."""
    try:
        d = binance_client.get_klines(symbol, "1h", limit=160)
        if d is None or len(d) < 130:
            return None
        h = d["high"].to_numpy()
        l = d["low"].to_numpy()
        # closed bars end at -2 (the last row is the live partial bar)
        heats = []
        for k in range(-13, -1):
            _ht = _heat_series(h, l, len(h) + k)
            if _ht is not None:
                heats.append(_ht)
        if len(heats) < 8:
            return None
        coil = sum(heats) / len(heats)
        if coil >= COIL_MAX:
            return None
        level = float(l[-25:-1].min())        # prior 24 CLOSED bars' low
        return {"symbol": symbol, "level": level,
                "coil": round(coil, 1),
                "heat_closed": round(heats[-1], 1)}
    except Exception:
        return None


def fire_check(symbol: str, level: float) -> dict | None:
    """60s-clock pass: price is at/through the level — do the INTRABAR
    gates hold? Returns the full plan or None.
    heat: computed INCLUDING the live partial bar (the verified
    intrabar evaluation); volume: accrued >= 1.5x the 20-bar mean."""
    try:
        d = binance_client.get_klines(symbol, "1h", limit=160)
        if d is None or len(d) < 130:
            return None
        h = d["high"].to_numpy()
        l = d["low"].to_numpy()
        v = d["volume"].to_numpy()
        heat = _heat_series(h, l, len(h) - 1)   # includes live bar
        if heat is None or not (HEAT_LO <= heat <= HEAT_HI):
            return None
        vma = float(v[-21:-1].mean())
        if not (vma > 0 and float(v[-1]) >= VOL_X * vma):
            return None
        # structural SL from PRE-BREAK bars only (exclude live bar)
        tr = h - l
        atr = float(tr[-15:-1].mean())
        if atr <= 0:
            return None
        sl = float(h[-11:-1].max()) + 0.25 * atr
        if not (0 < sl - level <= 4 * atr):
            sl = level + 1.5 * atr
        risk = sl - level
        if risk <= 0:
            return None
        return {"symbol": symbol, "side": "SHORT", "entry": level,
                "stop": round(sl, 10), "tp1": round(level - TP_R * risk, 10),
                "tp2": None, "heat": round(heat, 1),
                "risk": round(risk, 10)}
    except Exception:
        return None
