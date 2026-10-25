import datetime as dt
import unittest
from zoneinfo import ZoneInfo

from app.config import load_settings
from app.rules import ChannelDay, evaluate_contract_day, local_date_of, post_qualifies

S = load_settings({})
YGN = ZoneInfo("Asia/Yangon")
CONTRACT = {"quota_type": "daily_post", "quota_posts_per_day": 1, "pin_rule": "daily",
            "period_from": "2026-10-01", "period_to": "2026-10-31", "status": "active"}
AFTER = dt.datetime(2026, 10, 26, 0, 10, tzinfo=YGN)      # past the 25th's cutoff
BEFORE = dt.datetime(2026, 10, 25, 15, 0, tzinfo=YGN)
D = "2026-10-25"


def cd(key="pub:a", **kw):
    base = dict(channel_key=key, kind="public_preview", collector="preview", readable=True, qualified=1,
                posts_total=1, pinned_today=None, dead=False, renamed=False)
    base.update(kw)
    return ChannelDay(**base)


class TestLocalDate(unittest.TestCase):
    def test_local_date_yangon_boundary(self):
        self.assertEqual(local_date_of("2026-10-25T17:29:00+00:00", "Asia/Yangon"), "2026-10-25")
        self.assertEqual(local_date_of("2026-10-25T17:31:00+00:00", "Asia/Yangon"), "2026-10-26")
        self.assertEqual(local_date_of("2026-10-25T17:31:00Z", "Asia/Yangon"), "2026-10-26")


class TestPostQualifies(unittest.TestCase):
    def test_tag_and_media(self):
        self.assertEqual(post_qualifies({"has_target_hashtag": True, "has_media": True, "has_link": False, "has_sticker": False, "text": "x"}, D, S), (True, "ok"))
        self.assertEqual(post_qualifies({"has_target_hashtag": True, "has_media": False, "has_link": True, "has_sticker": False, "text": "x"}, D, S), (True, "ok"))
        self.assertEqual(post_qualifies({"has_target_hashtag": True, "has_media": False, "has_link": False, "has_sticker": False, "text": "x"}, D, S), (False, "no_media_or_link"))
        self.assertEqual(post_qualifies({"has_target_hashtag": False, "has_media": True, "has_link": False, "has_sticker": False, "text": "hello"}, "2026-11-05", S), (False, "no_tag"))

    def test_sticker_never_qualifies(self):
        self.assertEqual(post_qualifies({"has_target_hashtag": True, "has_media": False, "has_link": False, "has_sticker": True, "text": None}, D, S), (False, "sticker"))

    def test_legacy_platinum_before_enforcement(self):
        p = {"has_target_hashtag": False, "has_media": True, "has_link": False, "has_sticker": False, "text": "Platinum Club MM โปรโมชั่น"}
        self.assertEqual(post_qualifies(p, "2026-10-25", S), (True, "legacy_match"))
        self.assertEqual(post_qualifies(p, "2026-11-01", S), (False, "no_tag"))


class TestEvaluateContractDay(unittest.TestCase):
    def test_ok_when_all_channels_meet_quota(self):
        v = evaluate_contract_day(CONTRACT, [cd("pub:a"), cd("pub:b")], AFTER, D, S)
        self.assertEqual((v.status, v.required, v.qualified, v.pin_ok), ("ok", 2, 2, None))

    def test_all_channels_must_meet_quota(self):
        v = evaluate_contract_day(CONTRACT, [cd("pub:a"), cd("pub:b", qualified=0, posts_total=0)], AFTER, D, S)
        self.assertEqual((v.status, v.required, v.qualified), ("missed", 2, 1))

    def test_waiting_before_cutoff_missed_after(self):
        days = [cd(qualified=0, posts_total=0)]
        self.assertEqual(evaluate_contract_day(CONTRACT, days, BEFORE, D, S).status, "waiting")
        self.assertEqual(evaluate_contract_day(CONTRACT, days, AFTER, D, S).status, "missed")

    def test_invalid_when_posted_without_passing(self):
        v = evaluate_contract_day(CONTRACT, [cd(qualified=0, posts_total=3)], AFTER, D, S)
        self.assertEqual(v.status, "invalid")

    def test_private_without_mtproto_is_unverifiable(self):
        days = [cd("prv:H", kind="private", collector="invite", readable=False, qualified=0, posts_total=0)]
        self.assertEqual(evaluate_contract_day(CONTRACT, days, AFTER, D, S).status, "unverifiable")
        # a readable channel that is fine does not rescue the unverifiable one
        days2 = [cd("pub:a"), cd("prv:H", kind="private", collector="invite", readable=False, qualified=0, posts_total=0)]
        self.assertEqual(evaluate_contract_day(CONTRACT, days2, AFTER, D, S).status, "unverifiable")
        # but a readable channel that missed makes the contract missed, not unverifiable
        days3 = [cd("pub:a", qualified=0, posts_total=0), cd("prv:H", kind="private", collector="invite", readable=False, qualified=0, posts_total=0)]
        v3 = evaluate_contract_day(CONTRACT, days3, AFTER, D, S)
        self.assertEqual(v3.status, "missed")
        self.assertTrue(any("prv:H" in n for n in v3.notes), v3.notes)   # the unreadable channel is still named

    def test_pin_missing_only_with_pin_data(self):
        self.assertEqual(evaluate_contract_day(CONTRACT, [cd(pinned_today=False)], AFTER, D, S).status, "pin_missing")
        v = evaluate_contract_day(CONTRACT, [cd(pinned_today=True)], AFTER, D, S)
        self.assertEqual((v.status, v.pin_ok), ("ok", True))
        self.assertIsNone(evaluate_contract_day(CONTRACT, [cd(pinned_today=None)], AFTER, D, S).pin_ok)
        monthly = dict(CONTRACT, pin_rule="per_month:4")
        self.assertIsNone(evaluate_contract_day(monthly, [cd(pinned_today=False)], AFTER, D, S).pin_ok)

    def test_custom_quota_is_manual(self):
        self.assertEqual(evaluate_contract_day(dict(CONTRACT, quota_type="custom", quota_posts_per_day=None), [cd()], AFTER, D, S).status, "manual")

    def test_paused_outside_period_or_inactive(self):
        self.assertEqual(evaluate_contract_day(CONTRACT, [cd()], AFTER, "2026-11-03", S).status, "paused")
        self.assertEqual(evaluate_contract_day(dict(CONTRACT, status="stopped"), [cd()], AFTER, D, S).status, "paused")

    def test_dead_channel(self):
        self.assertEqual(evaluate_contract_day(CONTRACT, [cd(dead=True, readable=False, qualified=0, posts_total=0)], AFTER, D, S).status, "dead")

    def test_no_channels_is_unverifiable(self):
        self.assertEqual(evaluate_contract_day(CONTRACT, [], AFTER, D, S).status, "unverifiable")


if __name__ == "__main__":
    unittest.main()
