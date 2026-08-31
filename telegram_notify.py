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

# 📱 SECOND PHONE (user 2026-08-31): TELEGRAM_CHAT_ID accepts a
# COMMA-SEPARATED list — every buzz goes to every id. One id behaves
# exactly as before (nothing changes for existing setups); add a
# second id and both phones/accounts get the same alerts. A send is
# "ok" if at least one destination accepted it, so one dead id can
# never silence the others.
_CHATS = [c.strip() for c in _CHAT.split(",") if c.strip()]


def enabled() -> bool:
    return bool(_TOKEN and _CHATS)


def _send_one(chat_id: str, text: str, silent: bool) -> tuple[bool, str]:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
                "disable_notification": bool(silent),
            },
            timeout=10)
        if r.ok and (r.json() or {}).get("ok"):
            return (True, "sent")
        return (False, f"HTTP {r.status_code}: {r.text[:100]}")
    except Exception as exc:
        return (False, f"send failed: {exc}")


def send(text: str, silent: bool = False) -> tuple[bool, str]:
    """Send one Markdown message to every configured chat.

    Returns (ok, msg) — ok when at least one destination accepted."""
    if not enabled():
        return (False, "Telegram not configured "
                       "(set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID).")
    oks, errs = 0, []
    for _cid in _CHATS:
        ok, msg = _send_one(_cid, text, silent)
        if ok:
            oks += 1
        else:
            errs.append(f"{_cid}: {msg}")
    if oks:
        return (True, f"sent to {oks}/{len(_CHATS)}"
                      + (f" · failed {'; '.join(errs)}" if errs else ""))
    return (False, "; ".join(errs) or "no destinations")


def self_test() -> tuple[bool, str]:
    """Send a one-off ping so you can confirm the pipe works."""
    return send("✅ *Worker connected* — you'll get 🔥 TAKE NOW and "
                "SST1 conv≥70 alerts here 24/7.")


if __name__ == "__main__":
    ok, msg = self_test()
    print(("OK: " if ok else "FAIL: ") + msg)
