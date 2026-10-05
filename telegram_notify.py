"""Telegram push for the 24/7 worker — send the best setups to your phone.

Uses the Telegram Bot API (no extra dependency, just `requests`). Set
TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (see README_WORKER.md). Fails soft:
if unconfigured or the network hiccups, it never raises — the worker keeps
scanning and storing regardless.

🧵 THREADS (user 2026-10-05): send_thread() returns the message id per chat
so a later message can be posted as a REPLY to it — the ⏱ verdict, ⭐⚡ GO
and ❄️ freeze land inside the fire's own thread. send() is unchanged for
every existing caller.
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


def _send_one(chat_id: str, text: str, silent: bool,
              reply_to: int | None = None) -> tuple[bool, str, int | None]:
    try:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
            "disable_notification": bool(silent),
        }
        if reply_to:
            # the reply still goes out if the parent was deleted
            payload["reply_to_message_id"] = int(reply_to)
            payload["allow_sending_without_reply"] = True
        r = requests.post(
            f"https://api.telegram.org/bot{_TOKEN}/sendMessage",
            json=payload, timeout=10)
        j = {}
        try:
            j = r.json() or {}
        except Exception:
            j = {}
        if r.ok and j.get("ok"):
            mid = (j.get("result") or {}).get("message_id")
            return (True, "sent", int(mid) if mid is not None else None)
        return (False, f"HTTP {r.status_code}: {r.text[:100]}", None)
    except Exception as exc:
        return (False, f"send failed: {exc}", None)


def send_thread(text: str, reply_to: dict | None = None,
                silent: bool = False) -> tuple[bool, str, dict]:
    """Send one Markdown message to every configured chat and return the
    message ids per chat: (ok, msg, {chat_id: message_id}). Pass a previous
    call's ids dict as reply_to and the new message lands as a reply in each
    chat where that parent exists. ok when at least one destination
    accepted."""
    if not enabled():
        return (False, "Telegram not configured "
                       "(set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID).", {})
    oks, errs, ids = 0, [], {}
    for _cid in _CHATS:
        _parent = None
        try:
            _parent = (reply_to or {}).get(_cid)
        except Exception:
            _parent = None
        ok, msg, mid = _send_one(_cid, text, silent, _parent)
        if ok:
            oks += 1
            if mid is not None:
                ids[_cid] = mid
        else:
            errs.append(f"{_cid}: {msg}")
    if oks:
        return (True, f"sent to {oks}/{len(_CHATS)}"
                      + (f" · failed {'; '.join(errs)}" if errs else ""), ids)
    return (False, "; ".join(errs) or "no destinations", {})


def send(text: str, silent: bool = False) -> tuple[bool, str]:
    """Send one Markdown message to every configured chat.

    Returns (ok, msg) — ok when at least one destination accepted."""
    ok, msg, _ids = send_thread(text, None, silent)
    return (ok, msg)


def self_test() -> tuple[bool, str]:
    """Send a one-off ping so you can confirm the pipe works."""
    return send("✅ *Worker connected* — you'll get 🔥 TAKE NOW and "
                "SST1 conv≥70 alerts here 24/7.")


if __name__ == "__main__":
    ok, msg = self_test()
    print(("OK: " if ok else "FAIL: ") + msg)
