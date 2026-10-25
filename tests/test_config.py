import unittest

from app.config import load_settings


class TestSettings(unittest.TestCase):
    def test_defaults(self):
        s = load_settings({})
        self.assertEqual(s.tz, "Asia/Yangon")
        self.assertEqual(s.hashtag, "#platinumclubmm")
        self.assertEqual(s.hashtag_enforced_from, "2026-11-01")
        self.assertEqual(s.db_path, "data/audit.db")
        self.assertEqual(s.dash_user, "admin")
        self.assertIsNone(s.dash_password)
        self.assertFalse(s.mtproto_enabled)
        self.assertFalse(s.alerts_enabled)
        self.assertEqual((s.fetch_delay_min, s.fetch_delay_max), (1.5, 2.5))
        self.assertEqual(s.collector_interval_min, 30)

    def test_env_overrides(self):
        s = load_settings({"TG_API_ID": "123", "TG_API_HASH": "abc", "TG_SESSION": "1aa", "BOT_TOKEN": "t",
                           "OWNER_CHAT_ID": "99", "DB_PATH": "/data/audit.db", "DASH_PASSWORD": "pw",
                           "HASHTAG_ENFORCED_FROM": "2026-12-01", "COLLECTOR_INTERVAL_MIN": "15",
                           "FETCH_DELAY_MIN": "2", "FETCH_DELAY_MAX": "3"})
        self.assertEqual(s.tg_api_id, 123)
        self.assertTrue(s.mtproto_enabled)
        self.assertTrue(s.alerts_enabled)
        self.assertEqual(s.db_path, "/data/audit.db")
        self.assertEqual(s.dash_password, "pw")
        self.assertEqual(s.hashtag_enforced_from, "2026-12-01")
        self.assertEqual(s.collector_interval_min, 15)
        self.assertEqual((s.fetch_delay_min, s.fetch_delay_max), (2.0, 3.0))

    def test_alert_langs(self):
        self.assertEqual(load_settings({}).alert_langs, ("th",))
        self.assertEqual(load_settings({"ALERT_LANGS": "my, en ,xx"}).alert_langs, ("my", "en"))
        self.assertEqual(load_settings({"ALERT_LANGS": "zz"}).alert_langs, ("th",))

    def test_partial_tg_config_is_disabled(self):
        self.assertFalse(load_settings({"TG_API_ID": "1", "TG_API_HASH": "x"}).mtproto_enabled)


if __name__ == "__main__":
    unittest.main()
