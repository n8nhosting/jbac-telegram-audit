import json
import pathlib
import tempfile
import unittest

import httpx

from app import tgweb
from app.collector import DEAD_AFTER_MISSES, run_public_collector, upsert_post
from app.config import load_settings
from app.db import connect, migrate, one, all_rows
from app.importer import import_seed

HERE = pathlib.Path(__file__).resolve().parent
FIX = HERE.parents[0] / "tools" / "tests" / "fixtures"
SEED = json.loads((HERE / "fixtures" / "seed_small.json").read_text(encoding="utf-8"))
PREVIEW = (FIX / "tgme_s_mini_drama_channel.html").read_text(encoding="utf-8")
PROFILE = (FIX / "tgme_profile_channel_nopreview.html").read_text(encoding="utf-8")
INVITE = (FIX / "tgme_invite_sample.html").read_text(encoding="utf-8")
S = load_settings({"HASHTAG_ENFORCED_FROM": "2026-01-01"})          # hashtag already enforced: search page only
S_LEGACY = load_settings({"HASHTAG_ENFORCED_FROM": "2099-01-01"})   # still in the transition window


class _Resp:
    def __init__(self, status, text, url):
        self.status_code, self.text, self.url = status, text, url


class FakeClient:
    """routes: url -> (status, html, final_url); missing url raises a network error."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    async def get(self, url, **kw):
        self.calls.append(url)
        if url not in self.routes:
            raise httpx.ConnectError("no route")
        status, html, final = self.routes[url]
        return _Resp(status, html, final)


async def nosleep(_):
    pass


def routes_default(hashtag=S.hashtag):
    return {
        tgweb.search_url("chana", hashtag): (200, PREVIEW, tgweb.search_url("chana", hashtag)),
        tgweb.search_url("chanc", hashtag): (200, PROFILE, tgweb.profile_url("chanc")),   # redirected: no preview
        tgweb.profile_url("chanc"): (200, PROFILE, tgweb.profile_url("chanc")),             # later runs go straight here
        tgweb.invite_url("AAAA1111"): (200, INVITE, tgweb.invite_url("AAAA1111")),
    }


class TestCollector(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        migrate(self.conn)
        import_seed(self.conn, SEED)

    async def test_collector_upserts_posts_and_snapshots(self):
        client = FakeClient(routes_default())
        st = await run_public_collector(self.conn, S, client=client, sleep=nosleep)
        self.assertEqual((st.channels, st.posts_new, st.errors), (3, 20, 0))
        chana = one(self.conn, "SELECT * FROM channels WHERE channel_key='pub:chana'")
        self.assertEqual(chana["subscribers"], 108000)
        self.assertEqual(chana["title_observed"], "𝗠𝗶𝗻𝗶 𝗗𝗿𝗮𝗺𝗮 𝗖𝗵𝗮𝗻𝗻𝗲𝗹")
        self.assertEqual(chana["title"], "Chan A")                       # sheet name stays
        self.assertIsNotNone(chana["last_checked"])
        posts = all_rows(self.conn, "SELECT * FROM posts WHERE channel_id=? ORDER BY message_id", (chana["id"],))
        self.assertEqual(len(posts), 20)
        self.assertEqual((posts[0]["message_id"], posts[0]["source"], posts[0]["local_date"]), (30513, "preview", "2026-10-25"))
        self.assertEqual(posts[0]["permalink"], "https://t.me/Mini_Drama_Channel/30513")
        self.assertEqual(posts[0]["has_media"], 1)
        self.assertEqual(all_rows(self.conn, "SELECT subscribers FROM snapshots WHERE channel_id=?", (chana["id"],))[0]["subscribers"], 108000)
        self.assertEqual(one(self.conn, "SELECT COUNT(*) AS n FROM channel_aliases WHERE source='collector'")["n"], 0)
        self.assertNotIn(tgweb.preview_url("chana"), client.calls)      # hashtag enforced: no plain page fetch

    async def test_collector_marks_no_preview_channel(self):
        await run_public_collector(self.conn, S, client=FakeClient(routes_default()), sleep=nosleep)
        chanc = one(self.conn, "SELECT * FROM channels WHERE channel_key='pub:chanc'")
        self.assertEqual((chanc["collector"], chanc["kind"], chanc["subscribers"]), ("profile", "public_no_preview", 333880))
        self.assertEqual(one(self.conn, "SELECT COUNT(*) AS n FROM posts WHERE channel_id=?", (chanc["id"],))["n"], 0)
        self.assertIsNone(chanc["last_error"])

    async def test_unknown_page_keeps_preview_and_records_error(self):
        routes = routes_default()
        routes[tgweb.search_url("chana")] = (200, "<html><body>please wait</body></html>", tgweb.search_url("chana"))
        st = await run_public_collector(self.conn, S, client=FakeClient(routes), sleep=nosleep)
        chana = one(self.conn, "SELECT collector, kind, last_error FROM channels WHERE channel_key='pub:chana'")
        self.assertEqual((chana["collector"], chana["kind"]), ("preview", "public_preview"))
        self.assertIn("no_channel_info", chana["last_error"])
        self.assertEqual(st.errors, 1)

    async def test_invite_snapshot(self):
        await run_public_collector(self.conn, S, client=FakeClient(routes_default()), sleep=nosleep)
        prv = one(self.conn, "SELECT * FROM channels WHERE channel_key='prv:AAAA1111'")
        self.assertEqual((prv["subscribers"], prv["title_observed"]), (29783, "Bollywood Movies🇮🇳🇮🇳"))

    async def test_rename_creates_alias_and_event(self):
        routes = routes_default()
        await run_public_collector(self.conn, S, client=FakeClient(routes), sleep=nosleep)
        renamed = PREVIEW.replace("𝗠𝗶𝗻𝗶 𝗗𝗿𝗮𝗺𝗮 𝗖𝗵𝗮𝗻𝗻𝗲𝗹", "New Drama Name")
        routes[tgweb.search_url("chana")] = (200, renamed, tgweb.search_url("chana"))
        st = await run_public_collector(self.conn, S, client=FakeClient(routes), sleep=nosleep)
        self.assertEqual(st.renamed, 1)
        alias = one(self.conn, "SELECT * FROM channel_aliases WHERE source='collector'")
        self.assertEqual(alias["old_title"], "𝗠𝗶𝗻𝗶 𝗗𝗿𝗮𝗺𝗮 𝗖𝗵𝗮𝗻𝗻𝗲𝗹")
        self.assertEqual(one(self.conn, "SELECT event FROM channel_events ORDER BY id DESC LIMIT 1")["event"], "renamed")
        self.assertEqual(one(self.conn, "SELECT title_observed FROM channels WHERE channel_key='pub:chana'")["title_observed"], "New Drama Name")

    async def test_whitespace_only_title_change_is_not_a_rename(self):
        routes = routes_default()
        await run_public_collector(self.conn, S, client=FakeClient(routes), sleep=nosleep)
        spaced = PREVIEW.replace("𝗠𝗶𝗻𝗶 𝗗𝗿𝗮𝗺𝗮 𝗖𝗵𝗮𝗻𝗻𝗲𝗹", "𝗠𝗶𝗻𝗶  𝗗𝗿𝗮𝗺𝗮  𝗖𝗵𝗮𝗻𝗻𝗲𝗹 ")
        routes[tgweb.search_url("chana")] = (200, spaced, tgweb.search_url("chana"))
        st = await run_public_collector(self.conn, S, client=FakeClient(routes), sleep=nosleep)
        self.assertEqual(st.renamed, 0)

    async def test_second_run_updates_instead_of_duplicating(self):
        client = FakeClient(routes_default())
        await run_public_collector(self.conn, S, client=client, sleep=nosleep)
        st = await run_public_collector(self.conn, S, client=client, sleep=nosleep)
        self.assertEqual((st.posts_new, st.posts_updated), (0, 20))
        self.assertEqual(one(self.conn, "SELECT COUNT(*) AS n FROM posts")["n"], 20)
        self.assertEqual(one(self.conn, "SELECT COUNT(*) AS n FROM snapshots")["n"], 6)

    async def test_network_error_is_recorded_and_run_continues(self):
        routes = routes_default()
        del routes[tgweb.search_url("chana")]
        st = await run_public_collector(self.conn, S, client=FakeClient(routes), sleep=nosleep)
        self.assertEqual(st.errors, 1)
        self.assertIn("ConnectError", one(self.conn, "SELECT last_error FROM channels WHERE channel_key='pub:chana'")["last_error"])
        self.assertEqual(one(self.conn, "SELECT COUNT(*) AS n FROM snapshots")["n"], 2)
        run = one(self.conn, "SELECT * FROM runs WHERE kind='collector' ORDER BY id DESC LIMIT 1")
        self.assertEqual(run["ok"], 1)

    async def test_locked_database_on_one_channel_does_not_abort_the_run(self):
        """Another job (MTProto collector, rollup) may hold the write lock for a moment: that channel is skipped
        with an error, the run goes on, and the run record is still written."""
        with tempfile.TemporaryDirectory() as d:
            path = str(pathlib.Path(d) / "audit.db")
            conn = connect(path)
            conn.execute("PRAGMA busy_timeout=50")
            migrate(conn)
            import_seed(conn, SEED)
            other = connect(path)
            calls = []

            async def sleep(_):            # between channel 1 and 2: take the lock; between 2 and 3: release it
                calls.append(1)
                if len(calls) == 1:
                    other.execute("BEGIN IMMEDIATE")
                elif len(calls) == 2:
                    other.commit()

            try:
                st = await run_public_collector(conn, S, client=FakeClient(routes_default()), sleep=sleep)
                self.assertEqual(st.channels, 3)
                self.assertGreaterEqual(st.errors, 1)
                # channel 2 (prv:AAAA1111) met the lock and was skipped; channel 3 ran after the lock was released
                self.assertIsNone(one(conn, "SELECT last_checked FROM channels WHERE channel_key='prv:AAAA1111'")["last_checked"])
                self.assertIsNotNone(one(conn, "SELECT last_checked FROM channels WHERE channel_key='pub:chanc'")["last_checked"])
                self.assertEqual(one(conn, "SELECT COUNT(*) AS n FROM runs WHERE kind='collector'")["n"], 1)
            finally:
                other.close()
                conn.close()

    async def test_missing_username_marks_dead_only_after_consecutive_misses(self):
        routes = routes_default()
        gone = '<div class="tgme_page_description">If you have Telegram, you can contact <a>@chanc</a> right away.</div>'
        routes[tgweb.search_url("chanc")] = (200, gone, tgweb.profile_url("chanc"))
        routes[tgweb.profile_url("chanc")] = (200, gone, tgweb.profile_url("chanc"))
        for i in range(1, DEAD_AFTER_MISSES + 1):
            await run_public_collector(self.conn, S, client=FakeClient(routes), sleep=nosleep)
            chanc = one(self.conn, "SELECT dead_at, dead_misses, collector FROM channels WHERE channel_key='pub:chanc'")
            self.assertEqual(chanc["dead_misses"], i)
            if i < DEAD_AFTER_MISSES:
                self.assertIsNone(chanc["dead_at"], f"dead too early at miss {i}")
        self.assertIsNotNone(chanc["dead_at"])
        self.assertEqual(one(self.conn, "SELECT COUNT(*) AS n FROM channel_events WHERE event='dead'")["n"], 1)
        # it resolves again (still filed as preview, so the search URL is what gets fetched) → alive, misses reset
        routes[tgweb.search_url("chanc")] = (200, PROFILE, tgweb.profile_url("chanc"))
        await run_public_collector(self.conn, S, client=FakeClient(routes), sleep=nosleep)
        chanc = one(self.conn, "SELECT dead_at, dead_misses FROM channels WHERE channel_key='pub:chanc'")
        self.assertEqual((chanc["dead_at"], chanc["dead_misses"]), (None, 0))

    async def test_invite_page_without_channel_is_not_dead_on_first_miss(self):
        routes = routes_default()
        routes[tgweb.invite_url("AAAA1111")] = (200, "<html><body>nothing</body></html>", tgweb.invite_url("AAAA1111"))
        await run_public_collector(self.conn, S, client=FakeClient(routes), sleep=nosleep)
        prv = one(self.conn, "SELECT dead_at, dead_misses, last_error FROM channels WHERE channel_key='prv:AAAA1111'")
        self.assertIsNone(prv["dead_at"])
        self.assertEqual(prv["dead_misses"], 1)

    async def test_legacy_window_also_reads_plain_preview_page(self):
        routes = routes_default(S_LEGACY.hashtag)
        routes[tgweb.preview_url("chana")] = (200, PREVIEW, tgweb.preview_url("chana"))
        client = FakeClient(routes)
        st = await run_public_collector(self.conn, S_LEGACY, client=client, sleep=nosleep)
        self.assertIn(tgweb.preview_url("chana"), client.calls)
        self.assertEqual((st.posts_new, st.posts_updated, st.errors), (20, 20, 0))   # same 20 posts seen on both pages
        # a failing plain page is best-effort: no error recorded
        del routes[tgweb.preview_url("chana")]
        st2 = await run_public_collector(self.conn, S_LEGACY, client=FakeClient(routes), sleep=nosleep)
        self.assertEqual(st2.errors, 0)

    async def test_no_write_transaction_held_across_network_calls(self):
        """A write transaction left open while awaiting t.me blocks the rollup job ('database is locked')."""
        routes = routes_default(S_LEGACY.hashtag)
        routes[tgweb.preview_url("chana")] = (200, PREVIEW, tgweb.preview_url("chana"))
        conn, seen = self.conn, []

        class Probe(FakeClient):
            async def get(self, url, **kw):
                seen.append((url, conn.in_transaction))
                return await super().get(url, **kw)

        await run_public_collector(conn, S_LEGACY, client=Probe(routes), sleep=nosleep)
        self.assertGreaterEqual(len(seen), 4)
        self.assertFalse(any(tx for _, tx in seen), [u for u, tx in seen if tx])

    async def test_profile_without_any_info_adds_no_snapshot(self):
        routes = routes_default()
        restricted = (FIX / "tgme_profile_restricted.html").read_text(encoding="utf-8")
        routes[tgweb.search_url("chanc")] = (200, restricted, tgweb.profile_url("chanc"))
        await run_public_collector(self.conn, S, client=FakeClient(routes), sleep=nosleep)
        chanc = one(self.conn, "SELECT id, collector, kind FROM channels WHERE channel_key='pub:chanc'")
        self.assertEqual((chanc["collector"], chanc["kind"]), ("profile", "public_no_preview"))
        self.assertEqual(one(self.conn, "SELECT COUNT(*) AS n FROM snapshots WHERE channel_id=?", (chanc["id"],))["n"], 0)

    def test_upsert_post_sets_qualifies(self):
        chid = one(self.conn, "SELECT id FROM channels WHERE channel_key='pub:chana'")["id"]
        post = {"post_id": 1, "permalink": "https://t.me/x/1", "datetime": "2026-10-25T10:00:00+00:00", "views": 5,
                "text": "โปร #PlatinumClubMM", "has_target_hashtag": True, "has_media": True, "has_link": False,
                "has_sticker": False, "is_pinned": None}
        self.assertTrue(upsert_post(self.conn, chid, post, "preview", S))
        row = one(self.conn, "SELECT * FROM posts WHERE channel_id=? AND message_id=1", (chid,))
        self.assertEqual((row["qualifies"], row["qualify_reason"], row["local_date"], row["has_tag"]), (1, "ok", "2026-10-25", 1))
        self.assertFalse(upsert_post(self.conn, chid, dict(post, views=9), "preview", S))
        self.assertEqual(one(self.conn, "SELECT views FROM posts WHERE channel_id=? AND message_id=1", (chid,))["views"], 9)

    def test_upsert_post_from_two_connections_does_not_raise(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(pathlib.Path(d) / "t.db")
            c1 = connect(path)
            migrate(c1)
            import_seed(c1, SEED)
            c2 = connect(path)
            chid = one(c1, "SELECT id FROM channels WHERE channel_key='pub:chana'")["id"]
            post = {"post_id": 7, "datetime": "2026-10-25T10:00:00+00:00", "text": "#platinumclubmm", "has_target_hashtag": True,
                    "has_media": True, "has_link": False, "has_sticker": False, "views": 1}
            self.assertTrue(upsert_post(c1, chid, post, "preview", S))
            c1.commit()
            self.assertFalse(upsert_post(c2, chid, dict(post, views=2), "preview", S))
            c2.commit()
            self.assertEqual(one(c1, "SELECT COUNT(*) AS n FROM posts")["n"], 1)
            c1.close()
            c2.close()


if __name__ == "__main__":
    unittest.main()
