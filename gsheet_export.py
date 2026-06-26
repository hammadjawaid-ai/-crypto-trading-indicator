"""Export closed trades to a Google Sheet via a Google Apps Script webhook.

Lowest-friction true export: the user pastes a tiny Apps Script (see
README_GSHEET.md) into their own Google Sheet, deploys it as a web app,
and puts that URL in Streamlit secrets as GSHEET_WEBHOOK_URL. Then a single
click POSTs the closed trades and they appear in the Sheet — no JSON key
file, no database. Fails soft if not configured (the CSV download is the
always-available fallback).
"""
from __future__ import annotations

import json
import requests

import config

_URL = (getattr(config, "GSHEET_WEBHOOK_URL", "") or "").strip()


def enabled() -> bool:
    return bool(_URL)


def _f(v):
    try:
        return round(float(v), 8)
    except Exception:
        return None


def _row(bot: str, t: dict) -> dict:
    return {
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
    }


def export_closed(bot: str, closed: list[dict]) -> tuple[bool, str]:
    """POST all closed trades to the Google Sheet webhook. Returns
    (ok, message)."""
    if not enabled():
        return (False, "Google Sheets webhook not configured "
                       "(set GSHEET_WEBHOOK_URL in secrets).")
    if not closed:
        return (False, "No closed trades to export.")
    rows = [_row(bot, t) for t in closed]
    try:
        r = requests.post(
            _URL, data=json.dumps({"bot": bot, "rows": rows}),
            headers={"Content-Type": "application/json"}, timeout=15)
        if r.ok:
            return (True, f"Exported {len(rows)} trade(s) to Google Sheets.")
        return (False, f"Sheets webhook returned HTTP {r.status_code}.")
    except Exception as exc:
        return (False, f"Export failed: {exc}")
