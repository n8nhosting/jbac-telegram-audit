import datetime as dt
import json
import pathlib
import unittest
from types import SimpleNamespace

from app.collector import RunStats
from app.config import load_settings
from app.db import connect, migrate, one, all_rows
from app.importer import import_seed
from app.mtproto import _collect_entity, message_to_post, run_mtproto_collector

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


class TestRunDisabled(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_without_session(self):
        conn = connect(":memory:")
        migrate(conn)
        st = await run_mtproto_collector(conn, load_settings({}))
        self.assertEqual(st["skipped"], "mtproto not configured")


if __name__ == "__main__":
    unittest.main()
