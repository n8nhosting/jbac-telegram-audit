import datetime as dt
import json
import pathlib
import unittest
from types import SimpleNamespace

from app.collector import RunStats
from app.config import load_settings
from app.db import connect, migrate, one, all_rows
from app.importer import import_seed
from app.mtproto import _collect_entity, _resolve_entity, message_to_post, run_mtproto_collector

SEED = json.loads((pathlib.Path(__file__).resolve().parent / "fixtures" / "seed_small.json").read_text(encoding="utf-8"))

UTC = dt.timezone.utc


def msg(**kw):
    base = dict(id=5, date=dt.datetime(2026, 10, 25, 10, 0, tzinfo=UTC), message="โปร #PlatinumClubMM วันนี้",
                photo=None, video=None, document=None, sticker=None, pinned=False, views=12, web_preview=None, entities=[])
    base.update(kw)
    return SimpleNamespace(**base)


class TestMessageToPost(unittest.TestCase):
    def test_photo_with_tag(self):
        p = message_to_post(msg(photo=object(), pinned=True), "#platinumclubmm")
        self.assertEqual((p["post_id"], p["datetime"], p["is_pinned"], p["views"]), (5, "2026-10-25T10:00:00+00:00", True, 12))
        self.assertTrue(p["has_target_hashtag"])
        self.assertTrue(p["has_media"])
        self.assertFalse(p["has_sticker"])

    def test_sticker_is_not_media(self):
        p = message_to_post(msg(sticker=object(), message=None), "#platinumclubmm")
        self.assertTrue(p["has_sticker"])
        self.assertFalse(p["has_media"])
        self.assertFalse(p["has_target_hashtag"])

    def test_document_image_counts_as_media_but_pdf_does_not(self):
        img = SimpleNamespace(mime_type="image/jpeg")
        pdf = SimpleNamespace(mime_type="application/pdf")
        self.assertTrue(message_to_post(msg(document=img), "#platinumclubmm")["has_media"])
        self.assertFalse(message_to_post(msg(document=pdf), "#platinumclubmm")["has_media"])

    def test_link_detection(self):
        self.assertTrue(message_to_post(msg(message="ดู https://example.com/x #platinumclubmm"), "#platinumclubmm")["has_link"])
        self.assertTrue(message_to_post(msg(web_preview=object()), "#platinumclubmm")["has_link"])
        self.assertFalse(message_to_post(msg(), "#platinumclubmm")["has_link"])

    def test_permalink_for_private_peer(self):
        p = message_to_post(msg(), "#platinumclubmm", peer_id=1234567890, username=None)
        self.assertEqual(p["permalink"], "https://t.me/c/1234567890/5")
        p2 = message_to_post(msg(), "#platinumclubmm", peer_id=1234567890, username="chanx")
        self.assertEqual(p2["permalink"], "https://t.me/chanx/5")


class TestJoinPolicy(unittest.TestCase):
    def test_should_attempt_join(self):
        from app.mtproto import should_attempt_join
        now = dt.datetime(2026, 10, 25, tzinfo=UTC)
        self.assertTrue(should_attempt_join({"join_requested_at": None}, now))
        self.assertFalse(should_attempt_join({"join_requested_at": "2026-10-24T00:00:00+00:00"}, now))
        self.assertTrue(should_attempt_join({"join_requested_at": "2026-10-10T00:00:00+00:00"}, now))


class FakeTg:
    """Just enough of a Telethon client for _collect_entity; records whether a DB transaction was open per call."""

    def __init__(self, conn, msgs, pinned):
        self.conn, self.msgs, self.pinned, self.calls = conn, msgs, pinned, []

    async def get_messages(self, entity, limit=None, filter=None):
        self.calls.append(("get_messages", self.conn.in_transaction))
        return list(self.pinned) if filter is not None else list(self.msgs)

    async def __call__(self, request):
        self.calls.append(("request", self.conn.in_transaction))
        raise RuntimeError("full channel not available in the fake")


class TestCollectEntity(unittest.IsolatedAsyncioTestCase):
    async def test_collect_entity_fetches_then_writes(self):
        conn = connect(":memory:")
        migrate(conn)
        import_seed(conn, SEED)
        ch = one(conn, "SELECT * FROM channels WHERE channel_key='prv:AAAA1111'")
        entity = SimpleNamespace(id=1234567890, username=None, title="Chan B live")
        msgs = [msg(id=5, photo=object(), pinned=True), msg(id=6, message="no tag here", photo=object())]
        client = FakeTg(conn, msgs, pinned=[SimpleNamespace(id=5)])
        stats = RunStats()
        await _collect_entity(client, conn, ch, entity, load_settings({}), stats)
        self.assertEqual(stats.posts_new, 2)
        self.assertFalse(any(tx for _, tx in client.calls), client.calls)      # network first, writes after
        rows = all_rows(conn, "SELECT message_id, is_pinned, qualifies, source, permalink FROM posts WHERE channel_id=? ORDER BY message_id", (ch["id"],))
        self.assertEqual([(r["message_id"], r["is_pinned"], r["qualifies"], r["source"]) for r in rows],
                         [(5, 1, 1, "mtproto"), (6, 0, 0, "mtproto")])
        self.assertEqual(rows[0]["permalink"], "https://t.me/c/1234567890/5")
        self.assertEqual(json.loads(one(conn, "SELECT pinned_message_ids FROM pin_snapshots WHERE channel_id=?", (ch["id"],))["pinned_message_ids"]), [5])
        c = one(conn, "SELECT joined, tg_peer_id, last_message_id, title_observed FROM channels WHERE id=?", (ch["id"],))
        self.assertEqual((c["joined"], c["tg_peer_id"], c["last_message_id"], c["title_observed"]), (1, 1234567890, 6, "Chan B live"))


class FakeAccount:
    """A Telethon client stand-in for whole runs: resolves usernames, answers invite requests, records call order
    and whether the shared connection had a write transaction open while the 'network' call was in flight."""

    def __init__(self, conn, flood_on=None, flood_seconds=219):
        self.conn, self.flood_on, self.flood_seconds = conn, flood_on, flood_seconds
        self.visited, self.calls = [], []

    async def connect(self): pass
    async def disconnect(self): pass
    async def is_user_authorized(self): return True
    async def get_dialogs(self, limit=None): return []

    async def get_entity(self, key):
        from telethon import errors
        self.visited.append(key)
        self.calls.append(("get_entity", self.conn.in_transaction))
        if key == self.flood_on:
            self.flood_on = None
            raise errors.FloodWaitError(request=None, capture=self.flood_seconds)
        return SimpleNamespace(id=abs(hash(key)) % 10 ** 9, username=key, title=key)

    async def get_messages(self, entity, limit=None, filter=None):
        self.calls.append(("get_messages", self.conn.in_transaction))
        return []

    async def __call__(self, request):
        name = type(request).__name__
        self.calls.append((name, self.conn.in_transaction))
        if name == "CheckChatInviteRequest":
            self.visited.append("invite:" + request.hash)
            return SimpleNamespace(title="Chan B", participants_count=3)        # not a member yet
        if name == "ImportChatInviteRequest":
            return SimpleNamespace(chats=[SimpleNamespace(id=999, title="Chan B")])
        raise RuntimeError("full channel not available in the fake")


def _db():
    conn = connect(":memory:")
    migrate(conn)
    import_seed(conn, SEED)
    return conn


class TestResolveEntity(unittest.IsolatedAsyncioTestCase):
    async def test_invite_join_never_awaits_with_open_transaction(self):
        """The public collector and the web app share the file: a write transaction must not stay open across a
        Telegram round-trip (Telethon may sleep a flood wait inside it), or they hit 'database is locked'."""
        conn = _db()
        ch = one(conn, "SELECT * FROM channels WHERE channel_key='prv:AAAA1111'")
        client = FakeAccount(conn)
        stats = RunStats()
        entity, joined_now = await _resolve_entity(client, conn, ch, load_settings({}), 0, stats)
        self.assertTrue(joined_now)
        self.assertEqual(entity.id, 999)
        await _collect_entity(client, conn, ch, entity, load_settings({}), stats)
        self.assertFalse(conn.in_transaction)
        self.assertEqual([c for c in client.calls if c[1]], [], client.calls)
        row = one(conn, "SELECT joined, tg_peer_id FROM channels WHERE id=?", (ch["id"],))
        self.assertEqual((row["joined"], row["tg_peer_id"]), (1, 999))
        self.assertEqual(one(conn, "SELECT event FROM channel_events WHERE channel_id=? ORDER BY id DESC LIMIT 1", (ch["id"],))["event"], "joined")


class TestRunOrderAndFloodWait(unittest.IsolatedAsyncioTestCase):
    async def test_least_recently_checked_first_and_long_flood_wait_is_slept(self):
        """A run that stops early must not restart from the same channels next time, and a few minutes of
        FLOOD_WAIT is slept through instead of abandoning the remaining channels."""
        conn = _db()
        conn.execute("UPDATE channels SET kind='public_no_preview', collector='profile', last_checked='2026-10-20T00:00:00+00:00' WHERE channel_key='pub:chanc'")
        conn.execute("UPDATE channels SET kind='public_no_preview', collector='profile', last_checked='2026-10-26T00:00:00+00:00' WHERE channel_key='pub:chana'")
        conn.commit()
        client = FakeAccount(conn, flood_on="chanc")
        slept = []

        async def sleep(sec):
            slept.append(sec)

        st = await run_mtproto_collector(conn, load_settings({"TG_API_ID": "1", "TG_API_HASH": "h", "TG_SESSION": "s"}),
                                         client_factory=lambda: client, sleep=sleep)
        self.assertEqual(client.visited, ["invite:AAAA1111", "chanc", "chana"])     # never checked → oldest → newest
        self.assertEqual((st["channels"], st["flood_waits"], st["joins"]), (3, 1, 1))
        self.assertIn(220, slept)                                                     # 219 s + 1, then carry on
        self.assertEqual(one(conn, "SELECT ok FROM runs WHERE kind='mtproto'")["ok"], 1)
        self.assertEqual([c for c in client.calls if c[1]], [], client.calls)


class TestRunDisabled(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_without_session(self):
        conn = connect(":memory:")
        migrate(conn)
        st = await run_mtproto_collector(conn, load_settings({}))
        self.assertEqual(st["skipped"], "mtproto not configured")


if __name__ == "__main__":
    unittest.main()
