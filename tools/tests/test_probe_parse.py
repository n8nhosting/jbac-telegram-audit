"""Tests for tools/probe_tme.py parsers, against saved fixtures fetched 2026-10-25 (TDD: written first)."""
import sys, pathlib, unittest
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import probe_tme as pt  # noqa: E402

PREVIEW = (HERE / "fixtures" / "tgme_s_mini_drama_channel.html").read_text(encoding="utf-8")
INVITE = (HERE / "fixtures" / "tgme_invite_sample.html").read_text(encoding="utf-8")


class TestCounts(unittest.TestCase):
    def test_parse_count(self):
        for s, n in [("108K", 108000), ("29 783 subscribers", 29783), ("1.86K", 1860), ("122", 122),
                     ("4.9K", 4900), ("1.2M", 1200000), ("", None), (None, None)]:
            self.assertEqual(pt.parse_count(s), n, s)

    def test_hashtags(self):
        self.assertEqual(pt.extract_hashtags("hello #PlatinumClubMM and #d20261025 #platinumclubmm_extra"),
                         ["#platinumclubmm", "#d20261025", "#platinumclubmm_extra"])
        self.assertEqual(pt.extract_hashtags(None), [])

    def test_preview_url_detection(self):
        self.assertTrue(pt.is_preview_url("https://t.me/s/mini_drama_channel"))
        self.assertTrue(pt.is_preview_url("https://t.me/s/mini_drama_channel?before=30513"))
        self.assertFalse(pt.is_preview_url("https://t.me/mini_drama_channel"))


class TestParsePreview(unittest.TestCase):
    def setUp(self):
        self.p = pt.parse_preview(PREVIEW, "https://t.me/s/mini_drama_channel")

    def test_header(self):
        self.assertTrue(self.p["readable"])
        self.assertEqual(self.p["username"], "mini_drama_channel")
        self.assertEqual(self.p["title"], "𝗠𝗶𝗻𝗶 𝗗𝗿𝗮𝗺𝗮 𝗖𝗵𝗮𝗻𝗻𝗲𝗹")
        self.assertEqual(self.p["counters"], {"subscribers": 108000, "photos": 1860, "videos": 22600, "links": 4900})

    def test_posts(self):
        posts = self.p["posts"]
        self.assertEqual(len(posts), 20)
        first, last = posts[0], posts[-1]
        self.assertEqual(first["post_id"], 30513)
        self.assertEqual(first["permalink"], "https://t.me/Mini_Drama_Channel/30513")
        self.assertEqual(first["datetime"], "2026-10-25T07:33:04+00:00")
        self.assertEqual(first["views"], 122)
        self.assertTrue(first["has_video"])
        self.assertFalse(first["has_photo"])
        self.assertIsNone(first["is_pinned"])          # not exposed by the preview page
        self.assertEqual(last["post_id"], 30533)
        self.assertTrue(last["has_sticker"])
        self.assertFalse(last["has_media"])             # stickers are not ad media

    def test_window_summary(self):
        s = self.p["summary"]
        self.assertEqual(s["posts_in_window"], 20)
        self.assertAlmostEqual(s["window_hours"], 0.70, places=1)
        self.assertIsNone(s["posts_per_day_est"])       # window shorter than 24h -> no estimate
        self.assertEqual(s["newest_post_at"], "2026-10-25T08:15:08+00:00")
        self.assertEqual(s["posts_with_hashtag"], 0)
        self.assertEqual(self.p["before_cursor"], 30513)

    def test_no_preview_when_redirected_off_s(self):
        p = pt.parse_preview("<html><body>nothing</body></html>", "https://t.me/somegroup")
        self.assertFalse(p["readable"])
        self.assertEqual(p["reason"], "redirected_no_preview")

    def test_no_preview_when_markup_missing(self):
        p = pt.parse_preview("<html><body>nothing</body></html>", "https://t.me/s/somegroup")
        self.assertFalse(p["readable"])
        self.assertEqual(p["reason"], "no_channel_info")


class TestParseInvite(unittest.TestCase):
    def test_invite_page(self):
        i = pt.parse_invite(INVITE)
        self.assertEqual(i["title"], "Bollywood Movies🇮🇳🇮🇳")
        self.assertEqual(i["subscribers"], 29783)
        self.assertIn("@htetwaiyan20025", i["description"])
        self.assertEqual(i["action"], "Join Channel")
        self.assertTrue(i["visible"])

    def test_invite_missing(self):
        i = pt.parse_invite("<html><body>If you have Telegram, you can contact</body></html>")
        self.assertFalse(i["visible"])


PROFILE_CHANNEL = (HERE / "fixtures" / "tgme_profile_channel_nopreview.html").read_text(encoding="utf-8")
PROFILE_USER = (HERE / "fixtures" / "tgme_profile_user.html").read_text(encoding="utf-8")


class TestParseProfile(unittest.TestCase):
    """t.me/s/<u> redirected to t.me/<u>: the profile page still tells us what the username is."""

    def test_channel_with_preview_disabled(self):
        p = pt.parse_profile(PROFILE_CHANNEL)
        self.assertEqual(p["kind"], "channel_no_preview")
        self.assertEqual(p["subscribers"], 333880)
        self.assertTrue(p["title"])
        self.assertEqual(p["action"], "View in Telegram")

    def test_user_or_bot_account(self):
        p = pt.parse_profile(PROFILE_USER)
        self.assertEqual(p["kind"], "user_or_bot")
        self.assertIsNone(p["subscribers"])
        self.assertEqual(p["action"], "Send Message")

    def test_group_and_unknown(self):
        self.assertEqual(pt.parse_profile('<div class="tgme_page_title">G</div><div class="tgme_page_extra">1 234 members</div>'
                                          '<a class="tgme_action_button_new">View in Telegram</a>')["kind"], "group")
        self.assertEqual(pt.parse_profile("<html></html>")["kind"], "unknown")

    def test_restricted_channel_hidden_on_web(self):
        # real page: no title, "View in Telegram" button, "you can view posts by @x" — the channel exists but web hides it
        p = pt.parse_profile((HERE / "fixtures" / "tgme_profile_restricted.html").read_text(encoding="utf-8"))
        self.assertEqual(p["kind"], "restricted_channel")
        self.assertIsNone(p["subscribers"])

    def test_nonexistent_username_is_missing(self):
        # t.me/<u> for a username nobody owns: no title, no button, only the generic contact line
        html = '<div class="tgme_page_description">If you have Telegram, you can contact <a>@nobody</a> right away.</div>'
        self.assertEqual(pt.parse_profile(html)["kind"], "missing")

    def test_sheet_subs_pairing_by_link_position(self):
        links = [{"kind": "public", "username": "a"}, {"kind": "private", "invite_hash": "H"},
                 {"kind": "external", "url": "https://facebook.com/x"}, {"kind": "public", "username": "b"}]
        contract = {"links": links, "sub_view": {"subs": [1000, 2000, 3000]}}
        self.assertEqual(pt.sheet_subs_for(contract, "pub:b"), 3000)
        self.assertEqual(pt.sheet_subs_for(contract, "prv:H"), 2000)
        self.assertIsNone(pt.sheet_subs_for({"links": links, "sub_view": {"subs": [5]}}, "pub:b"))
        self.assertEqual(pt.sheet_subs_for({"links": links[:1], "sub_view": {"subs": [7]}}, "pub:a"), 7)
        self.assertIsNone(pt.sheet_subs_for({"links": links, "sub_view": {"subs": []}}, "pub:a"))

    def test_sync_with_seed_drops_usernames_no_longer_current(self):
        seed = {"contracts": [], "channels": [
            {"kind": "public", "username": "a", "is_old_link": False},
            {"kind": "public", "username": "stale", "is_old_link": True}]}
        rep = {"channels": [{"username": "a", "readable": True, "channel_id": "pub:a", "contract_id": "c1", "sheet_subs": []},
                            {"username": "stale", "readable": False, "channel_id": "pub:stale", "contract_id": "c1", "sheet_subs": []}],
               "invites": [], "hashtag_checks": []}
        out = pt.sync_with_seed(rep, seed)
        self.assertEqual([r["username"] for r in out["channels"]], ["a"])
        self.assertEqual(out["dropped_old_link_usernames"], ["stale"])
        self.assertEqual(out["summary"]["public_total"], 1)

    def test_repair_sheet_subs_from_seed(self):
        seed = {"contracts": [{"contract_id": "c1", "links": [{"kind": "public", "username": "a"}, {"kind": "public", "username": "b"}],
                               "sub_view": {"subs": [10, 20]}}]}
        rep = {"channels": [{"username": "b", "channel_id": "pub:b", "contract_id": "c1", "sheet_subs": [10]},
                            {"username": "zz", "channel_id": "pub:zz", "contract_id": "missing", "sheet_subs": [1]}],
               "invites": [], "hashtag_checks": []}
        out = pt.repair_sheet_subs(rep, seed)
        self.assertEqual(out["channels"][0]["sheet_subs"], [20])
        self.assertEqual(out["channels"][1]["sheet_subs"], [])

    def test_enrich_report_uses_saved_pages(self):
        import tempfile, pathlib as pl
        with tempfile.TemporaryDirectory() as d:
            raw = pl.Path(d)
            (raw / "chan_a.html").write_text(PROFILE_CHANNEL, encoding="utf-8")
            (raw / "user_b.html").write_text(PROFILE_USER, encoding="utf-8")
            rep = {"channels": [
                {"username": "chan_a", "readable": False, "reason": "redirected_no_preview", "sheet_name": "x", "live_subscribers": None, "title": None},
                {"username": "user_b", "readable": False, "reason": "redirected_no_preview", "sheet_name": "y", "live_subscribers": None, "title": None},
                {"username": "ok_c", "readable": True, "reason": None, "sheet_name": "z", "live_subscribers": 5, "title": "z"},
            ], "invites": [], "hashtag_checks": []}
            out = pt.enrich_profiles(rep, raw)
            a, b, c = out["channels"]
            self.assertEqual(a["profile_kind"], "channel_no_preview")
            self.assertEqual(a["live_subscribers"], 333880)
            self.assertEqual(b["profile_kind"], "user_or_bot")
            self.assertNotIn("profile_kind", c)
            self.assertEqual(out["summary"]["public_unreadable_by_kind"], {"channel_no_preview": 1, "user_or_bot": 1})


if __name__ == "__main__":
    unittest.main()
