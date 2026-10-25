import re
import unittest

from app.i18n import LANGS, STRINGS, pin_label, resolve_lang, status_label, t

THAI = re.compile(r"[฀-๿]")
MYANMAR = re.compile(r"[က-႟]")


class TestStrings(unittest.TestCase):
    def test_languages(self):
        self.assertEqual(LANGS, ("th", "en", "my"))

    def test_every_key_has_all_three_languages(self):
        missing = [(k, lang) for k, v in STRINGS.items() for lang in LANGS if not v.get(lang)]
        self.assertEqual(missing, [])

    def test_translations_are_in_their_script(self):
        self.assertEqual(t("th", "status.ok"), "ครบ")
        self.assertEqual(t("en", "status.ok"), "Complete")
        self.assertTrue(MYANMAR.search(t("my", "status.ok")))
        self.assertFalse(THAI.search(t("en", "kpi.missed")))
        self.assertTrue(MYANMAR.search(t("my", "kpi.missed")))

    def test_format_arguments(self):
        self.assertEqual(t("en", "meta.contracts", n=87), "87 contracts")
        self.assertEqual(t("th", "row.channels", n=3), "3 ช่อง")

    def test_unknown_key_falls_back_to_key(self):
        self.assertEqual(t("en", "nope.key"), "nope.key")

    def test_status_and_pin_labels(self):
        self.assertEqual(status_label("en", "missed"), "Missed")
        self.assertEqual(status_label("th", None), "ยังไม่ประมวลผล")
        self.assertEqual(status_label("en", "weird"), "weird")
        self.assertEqual(pin_label("en", "daily"), "pin daily")
        self.assertEqual(pin_label("en", "per_month:4"), "pin 4×/month")
        self.assertEqual(pin_label("th", "every_days:3"), "pin ทุก 3 วัน")
        self.assertTrue(MYANMAR.search(pin_label("my", "none")))


class TestResolveLang(unittest.TestCase):
    def test_query_then_cookie_then_header_then_default(self):
        self.assertEqual(resolve_lang("en", "my", "th"), "en")
        self.assertEqual(resolve_lang(None, "my", "en-US"), "my")
        self.assertEqual(resolve_lang(None, None, "my-MM,en;q=0.8"), "my")
        self.assertEqual(resolve_lang(None, None, "en-US,en;q=0.9"), "en")
        self.assertEqual(resolve_lang(None, None, "fr-FR"), "th")
        self.assertEqual(resolve_lang(None, None, None), "th")

    def test_invalid_values_are_ignored(self):
        self.assertEqual(resolve_lang("xx", "yy", None), "th")
        self.assertEqual(resolve_lang("EN", None, None), "en")


if __name__ == "__main__":
    unittest.main()
