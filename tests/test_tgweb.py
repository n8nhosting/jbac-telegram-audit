import pathlib
import unittest

import httpx

from app import tgweb

FIX = pathlib.Path(__file__).resolve().parents[1] / "tools" / "tests" / "fixtures"


class TestUrls(unittest.TestCase):
    def test_urls(self):
        self.assertEqual(tgweb.search_url("Mini_Drama_Channel"), "https://t.me/s/Mini_Drama_Channel?q=%23platinumclubmm")
        self.assertEqual(tgweb.search_url("x", "#OtherTag"), "https://t.me/s/x?q=%23othertag")
        self.assertEqual(tgweb.preview_url("x"), "https://t.me/s/x")
        self.assertEqual(tgweb.profile_url("x"), "https://t.me/x")
        self.assertEqual(tgweb.invite_url("AbC-1"), "https://t.me/+AbC-1")


class TestParsersStillWork(unittest.TestCase):
    def test_parse_preview_fixture(self):
        html = (FIX / "tgme_s_mini_drama_channel.html").read_text(encoding="utf-8")
        p = tgweb.parse_preview(html, "https://t.me/s/mini_drama_channel")
        self.assertTrue(p["readable"])
        self.assertEqual(len(p["posts"]), 20)
        self.assertEqual(p["counters"]["subscribers"], 108000)
        self.assertEqual(p["posts"][0]["permalink"], "https://t.me/Mini_Drama_Channel/30513")

    def test_parse_profile_and_invite_fixtures(self):
        self.assertEqual(tgweb.parse_profile((FIX / "tgme_profile_user.html").read_text(encoding="utf-8"))["kind"], "user_or_bot")
        self.assertEqual(tgweb.parse_invite((FIX / "tgme_invite_sample.html").read_text(encoding="utf-8"))["subscribers"], 29783)


class _Resp:
    def __init__(self, status, text, url):
        self.status_code, self.text, self.url = status, text, url


class TestFetch(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_text_retries_429_then_ok(self):
        calls, sleeps = [], []

        class C:
            async def get(self, url, **kw):
                calls.append(url)
                return _Resp(429, "", url) if len(calls) == 1 else _Resp(200, "<html>ok</html>", url)

        async def fake_sleep(s):
            sleeps.append(s)

        r = await tgweb.fetch_text(C(), "https://t.me/s/x", retries=2, sleep=fake_sleep)
        self.assertTrue(r.ok)
        self.assertEqual((r.status, r.final_url, r.html), (200, "https://t.me/s/x", "<html>ok</html>"))
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(sleeps), 1)

    async def test_fetch_text_gives_up_on_network_error(self):
        class C:
            async def get(self, url, **kw):
                raise httpx.ConnectError("boom")

        async def fake_sleep(s):
            pass

        r = await tgweb.fetch_text(C(), "https://t.me/s/x", retries=1, sleep=fake_sleep)
        self.assertFalse(r.ok)
        self.assertIsNone(r.status)
        self.assertIn("boom", r.error)

    async def test_fetch_text_404_is_not_ok_but_no_retry(self):
        calls = []

        class C:
            async def get(self, url, **kw):
                calls.append(url)
                return _Resp(404, "nope", url)

        async def fake_sleep(s):
            pass

        r = await tgweb.fetch_text(C(), "https://t.me/s/x", retries=3, sleep=fake_sleep)
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "http_404")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
