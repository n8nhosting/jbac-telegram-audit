import datetime as dt
import json
import pathlib
import unittest
from zoneinfo import ZoneInfo

from app.collector import upsert_post
from app.config import load_settings
from app.db import connect, migrate, one, all_rows
from app.importer import import_seed
from app.rollup import build_channel_days, rollup_date

SEED = json.loads((pathlib.Path(__file__).resolve().parent / "fixtures" / "seed_small.json").read_text(encoding="utf-8"))
S = load_settings({})
YGN = ZoneInfo("Asia/Yangon")
AFTER = dt.datetime(2026, 10, 26, 0, 10, tzinfo=YGN)
D = "2026-10-25"
POST = {"post_id": 1, "permalink": "https://t.me/ChanA/1", "datetime": "2026-10-25T10:00:00+00:00", "views": 5,
        "text": "โปร #platinumclubmm", "has_target_hashtag": True, "has_media": True, "has_link": False, "has_sticker": False}


class TestRollup(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        migrate(self.conn)
        import_seed(self.conn, SEED)
        self.ids = {r["channel_key"]: r["id"] for r in all_rows(self.conn, "SELECT id, channel_key FROM channels")}
        # the collector has visited both preview channels today
        self.conn.execute("UPDATE channels SET last_checked='2026-10-25T12:00:00+00:00' WHERE collector='preview'")
        self.c1 = one(self.conn, "SELECT id FROM contracts WHERE sheet_contract_id='2026-10-r005'")["id"]
        self.c2 = one(self.conn, "SELECT id FROM contracts WHERE sheet_contract_id='2026-10-r006'")["id"]

    def test_channel_days_readability(self):
        days = {d.channel_key: d for d in build_channel_days(self.conn, self.c2, D)}
        self.assertEqual(set(days), {"prv:AAAA1111", "pub:chanc"})
        self.assertFalse(days["prv:AAAA1111"].readable)
        self.assertTrue(days["pub:chanc"].readable)
        self.assertIsNone(days["pub:chanc"].pinned_today)

    def test_unchecked_preview_channel_is_not_readable(self):
        self.conn.execute("UPDATE channels SET last_checked=NULL WHERE channel_key='pub:chana'")
        days = build_channel_days(self.conn, self.c1, D)
        self.assertFalse(days[0].readable)

    def test_rollup_writes_rows_and_is_idempotent(self):
        upsert_post(self.conn, self.ids["pub:chana"], POST, "preview", S)
        self.assertEqual(rollup_date(self.conn, D, S, now_local=AFTER), 2)
        r1 = one(self.conn, "SELECT * FROM daily_rollup WHERE contract_id=? AND local_date=?", (self.c1, D))
        self.assertEqual((r1["status"], r1["required"], r1["qualified"], r1["pin_ok"]), ("ok", 1, 1, None))
        r2 = one(self.conn, "SELECT * FROM daily_rollup WHERE contract_id=? AND local_date=?", (self.c2, D))
        self.assertEqual(r2["status"], "missed")          # chanc readable but no post; the private channel alone would be unverifiable
        self.assertEqual(rollup_date(self.conn, D, S, now_local=AFTER), 2)
        self.assertEqual(one(self.conn, "SELECT COUNT(*) AS n FROM daily_rollup")["n"], 2)

    def test_rollup_unverifiable_when_readable_channels_are_fine(self):
        upsert_post(self.conn, self.ids["pub:chanc"], dict(POST, permalink="https://t.me/chanc/1"), "preview", S)
        rollup_date(self.conn, D, S, now_local=AFTER)
        self.assertEqual(one(self.conn, "SELECT status FROM daily_rollup WHERE contract_id=?", (self.c2,))["status"], "unverifiable")

    def test_pinned_today_from_pin_snapshot(self):
        upsert_post(self.conn, self.ids["pub:chana"], POST, "preview", S)
        self.conn.execute("INSERT INTO pin_snapshots(channel_id, captured_at, local_date, pinned_message_ids) VALUES(?,?,?,?)",
                          (self.ids["pub:chana"], "2026-10-25T12:00:00+00:00", D, json.dumps([1])))
        self.assertTrue(build_channel_days(self.conn, self.c1, D)[0].pinned_today)
        self.conn.execute("UPDATE pin_snapshots SET pinned_message_ids='[999]'")
        self.assertFalse(build_channel_days(self.conn, self.c1, D)[0].pinned_today)

    def test_dead_channel_flag(self):
        self.conn.execute("UPDATE channels SET dead_at='2026-10-24T00:00:00+00:00' WHERE channel_key='pub:chana'")
        self.assertTrue(build_channel_days(self.conn, self.c1, D)[0].dead)
        rollup_date(self.conn, D, S, now_local=AFTER)
        self.assertEqual(one(self.conn, "SELECT status FROM daily_rollup WHERE contract_id=?", (self.c1,))["status"], "dead")


if __name__ == "__main__":
    unittest.main()
