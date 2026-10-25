import datetime as dt
import json
import pathlib
import unittest
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.collector import upsert_post
from app.config import load_settings
from app.db import connect, migrate, one
from app.importer import import_seed
from app.rollup import rollup_date
from app.web import create_app

FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "seed_small.json"
SEED = json.loads(FIX.read_text(encoding="utf-8"))
D = "2026-10-25"
AFTER = dt.datetime(2026, 10, 26, 0, 10, tzinfo=ZoneInfo("Asia/Yangon"))
POST = {"post_id": 1, "permalink": "https://t.me/ChanA/1", "datetime": "2026-10-25T10:00:00+00:00", "views": 5,
        "text": "โปร #platinumclubmm", "has_target_hashtag": True, "has_media": True, "has_link": False, "has_sticker": False}


def _client(settings=None, conn=None):
    conn = conn or connect(":memory:")
    migrate(conn)
    app = create_app(settings or load_settings({}), conn=conn)
    return TestClient(app), conn


class TestWeb(unittest.TestCase):
    def test_dashboard_renders_empty_db(self):
        client, _ = _client()
        r = client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("ยังไม่มีข้อมูล", r.text)

    def test_healthz(self):
        client, _ = _client()
        self.assertEqual(client.get("/healthz").json()["ok"], True)

    def test_basic_auth_required_when_password_set(self):
        client, _ = _client(load_settings({"DASH_PASSWORD": "pw"}))
        self.assertEqual(client.get("/").status_code, 401)
        self.assertEqual(client.get("/healthz").status_code, 200)
        self.assertEqual(client.get("/", auth=("admin", "pw")).status_code, 200)
        self.assertEqual(client.get("/", auth=("admin", "wrong")).status_code, 401)

    def test_import_endpoint(self):
        client, conn = _client()
        r = client.post("/admin/import", files={"seed": ("seed.json", FIX.read_bytes(), "application/json")})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["contracts"], 2)
        self.assertEqual(one(conn, "SELECT COUNT(*) AS n FROM channels")["n"], 3)

    def test_dashboard_and_api_after_rollup(self):
        client, conn = _client()
        import_seed(conn, SEED)
        conn.execute("UPDATE channels SET last_checked='2026-10-25T12:00:00+00:00' WHERE collector='preview'")
        chana = one(conn, "SELECT id FROM channels WHERE channel_key='pub:chana'")["id"]
        upsert_post(conn, chana, POST, "preview", load_settings({}))
        rollup_date(conn, D, load_settings({}), now_local=AFTER)
        r = client.get(f"/?date={D}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Chan A", r.text)
        self.assertIn("Chan B", r.text)
        s = client.get(f"/api/summary?date={D}").json()
        self.assertEqual((s["total"], s["ok"], s["missed"]), (2, 1, 1))
        rows = client.get(f"/api/contracts?date={D}").json()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["status"], "missed")          # exceptions first
        c1 = one(conn, "SELECT id FROM contracts WHERE sheet_contract_id='2026-10-r005'")["id"]
        d = client.get(f"/contracts/{c1}?date={D}")
        self.assertEqual(d.status_code, 200)
        self.assertIn("https://t.me/ChanA/1", d.text)
        csv_r = client.get(f"/export.csv?from={D}&to={D}")
        self.assertEqual(csv_r.status_code, 200)
        self.assertTrue(csv_r.headers["content-type"].startswith("text/csv"))
        self.assertTrue(csv_r.text.lstrip("﻿").splitlines()[0].startswith("local_date,contract"))   # BOM for Excel
        self.assertEqual(len(csv_r.text.strip().splitlines()), 3)

    def test_filter_by_status_and_unknown_contract(self):
        client, conn = _client()
        import_seed(conn, SEED)
        rollup_date(conn, D, load_settings({}), now_local=AFTER)
        r = client.get(f"/?date={D}&status=ok")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(client.get("/contracts/9999").status_code, 404)

    def test_openapi_and_docs_not_served(self):
        client, _ = _client()
        self.assertEqual(client.get("/openapi.json").status_code, 404)
        self.assertEqual(client.get("/docs").status_code, 404)

    def test_admin_collector_409_while_running(self):
        from app import collector
        client, _ = _client()
        collector._RUNNING = True
        try:
            self.assertEqual(client.post("/admin/run/collector").status_code, 409)
        finally:
            collector._RUNNING = False

    def test_non_ascii_password_does_not_crash(self):
        client, _ = _client(load_settings({"DASH_PASSWORD": "รหัสผ่าน"}))
        self.assertEqual(client.get("/", auth=("admin", "wrong")).status_code, 401)

    def test_language_switch_query_cookie_and_header(self):
        client, conn = _client()
        import_seed(conn, SEED)
        conn.execute("UPDATE channels SET last_checked='2026-10-25T12:00:00+00:00' WHERE collector='preview'")
        rollup_date(conn, D, load_settings({}), now_local=AFTER)
        th = client.get(f"/?date={D}")
        self.assertIn("ขาด (เลย cutoff)", th.text)
        en = client.get(f"/?date={D}&lang=en")
        self.assertIn("Missed (past cutoff)", en.text)
        self.assertNotIn("ขาด (เลย cutoff)", en.text)
        self.assertEqual(en.cookies.get("lang"), "en")
        again = client.get(f"/?date={D}")                      # cookie remembered
        self.assertIn("Missed (past cutoff)", again.text)
        my = client.get(f"/?date={D}&lang=my")
        self.assertIn("ပျက်ကွက်", my.text)
        self.assertIn('lang="my"', my.text)
        c1 = one(conn, "SELECT id FROM contracts WHERE sheet_contract_id='2026-10-r005'")["id"]
        detail = client.get(f"/contracts/{c1}?date={D}&lang=en")
        self.assertIn("Channels in contract", detail.text)
        fresh = TestClient(create_app(load_settings({}), conn=conn))
        hdr = fresh.get(f"/?date={D}", headers={"Accept-Language": "my-MM,my;q=0.9"})
        self.assertIn("ပျက်ကွက်", hdr.text)
        rows = client.get(f"/api/contracts?date={D}&lang=en").json()
        self.assertEqual(rows[0]["status_label"], "Missed")

    def test_admin_run_rollup(self):
        client, conn = _client()
        import_seed(conn, SEED)
        r = client.post(f"/admin/run/rollup?date={D}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["rows"], 2)


if __name__ == "__main__":
    unittest.main()
