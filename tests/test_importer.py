import json
import pathlib
import unittest

from app.db import connect, migrate, one, all_rows
from app.importer import import_seed

SEED = json.loads((pathlib.Path(__file__).resolve().parent / "fixtures" / "seed_small.json").read_text(encoding="utf-8"))


def _counts(conn):
    q = lambda t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    return {t: q(t) for t in ("contracts", "channels", "channel_aliases", "reg_monthly", "contract_channels", "price_history")}


class TestImporter(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        migrate(self.conn)

    def test_import_counts_and_mapping(self):
        st = import_seed(self.conn, SEED)
        self.assertEqual((st.contracts, st.channels, st.aliases, st.reg_rows, st.skipped_external), (2, 3, 1, 3, 1))
        prv = one(self.conn, "SELECT * FROM channels WHERE channel_key='prv:AAAA1111'")
        self.assertEqual((prv["kind"], prv["collector"], prv["invite_hash"]), ("private", "invite", "AAAA1111"))
        pub = one(self.conn, "SELECT * FROM channels WHERE channel_key='pub:chana'")
        self.assertEqual((pub["kind"], pub["collector"], pub["username"], pub["title"]), ("public_preview", "preview", "chana", "Chan A"))
        c1 = one(self.conn, "SELECT * FROM contracts WHERE sheet_contract_id='2026-10-r005'")
        self.assertEqual((c1["amount_mmk"], c1["pin_rule"], c1["exclusivity"], c1["quota_posts_per_day"]), (450000, "daily", 1, 1))
        self.assertEqual(json.loads(c1["names"]), ["Chan A"])
        regs = all_rows(self.conn, "SELECT month, reg FROM reg_monthly WHERE contract_id=? ORDER BY month", (c1["id"],))
        self.assertEqual([(r["month"], r["reg"]) for r in regs], [("2026-08", 0), ("2026-09", 2)])
        self.assertEqual(one(self.conn, "SELECT amount_mmk FROM price_history WHERE contract_id=?", (c1["id"],))["amount_mmk"], 400000)
        alias = one(self.conn, "SELECT * FROM channel_aliases")
        self.assertEqual((alias["old_channel_key"], alias["old_title"], alias["source"]), ("pub:olda", "Old A", "sheet"))
        self.assertEqual(alias["channel_id"], pub["id"])
        self.assertEqual(_counts(self.conn)["contract_channels"], 3)

    def test_import_twice_is_idempotent(self):
        import_seed(self.conn, SEED)
        before = _counts(self.conn)
        import_seed(self.conn, SEED)
        self.assertEqual(_counts(self.conn), before)
        self.assertEqual(before, {"contracts": 2, "channels": 3, "channel_aliases": 1, "reg_monthly": 3,
                                  "contract_channels": 3, "price_history": 1})

    def test_collector_from_probe_kind(self):
        probe = {"channels": [
            {"username": "chana", "readable": False, "profile_kind": "channel_no_preview"},
            {"username": "chanc", "readable": True},
        ]}
        import_seed(self.conn, SEED, probe)
        a = one(self.conn, "SELECT kind, collector FROM channels WHERE channel_key='pub:chana'")
        c = one(self.conn, "SELECT kind, collector FROM channels WHERE channel_key='pub:chanc'")
        self.assertEqual((a["kind"], a["collector"]), ("public_no_preview", "profile"))
        self.assertEqual((c["kind"], c["collector"]), ("public_preview", "preview"))

    def test_user_or_bot_handle_is_not_a_channel(self):
        probe = {"channels": [{"username": "chanc", "readable": False, "profile_kind": "user_or_bot"}]}
        import_seed(self.conn, SEED, probe)
        c = one(self.conn, "SELECT kind, collector FROM channels WHERE channel_key='pub:chanc'")
        self.assertEqual((c["kind"], c["collector"]), ("not_channel", "none"))

    def test_reimport_leaves_manually_locked_contract_alone(self):
        import_seed(self.conn, SEED)
        self.conn.execute("UPDATE contracts SET amount_mmk=999, quota_posts_per_day=5, manual_locked=1 WHERE sheet_contract_id='2026-10-r005'")
        self.conn.execute("UPDATE contracts SET amount_mmk=111 WHERE sheet_contract_id='2026-10-r006'")
        self.conn.commit()
        import_seed(self.conn, SEED)
        locked = one(self.conn, "SELECT amount_mmk, quota_posts_per_day FROM contracts WHERE sheet_contract_id='2026-10-r005'")
        free = one(self.conn, "SELECT amount_mmk FROM contracts WHERE sheet_contract_id='2026-10-r006'")
        self.assertEqual((locked["amount_mmk"], locked["quota_posts_per_day"]), (999, 5))
        self.assertNotEqual(free["amount_mmk"], 111)                      # unlocked rows still follow the sheet
        self.assertEqual(one(self.conn, "SELECT COUNT(*) AS n FROM contract_channels")["n"], 3)   # links still attached

    def test_reimport_leaves_manually_locked_channel_alone(self):
        import_seed(self.conn, SEED)
        self.conn.execute("UPDATE channels SET title='Renamed by hand', manual_locked=1 WHERE channel_key='pub:chana'")
        self.conn.commit()
        import_seed(self.conn, SEED, {"channels": [{"username": "chana", "readable": False, "profile_kind": "channel_no_preview"}]})
        ch = one(self.conn, "SELECT title, kind, collector FROM channels WHERE channel_key='pub:chana'")
        self.assertEqual((ch["title"], ch["kind"], ch["collector"]), ("Renamed by hand", "public_preview", "preview"))


if __name__ == "__main__":
    unittest.main()
