"""Classify a Telegram link the way the Excel extractor does (tools/extract_channels.py), for the add-channel forms.

Shapes: https://t.me/+HASH · t.me/joinchat/HASH · t.me/c/<id>/<msg> (private permalink, no hash) ·
t.me/<username>[/<post>] · t.me/s/<username> · @username · bare username. Anything else is external/other.
"""
from __future__ import annotations

import re

_USERNAME = re.compile(r"[A-Za-z0-9_]{3,}")


def classify_url(raw: str | None) -> dict:
    info = {"kind": "other", "url": (raw or "").strip(), "username": None, "invite_hash": None, "sample_post_id": None}
    s = (raw or "").strip().lstrip("‎‏﻿")
    if not s:
        return info
    if s.startswith("@"):
        s = s[1:]
    m = re.match(r"^(?:https?://)?(?:www\.)?t\.me/(.+)$", s, re.I)
    if m:
        path = m.group(1)
    elif re.match(r"^(?:https?://)?[\w.-]+\.[a-z]{2,}(/|$)", s, re.I):
        info["kind"] = "external"
        return info
    else:
        path = s                                                       # bare username
    path = path.strip().rstrip("/")
    if path.startswith("+"):
        info.update(kind="private", invite_hash=path[1:].split("/")[0].split("?")[0])
        info["url"] = f"https://t.me/+{info['invite_hash']}"
        return info
    low = path.lower()
    if low.startswith("joinchat/"):
        info.update(kind="private", invite_hash=path.split("/", 1)[1].split("?")[0].split("/")[0])
        info["url"] = f"https://t.me/+{info['invite_hash']}"
        return info
    if low.startswith("c/"):
        info.update(kind="private", url=f"https://t.me/{path}")
        return info
    if low.startswith("s/"):
        path = path[2:]
    parts = path.split("?")[0].split("/")
    username = parts[0]
    if not _USERNAME.fullmatch(username):
        return info
    post_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    info.update(kind="public", url=f"https://t.me/{username}", username=username.lower(), sample_post_id=post_id)
    return info


def channel_key_for(info: dict) -> str | None:
    if info.get("kind") == "public" and info.get("username"):
        return f"pub:{info['username']}"
    if info.get("kind") == "private" and info.get("invite_hash"):
        return f"prv:{info['invite_hash']}"
    return None
