"""HTML management pages: contracts, channels, regs, lists, data, settings (server-rendered forms)."""
import datetime as dt
import json
import pathlib
import unittest
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.collector import upsert_post
from app.config import load_settings
from app.db import connect, migrate, one, all_rows
from app.importer import import_seed
from app.rollup import rollup_date
from app.web import create_app

FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "seed_small.json"
SEED = json.loads(FIX.read_text(encoding="utf-8"))
D = "2026-10-25"
AFTER = dt.datetime(2026, 10, 26, 0, 10, tzinfo=ZoneInfo("Asia/Yangon"))
POST = {"post_id": 1, "permalink": "https://t.me/ChanA/1", "datetime": "2026-10-25T10:00:00+00:00", "views": 5,
        "text": "โปร #platinumclubmm", "has_target_hashtag": True, "has_media": True, "has_link": False, "has_sticker": False}


class ManageCase(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        migrate(self.conn)
        import_seed(self.conn, SEED)
        self.client = TestClient(create_app(load_settings({}), conn=self.conn))
        self.client.get("/manage/contracts")                       # mints the csrf cookie
        self.csrf = self.client.cookies.get("csrf")
        self.assertTrue(self.csrf)

    def post(self, path, **data):
        data.setdefault("csrf", self.csrf)
        return self.client.post(path, data=data, follow_redirects=False)

    def cid(self, sheet_id="2026-10-r005"):
        return one(self.conn, "SELECT id FROM contracts WHERE sheet_contract_id=?", (sheet_id,))["id"]


class TestContracts(ManageCase):
    CREATE = dict(month="2026-10", names="New One\nNew Two", section="only_two", exclusivity="2", quota_type="daily_post",
                  quota_posts_per_day="1", pin_kind="per_month", pin_n="4", amount_mmk="250,000", period_from="2026-10-05",
                  period_to="2026-11-04", admin_accounts="@x @y", remark_raw="1 day 1 post", status="active", note="")

    def test_list_renders_and_filters(self):
        r = self.client.get("/manage/contracts?lang=en")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Chan A", r.text)
        self.assertIn("Chan B", r.text)
        r = self.client.get("/manage/contracts?q=Chan+B")
        self.assertIn("Chan B", r.text)
        self.assertNotIn("Chan A", r.text)

    def test_create_contract_via_form(self):
        r = self.post("/manage/contracts/new", **self.CREATE)
        self.assertEqual(r.status_code, 303, r.text)
        row = one(self.conn, "SELECT * FROM contracts WHERE sheet_contract_id='2026-10-m001'")
        self.assertIsNotNone(row)
        self.assertEqual(json.loads(row["names"]), ["New One", "New Two"])
        self.assertEqual(json.loads(row["admin_accounts"]), ["@x", "@y"])
        self.assertEqual((row["pin_rule"], row["amount_mmk"], row["exclusivity"], row["manual_locked"]), ("per_month:4", 250000, 2, 1))
        self.assertTrue(r.headers["location"].startswith(f"/manage/contracts/{row['id']}/edit"))
        self.assertEqual(one(self.conn, "SELECT action FROM admin_log ORDER BY id DESC LIMIT 1")["action"], "contract.create")
        self.post("/manage/contracts/new", **self.CREATE)              # second manual contract gets the next number
        self.assertIsNotNone(one(self.conn, "SELECT 1 FROM contracts WHERE sheet_contract_id='2026-10-m002'"))

    def test_create_rejects_missing_csrf_and_foreign_origin(self):
        r = self.client.post("/manage/contracts/new", data=dict(self.CREATE), follow_redirects=False)
        self.assertEqual(r.status_code, 403)
        r = self.client.post("/manage/contracts/new", data=dict(self.CREATE, csrf=self.csrf),
                             headers={"origin": "https://evil.example"}, follow_redirects=False)
        self.assertEqual(r.status_code, 403)
        self.assertIsNone(one(self.conn, "SELECT 1 FROM contracts WHERE sheet_contract_id='2026-10-m001'"))

    def test_create_validates_required_fields(self):
        r = self.post("/manage/contracts/new", **dict(self.CREATE, names="", month="bad"))
        self.assertEqual(r.status_code, 200)                           # form re-rendered with errors
        self.assertIsNone(one(self.conn, "SELECT 1 FROM contracts WHERE sheet_contract_id='2026-10-m001'"))

    def test_edit_updates_and_locks(self):
        cid = self.cid()
        r = self.client.get(f"/manage/contracts/{cid}/edit?lang=en")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Chan A", r.text)
        self.assertIn('name="csrf"', r.text)
        r = self.post(f"/manage/contracts/{cid}/edit", **dict(self.CREATE, names="Chan A", amount_mmk="123456", pin_kind="daily", status="paused"))
        self.assertEqual(r.status_code, 303, r.text)
        row = one(self.conn, "SELECT * FROM contracts WHERE id=?", (cid,))
        self.assertEqual((row["amount_mmk"], row["pin_rule"], row["status"], row["manual_locked"]), (123456, "daily", "paused", 1))
        import_seed(self.conn, SEED)                                   # the sheet no longer overwrites it
        self.assertEqual(one(self.conn, "SELECT amount_mmk FROM contracts WHERE id=?", (cid,))["amount_mmk"], 123456)

    def test_add_channel_by_url_creates_or_reuses_and_attaches(self):
        cid = self.cid()
        r = self.post(f"/manage/contracts/{cid}/channels/add", url="https://t.me/+AbCdEf123", title="Priv One")
        self.assertEqual(r.status_code, 303, r.text)
        ch = one(self.conn, "SELECT * FROM channels WHERE channel_key='prv:AbCdEf123'")
        self.assertEqual((ch["kind"], ch["collector"], ch["title"], ch["manual_locked"]), ("private", "invite", "Priv One", 1))
        self.assertIsNotNone(one(self.conn, "SELECT 1 FROM contract_channels WHERE contract_id=? AND channel_id=?", (cid, ch["id"])))
        other = self.cid("2026-10-r006")
        self.post(f"/manage/contracts/{other}/channels/add", url="t.me/+AbCdEf123", title="")
        self.assertEqual(one(self.conn, "SELECT COUNT(*) AS n FROM channels WHERE channel_key='prv:AbCdEf123'")["n"], 1)
        self.assertEqual(one(self.conn, "SELECT COUNT(*) AS n FROM contract_channels WHERE channel_id=?", (ch["id"],))["n"], 2)
        r = self.post(f"/manage/contracts/{cid}/channels/add", url="https://t.me/s/NewChan", title="")
        pub = one(self.conn, "SELECT kind, collector, username FROM channels WHERE channel_key='pub:newchan'")
        self.assertEqual((pub["kind"], pub["collector"], pub["username"]), ("public_preview", "preview", "newchan"))
        r = self.post(f"/manage/contracts/{cid}/channels/add", url="https://facebook.com/x", title="")
        self.assertEqual(r.status_code, 303)
        self.assertIn("flash=", r.headers.get("set-cookie", ""))        # rejected with a flash, not a 500

    def test_detach_channel(self):
        cid = self.cid()
        chid = one(self.conn, "SELECT id FROM channels WHERE channel_key='pub:chana'")["id"]
        r = self.post(f"/manage/contracts/{cid}/channels/{chid}/detach")
        self.assertEqual(r.status_code, 303)
        self.assertIsNone(one(self.conn, "SELECT 1 FROM contract_channels WHERE contract_id=? AND channel_id=?", (cid, chid)))
        self.assertIsNotNone(one(self.conn, "SELECT 1 FROM channels WHERE id=?", (chid,)))   # channel row kept

    def test_unknown_contract_404(self):
        self.assertEqual(self.client.get("/manage/contracts/9999/edit").status_code, 404)


class TestChannels(ManageCase):
    def chid(self, key="pub:chana"):
        return one(self.conn, "SELECT id FROM channels WHERE channel_key=?", (key,))["id"]

    def test_list_and_filters(self):
        r = self.client.get("/manage/channels?lang=en")
        self.assertEqual(r.status_code, 200)
        self.assertIn("pub:chana", r.text)
        self.conn.execute("UPDATE channels SET dead_at='2026-10-20T00:00:00+00:00', dead_misses=3 WHERE channel_key='pub:chanc'")
        self.conn.commit()
        r = self.client.get("/manage/channels?dead=1")
        self.assertIn("pub:chanc", r.text)
        self.assertNotIn("pub:chana", r.text)
        r = self.client.get("/manage/channels?q=AAAA")
        self.assertIn("prv:AAAA1111", r.text)
        self.assertNotIn("pub:chana", r.text)

    def test_new_channel_creates_and_optionally_attaches(self):
        cid = self.cid()
        r = self.post("/manage/channels/new", url="https://t.me/BrandNew", title="Brand New", contract_id=str(cid), note="hello")
        self.assertEqual(r.status_code, 303, r.text)
        ch = one(self.conn, "SELECT * FROM channels WHERE channel_key='pub:brandnew'")
        self.assertEqual((ch["title"], ch["note"], ch["manual_locked"], ch["kind"]), ("Brand New", "hello", 1, "public_preview"))
        self.assertIsNotNone(one(self.conn, "SELECT 1 FROM contract_channels WHERE contract_id=? AND channel_id=?", (cid, ch["id"])))
        self.assertTrue(r.headers["location"].startswith(f"/manage/channels/{ch['id']}/edit"))
        r = self.post("/manage/channels/new", url="@BrandNew", title="", contract_id="", note="")
        self.assertEqual(r.status_code, 303)
        self.assertEqual(one(self.conn, "SELECT COUNT(*) AS n FROM channels WHERE channel_key='pub:brandnew'")["n"], 1)
        r = self.post("/manage/channels/new", url="https://facebook.com/x", title="", contract_id="", note="")
        self.assertEqual(r.status_code, 200)                           # form re-rendered with the link error

    def test_edit_moves_link_and_keeps_alias(self):
        chid = self.chid()
        r = self.client.get(f"/manage/channels/{chid}/edit?lang=en")
        self.assertEqual(r.status_code, 200)
        self.assertIn('value="https://t.me/chana"', r.text)
        r = self.post(f"/manage/channels/{chid}/edit", url="https://t.me/ChanA_new", title="Chan A new", note="moved")
        self.assertEqual(r.status_code, 303, r.text)
        ch = one(self.conn, "SELECT * FROM channels WHERE id=?", (chid,))
        self.assertEqual((ch["channel_key"], ch["username"], ch["title"], ch["manual_locked"], ch["note"]), ("pub:chana_new", "chana_new", "Chan A new", 1, "moved"))
        self.assertIsNone(ch["last_message_id"])
        alias = one(self.conn, "SELECT * FROM channel_aliases WHERE channel_id=? ORDER BY id DESC LIMIT 1", (chid,))
        self.assertEqual((alias["old_channel_key"], alias["source"]), ("pub:chana", "manual"))
        self.assertEqual(one(self.conn, "SELECT action FROM admin_log ORDER BY id DESC LIMIT 1")["action"], "channel.update")

    def test_edit_rejects_link_collision(self):
        chid = self.chid()
        r = self.post(f"/manage/channels/{chid}/edit", url="https://t.me/ChanC", title="", note="")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(one(self.conn, "SELECT channel_key FROM channels WHERE id=?", (chid,))["channel_key"], "pub:chana")

    def test_revive_dead_channel(self):
        chid = self.chid("pub:chanc")
        self.conn.execute("UPDATE channels SET dead_at='2026-10-20T00:00:00+00:00', dead_misses=3, last_error='gone' WHERE id=?", (chid,))
        self.conn.commit()
        r = self.post(f"/manage/channels/{chid}/revive")
        self.assertEqual(r.status_code, 303)
        ch = one(self.conn, "SELECT dead_at, dead_misses, last_error FROM channels WHERE id=?", (chid,))
        self.assertEqual((ch["dead_at"], ch["dead_misses"], ch["last_error"]), (None, 0, None))
        self.assertEqual(one(self.conn, "SELECT action FROM admin_log ORDER BY id DESC LIMIT 1")["action"], "channel.revive")

    def test_unknown_channel_404(self):
        self.assertEqual(self.client.get("/manage/channels/9999/edit").status_code, 404)


if __name__ == "__main__":
    unittest.main()
