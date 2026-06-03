"""Persistent signal fire log.

The dashboard is stateless — every scan is a fresh snapshot. If a
STRONG+ signal fires at 03:00 UTC and the pattern resets by 04:00,
a user who refreshes at 09:00 sees nothing.

This module persists EVERY STRONG+ fire to `.signal_fires.json` along
with the entry price + lanes that fired + timestamp. When the dashboard
loads, it reads back the last N hours of fires and renders them as a
🔥 RECENT FIRES section with post-fire performance — so the user can
audit "what would I have caught" + "did it play out".

The state file is gitignored and lives next to .paper_bot.json. On
Streamlit Cloud the filesystem is ephemeral — fires log per session.

Public API mirrors paper_bot's style:
    fires = load_fires(path)
    record_fires(path, picks, source="unified")
    recent = recent_fires(fires, hours=12)
    enrich_perf(recent, prices)  # in-place add pct_since_fire
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

# How long to keep a fire entry in the log before pruning
_MAX_AGE_HOURS = 48

# Dedupe window — don't re-log the same symbol+side if it fired within
# this many seconds (prevents spamming the log when the same coin keeps
# firing on every cache refresh).
_DEDUPE_WINDOW_SEC = 4 * 3600  # 4 hours


def load_fires(path) -> list:
    """Load the fire log. Returns [] if file missing or corrupt."""
    try:
        p = Path(path)
        if not p.exists():
            return []
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return data
    except Exception:
        return []


def save_fires(path, fires: list) -> None:
    """Atomic-ish write — write to .tmp then replace, so a half-written
    file doesn't blow away the log."""
    try:
        p = Path(path)
        # Ensure parent dir exists (Streamlit Cloud, temp paths, etc.)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(fires, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except Exception:
        # Best-effort — log is not critical state
        pass


def _prune_old(fires: list, max_age_hours: int = _MAX_AGE_HOURS) -> list:
    """Drop fires older than max_age_hours."""
    cutoff = time.time() - max_age_hours * 3600
    return [f for f in fires if (f.get("fired_at") or 0) >= cutoff]


def _was_recently_logged(fires: list, symbol: str, side: str,
                         dedupe_sec: int = _DEDUPE_WINDOW_SEC) -> bool:
    """Check if same symbol+side fired within the dedupe window — keeps
    the log clean instead of logging the same coin every 15 min while
    the signal stays active."""
    cutoff = time.time() - dedupe_sec
    for f in fires:
        if (f.get("symbol") == symbol
                and (f.get("side") or "").upper() == side.upper()
                and (f.get("fired_at") or 0) >= cutoff):
            return True
    return False


def record_fires(path, picks: list, source: str = "unified",
                 min_score: float = 80.0) -> int:
    """Append every STRONG+ pick to the log (with dedupe).

    `picks` is a list of dicts shaped like the unified composite or
    Pattern Scout output — must have:
        symbol, side, score, tier, trade_plan (entry/stop/tp1/tp2),
        active_lanes (optional), reasons (optional)

    Returns the count of new fires logged this call."""
    if not picks:
        return 0
    fires = _prune_old(load_fires(path))
    now = time.time()
    new_count = 0
    for p in picks:
        try:
            sym = p.get("symbol", "")
            side = (p.get("side") or "").upper()
            sc = float(p.get("score") or 0)
            if not sym or side not in ("LONG", "SHORT") or sc < min_score:
                continue
            if _was_recently_logged(fires, sym, side):
                continue
            plan = p.get("trade_plan") or {}
            entry = float(plan.get("entry") or p.get("price_now") or 0)
            if entry <= 0:
                continue
            fires.append({
                "symbol": sym,
                "base": p.get("base", sym.replace("USDT", "")),
                "side": side,
                "score": round(sc, 1),
                "tier": p.get("tier", "STRONG"),
                "entry": entry,
                "stop": float(plan.get("stop") or 0),
                "tp1": float(plan.get("tp1") or 0),
                "tp2": float(plan.get("tp2") or 0),
                "rr": float(plan.get("rr") or 0),
                "active_lanes": list((p.get("active_lanes") or [])[:6]),
                "n_strong_lanes": int(p.get("n_strong_lanes") or 0),
                "reasons": list((p.get("reasons") or [])[:4]),
                "fired_at": now,
                "source": source,
            })
            new_count += 1
        except Exception:
            continue
    if new_count:
        save_fires(path, fires)
    return new_count


def recent_fires(fires: list, hours: float = 12.0) -> list:
    """Return fires from the last `hours` hours, newest first."""
    cutoff = time.time() - hours * 3600
    recent = [f for f in fires if (f.get("fired_at") or 0) >= cutoff]
    recent.sort(key=lambda f: f.get("fired_at") or 0, reverse=True)
    return recent


def enrich_perf(fires: list, prices: dict) -> list:
    """Add post-fire performance fields IN-PLACE.

    For each fire, computes:
        pct_since_fire: % move from entry to current price (LONG=+,
                        SHORT=- means winning)
        winning: bool — True if pct_since_fire is in the trade's favour
        current_price: float

    Returns the same list (mutated)."""
    for f in fires:
        try:
            sym = f.get("symbol")
            entry = float(f.get("entry") or 0)
            side = (f.get("side") or "").upper()
            cur = float(prices.get(sym) or 0) if prices else 0
            if entry <= 0 or cur <= 0:
                f["pct_since_fire"] = None
                f["winning"] = None
                f["current_price"] = cur
                continue
            raw_pct = (cur / entry - 1) * 100
            if side == "LONG":
                fav_pct = raw_pct
            else:  # SHORT — winning when price drops
                fav_pct = -raw_pct
            f["pct_since_fire"] = round(fav_pct, 2)
            f["winning"] = fav_pct > 0
            f["current_price"] = cur
            # Did SL or TP hit since fire? (best-effort given we only
            # have current price, not the high/low since fire)
            tp1 = float(f.get("tp1") or 0)
            sl = float(f.get("stop") or 0)
            if side == "LONG":
                f["tp1_hit"] = tp1 > 0 and cur >= tp1
                f["sl_hit"] = sl > 0 and cur <= sl
            else:
                f["tp1_hit"] = tp1 > 0 and cur <= tp1
                f["sl_hit"] = sl > 0 and cur >= sl
        except Exception:
            f["pct_since_fire"] = None
            f["winning"] = None
    return fires
