"""App shell shared by every page: sidebar, topbar, theme toggle, logout."""
import datetime as dt
import json
import pathlib
import re
import unittest
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.config import load_settings
from app.db import connect, migrate, one
from app.importer import import_seed
from app.rollup import rollup_date
from app.web import create_app

FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "seed_small.json"
SEED = json.loads(FIX.read_text(encoding="utf-8"))
D = "2026-10-25"
AFTER = dt.datetime(2026, 10, 26, 0, 10, tzinfo=ZoneInfo("Asia/Yangon"))


def _client(settings=None):
    conn = connect(":memory:")
    migrate(conn)
    return TestClient(create_app(settings or load_settings({}), conn=conn)), conn


class TestShell(unittest.TestCase):
    def test_sidebar_marks_dashboard_active_and_topbar_has_controls(self):
        client, _ = _client()
        html = client.get("/").text
        self.assertIn('class="sidebar"', html)
        self.assertRegex(html, r'<a[^>]*data-nav="dashboard"[^>]*class="sbitem on"')
        self.assertRegex(html, r'<a[^>]*data-nav="contracts"[^>]*class="sbitem"')
        self.assertIn('id="themeBtn"', html)
        self.assertIn("adm_theme", html)
        self.assertIn('class="langs"', html)
        self.assertIn('href="/logout"', html)

    def test_contract_detail_keeps_dashboard_nav_active(self):
        client, conn = _client()
        import_seed(conn, SEED)
        c1 = one(conn, "SELECT id FROM contracts WHERE sheet_contract_id='2026-10-r005'")["id"]
        html = client.get(f"/contracts/{c1}").text
        self.assertRegex(html, r'<a[^>]*data-nav="dashboard"[^>]*class="sbitem on"')

    def test_logout_clears_basic_auth_by_answering_401(self):
        client, _ = _client(load_settings({"DASH_PASSWORD": "pw"}))
        r = client.get("/logout", auth=("admin", "pw"))
        self.assertEqual(r.status_code, 401)
        self.assertIn("WWW-Authenticate", r.headers)

    def test_dashboard_has_gradient_kpi_tiles(self):
        client, conn = _client()
        import_seed(conn, SEED)
        rollup_date(conn, D, load_settings({}), now_local=AFTER)
        html = client.get(f"/?date={D}&lang=en").text
        self.assertGreaterEqual(len(re.findall(r'class="kpi ', html)), 5)
        self.assertIn("Needs action", html)
        self.assertIn('class="bar"', html)          # the band bar survives under the tiles


if __name__ == "__main__":
    unittest.main()
