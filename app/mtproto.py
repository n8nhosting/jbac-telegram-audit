"""Optional MTProto collector (Telethon): private channels, channels without web preview, and pin state.

Enabled only when TG_API_ID, TG_API_HASH and TG_SESSION are set. The account joins a private channel at most once
(≤ settings.max_joins_per_run joins per run), never posts, respects FLOOD_WAIT, and reads public channels without joining.
`channels.joined = 1` means "this account can read the channel's history".

Rule for every write here: commit before the next await. The public collector, the rollup job and the web app share
the SQLite file, and Telethon may sleep a flood wait inside a request — a transaction left open across that await
makes them fail with "database is locked".
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import random
import re
import sqlite3

from .collector import _snapshot, RunStats, upsert_post
from .db import now_utc
from .rules import local_date_of, now_local
from .tgweb import extract_hashtags

URL_RE = re.compile(r"https?://|t\.me/", re.I)


def message_to_post(msg, hashtag: str, peer_id: int | None = None, username: str | None = None) -> dict:
    """Map a Telethon Message (duck-typed) to the post dict that collector.upsert_post understands."""
    text = getattr(msg, "message", None) or None
    tags = extract_hashtags(text)
    doc = getattr(msg, "document", None)
    mime = ((getattr(doc, "mime_type", None) or "") if doc is not None else "").lower()
    has_sticker = getattr(msg, "sticker", None) is not None
    has_photo = getattr(msg, "photo", None) is not None
    has_video = getattr(msg, "video", None) is not None or mime.startswith("video/")
    has_media = (has_photo or has_video or mime.startswith("image/")) and not has_sticker
    entities = getattr(msg, "entities", None) or []
    has_link = bool(getattr(msg, "web_preview", None)) or bool(URL_RE.search(text or "")) \
        or any("url" in type(e).__name__.lower() for e in entities)
    date = getattr(msg, "date", None) or dt.datetime.now(dt.timezone.utc)
    if date.tzinfo is None:
        date = date.replace(tzinfo=dt.timezone.utc)
    mid = int(msg.id)
    if username:
        permalink = f"https://t.me/{username}/{mid}"
    elif peer_id:
        permalink = f"https://t.me/c/{peer_id}/{mid}"
    else:
        permalink = None
    return {
        "post_id": mid, "message_id": mid,
        "datetime": date.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "text": text, "hashtags": tags, "has_target_hashtag": hashtag.lower() in tags,
        "has_photo": has_photo, "has_video": has_video, "has_sticker": has_sticker,
        "has_media": has_media, "has_link": has_link,
        "is_pinned": bool(getattr(msg, "pinned", False)),
        "views": getattr(msg, "views", None), "permalink": permalink,
    }


JOIN_RETRY_DAYS = 7
FLOOD_WAIT_MAX_SLEEP = 600      # seconds: sleep through a FLOOD_WAIT up to this long, abandon the run beyond it


def should_attempt_join(ch, now: dt.datetime | None = None, days: int = JOIN_RETRY_DAYS) -> bool:
    """A join request that is pending approval, or an invite that failed, is not retried for `days` days."""
    stamp = ch["join_requested_at"] if ch["join_requested_at"] is not None else None
    if not stamp:
        return True
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        then = dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return True
    if then.tzinfo is None:
        then = then.replace(tzinfo=dt.timezone.utc)
    return (now - then) >= dt.timedelta(days=days)


def _mark_joined(conn, ch, peer_id: int | None, note: str):
    conn.execute("UPDATE channels SET joined=1, tg_peer_id=COALESCE(?, tg_peer_id), last_error=NULL WHERE id=?", (peer_id, ch["id"]))
    conn.execute("INSERT INTO channel_events(channel_id, event, happened_at, note) VALUES(?,?,?,?)", (ch["id"], "joined", now_utc(), note))
    conn.commit()


async def _resolve_entity(client, conn, ch, settings, joins_used: int, stats: RunStats):
    """Return (entity, joined_now) or (None, False) when the channel cannot be read yet."""
    from telethon import errors
    from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
    from telethon.tl.types import ChatInviteAlready, PeerChannel

    if ch["username"]:
        return await client.get_entity(ch["username"]), False
    if ch["invite_hash"]:
        if ch["joined"] and ch["tg_peer_id"]:
            try:
                return await client.get_entity(PeerChannel(int(ch["tg_peer_id"]))), False
            except (ValueError, errors.RPCError):
                pass
        res = await client(CheckChatInviteRequest(ch["invite_hash"]))
        if isinstance(res, ChatInviteAlready):
            chat = res.chat
            if not ch["joined"]:
                _mark_joined(conn, ch, getattr(chat, "id", None), "already a member")
            return chat, False
        # not a member yet: record what the invite page tells us, join only within budget
        title = getattr(res, "title", None)
        count = getattr(res, "participants_count", None)
        _snapshot(conn, ch, count, title, "mtproto_invite", stats, now_utc())
        conn.commit()
        if not should_attempt_join(ch):
            conn.execute("UPDATE channels SET last_checked=? WHERE id=?", (now_utc(), ch["id"]))
            return None, False
        if joins_used >= settings.max_joins_per_run:
            conn.execute("UPDATE channels SET last_checked=?, last_error='join budget exhausted this run' WHERE id=?", (now_utc(), ch["id"]))
            return None, False
        try:
            upd = await client(ImportChatInviteRequest(ch["invite_hash"]))
        except errors.InviteRequestSentError:
            conn.execute("UPDATE channels SET join_requested_at=?, last_checked=?, last_error='join request pending admin approval' WHERE id=?",
                         (now_utc(), now_utc(), ch["id"]))
            conn.execute("INSERT INTO channel_events(channel_id, event, happened_at, note) VALUES(?,?,?,?)",
                         (ch["id"], "join_requested", now_utc(), "waiting for admin approval"))
            return None, True            # counts against the join budget
        except (errors.InviteHashExpiredError, errors.InviteHashInvalidError, errors.ChannelsTooMuchError) as e:
            conn.execute("UPDATE channels SET join_requested_at=?, last_checked=?, last_error=? WHERE id=?",
                         (now_utc(), now_utc(), f"{type(e).__name__}", ch["id"]))
            return None, False
        chats = getattr(upd, "chats", None) or []
        chat = chats[0] if chats else None
        _mark_joined(conn, ch, getattr(chat, "id", None), "joined via invite link")
        return chat, True
    return None, False


async def _collect_entity(client, conn, ch, entity, settings, stats: RunStats):
    from telethon.tl.functions.channels import GetFullChannelRequest
    from telethon.tl.types import InputMessagesFilterPinned

    peer_id = getattr(entity, "id", None)
    username = getattr(entity, "username", None) or ch["username"]
    # 1) all network calls first — no database transaction may stay open while awaiting Telegram
    messages = list(await client.get_messages(entity, limit=120))
    pinned = await client.get_messages(entity, filter=InputMessagesFilterPinned, limit=50)
    subscribers = None
    try:
        full = await client(GetFullChannelRequest(entity))
        subscribers = getattr(full.full_chat, "participants_count", None)
    except Exception:  # groups / permission quirks — the snapshot is still useful without the count
        pass
    # 2) then write
    newest = None
    for m in messages:
        post = message_to_post(m, settings.hashtag, peer_id, username)
        if upsert_post(conn, ch["id"], post, "mtproto", settings):
            stats.posts_new += 1
        else:
            stats.posts_updated += 1
        newest = max(newest or 0, post["message_id"])
    pinned_ids = [int(m.id) for m in (pinned or [])]
    today = now_local(settings.tz).date().isoformat()
    conn.execute("INSERT INTO pin_snapshots(channel_id, captured_at, local_date, pinned_message_ids) VALUES(?,?,?,?)",
                 (ch["id"], now_utc(), today, json.dumps(pinned_ids)))
    if pinned_ids:
        conn.execute(f"UPDATE posts SET is_pinned=1 WHERE channel_id=? AND message_id IN ({','.join('?' * len(pinned_ids))})",
                     [ch["id"], *pinned_ids])
    _snapshot(conn, ch, subscribers, getattr(entity, "title", None), "mtproto", stats, now_utc())
    conn.execute("UPDATE channels SET joined=1, tg_peer_id=COALESCE(?, tg_peer_id), last_message_id=COALESCE(?, last_message_id),"
                 " last_checked=?, last_error=NULL WHERE id=?", (peer_id, newest, now_utc(), ch["id"]))
    conn.commit()


async def run_mtproto_collector(conn: sqlite3.Connection, settings, log=None, client_factory=None, sleep=None) -> dict:
    log = log or (lambda s: None)
    sleep = sleep or asyncio.sleep
    if not settings.mtproto_enabled:
        return {"skipped": "mtproto not configured"}
    from telethon import TelegramClient, errors
    from telethon.sessions import StringSession

    stats = RunStats()
    joins = 0
    flood_waits = 0
    started = now_utc()
    client = client_factory() if client_factory else TelegramClient(StringSession(settings.tg_session), settings.tg_api_id, settings.tg_api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            conn.execute("INSERT INTO runs(kind, started_at, finished_at, ok, detail) VALUES('mtproto', ?, ?, 0, ?)",
                         (started, now_utc(), json.dumps({"error": "session not authorized"})))
            conn.commit()
            return {"error": "session not authorized"}
        try:
            await client.get_dialogs(limit=None)    # warm the entity cache so PeerChannel(id) resolves
        except errors.FloodWaitError as e:
            conn.execute("INSERT INTO runs(kind, started_at, finished_at, ok, detail) VALUES('mtproto', ?, ?, 0, ?)",
                         (started, now_utc(), json.dumps({"error": f"FLOOD_WAIT {e.seconds}s at get_dialogs"})))
            conn.commit()
            return {"error": f"FLOOD_WAIT {e.seconds}s"}
        # a channel the account already reads (joined=1) keeps being read even if the invite page went dark
        chans = conn.execute(
            "SELECT * FROM channels WHERE kind IN ('private','public_no_preview','group','unknown') "
            "AND collector IN ('invite','profile','mtproto') AND (dead_at IS NULL OR joined=1) "
            "ORDER BY last_checked IS NOT NULL, last_checked, id").fetchall()     # never checked, then oldest first
        for i, ch in enumerate(chans):
            stats.channels += 1
            try:
                entity, joined_now = await _resolve_entity(client, conn, ch, settings, joins, stats)
                if joined_now:
                    joins += 1
                if entity is not None:
                    await _collect_entity(client, conn, ch, entity, settings, stats)
            except errors.FloodWaitError as e:
                flood_waits += 1
                conn.execute("UPDATE channels SET last_error=?, last_checked=? WHERE id=?", (f"FLOOD_WAIT {e.seconds}s", now_utc(), ch["id"]))
                conn.commit()
                if e.seconds <= FLOOD_WAIT_MAX_SLEEP:
                    log(f"flood wait {e.seconds}s — sleeping, then continuing")
                    await sleep(e.seconds + 1)
                    continue
                log(f"flood wait {e.seconds}s — stopping this run")
                break
            except (errors.RPCError, ValueError, TypeError) as e:
                stats.errors += 1
                conn.execute("UPDATE channels SET last_error=?, last_checked=? WHERE id=?", (f"{type(e).__name__}: {e}"[:300], now_utc(), ch["id"]))
            conn.commit()
            log(f"[mtproto {i + 1}/{len(chans)}] {ch['channel_key']} new={stats.posts_new} upd={stats.posts_updated} joins={joins} err={stats.errors}")
            if i < len(chans) - 1:
                await sleep(random.uniform(1.0, 2.0))
    finally:
        await client.disconnect()
    detail = {**stats.as_dict(), "joins": joins, "flood_waits": flood_waits}
    conn.execute("INSERT INTO runs(kind, started_at, finished_at, ok, detail) VALUES('mtproto', ?, ?, 1, ?)", (started, now_utc(), json.dumps(detail)))
    conn.commit()
    return detail
