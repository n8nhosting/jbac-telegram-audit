import json
import pathlib
import unittest

from app.alerts import build_summary, format_alert, maybe_send
from app.config import load_settings
from app.db import connect, migrate, one

SEED = json.loads((pathlib.Path(__file__).resolve().parent / "fixtures" / "seed_small.json").read_text(encoding="utf-8"))
D = "2026-10-25"


def _seed_rollups(conn):
    from app.importer import import_seed
    import_seed(conn, SEED)
    c1 = one(conn, "SELECT id FROM contracts WHERE sheet_contract_id='2026-10-r005'")["id"]
    c2 = one(conn, "SELECT id FROM contracts WHERE sheet_contract_id='2026-10-r006'")["id"]
    conn.execute("INSERT INTO daily_rollup(local_date, contract_id, required, qualified, pin_ok, status, notes, computed_at)"
                 " VALUES(?,?,?,?,?,?,?,?)", (D, c1, 1, 1, None, "ok", "[]", "2026-10-25T17:00:00+00:00"))
    conn.execute("INSERT INTO daily_rollup(local_date, contract_id, required, qualified, pin_ok, status, notes, computed_at)"
                 " VALUES(?,?,?,?,?,?,?,?)", (D, c2, 2, 0, None, "missed", "[]", "2026-10-25T17:00:00+00:00"))
    conn.commit()


class TestAlerts(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        migrate(self.conn)
        _seed_rollups(self.conn)

    def test_build_summary_counts(self):
        s = build_summary(self.conn, D)
        self.assertEqual((s.local_date, s.total, s.ok, s.missed, s.waiting, s.unverifiable), (D, 2, 1, 1, 0, 0))
        self.assertEqual(s.posts, 0)

    def test_format_alert_thai_contains_counts(self):
        s = build_summary(self.conn, D)
        text = format_alert(s, "summary")
        self.assertIn("2026-10-25", text)
        self.assertIn("ครบ 1", text)
        self.assertIn("ขาด 1", text)
        warn = format_alert(s, "warn")
        self.assertIn("ยังขาด", warn)

    def test_format_alert_other_languages(self):
        s = build_summary(self.conn, D)
        en = format_alert(s, "summary", lang="en")
        self.assertIn("Complete 1", en)
        self.assertIn("Missed 1", en)
        self.assertNotIn("ครบ", en)
        my = format_alert(s, "final", lang="my")
        self.assertIn("ပြည့် 1", my)
        self.assertIn("2026-10-25", my)

    async def test_maybe_send_uses_configured_languages(self):
        sent = []

        async def sender(text):
            sent.append(text)
            return True

        settings = load_settings({"ALERT_LANGS": "th,en"})
        self.assertEqual(settings.alert_langs, ("th", "en"))
        await maybe_send(self.conn, settings, D, "summary", sender=sender)
        self.assertIn("ครบ 1", sent[0])
        self.assertIn("Complete 1", sent[0])

    async def test_maybe_send_once(self):
        sent = []

        async def sender(text):
            sent.append(text)
            return True

        self.assertTrue(await maybe_send(self.conn, load_settings({}), D, "summary", sender=sender))
        self.assertFalse(await maybe_send(self.conn, load_settings({}), D, "summary", sender=sender))
        self.assertEqual(len(sent), 1)
        self.assertEqual(one(self.conn, "SELECT kind FROM alerts WHERE local_date=?", (D,))["kind"], "summary")

    async def test_maybe_send_without_bot_config_sends_nothing(self):
        self.assertFalse(await maybe_send(self.conn, load_settings({}), D, "warn"))
        self.assertIsNone(one(self.conn, "SELECT id FROM alerts"))


if __name__ == "__main__":
    unittest.main()
