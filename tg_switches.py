"""🔔 Telegram bells: every stream that can ring the phone, its desk record, and a switch for it that can be
flipped from the phone (user 2026-11-17: "for every telegram streams we have show me the wn rates so I can see or
mute from my mobile phone"). No Streamlit in here.

The switches are the worker's own existing on/off flags (agent_worker.TG_*). A flip made on the page is written to
<STATE_DIR>/.tg_switches.json and the worker applies it at the start of its next cycle, so the bell code itself is
untouched: a muted bell goes silent exactly as it does when its flag is False in the code (records, desk tiers
and boards go on). Deleting the file returns every bell to the code's own setting.
"""
from __future__ import annotations

import bisect
import json
import os
import re
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FILE = ".tg_switches.json"
# (flag in agent_worker or None when the bell has no switch, label, desk tier or None, note)
# 🎮 = a stream the stock-only demo trades (user 2026-11-17: "add the streams to the list which I mentioned
# above that we set for demo as well so we finalize the notifications accordingly").
REGISTRY = [
    (None, "⭐ ELITE STAR, gated", "elite_star:gated", "rings when the star passes its four-rule read"),
    (None, "🎮 ⭐ ELITE STAR, every fire", "elite_star", "demo stream; the phone rings only for the gated ones above"),
    (None, "🎮 💎✅ ELITE CONFIRMED ENTRY", "elite_confirm", "demo stream"),
    (None, "🎮 💥 STRONG TRIGGER", "trig_strong", "demo stream"),
    (None, "💎 ELITE CONVICTION", "elite_conv", "left the demo on 17 Nov"),
    ("TG_STAR_PRIME", "⭐🥇 STAR × PRIME", "star_prime", ""),
    ("TG_STAR_TRIG", "⭐💥 STAR × STRONG TRIGGER", "star_trig", ""),
    ("TG_STAR_TAKENOW", "⭐✅🔥 STAR × TAKE NOW HOT", "star_takenow", ""),
    ("TG_STAR_APEXV2", "⭐🏆² STAR × APEX V2", "star_apexv2", ""),
    ("TG_APEX_V2_GATED", "🏆💎 APEX V2 GATED", "apex_v2_gated", ""),
    ("TG_PRIME_TRIG", "💥🥇 PRIME × STRONG TRIGGER", "prime_trig", ""),
    ("TG_CONV_PRIME", "💎🥇 ELITE × PRIME", "conv_prime", ""),
    ("TG_LEG2_PRIME", "🔥🥇 SECOND LEG × PRIME", "leg2_prime", ""),
    (None, "🎮 💎⚡ CONVICTION REVIVAL · ⭐⚡ GO REVIVED", "go_revived", "demo stream; entered at the GO; the star's GO is a thread reply"),
    ("TG_GO_LIVE", "💎⚡ GO LIVE", "go_live", ""),
    ("TG_TRIGKR_PRIME", "💥🔮🥇 TRIGGER × KRONOS × PRIME", "trigkr_prime", ""),
    ("TG_ARRIVAL_T1", "⚡🔥 ARRIVAL T1", None, ""),
    ("TG_NEAR90", "🎯 90% of the way to TP1 ping", None, "a progress ping, not an entry"),
    ("TG_FREEZE", "❄️ FREEZE reply", None, "a thread reply, not an entry"),
]
FLAGS = [r[0] for r in REGISTRY if r[0]]
# bells with no switch: what the code does with them today (True rings, False silent on the phone)
FIXED = {"elite_star:gated": True, "go_revived": True, "elite_star": False, "elite_confirm": False,
         "trig_strong": False, "elite_conv": False}


def _state_dir() -> str:
    try:
        import config
        d = (getattr(config, "STATE_DIR", "") or "").strip()
    except Exception:
        d = (os.environ.get("STATE_DIR") or "").strip()
    return d if d and os.path.isdir(d) else HERE


def overrides() -> dict:
    """{flag: bool} set from the page. {} when nothing was ever flipped or the file is unreadable."""
    try:
        with open(os.path.join(_state_dir(), FILE), encoding="utf-8") as f:
            d = json.load(f)
        return {k: bool(v) for k, v in d.items() if k in FLAGS} if isinstance(d, dict) else {}
    except Exception:
        return {}


def set_switch(flag: str, on: bool) -> bool:
    """Record one flip (atomic write). False when the flag is not a known switch or the write fails."""
    if flag not in FLAGS:
        return False
    try:
        d = overrides()
        d[flag] = bool(on)
        path = os.path.join(_state_dir(), FILE)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(path + ".tmp", path)
        return True
    except Exception:
        return False


def apply(module) -> dict:
    """Worker side: set each flipped flag on the worker module. Returns what changed {flag: new value}."""
    changed = {}
    for flag, val in overrides().items():
        if hasattr(module, flag) and bool(getattr(module, flag)) != val:
            setattr(module, flag, val)
            changed[flag] = val
    return changed


def code_defaults(path: str | None = None) -> dict:
    """{flag: bool} as written in agent_worker.py, read from the source so the page never imports the worker."""
    out = {}
    try:
        with open(path or os.path.join(HERE, "agent_worker.py"), encoding="utf-8") as f:
            src = f.read()
        for flag in FLAGS:
            m = re.search(rf"^{flag}\s*=\s*(True|False)\b", src, re.M)
            if m:
                out[flag] = m.group(1) == "True"
    except Exception:
        pass
    return out


def status() -> list:
    """One row per bell: {"flag", "label", "tier", "note", "on" (True / False / None = always on), "set_here"}."""
    dflt, ov = code_defaults(), overrides()
    rows = []
    for flag, label, tier, note in REGISTRY:
        on = None if flag is None else ov.get(flag, dflt.get(flag))
        rows.append({"flag": flag, "label": label, "tier": tier, "note": note, "on": on, "set_here": flag in ov,
                     "fixed": FIXED.get(tier) if flag is None else None})
    return rows


def _cell(rs) -> dict:
    n = len(rs)
    return {"n": n, "win": (sum(1 for r in rs if r > 0) / n) if n else None, "r": (sum(rs) / n) if n else None}


def records(con, now: float | None = None, days: float = 14.0) -> dict:
    """{tier key: {"all", "recent", "tok", "tok_recent"}} from the desk ledger (clean closes; a win is pnl_r > 0).
    "recent" is the last `days` by close time; "tok" / "tok_recent" are the tokenized seats of the same stream.
    The gated star is the star tier cut to the fires the bell's own gate passed (the stamp on the star's signal
    row, within 30 minutes)."""
    now = time.time() if now is None else float(now)
    cut = now - days * 86400.0
    out = {}
    tiers = sorted({r[2] for r in REGISTRY if r[2] and ":" not in r[2]})
    marks = ",".join("?" * (2 * len(tiers)))
    by = {}
    for tier, closed_at, r in con.execute(
            f"SELECT tier, closed_at, pnl_r FROM shadow_trades WHERE status='CLOSED' AND pnl_r IS NOT NULL AND tier IN ({marks})",
            tiers + ["tok:" + t for t in tiers]):
        by.setdefault(tier, []).append((closed_at, r))
    for t in tiers:
        a = by.get(t, [])
        k = by.get("tok:" + t, [])
        out[t] = {"all": _cell([r for _, r in a]), "recent": _cell([r for c, r in a if (c or 0) >= cut]),
                  "tok": _cell([r for _, r in k]), "tok_recent": _cell([r for c, r in k if (c or 0) >= cut])}
    sig = {}
    for ts, sym, side in con.execute(
            "SELECT ts, symbol, side FROM signals WHERE stream='elite_star' AND (extra LIKE '%\"gate\": \"pass\"%' "
            "OR extra LIKE '%\"gate\": \"1317-pass\"%') ORDER BY ts"):
        sig.setdefault((sym, side), []).append(ts)
    cells = {"elite_star": [], "tok:elite_star": []}
    for tier, sym, side, o, c, r in con.execute(
            "SELECT tier, symbol, side, opened_at, closed_at, pnl_r FROM shadow_trades WHERE status='CLOSED' AND pnl_r IS NOT NULL "
            "AND tier IN ('elite_star','tok:elite_star')"):
        L = sig.get((sym, side), [])
        i = bisect.bisect_left(L, o)
        if any(abs(x - o) <= 1800 for x in L[max(0, i - 1):i + 1]):
            cells[tier].append((c, r))
    g, gk = cells["elite_star"], cells["tok:elite_star"]
    out["elite_star:gated"] = {"all": _cell([r for _, r in g]), "recent": _cell([r for c, r in g if (c or 0) >= cut]),
                               "tok": _cell([r for _, r in gk]), "tok_recent": _cell([r for c, r in gk if (c or 0) >= cut])}
    return out
