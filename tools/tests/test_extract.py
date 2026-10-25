"""Tests for tools/extract_channels.py parsers (TDD: written before implementation)."""
import sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import extract_channels as ex  # noqa: E402


class TestParseReg(unittest.TestCase):
    def test_standard_four_months(self):
        self.assertEqual(
            ex.parse_reg("Sep Reg -2 / Aug Reg -2 / July Reg-0 / June Reg-1"),
            [{"month": "Sep", "reg": 2}, {"month": "Aug", "reg": 2},
             {"month": "July", "reg": 0}, {"month": "June", "reg": 1}])

    def test_irregular_spacing_and_lowercase(self):
        self.assertEqual(
            ex.parse_reg("Oct Reg  - 0 / Sep reg   -6 / Aug reg   -11 / July Reg  -21"),
            [{"month": "Oct", "reg": 0}, {"month": "Sep", "reg": 6},
             {"month": "Aug", "reg": 11}, {"month": "July", "reg": 21}])

    def test_typo_rug(self):
        out = ex.parse_reg("Oct Reg -1 / Sep Reg -1 / Aug Rug -0 / July Reg-2")
        self.assertIn({"month": "Aug", "reg": 0}, out)
        self.assertEqual(len(out), 4)

    def test_empty(self):
        self.assertEqual(ex.parse_reg(""), [])
        self.assertEqual(ex.parse_reg(None), [])


class TestParseStreak(unittest.TestCase):
    def test_ordinals(self):
        self.assertEqual(ex.parse_streak("33th time continue"), 33)
        self.assertEqual(ex.parse_streak("3rd time continue"), 3)
        self.assertEqual(ex.parse_streak("21th  time continue"), 21)
        self.assertEqual(ex.parse_streak("17th time continue န"), 17)

    def test_missing(self):
        self.assertIsNone(ex.parse_streak(""))
        self.assertIsNone(ex.parse_streak(None))


class TestParsePeriod(unittest.TestCase):
    def test_same_month(self):
        p = ex.parse_period("1.10.26 - 31.10.26")
        self.assertEqual((p["from"], p["to"]), ("2026-10-01", "2026-10-31"))
        self.assertEqual(p["flags"], [])

    def test_cross_year(self):
        p = ex.parse_period("21.10.25 - 31.10.26")
        self.assertEqual((p["from"], p["to"]), ("2025-10-21", "2026-10-31"))

    def test_start_date_only(self):
        p = ex.parse_period("29.6.26 (start date)")
        self.assertEqual(p["from"], "2026-06-29")
        self.assertIsNone(p["to"])
        self.assertIn("open_ended", p["flags"])

    def test_invalid_day(self):
        p = ex.parse_period("8.10.26- 31.11.26")
        self.assertEqual(p["from"], "2026-10-08")
        self.assertIsNone(p["to"])
        self.assertTrue(any(f.startswith("invalid_date") for f in p["flags"]))

    def test_trailing_junk(self):
        p = ex.parse_period("10.10.26 - 10.11.26  / ")
        self.assertEqual((p["from"], p["to"]), ("2026-10-10", "2026-11-10"))

    def test_unparsed(self):
        p = ex.parse_period("telebet owner channelမ")
        self.assertEqual((p["from"], p["to"]), (None, None))
        self.assertIn("unparsed", p["flags"])


class TestParseRemark(unittest.TestCase):
    def test_daily_pin_only_us(self):
        r = ex.parse_remark("1 day 1 post / pin daily  / only us /")
        self.assertEqual(r, {"quota_type": "daily_post", "quota_posts_per_day": 1,
                             "pin_rule": "daily", "exclusivity": 1})

    def test_monthly_pins_compact(self):
        r = ex.parse_remark("1day 1post / 1 month 4 pin / only us")
        self.assertEqual(r["quota_posts_per_day"], 1)
        self.assertEqual(r["pin_rule"], "per_month:4")

    def test_every_three_days(self):
        self.assertEqual(ex.parse_remark("1day 1post / three day a pin one time / only us")["pin_rule"],
                         "every_days:3")

    def test_only_three_with_one_pin(self):
        r = ex.parse_remark("1 day 1 post / 1 month 1 pin  / only three /")
        self.assertEqual((r["pin_rule"], r["exclusivity"]), ("per_month:1", 3))

    def test_only_five_capital_daily(self):
        r = ex.parse_remark("1 day 1 post  / pin Daily  / only five")
        self.assertEqual((r["pin_rule"], r["exclusivity"]), ("daily", 5))

    def test_typo_thtee(self):
        self.assertEqual(ex.parse_remark("1 day 1 post / pin daily / only thtee")["exclusivity"], 3)

    def test_burmese_note_after_exclusivity(self):
        r = ex.parse_remark("1day 1post / Pin daily  / only two (2D ကြေငြာလေးတွေတော့ရှိပါတယ်တဲ့ရှင့် အမ)")
        self.assertEqual(r["exclusivity"], 2)

    def test_custom_influencer(self):
        r = ex.parse_remark("tiktoker / Tiktok bio + photo post + telegram channel project")
        self.assertEqual(r["quota_type"], "custom")
        self.assertIsNone(r["quota_posts_per_day"])
        self.assertEqual(r["pin_rule"], "none")
        self.assertIsNone(r["exclusivity"])

    def test_empty(self):
        self.assertEqual(ex.parse_remark(None)["quota_type"], "unknown")


class TestExtractLinks(unittest.TestCase):
    def test_public_with_junk_hyperlink_dedupes(self):
        links = ex.extract_links("https://t.me/MM_TV_SERIES_CHANNEL95MK",
                                 "https://t.me/MM_TV_SERIES_CHANNEL95MK(old")
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["kind"], "public")
        self.assertEqual(links[0]["username"], "mm_tv_series_channel95mk")

    def test_public_post_link(self):
        l = ex.extract_links("https://t.me/channel_k_movie2/8847")[0]
        self.assertEqual((l["kind"], l["username"], l["sample_post_id"]), ("public", "channel_k_movie2", 8847))
        self.assertEqual(l["url"], "https://t.me/channel_k_movie2")

    def test_private_invite(self):
        l = ex.extract_links("https://t.me/+SAMPLEinviteHASH")[0]
        self.assertEqual((l["kind"], l["invite_hash"]), ("private", "SAMPLEinviteHASH"))
        self.assertIsNone(l["username"])

    def test_private_invite_leading_dash(self):
        l = ex.extract_links("https://t.me/+-DSRBu_wwYsxYmY1")[0]
        self.assertEqual(l["invite_hash"], "-DSRBu_wwYsxYmY1")

    def test_mixed_multi(self):
        links = ex.extract_links("https://t.me/slmoviegood  / https://t.me/+q5NEua606tJmNmU1 / https://t.me/other")
        self.assertEqual([l["kind"] for l in links], ["public", "private", "public"])

    def test_c_links_are_private(self):
        self.assertEqual(ex.extract_links("https://t.me/c/1234567890/55")[0]["kind"], "private")

    def test_external_trimmed(self):
        l = ex.extract_links("https://www.tiktok.com/@papa1065?_r=1&_t=ZS-993mo0vfghu )")[0]
        self.assertEqual(l["kind"], "external")
        self.assertFalse(l["url"].endswith(")"))

    def test_hyperlink_target_adds_missing_link(self):
        links = ex.extract_links(" / https://t.me/+1nnrUyUNHHFhNWRl / https://t.me/+9Nyi1vvKh1M3OGVl  /",
                                 "https://t.me/+ZnK7DPZp9y1iNGQ1")
        self.assertEqual(len(links), 3)
        self.assertTrue(all(l["kind"] == "private" for l in links))

    def test_empty(self):
        self.assertEqual(ex.extract_links(None, None), [])


class TestParseK(unittest.TestCase):
    def test_values(self):
        for s, n in [("5.7K", 5700), ("829", 829), ("30k", 30000), ("1.4K", 1400),
                     ("346K", 346000), ("32.8K", 32800), ("77k", 77000)]:
            self.assertEqual(ex.parse_k(s), n, s)


class TestParseSubView(unittest.TestCase):
    def test_single(self):
        sv = ex.parse_sub_view("sub -346K / 3 day ago view -5.7K / 7 day ago view -6.5K")
        self.assertEqual(sv, {"subs": [346000], "views_3d": [5700], "views_7d": [6500]})

    def test_multi_channel(self):
        sv = ex.parse_sub_view("sub -23K/19K / 3 day ago view -290/210 / 7 day ago view -394/265")
        self.assertEqual(sv, {"subs": [23000, 19000], "views_3d": [290, 210], "views_7d": [394, 265]})

    def test_days_view_variant(self):
        sv = ex.parse_sub_view("sub-27K/16K / 3 days view -552/391 / 7 days view -424/347")
        self.assertEqual(sv["subs"], [27000, 16000])
        self.assertEqual(sv["views_7d"], [424, 347])

    def test_empty(self):
        self.assertEqual(ex.parse_sub_view(None), {"subs": [], "views_3d": [], "views_7d": []})


class TestSmallHelpers(unittest.TestCase):
    def test_section(self):
        self.assertEqual(ex.section_from_header("ONLY US "), "only_us")
        self.assertEqual(ex.section_from_header("Only Two"), "only_two")
        self.assertEqual(ex.section_from_header("Only three"), "only_three")
        self.assertEqual(ex.section_from_header("Only four"), "only_four")
        self.assertEqual(ex.section_from_header("October - Sexy Model, Net Idol , Page  and Vd creator"), "influencer")

    def test_split_names(self):
        # the sheet separates channel names with newlines; a '/' inside a name must survive
        self.assertEqual(ex.split_names("MMSUB MOVIE  \n၂၀၂၆ထွက်ဇာတ်ကားမျာ\nမြန်"),
                         ["MMSUB MOVIE", "၂၀၂၆ထွက်ဇာတ်ကားမျာ", "မြန်"])
        self.assertEqual(ex.split_names("Channel Z (Movie) / Z Movie Channel /"), ["Channel Z (Movie)", "Z Movie Channel"])
        self.assertEqual(ex.split_names("မြန်မာဇာတ်လမ်းတွဲများ(မုန်းမာန်ငြိုး/မှတစ်ပါး)"),
                         ["မြန်မာဇာတ်လမ်းတွဲများ(မုန်းမာန်ငြိုး/မှတစ်ပါး)"])
        self.assertEqual(ex.split_names("MM/Sub Movies"), ["MM/Sub Movies"])
        self.assertEqual(ex.split_names(None), [])

    def test_admins(self):
        self.assertEqual(ex.parse_admins("@Thura833 @ZTPP2208 / @DiDi186"), ["@Thura833", "@ZTPP2208", "@DiDi186"])
        self.assertEqual(ex.parse_admins("  @htetwaiyan20025"), ["@htetwaiyan20025"])
        self.assertEqual(ex.parse_admins(None), [])

    def test_sheet_month(self):
        cases = {"October 2026 MKT Pla": "2026-10", "Nov  2025 MKT Pla": "2025-11", "Jan 24MKT Plan": "2024-01",
                 "Feb z24MKT Plan": "2024-02", "Mar 2024 MKT Pla": "2024-03", " June 2024 MKT Pla": "2024-06",
                 "Nov MKT Plan": "2022-11", "Dec MKT Plan": "2022-12", "Jan  MKT Plan": "2023-01",
                 "Oct MKT Plan": "2023-10", "Nov 2 MKT Plan": "2023-11", "Dec2 MKT Plan": "2023-12",
                 "   Sep 2025 MKT Pla": "2025-09", "Reg List": None}
        for title, exp in cases.items():
            self.assertEqual(ex.sheet_month_from_title(title), exp, title)

    def test_map_headers(self):
        hdr = ["Reg", "Admin account", "Continue TIme", "Plan to Post Date", "Cele Name ", "Page / acc (LINK)",
               "Post  / ads active", "Situration", "Payment  note", "Total amount ", "Payment 1", "Payment 2",
               "Payment Date ", "Remark", "Title", "Note", "Posted Date", "Old Name", "Old Link"]
        m = ex.map_headers(hdr)
        self.assertEqual(m["reg"], 0)
        self.assertEqual(m["name"], 4)
        self.assertEqual(m["link"], 5)
        self.assertEqual(m["sub_view"], 6)
        self.assertEqual(m["status"], 7)
        self.assertEqual(m["amount"], 9)
        self.assertEqual(m["remark"], 13)
        self.assertEqual(m["posted_date"], 16)
        self.assertEqual(m["old_link"], 18)


class TestParseMonthSheet(unittest.TestCase):
    """Integration on a tiny in-memory workbook shaped like the 2025-2026 sheets."""

    def _ws(self):
        import openpyxl
        from openpyxl.comments import Comment
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "October 2026 MKT Pla"
        ws.append([None, None, None, "Platinum October Marketing Plan", None, None, None, 129, None, 550000])
        ws.append(["Reg", "Admin account", "Continue TIme", "Plan to Post Date", "Cele Name ", "Page / acc (LINK)",
                   "Post  / ads active", "Situration", "Payment  note", "Total amount ", "Payment 1", "Payment 2",
                   "Payment Date ", "Remark", "Title", "Note", "Posted Date", "Old Name", "Old Link"])
        ws.append([None, None, None, "October Telegram Channel"])
        ws.append([None, None, "ONLY US "])
        ws.append(["Sep Reg -2 / Aug Reg -0", "@M_A_W_T2024", "33th time continue", "1.10.26 - 31.10.26",
                   "Chan A", "https://t.me/ChanA", "sub -346K / 3 day ago view -5.7K / 7 day ago view -6.5K",
                   "On Process", None, 450000, None, 450000, "3.10.26", "1 day 1 post / pin daily / only us",
                   None, "Kpay - X", None, "Old A", "https://t.me/OldA"])
        ws.append([None, None, "Only Two"])
        ws.append(["Sep Reg -0 / Aug Reg -1", "@b1 / @b2", "5th time continue", "2.10.26 - 2.11.26",
                   "Chan B / Chan C", "https://t.me/+AAAA1111 / https://t.me/chanc/77",
                   "sub -10K/20K / 3 day ago view -100/200 / 7 day ago view -300/400",
                   "On Process", None, 100000, None, 100000, "2.10.26", "1 day 1 post / 1 month 4 pin / only two"])
        ws["F5"].hyperlink = "https://t.me/ChanA(old"
        ws["J5"].comment = Comment("400000", "")
        return ws

    def test_contracts_and_channels(self):
        ws = self._ws()
        contracts = ex.parse_month_sheet(ws)
        self.assertEqual(len(contracts), 2)
        a, b = contracts
        self.assertEqual(a["contract_id"], "2026-10-r005")
        self.assertEqual(a["section"], "only_us")
        self.assertEqual(a["streak_months"], 33)
        self.assertEqual(a["amount_mmk"], 450000)
        self.assertEqual(a["pin_rule"], "daily")
        self.assertEqual(a["price_history_note"], "400000")
        self.assertEqual(a["old_name"], "Old A")
        self.assertEqual(b["section"], "only_two")
        self.assertEqual(b["exclusivity"], 2)
        self.assertEqual(b["admin_accounts"], ["@b1", "@b2"])
        channels = ex.flatten_channels(contracts)
        kinds = sorted((c["kind"], c["is_old_link"]) for c in channels)
        self.assertEqual(kinds, [("private", False), ("public", False), ("public", False), ("public", True)])
        names = {c["channel_id"]: c["name"] for c in channels}
        self.assertEqual(names["prv:AAAA1111"], "Chan B")
        self.assertEqual(names["pub:chanc"], "Chan C")
        self.assertEqual(names["pub:chana"], "Chan A")

    def test_sheet_totals(self):
        ws = self._ws()
        t = ex.sheet_totals(ws)
        self.assertEqual(t["amount_header"], 550000)
        self.assertEqual(t["amount_sum"], 550000)
        self.assertEqual(t["contracts"], 2)

    def test_stale_hyperlink_target_stays_an_old_link(self):
        """Cell text names the current channels; the cell's hyperlink still points at the Old Link."""
        ws = self._ws()
        ws.append(["Sep Reg -0", "@d", "2nd time continue", "1.10.26 - 31.10.26", "Chan D\nChan E",
                   "https://t.me/new1 / https://t.me/new2", "sub -1K/2K", "On Process", None, 5000, None, 5000,
                   "1.10.26", "1 day 1 post / pin daily / only us", None, None, None, "Old D",
                   "https://t.me/oldd (old link - https://t.me/older)"])
        ws["F7"].hyperlink = "https://t.me/oldd"
        c = ex.parse_month_sheet(ws)[-1]
        self.assertEqual([l["username"] for l in c["links"]], ["new1", "new2"])
        self.assertEqual([l["username"] for l in c["old_links"]], ["oldd", "older"])
        self.assertEqual(c["names"], ["Chan D", "Chan E"])
        self.assertEqual(c["sub_view"]["subs"], [1000, 2000])


if __name__ == "__main__":
    unittest.main()
