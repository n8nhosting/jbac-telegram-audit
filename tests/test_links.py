"""t.me URL classifier used by the "add channel" forms (same shapes the Excel extractor understands)."""
import unittest

from app.links import channel_key_for, classify_url


class TestClassifyUrl(unittest.TestCase):
    def test_invite_link_is_private(self):
        info = classify_url("https://t.me/+oe7X-ebBNxk2MmFl")
        self.assertEqual((info["kind"], info["invite_hash"], info["username"]), ("private", "oe7X-ebBNxk2MmFl", None))
        self.assertEqual(info["url"], "https://t.me/+oe7X-ebBNxk2MmFl")
        self.assertEqual(classify_url("https://t.me/joinchat/AAAAbbb")["invite_hash"], "AAAAbbb")

    def test_public_shapes_normalise_to_lowercase_username(self):
        for raw in ("https://t.me/s/MM_TV?q=x", "t.me/MM_TV/123", "@MM_TV", "MM_TV", "https://www.t.me/MM_TV"):
            info = classify_url(raw)
            self.assertEqual((info["kind"], info["username"]), ("public", "mm_tv"), raw)
            self.assertEqual(info["url"], "https://t.me/MM_TV", raw)
        self.assertEqual(classify_url("t.me/MM_TV/123")["sample_post_id"], 123)

    def test_private_permalink_external_and_junk(self):
        self.assertEqual(classify_url("https://t.me/c/12345/6")["kind"], "private")
        self.assertIsNone(classify_url("https://t.me/c/12345/6")["invite_hash"])
        self.assertEqual(classify_url("https://facebook.com/x")["kind"], "external")
        self.assertEqual(classify_url("https://t.me/ab")["kind"], "other")
        self.assertEqual(classify_url("")["kind"], "other")

    def test_channel_key(self):
        self.assertEqual(channel_key_for(classify_url("https://t.me/ChanA")), "pub:chana")
        self.assertEqual(channel_key_for(classify_url("https://t.me/+AbC")), "prv:AbC")
        self.assertIsNone(channel_key_for(classify_url("https://t.me/c/1/2")))
        self.assertIsNone(channel_key_for(classify_url("https://x.com/y")))


if __name__ == "__main__":
    unittest.main()
