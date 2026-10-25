#!/usr/bin/env python
"""Create a Telethon StringSession for the audit account — run this ON YOUR OWN PC, once.

    .venv/Scripts/python tools/tg_login.py

It asks for api_id / api_hash (from https://my.telegram.org → API development tools), then the phone number,
the login code Telegram sends to the app, and the 2FA password if the account has one. It prints ONE line:
the session string. Paste it into the Coolify environment variable TG_SESSION (mark it as a secret).
Nothing is written to disk here; never commit the string or send it through chat.
"""
import getpass

from telethon.sessions import StringSession
from telethon.sync import TelegramClient


def main():
    api_id = int(input("api_id: ").strip())
    api_hash = getpass.getpass("api_hash (hidden): ").strip()
    with TelegramClient(StringSession(), api_id, api_hash) as client:
        me = client.get_me()
        print(f"\nlogged in as @{me.username or me.id} — copy the line below into Coolify as TG_SESSION:\n")
        print(client.session.save())


if __name__ == "__main__":
    main()
