"""Public collector: reads t.me pages that need no account.

- collector='preview': https://t.me/s/<u>?q=%23platinumclubmm → tagged posts + title/subscribers
  (during the hashtag transition window the plain https://t.me/s/<u> page is read too, so untagged
  "platinum" posts can count as legacy_match); if the preview is gone the channel is re-filed as 'profile'
- collector='profile': https://t.me/<u>      → title/subscribers only
- collector='invite' : https://t.me/+<hash>  → title/subscribers only (never joins)
A channel is marked dead only after DEAD_AFTER_MISSES consecutive runs where the page showed no channel.
Sequential, random delay between channels, one run at a time (lock), every settings.collector_interval_min minutes.
"""
from __future__ import annotations

import asyncio
import json
import random
import sqlite3
from dataclasses import dataclass

from . import tgweb
from .db import now_utc
from .rules import local_date_of, now_local, post_qualifies

DEAD_AFTER_MISSES = 3
PROFILE_KIND = {"channel_no_preview": "public_no_preview", "restricted_channel": "public_no_preview",
                "group": "group", "user_or_bot": "not_channel"}
_RUNNING = False
_LOCKS: dict[int, asyncio.Lock] = {}


def is_running() -> bool:
    return _RUNNING


def _lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    return _LOCKS.setdefault(id(loop), asyncio.Lock())


@dataclass
class RunStats:
    channels: int = 0
    posts_new: int = 0
    posts_updated: int = 0
    snapshots: int = 0
    renamed: int = 0
    dead: int = 0
    errors: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _norm_title(t) -> str | None:
    return " ".join(str(t).split()) or None if t else None


def upsert_post(conn: sqlite3.Connection, channel_id: int, post: dict, source: str, settings) -> bool:
    """Insert or refresh one post; returns True when the post is new. Safe across connections."""
    mid = post.get("post_id") if post.get("post_id") is not None else post.get("message_id")
    posted_at = post.get("datetime") or post.get("posted_at")
    if mid is None or not posted_at:
        return False
    local_date = local_date_of(posted_at, settings.tz)
    ok, reason = post_qualifies(post, local_date, settings)
    has_tag = int(bool(post.get("has_target_hashtag") or post.get("has_tag")))
    has_media, has_link, has_sticker = (int(bool(post.get(k))) for k in ("has_media", "has_link", "has_sticker"))
    legacy = int(reason == "legacy_match")
    text = (post.get("text") or "")[:500] or None
    now = now_utc()
    cur = conn.execute(
        """INSERT OR IGNORE INTO posts(channel_id, message_id, posted_at, local_date, has_tag, has_media, has_link, has_sticker,
               legacy_match, is_pinned, text_preview, permalink, views, source, qualifies, qualify_reason, first_seen, last_seen)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (channel_id, mid, posted_at, local_date, has_tag, has_media, has_link, has_sticker, legacy, post.get("is_pinned"),
         text, post.get("permalink"), post.get("views"), source, int(ok), reason, now, now))
    if cur.rowcount == 1:
        return True
    conn.execute(
        """UPDATE posts SET views=COALESCE(?, views), last_seen=?, text_preview=COALESCE(?, text_preview),
               is_pinned=COALESCE(?, is_pinned), has_tag=?, has_media=?, has_link=?, has_sticker=?, legacy_match=?,
               qualifies=?, qualify_reason=?, permalink=COALESCE(permalink, ?)
           WHERE channel_id=? AND message_id=?""",
        (post.get("views"), now, text, post.get("is_pinned"), has_tag, has_media, has_link, has_sticker, legacy,
         int(ok), reason, post.get("permalink"), channel_id, mid))
    return False


def _observe_title(conn, ch, new_title, stats: RunStats, now: str):
    new_title = _norm_title(new_title)
    if not new_title:
        return
    old = _norm_title(ch["title_observed"])
    if old and old != new_title:
        conn.execute("INSERT INTO channel_aliases(channel_id, contract_id, old_title, old_url, old_channel_key, seen_at, source)"
                     " VALUES(?,?,?,?,?,?,?)", (ch["id"], None, old, None, None, now, "collector"))
        conn.execute("INSERT INTO channel_events(channel_id, event, happened_at, note) VALUES(?,?,?,?)",
                     (ch["id"], "renamed", now, json.dumps({"from": old, "to": new_title}, ensure_ascii=False)))
        stats.renamed += 1
    conn.execute("UPDATE channels SET title_observed=? WHERE id=?", (new_title, ch["id"]))


def _alive(conn, ch, now: str):
    """The page resolved: reset the miss counter and clear a previous death."""
    if ch["dead_at"]:
        conn.execute("INSERT INTO channel_events(channel_id, event, happened_at, note) VALUES(?,?,?,?)",
                     (ch["id"], "alive", now, "resolves again"))
    conn.execute("UPDATE channels SET dead_misses=0, dead_at=NULL, last_checked=?, last_error=NULL WHERE id=?", (now, ch["id"]))


def _snapshot(conn, ch, subscribers, title, source, stats: RunStats, now: str):
    _alive(conn, ch, now)
    if subscribers is None and not _norm_title(title):
        return                                                     # nothing known: no empty snapshot row
    conn.execute("INSERT INTO snapshots(channel_id, captured_at, subscribers, title, source) VALUES(?,?,?,?,?)",
                 (ch["id"], now, subscribers, _norm_title(title), source))
    stats.snapshots += 1
    if subscribers is not None:
        conn.execute("UPDATE channels SET subscribers=? WHERE id=?", (subscribers, ch["id"]))
    _observe_title(conn, ch, title, stats, now)


def _miss(conn, ch, stats: RunStats, now: str, note: str):
    """The page showed no channel this run; dead only after DEAD_AFTER_MISSES consecutive misses."""
    misses = int(ch["dead_misses"] or 0) + 1
    conn.execute("UPDATE channels SET dead_misses=?, last_checked=?, last_error=? WHERE id=?", (misses, now, note, ch["id"]))
    if misses >= DEAD_AFTER_MISSES and not ch["dead_at"]:
        conn.execute("UPDATE channels SET dead_at=? WHERE id=?", (now, ch["id"]))
        conn.execute("INSERT INTO channel_events(channel_id, event, happened_at, note) VALUES(?,?,?,?)",
                     (ch["id"], "dead", now, f"{note} ({misses} runs in a row)"))
        stats.dead += 1


def _error(conn, ch, error: str | None, stats: RunStats, now: str):
    stats.errors += 1
    conn.execute("UPDATE channels SET last_error=?, last_checked=? WHERE id=?", ((error or "fetch failed")[:300], now, ch["id"]))


def _apply_profile(conn, ch, prof: dict, stats: RunStats, now: str) -> str:
    """Profile/redirect page → snapshot + kind/collector; returns the profile kind."""
    kind = prof["kind"]
    if kind == "missing":
        _miss(conn, ch, stats, now, "username does not resolve")
        return kind
    if kind == "unknown":
        _error(conn, ch, "profile page not recognised", stats, now)
        return kind
    _snapshot(conn, ch, prof.get("subscribers"), prof.get("title"), "profile", stats, now)
    new_kind = PROFILE_KIND.get(kind)
    new_collector = "none" if kind == "user_or_bot" else "profile"
    conn.execute("UPDATE channels SET kind=COALESCE(?, kind), collector=? WHERE id=?", (new_kind, new_collector, ch["id"]))
    return kind


def _in_legacy_window(settings) -> bool:
    return now_local(settings.tz).date().isoformat() < settings.hashtag_enforced_from


async def _collect_preview(conn, ch, settings, client, stats: RunStats, sleep, now: str):
    r = await tgweb.fetch_text(client, tgweb.search_url(ch["username"], settings.hashtag), sleep=sleep)
    if not r.ok:
        _error(conn, ch, r.error, stats, now)
        return
    p = tgweb.parse_preview(r.html, r.final_url, settings.hashtag)
    if not p["readable"]:
        if p["reason"] == "redirected_no_preview":
            _apply_profile(conn, ch, tgweb.parse_profile(r.html), stats, now)   # preview gone for good
        else:
            _error(conn, ch, "no_channel_info (page without channel header)", stats, now)  # transient: keep preview
        return
    for post in p["posts"]:
        if upsert_post(conn, ch["id"], post, "preview", settings):
            stats.posts_new += 1
        else:
            stats.posts_updated += 1
    counters = p.get("counters") or {}
    _snapshot(conn, ch, counters.get("subscribers") or counters.get("members"), p.get("title"), "preview", stats, now)
    conn.commit()   # never hold the write lock while awaiting the network: the rollup job shares the database
    if _in_legacy_window(settings):
        # before hashtag enforcement untagged "platinum" posts count too; the search page cannot show them
        await sleep(random.uniform(settings.fetch_delay_min, settings.fetch_delay_max))
        r2 = await tgweb.fetch_text(client, tgweb.preview_url(ch["username"]), sleep=sleep)
        if r2.ok:
            p2 = tgweb.parse_preview(r2.html, r2.final_url, settings.hashtag)
            for post in p2.get("posts", []):
                if upsert_post(conn, ch["id"], post, "preview", settings):
                    stats.posts_new += 1
                else:
                    stats.posts_updated += 1
            conn.commit()


async def _collect_channel(conn, ch, settings, client, stats: RunStats, sleep):
    now = now_utc()
    if ch["collector"] == "preview":
        await _collect_preview(conn, ch, settings, client, stats, sleep, now)
    elif ch["collector"] == "profile":
        r = await tgweb.fetch_text(client, tgweb.profile_url(ch["username"]), sleep=sleep)
        if not r.ok:
            _error(conn, ch, r.error, stats, now)
            return
        _apply_profile(conn, ch, tgweb.parse_profile(r.html), stats, now)
    elif ch["collector"] == "invite":
        r = await tgweb.fetch_text(client, tgweb.invite_url(ch["invite_hash"]), sleep=sleep)
        if not r.ok:
            _error(conn, ch, r.error, stats, now)
            return
        inv = tgweb.parse_invite(r.html)
        if inv["visible"]:
            _snapshot(conn, ch, inv.get("subscribers"), inv.get("title"), "invite", stats, now)
        else:
            _miss(conn, ch, stats, now, "invite page shows no channel")


async def run_public_collector(conn: sqlite3.Connection, settings, client=None, sleep=None, log=None) -> RunStats:
    global _RUNNING
    sleep = sleep or asyncio.sleep
    log = log or (lambda s: None)
    stats = RunStats()
    started = now_utc()
    own_client = client is None
    async with _lock():
        _RUNNING = True
        if own_client:
            import httpx
            client = httpx.AsyncClient(headers=tgweb.default_headers(), timeout=20)
        try:
            chans = conn.execute("SELECT * FROM channels WHERE collector IN ('preview','profile','invite') ORDER BY id").fetchall()
            for i, ch in enumerate(chans):
                stats.channels += 1
                try:
                    await _collect_channel(conn, ch, settings, client, stats, sleep)
                except Exception as e:  # never let one channel stop the run
                    _error(conn, ch, f"{type(e).__name__}: {e}", stats, now_utc())
                conn.commit()
                log(f"[{i + 1}/{len(chans)}] {ch['channel_key']} new={stats.posts_new} upd={stats.posts_updated} err={stats.errors}")
                if i < len(chans) - 1:
                    await sleep(random.uniform(settings.fetch_delay_min, settings.fetch_delay_max))
        finally:
            _RUNNING = False
            if own_client:
                await client.aclose()
    conn.execute("INSERT INTO runs(kind, started_at, finished_at, ok, detail) VALUES('collector', ?, ?, 1, ?)",
                 (started, now_utc(), json.dumps(stats.as_dict())))
    conn.commit()
    return stats
