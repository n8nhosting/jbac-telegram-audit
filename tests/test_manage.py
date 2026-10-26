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


class TestRegs(ManageCase):
    def test_grid_shows_months_and_seed_values(self):
        cid = self.cid()
        r = self.client.get("/manage/regs?to=2026-10&months=3&lang=en")
        self.assertEqual(r.status_code, 200)
        for month in ("2026-08", "2026-09", "2026-10"):
            self.assertIn(f'name="reg-{cid}-{month}"', r.text)
        self.assertNotIn(f'name="reg-{cid}-2026-07"', r.text)
        self.assertRegex(r.text, rf'name="reg-{cid}-2026-09"[^>]*value="2"')      # Sep reg 2 from the sheet

    def test_save_touches_only_filled_cells(self):
        cid = self.cid()
        r = self.post("/manage/regs", to="2026-10", months="3", **{f"reg-{cid}-2026-10": "7", f"reg-{cid}-2026-09": "", f"reg-{cid}-2026-08": "-"})
        self.assertEqual(r.status_code, 303, r.text)
        regs = {r["month"]: r["reg"] for r in all_rows(self.conn, "SELECT month, reg FROM reg_monthly WHERE contract_id=?", (cid,))}
        self.assertEqual(regs.get("2026-10"), 7)
        self.assertEqual(regs.get("2026-09"), 2)                      # blank = untouched
        self.assertNotIn("2026-08", regs)                              # "-" = removed
        other = self.cid("2026-10-r006")
        self.assertIsNone(one(self.conn, "SELECT 1 FROM reg_monthly WHERE contract_id=? AND month='2026-10'", (other,)))
        self.assertEqual(one(self.conn, "SELECT action FROM admin_log ORDER BY id DESC LIMIT 1")["action"], "reg.save")

    def test_save_rejects_non_numbers(self):
        cid = self.cid()
        r = self.post("/manage/regs", to="2026-10", months="3", **{f"reg-{cid}-2026-10": "abc"})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(one(self.conn, "SELECT 1 FROM reg_monthly WHERE contract_id=? AND month='2026-10'", (cid,)))


class TestLists(ManageCase):
    def test_add_stop_event_updates_contract_status(self):
        cid = self.cid()
        r = self.post("/manage/lists/add", contract_id=str(cid), event="stop", happened_at="2026-10-20", amount_mmk="", note="no reg 3 months")
        self.assertEqual(r.status_code, 303, r.text)
        ev = one(self.conn, "SELECT * FROM channel_events WHERE contract_id=? ORDER BY id DESC LIMIT 1", (cid,))
        self.assertEqual((ev["event"], ev["happened_at"][:10], ev["note"]), ("stop", "2026-10-20", "no reg 3 months"))
        c = one(self.conn, "SELECT status, manual_locked FROM contracts WHERE id=?", (cid,))
        self.assertEqual((c["status"], c["manual_locked"]), ("stopped", 1))
        self.assertEqual(one(self.conn, "SELECT action FROM admin_log ORDER BY id DESC LIMIT 1")["action"], "list.add")

    def test_refund_stores_amount_and_follow_up_keeps_status(self):
        cid = self.cid()
        self.post("/manage/lists/add", contract_id=str(cid), event="refund", happened_at="2026-10-21", amount_mmk="150,000", note="")
        ev = one(self.conn, "SELECT amount_mmk FROM channel_events WHERE contract_id=? AND event='refund'", (cid,))
        self.assertEqual(ev["amount_mmk"], 150000)
        self.assertEqual(one(self.conn, "SELECT status FROM contracts WHERE id=?", (cid,))["status"], "refund")
        other = self.cid("2026-10-r006")
        self.post("/manage/lists/add", contract_id=str(other), event="follow_up", happened_at="2026-10-21", amount_mmk="", note="ask admin")
        self.assertEqual(one(self.conn, "SELECT status FROM contracts WHERE id=?", (other,))["status"], "active")

    def test_invalid_event_or_contract_rejected(self):
        cid = self.cid()
        r = self.post("/manage/lists/add", contract_id=str(cid), event="bogus", happened_at="2026-10-20", amount_mmk="", note="")
        self.assertEqual(r.status_code, 200)
        r = self.post("/manage/lists/add", contract_id="9999", event="stop", happened_at="2026-10-20", amount_mmk="", note="")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(one(self.conn, "SELECT COUNT(*) AS n FROM channel_events")["n"], 0)

    def test_list_filters_and_delete(self):
        cid = self.cid()
        self.post("/manage/lists/add", contract_id=str(cid), event="stop", happened_at="2026-10-20", amount_mmk="", note="STOPNOTE")
        self.post("/manage/lists/add", contract_id=str(cid), event="follow_up", happened_at="2026-10-21", amount_mmk="", note="FOLLOWNOTE")
        r = self.client.get("/manage/lists?kind=stop&lang=en")
        self.assertIn("STOPNOTE", r.text)
        self.assertNotIn("FOLLOWNOTE", r.text)
        ev_id = one(self.conn, "SELECT id FROM channel_events WHERE note='FOLLOWNOTE'")["id"]
        r = self.post(f"/manage/lists/{ev_id}/delete")
        self.assertEqual(r.status_code, 303)
        self.assertIsNone(one(self.conn, "SELECT 1 FROM channel_events WHERE id=?", (ev_id,)))


class TestReports(ManageCase):
    def setUp(self):
        super().setUp()
        self.conn.execute("UPDATE channels SET last_checked='2026-10-25T12:00:00+00:00' WHERE collector='preview'")
        chana = one(self.conn, "SELECT id FROM channels WHERE channel_key='pub:chana'")["id"]
        upsert_post(self.conn, chana, POST, "preview", load_settings({}))
        rollup_date(self.conn, "2026-10-24", load_settings({}), now_local=AFTER)
        rollup_date(self.conn, "2026-10-25", load_settings({}), now_local=AFTER)

    def test_month_summary_numbers(self):
        from app.reports import month_summary
        s = month_summary(self.conn, "2026-10")
        fee = one(self.conn, "SELECT COALESCE(SUM(amount_mmk),0) AS f FROM contracts WHERE month='2026-10' AND status IN ('active','paused')")["f"]
        self.assertEqual((s["contracts"], s["fee_total"], s["days_computed"]), (2, fee, 2))
        self.assertEqual(s["ok_days"], 1)
        self.assertEqual(s["missed_days"], one(self.conn, "SELECT COUNT(*) AS n FROM daily_rollup WHERE status='missed'")["n"])
        self.assertGreaterEqual(s["channels_public"] + s["channels_private"], 3)
        self.assertEqual(month_summary(self.conn, "2025-01")["contracts"], 0)

    def test_month_grid_cells(self):
        from app.reports import month_days, month_grid
        self.assertEqual(len(month_days("2026-10")), 31)
        self.assertEqual(len(month_days("2026-02")), 28)
        rows = month_grid(self.conn, "2026-10")
        self.assertEqual(len(rows), 2)
        r005 = next(r for r in rows if r["sheet_contract_id"] == "2026-10-r005")
        self.assertEqual(len(r005["cells"]), 31)
        by_day = {c["date"]: c["status"] for c in r005["cells"]}
        self.assertEqual((by_day["2026-10-25"], by_day["2026-10-24"], by_day["2026-10-01"]), ("ok", "missed", None))
        self.assertEqual((r005["ok"], r005["missed"]), (1, 1))
        self.assertEqual(month_grid(self.conn, "2025-01"), [])

    def test_report_page_renders_and_tolerates_empty_month(self):
        r = self.client.get("/reports/month?month=2026-10&lang=en")
        self.assertEqual(r.status_code, 200)
        self.assertIn('data-day="2026-10-25"', r.text)
        self.assertIn("Chan A", r.text)
        self.assertEqual(self.client.get("/reports/month?month=2025-01").status_code, 200)
        self.assertEqual(self.client.get("/reports/month?month=garbage").status_code, 200)


class TestDataAndSettings(ManageCase):
    def test_data_page_renders(self):
        r = self.client.get("/manage/data?lang=en")
        self.assertEqual(r.status_code, 200)
        self.assertIn('enctype="multipart/form-data"', r.text)
        self.assertIn("/export.csv", r.text)

    def test_import_via_form_and_bad_json(self):
        r = self.client.post("/manage/data/import", data={"csrf": self.csrf},
                             files={"seed": ("seed.json", FIX.read_bytes(), "application/json")}, follow_redirects=False)
        self.assertEqual(r.status_code, 303, r.text)
        self.assertEqual(one(self.conn, "SELECT COUNT(*) AS n FROM runs WHERE kind='import'")["n"], 2)   # setUp import + this one
        r = self.client.post("/manage/data/import", data={"csrf": self.csrf},
                             files={"seed": ("seed.json", b"{not json", "application/json")}, follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertIn("flash=", r.headers.get("set-cookie", ""))
        self.assertEqual(one(self.conn, "SELECT COUNT(*) AS n FROM runs WHERE kind='import'")["n"], 2)

    def test_run_rollup_via_form_requires_csrf(self):
        r = self.client.post("/manage/data/run/rollup", data={"date": D}, follow_redirects=False)
        self.assertEqual(r.status_code, 403)
        r = self.post("/manage/data/run/rollup", date=D)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(one(self.conn, "SELECT COUNT(*) AS n FROM daily_rollup WHERE local_date=?", (D,))["n"], 2)
        self.assertEqual(self.post("/manage/data/run/bogus").status_code, 404)

    def test_settings_page_masks_secrets_and_shows_log(self):
        conn = connect(":memory:")
        migrate(conn)
        import_seed(conn, SEED)
        client = TestClient(create_app(load_settings({"DASH_PASSWORD": "secretpw", "BOT_TOKEN": "123:abcDEF", "OWNER_CHAT_ID": "42"}), conn=conn))
        client.get("/manage/contracts", auth=("admin", "secretpw"))
        csrf = client.cookies.get("csrf")
        cid = one(conn, "SELECT id FROM contracts WHERE sheet_contract_id='2026-10-r005'")["id"]
        client.post(f"/manage/contracts/{cid}/edit", data=dict(TestContracts.CREATE, names="Chan A", csrf=csrf), auth=("admin", "secretpw"), follow_redirects=False)
        r = client.get("/manage/settings?lang=en", auth=("admin", "secretpw"))
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("secretpw", r.text)
        self.assertNotIn("123:abcDEF", r.text)
        self.assertIn("Asia/Yangon", r.text)
        self.assertIn("contract.update", r.text)


if __name__ == "__main__":
    unittest.main()
