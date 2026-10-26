"""UI helpers and rendered-page checks for the redesigned dashboard."""
import datetime as dt
import json
import pathlib
import re
import unittest
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.collector import upsert_post
from app.config import load_settings
from app.db import connect, migrate, one
from app.i18n import LANGS, STRINGS, t
from app.importer import import_seed
from app.rollup import rollup_date
from app.rules import local_ts
from app.web import create_app, cutoff_info, notes_digest, group_of

FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "seed_small.json"
SEED = json.loads(FIX.read_text(encoding="utf-8"))
D = "2026-10-25"
TZ = ZoneInfo("Asia/Yangon")
AFTER = dt.datetime(2026, 10, 26, 0, 10, tzinfo=TZ)
POST = {"post_id": 1, "permalink": "https://t.me/ChanA/1", "datetime": "2026-10-25T10:00:00+00:00", "views": 5,
        "text": "โปร #platinumclubmm", "has_target_hashtag": True, "has_media": True, "has_link": False, "has_sticker": False}
# an untranslated key shows up as bare text like "row.view"; CSS selectors such as ".kpi.ok" are excluded by the lookbehind
RAW_KEY = re.compile(r"(?<![.\w-])(?:row|kpi|hero|group|nav|th|c|meta|status|pin|empty|footer)\.[a-z_]+\b")


def _client(conn=None):
    conn = conn or connect(":memory:")
    migrate(conn)
    return TestClient(create_app(load_settings({}), conn=conn)), conn


class TestCutoffInfo(unittest.TestCase):
    def test_open_day_counts_down_to_2359(self):
        now = dt.datetime(2026, 10, 26, 14, 32, tzinfo=TZ)
        self.assertEqual(cutoff_info("2026-10-26", now), {"state": "open", "hours": 9, "minutes": 27})

    def test_past_day_is_closed_and_future_day_is_future(self):
        now = dt.datetime(2026, 10, 26, 14, 32, tzinfo=TZ)
        self.assertEqual(cutoff_info("2026-10-25", now)["state"], "closed")
        self.assertEqual(cutoff_info("2026-10-27", now)["state"], "future")

    def test_last_minute_of_day_is_still_open_with_zero_left(self):
        now = dt.datetime(2026, 10, 26, 23, 59, 30, tzinfo=TZ)
        self.assertEqual(cutoff_info("2026-10-26", now), {"state": "open", "hours": 0, "minutes": 0})


class TestNotesDigest(unittest.TestCase):
    def test_unreadable_channels_are_counted_not_listed(self):
        obj = {"notes": ["prv:abc (invite): not readable", "pub:x (profile): not readable"],
               "channels": [{"channel_key": "prv:abc", "readable": False}, {"channel_key": "pub:x", "readable": False}]}
        self.assertEqual(notes_digest(obj, "en"), "2 channels not readable yet")
        self.assertNotIn("prv:abc", notes_digest(obj, "th"))

    def test_short_channels_keep_counts_and_name(self):
        obj = {"notes": ["pub:chana: 0/1"], "channels": [{"channel_key": "pub:chana", "readable": True, "qualified": 0}]}
        self.assertEqual(notes_digest(obj, "en"), "chana 0/1")

    def test_dead_channel_note_uses_status_label_not_raw_suffix(self):
        obj = {"notes": ["prv:xnjQYYLAJJRlZDZ: dead"], "channels": [{"channel_key": "prv:xnjQYYLAJJRlZDZ", "dead": True}]}
        self.assertEqual(notes_digest(obj, "en"), "xnjQYYLAJJRlZDZ: Dead channel")
        self.assertEqual(notes_digest(obj, "th"), "xnjQYYLAJJRlZDZ: ช่องตาย")

    def test_other_notes_pass_through_and_empty_is_empty(self):
        self.assertEqual(notes_digest({"notes": ["custom quota — check by hand"], "channels": []}, "en"), "custom quota — check by hand")
        self.assertEqual(notes_digest({"notes": [], "channels": []}, "en"), "")
        self.assertEqual(notes_digest(None, "en"), "")


class TestGroups(unittest.TestCase):
    def test_statuses_map_to_severity_bands(self):
        self.assertEqual([group_of(s) for s in ("missed", "invalid", "pin_missing", "dead")], ["action"] * 4)
        self.assertEqual(group_of("unverifiable"), "unverifiable")
        self.assertEqual(group_of("waiting"), "waiting")
        self.assertEqual(group_of("ok"), "ok")
        self.assertEqual([group_of(s) for s in ("paused", "manual", None)], ["other"] * 3)


class TestRenderedPages(unittest.TestCase):
    def setUp(self):
        self.client, self.conn = _client()
        import_seed(self.conn, SEED)
        self.conn.execute("UPDATE channels SET last_checked='2026-10-25T12:00:00+00:00' WHERE collector='preview'")
        chana = one(self.conn, "SELECT id FROM channels WHERE channel_key='pub:chana'")["id"]
        upsert_post(self.conn, chana, POST, "preview", load_settings({}))
        rollup_date(self.conn, D, load_settings({}), now_local=AFTER)

    def test_no_untranslated_keys_leak_into_pages(self):
        c1 = one(self.conn, "SELECT id FROM contracts WHERE sheet_contract_id='2026-10-r005'")["id"]
        ch = one(self.conn, "SELECT id FROM channels WHERE channel_key='pub:chana'")["id"]
        pages = [f"/?date={D}", f"/contracts/{c1}?date={D}", "/manage/contracts", "/manage/contracts/new", f"/manage/contracts/{c1}/edit",
                 "/manage/channels", "/manage/channels/new", f"/manage/channels/{ch}/edit", "/manage/regs?to=2026-10&months=3",
                 "/manage/lists", "/reports/month?month=2026-10", "/manage/data", "/manage/settings"]
        for lang in LANGS:
            for page in pages:
                r = self.client.get(f"{page}{'&' if '?' in page else '?'}lang={lang}")
                self.assertEqual(r.status_code, 200, (lang, page))
                self.assertIsNone(RAW_KEY.search(r.text), (lang, page, RAW_KEY.search(r.text)))

    def test_overview_has_hero_bands_and_status_glyphs(self):
        html = self.client.get(f"/?date={D}&lang=en").text
        self.assertIn('class="hero', html)
        self.assertIn("Needs action", html)
        self.assertIn('data-band="action"', html)
        self.assertIn('data-band="ok"', html)
        self.assertIn("<svg", html)
        self.assertNotIn("✅", html)

    def test_favicon_served(self):
        r = self.client.get("/favicon.ico")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.headers["content-type"].startswith("image/svg+xml"))

    def test_every_new_key_has_three_languages(self):
        for key in ("row.view", "hero.needs_action", "hero.cutoff_left", "hero.cutoff_closed", "group.action", "row.unreadable"):
            self.assertIn(key, STRINGS, key)
            for lang in LANGS:
                self.assertTrue(STRINGS[key].get(lang), (key, lang))
        self.assertEqual(t("en", "hero.cutoff_left", h=9, m=27, tz="Asia/Yangon"), "9 h 27 min to cutoff 23:59 Asia/Yangon")


class TestLocalTs(unittest.TestCase):
    """Every timestamp the UI shows is converted from the stored UTC value to the audit timezone."""

    def test_utc_iso_string_to_yangon(self):
        self.assertEqual(local_ts("2026-10-26T18:28:00+00:00", "Asia/Yangon"), "2026-10-27 00:58")

    def test_naive_string_is_treated_as_utc(self):
        self.assertEqual(local_ts("2026-10-26T18:28:00", "Asia/Yangon"), "2026-10-27 00:58")

    def test_aware_datetime_and_custom_format(self):
        d = dt.datetime(2026, 10, 26, 18, 40, tzinfo=dt.timezone.utc)
        self.assertEqual(local_ts(d, "Asia/Yangon"), "2026-10-27 01:10")
        self.assertEqual(local_ts(d, "Asia/Yangon", "%H:%M"), "01:10")

    def test_date_only_and_empty_values_pass_through(self):
        self.assertEqual(local_ts("2026-10-05", "Asia/Yangon"), "2026-10-05")      # a calendar day has no clock to shift
        self.assertEqual(local_ts(None, "Asia/Yangon"), "—")
        self.assertEqual(local_ts("", "Asia/Yangon"), "—")
        self.assertEqual(local_ts("garbage", "Asia/Yangon"), "garbage")


if __name__ == "__main__":
    unittest.main()
