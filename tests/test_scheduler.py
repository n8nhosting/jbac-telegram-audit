import datetime as dt
import json
import pathlib
import unittest
from zoneinfo import ZoneInfo

from app.config import load_settings
from app.db import connect, migrate, one
from app.importer import import_seed
from app.scheduler import alert_tick, rollup_tick

SEED = json.loads((pathlib.Path(__file__).resolve().parent / "fixtures" / "seed_small.json").read_text(encoding="utf-8"))
S = load_settings({})
YGN = ZoneInfo("Asia/Yangon")


class TestTicks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        migrate(self.conn)
        import_seed(self.conn, SEED)
        self.c1 = one(self.conn, "SELECT id FROM contracts WHERE sheet_contract_id='2026-10-r005'")["id"]

    async def test_rollup_tick_reprocesses_stuck_waiting_days(self):
        now = dt.datetime(2026, 10, 25, 14, 0, tzinfo=YGN)
        old = "2026-10-22"
        self.conn.execute("INSERT INTO daily_rollup(local_date, contract_id, required, qualified, pin_ok, status, notes, computed_at)"
                          " VALUES(?,?,1,0,NULL,'waiting','{}','x')", (old, self.c1))
        dates = await rollup_tick(self.conn, S, now)
        self.assertEqual(dates[:2], ["2026-10-25", "2026-10-24"])
        self.assertIn(old, dates)
        self.assertNotEqual(one(self.conn, "SELECT status FROM daily_rollup WHERE local_date=? AND contract_id=?", (old, self.c1))["status"], "waiting")

    async def test_rollup_tick_sends_missed_final_alert_for_yesterday(self):
        sent = []

        async def sender(text):
            sent.append(text)
            return True

        now = dt.datetime(2026, 10, 25, 9, 0, tzinfo=YGN)          # well past 00:06
        await rollup_tick(self.conn, S, now, sender=sender)
        self.assertEqual(len(sent), 1)
        self.assertIn("2026-10-24", sent[0])
        await rollup_tick(self.conn, S, now, sender=sender)       # idempotent
        self.assertEqual(len(sent), 1)
        early = dt.datetime(2026, 10, 26, 0, 2, tzinfo=YGN)       # before the 00:06 cron: not yet
        await rollup_tick(self.conn, S, early, sender=sender)
        self.assertEqual(len(sent), 1)

    async def test_alert_tick_collects_then_rolls_then_sends_once(self):
        calls, sent = [], []

        async def collector(conn, settings):
            calls.append("collect")

        async def sender(text):
            sent.append(text)
            return True

        now = dt.datetime(2026, 10, 26, 0, 6, tzinfo=YGN)
        self.assertTrue(await alert_tick(self.conn, S, "2026-10-25", "final", now, collector=collector, sender=sender))
        self.assertEqual((calls, len(sent)), (["collect"], 1))
        self.assertEqual(one(self.conn, "SELECT COUNT(*) AS n FROM daily_rollup WHERE local_date='2026-10-25'")["n"], 2)
        self.assertFalse(await alert_tick(self.conn, S, "2026-10-25", "final", now, collector=collector, sender=sender))
        self.assertEqual(calls, ["collect"])                      # already sent: no second collection


if __name__ == "__main__":
    unittest.main()
