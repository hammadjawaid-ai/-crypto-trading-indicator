"""Durable closed-trade storage on Supabase (survives Streamlit Cloud
redeploys, which wipe the local .json files).

Why: Streamlit Cloud has an EPHEMERAL filesystem — every redeploy/reboot
resets .paper_bot.json / .sureshot_bot.json / .live_bot.json, erasing the
closed-trade history. localStorage was only a per-browser cache. This
mirrors every closed trade to a Supabase Postgres table via its REST
(PostgREST) API, so the history is permanent AND readable directly in
Supabase's table viewer.

Design:
  - One row per closed trade, keyed by id = "{bot}|{symbol}|{exit_at}"
    so re-saving is an idempotent upsert (no duplicates).
  - `bot` is 'paper' | 'sureshot' | 'live'.
  - The full trade dict is kept in the `raw` jsonb column so nothing is
    lost; flat columns (symbol/side/pnl_usd/…) make it human-readable.
  - Everything fails SOFT: if Supabase isn't configured or a call errors,
    functions no-op / return [] and the app keeps working on local state.

Setup (one-time, user):
  1. Create a free project at supabase.com.
  2. SQL editor → run the CREATE TABLE in README_SUPABASE.sql.
  3. Project settings → API → copy the Project URL + the service_role key.
  4. Put them in Streamlit secrets (.streamlit/secrets.toml or the Cloud
     dashboard):  SUPABASE_URL = "..."   SUPABASE_KEY = "..."
"""
from __future__ import annotations

import json
import requests

import config

_URL = (getattr(config, "SUPABASE_URL", "") or "").rstrip("/")
_KEY = getattr(config, "SUPABASE_KEY", "") or ""
_TABLE = "closed_trades"
_TIMEOUT = 8


def enabled() -> bool:
    """True only when both Supabase URL + key are configured."""
    return bool(_URL and _KEY)


def _headers() -> dict:
    return {
        "apikey": _KEY,
        "Authorization": f"Bearer {_KEY}",
        "Content-Type": "application/json",
    }


def _f(v):
    try:
        return float(v)
    except Exception:
        return None


def _trade_id(bot: str, t: dict) -> str:
    return f"{bot}|{t.get('symbol')}|{int(float(t.get('exit_at') or 0))}"


def _row(bot: str, t: dict) -> dict:
    return {
        "id": _trade_id(bot, t),
        "bot": bot,
        "symbol": t.get("symbol"),
        "base": t.get("base"),
        "side": t.get("side"),
        "entry": _f(t.get("entry")),
        "exit": _f(t.get("exit") if t.get("exit") is not None
                   else t.get("exit_price")),
        "pnl_usd": _f(t.get("pnl_usd") if t.get("pnl_usd") is not None
                      else t.get("pnl")),
        "pnl_pct": _f(t.get("pnl_pct")),
        "qty": _f(t.get("qty")),
        "opened_at": _f(t.get("opened_at") if t.get("opened_at") is not None
                        else t.get("entry_at")),
        "exit_at": _f(t.get("exit_at")),
        "reason": t.get("reason"),
        "raw": t,
    }


def save_closed(bot: str, closed: list[dict]) -> int:
    """Upsert all closed trades for `bot`. Idempotent (id-keyed). Returns
    the number sent, or 0 on no-op/failure. Safe to call every render."""
    if not enabled() or not closed:
        return 0
    rows = []
    for t in closed:
        try:
            rows.append(_row(bot, t))
        except Exception:
            continue
    if not rows:
        return 0
    try:
        r = requests.post(
            f"{_URL}/rest/v1/{_TABLE}",
            headers={**_headers(),
                     "Prefer": "resolution=merge-duplicates,return=minimal"},
            data=json.dumps(rows), timeout=_TIMEOUT)
        return len(rows) if r.ok else 0
    except Exception:
        return 0


def load_closed(bot: str) -> list[dict]:
    """Return all durably-stored closed trades for `bot` (oldest first),
    as the original trade dicts. [] if disabled / on error."""
    if not enabled():
        return []
    try:
        r = requests.get(
            f"{_URL}/rest/v1/{_TABLE}",
            headers=_headers(),
            params={"bot": f"eq.{bot}", "select": "raw",
                    "order": "exit_at.asc"},
            timeout=_TIMEOUT)
        if r.ok:
            return [row["raw"] for row in r.json()
                    if isinstance(row, dict) and row.get("raw")]
    except Exception:
        pass
    return []


def merge_into_state(bot: str, state: dict) -> dict:
    """Load durable closed trades and merge them into state['closed'],
    de-duped by (symbol, exit_at). Also pushes any local-only closed
    trades up to Supabase. Use on bot load so a wiped container recovers
    its full history. Returns the state (mutated in place)."""
    if not enabled() or state is None:
        return state
    local = list(state.get("closed") or [])
    remote = load_closed(bot)

    def _key(t):
        return (t.get("symbol"), int(float(t.get("exit_at") or 0)))

    seen = set()
    merged = []
    for t in remote + local:          # remote first; local overwrites dupes
        k = _key(t)
        if k in seen:
            continue
        seen.add(k)
        merged.append(t)
    merged.sort(key=lambda t: float(t.get("exit_at") or 0))
    state["closed"] = merged
    # Push anything that was only local so Supabase is complete.
    remote_keys = {_key(t) for t in remote}
    local_only = [t for t in local if _key(t) not in remote_keys]
    if local_only:
        save_closed(bot, local_only)
    return state
