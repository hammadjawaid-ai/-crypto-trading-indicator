"""Telegram push for the 24/7 worker — send the best setups to your phone.

Uses the Telegram Bot API (no extra dependency, just `requests`). Set
TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (see README_WORKER.md). Fails soft:
if unconfigured or the network hiccups, it never raises — the worker keeps
scanning and storing regardless.
"""
from __future__ import annotations

import requests

import config

_TOKEN = (getattr(config, "TELEGRAM_BOT_TOKEN", "") or "").strip()
_CHAT = (getattr(config, "TELEGRAM_CHAT_ID", "") or "").strip()


def enabled() -> bool:
    return bool(_TOKEN and _CHAT)


def send(text: str, silent: bool = False) -> tuple[bool, str]:
    """Send one Markdown message to the configured chat. Returns (ok, msg)."""
    if not enabled():
        return (False, "Telegram not configured "
                       "(set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID).")
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{_TOKEN}/sendMessage",
            json={
                "chat_id": _CHAT,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
                "disable_notification": bool(silent),
            },
            timeout=10)
        if r.ok and (r.json() or {}).get("ok"):
            return (True, "sent")
        return (False, f"Telegram HTTP {r.status_code}: {r.text[:120]}")
    except Exception as exc:
        return (False, f"Telegram send failed: {exc}")


def self_test() -> tuple[bool, str]:
    """Send a one-off ping so you can confirm the pipe works."""
    return send("✅ *Worker connected* — you'll get 🔥 TAKE NOW and "
                "SST1 conv≥70 alerts here 24/7.")


if __name__ == "__main__":
    ok, msg = self_test()
    print(("OK: " if ok else "FAIL: ") + msg)
