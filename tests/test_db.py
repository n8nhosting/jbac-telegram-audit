import unittest

from app.db import connect, migrate, now_utc

EXPECTED = {"contracts", "channels", "contract_channels", "channel_aliases", "posts", "pin_snapshots", "snapshots",
            "post_view_snapshots", "daily_rollup", "reg_monthly", "price_history", "channel_events", "alerts", "runs",
            "schema_migrations"}


class TestDb(unittest.TestCase):
    def test_migrate_creates_tables(self):
        conn = connect(":memory:")
        migrate(conn)
        names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue(EXPECTED <= names, EXPECTED - names)
        self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_migrate_is_idempotent(self):
        conn = connect(":memory:")
        migrate(conn)
        migrate(conn)
        rows = conn.execute("SELECT name FROM schema_migrations ORDER BY name").fetchall()
        self.assertEqual([r["name"] for r in rows], ["0001_init.sql"])

    def test_channels_unique_key_and_collector_check(self):
        conn = connect(":memory:")
        migrate(conn)
        conn.execute("INSERT INTO channels(channel_key, kind, collector) VALUES ('pub:a', 'public_preview', 'preview')")
        with self.assertRaises(Exception):
            conn.execute("INSERT INTO channels(channel_key, kind, collector) VALUES ('pub:a', 'public_preview', 'preview')")
        with self.assertRaises(Exception):
            conn.execute("INSERT INTO channels(channel_key, kind, collector) VALUES ('pub:b', 'public_preview', 'bogus')")

    def test_now_utc_is_iso_z(self):
        self.assertRegex(now_utc(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")


if __name__ == "__main__":
    unittest.main()
