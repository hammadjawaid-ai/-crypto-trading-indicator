"""TG PULL — dump a Telegram channel's history through YOUR OWN account (for channels whose
owner blocked Export / Forward). Writes the same result.json shape Telegram Desktop exports,
so channel_study.py runs on it unchanged. Research only; nothing here touches the worker.

One-time setup (you do this, never paste the values to Claude):
  1. https://my.telegram.org → API development tools → create an app → note api_id and api_hash
  2. in a terminal:   research_meta\\.venv\\Scripts\\python.exe research_meta\\tg_pull.py --list
     it asks for api_id, api_hash, your phone number and the login code Telegram sends you;
     the login is saved to research_meta/tg_user.session (keep that file private)
  3. research_meta\\.venv\\Scripts\\python.exe research_meta\\tg_pull.py "Crypto Andrew VIP"
     → research_meta/channel_export/crypto_andrew_vip/result.json

Then:  research_meta\\.venv\\Scripts\\python.exe -I research_meta\\channel_study.py research_meta\\channel_export\\crypto_andrew_vip
"""
import asyncio
import getpass
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
RM = os.path.dirname(os.path.abspath(__file__))
SESSION = os.path.join(RM, "tg_user")
OUT = os.path.join(RM, "channel_export")


def creds():
    api_id = os.environ.get("TG_API_ID") or input("api_id: ").strip()
    api_hash = os.environ.get("TG_API_HASH") or getpass.getpass("api_hash (hidden): ").strip()
    return int(api_id), api_hash


async def main():
    from telethon import TelegramClient
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    api_id, api_hash = creds()
    async with TelegramClient(SESSION, api_id, api_hash) as client:
        me = await client.get_me()
        print(f"logged in as {me.first_name or ''} (id {me.id})")
        if "--session" in sys.argv:
            from telethon.sessions import StringSession
            print(chr(10) + "TG_SESSION (paste into Render env as TG_SESSION — never into chat):" + chr(10))
            print(StringSession.save(client.session))
            return
        dialogs = await client.get_dialogs(limit=300)
        if "--list" in sys.argv or not args:
            print("\nchannels / groups you can read:")
            for d in dialogs:
                if d.is_channel or d.is_group:
                    print(f"  {d.name!r:45s} id {d.id}")
            return
        want = args[0].lower()
        hits = [d for d in dialogs if want in (d.name or "").lower()]
        if not hits:
            print(f"no dialog matching {args[0]!r} — run with --list"); return
        d = hits[0]
        print(f"pulling {d.name!r} …")
        msgs = []
        async for m in client.iter_messages(d.entity, limit=None):
            if m.action is not None:
                continue
            msgs.append(dict(id=m.id, type="message", date=m.date.isoformat(), date_unixtime=str(int(m.date.timestamp())),
                             text=m.message or "", reply_to_message_id=(m.reply_to.reply_to_msg_id if m.reply_to else None),
                             photo=bool(m.photo), edited=m.edit_date.isoformat() if m.edit_date else None))
            if len(msgs) % 500 == 0:
                print(f"  {len(msgs)} messages …", flush=True)
        msgs.reverse()
        slug = re.sub(r"[^a-z0-9]+", "_", d.name.lower()).strip("_")
        folder = os.path.join(OUT, slug)
        os.makedirs(folder, exist_ok=True)
        p = os.path.join(folder, "result.json")
        json.dump(dict(name=d.name, type="channel", id=d.id, messages=msgs), open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"wrote {len(msgs)} messages → {p}")
        print(f"next: research_meta\\.venv\\Scripts\\python.exe -I research_meta\\channel_study.py \"{folder}\"")


if __name__ == "__main__":
    asyncio.run(main())
