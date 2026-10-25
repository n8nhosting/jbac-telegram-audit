"""Tests for tools/build_dashboard_data.py (TDD: written before implementation)."""
import sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import build_dashboard_data as bd  # noqa: E402


def _contract(**kw):
    base = {"contract_id": "2026-10-r005", "month": "2026-10", "section": "only_us", "names": ["Chan A", "Chan B"],
            "admin_accounts": ["@a"], "streak_months": 33, "quota_type": "daily_post", "quota_posts_per_day": 1,
            "pin_rule": "daily", "exclusivity": 1, "amount_mmk": 450000,
            "reg_history": [{"month": "Sep", "reg": 2}, {"month": "Aug", "reg": 2}, {"month": "July", "reg": 0}, {"month": "June", "reg": 1}],
            "links": [{"kind": "public"}, {"kind": "private"}], "old_name": None, "old_links": [], "status_sheet": "On Process"}
    base.update(kw)
    return base


class TestRosterRows(unittest.TestCase):
    def test_cost_per_reg_uses_months_covered(self):
        r = bd.roster_rows([_contract()])[0]
        self.assertEqual(r["reg_sum"], 5)
        self.assertEqual(r["reg_months"], 4)
        self.assertEqual(r["cost_per_reg_mmk"], 360000)     # 450000 * 4 months / 5 reg
        self.assertEqual(r["name"], "Chan A / Chan B")
        self.assertEqual(r["public_links"], 1)
        self.assertEqual(r["private_links"], 1)
        self.assertEqual(r["exclusivity_label"], "only us")
        self.assertFalse(r["zero_reg"])

    def test_zero_reg_flag_needs_three_months(self):
        z = bd.roster_rows([_contract(reg_history=[{"month": "Sep", "reg": 0}, {"month": "Aug", "reg": 0}, {"month": "July", "reg": 0}])])[0]
        self.assertTrue(z["zero_reg"])
        self.assertIsNone(z["cost_per_reg_mmk"])
        short = bd.roster_rows([_contract(reg_history=[{"month": "Sep", "reg": 0}])])[0]
        self.assertFalse(short["zero_reg"])

    def test_no_amount_row(self):
        r = bd.roster_rows([_contract(amount_mmk=None)])[0]
        self.assertIsNone(r["cost_per_reg_mmk"])
        self.assertEqual(r["amount_mmk"], 0)

    def test_exclusivity_labels(self):
        self.assertEqual(bd.exclusivity_label(1), "only us")
        self.assertEqual(bd.exclusivity_label(3), "3 ads")
        self.assertEqual(bd.exclusivity_label(None), "custom")


class TestMonthlyRows(unittest.TestCase):
    def test_types_and_fields(self):
        rows = bd.monthly_rows([{"month": "2026-10", "era": "roster", "active_contracts": "87", "amount_active_sum": "24785602",
                                 "amount_sum": "24785602", "public_channels": "108", "private_channels": "76",
                                 "renamed_rows": "38", "contracts": "87"}])
        self.assertEqual(rows, [{"month": "2026-10", "era": "roster", "contracts": 87, "amount_mmk": 24785602,
                                 "public_channels": 108, "private_channels": 76, "renamed_rows": 38}])


class TestRegSourceRows(unittest.TestCase):
    def test_pivot(self):
        rows = bd.reg_source_rows([
            {"source": "Total", "month": "2026-01", "reg": "293", "is_total": "True"},
            {"source": "Telegram  Channel", "month": "2026-01", "reg": "129", "is_total": "False"},
            {"source": "Friend", "month": "2026-01", "reg": "18", "is_total": "False"},
            {"source": "Ma Pyae", "month": "2026-01", "reg": "1", "is_total": "False"},
        ])
        self.assertEqual(rows, [{"month": "2026-01", "total": 293, "telegram_channel": 129, "friend": 18, "other": 146}])

    def test_skips_months_without_total(self):
        rows = bd.reg_source_rows([{"source": "Telegram Channel", "month": "2026-08", "reg": "0", "is_total": "False"}])
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
