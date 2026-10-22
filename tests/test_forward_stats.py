import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from infrastructure.stats.forward_stats import ForwardStatsStore

TZ = timezone(timedelta(hours=7))


class MutableClock:
    def __init__(self, moment):
        self.moment = moment

    def __call__(self):
        return self.moment

    def advance(self, **kwargs):
        self.moment += timedelta(**kwargs)


class ForwardStatsStoreTest(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.path = os.path.join(temp_dir.name, "stats.json")

    def test_records_lifetime_and_daily_totals(self):
        clock = MutableClock(datetime(2026, 10, 22, 9, 0, tzinfo=TZ))
        store = ForwardStatsStore(self.path, clock=clock)

        store.record(sent=10, failed=1)
        snapshot = store.record(sent=5, failed=0)

        self.assertEqual(snapshot.today_forwarded, 15)
        self.assertEqual(snapshot.today_failed, 1)
        self.assertEqual(snapshot.lifetime_forwarded, 15)
        self.assertEqual(snapshot.lifetime_failed, 1)

        with open(self.path, encoding="utf-8") as stream:
            payload = json.load(stream)
        self.assertEqual(payload["lifetime"], {"forwarded": 15, "failed": 1})
        self.assertEqual(
            payload["daily"]["2026-10-22"], {"forwarded": 15, "failed": 1}
        )

    def test_totals_survive_restart(self):
        clock = MutableClock(datetime(2026, 10, 22, 9, 0, tzinfo=TZ))
        ForwardStatsStore(self.path, clock=clock).record(sent=7, failed=2)

        reopened = ForwardStatsStore(self.path, clock=clock)

        snapshot = reopened.snapshot()
        self.assertEqual(snapshot.lifetime_forwarded, 7)
        self.assertEqual(snapshot.lifetime_failed, 2)
        self.assertEqual(snapshot.today_forwarded, 7)

    def test_new_day_resets_daily_counter_and_logs_summary(self):
        clock = MutableClock(datetime(2026, 10, 22, 23, 55, tzinfo=TZ))
        store = ForwardStatsStore(self.path, clock=clock)
        store.record(sent=40, failed=1)

        clock.advance(minutes=10)
        with self.assertLogs("stellar.forwarder", level="INFO") as captured:
            snapshot = store.record(sent=3, failed=0)

        self.assertIn(
            "Daily summary 2026-10-22: forwarded=40, failed=1",
            "\n".join(captured.output),
        )
        self.assertEqual(snapshot.today_forwarded, 3)
        self.assertEqual(snapshot.lifetime_forwarded, 43)

    def test_prunes_daily_counters_older_than_retention(self):
        clock = MutableClock(datetime(2026, 10, 1, 9, 0, tzinfo=TZ))
        store = ForwardStatsStore(self.path, retention_days=3, clock=clock)
        store.record(sent=5, failed=0)

        clock.advance(days=10)
        store.record(sent=1, failed=0)

        with open(self.path, encoding="utf-8") as stream:
            payload = json.load(stream)
        self.assertEqual(sorted(payload["daily"]), ["2026-10-11"])
        self.assertEqual(payload["lifetime"]["forwarded"], 6)

    def test_corrupt_stats_file_starts_from_zero(self):
        with open(self.path, "w", encoding="utf-8") as stream:
            stream.write("{not json")

        clock = MutableClock(datetime(2026, 10, 22, 9, 0, tzinfo=TZ))
        with self.assertLogs("stellar.forwarder", level="WARNING"):
            store = ForwardStatsStore(self.path, clock=clock)

        snapshot = store.record(sent=2, failed=0)
        self.assertEqual(snapshot.lifetime_forwarded, 2)

    def test_unwritable_stats_path_only_logs_an_error(self):
        path = os.path.join(self.path, "nested", "stats.json")
        clock = MutableClock(datetime(2026, 10, 22, 9, 0, tzinfo=TZ))
        store = ForwardStatsStore(path, clock=clock)

        with self.assertLogs("stellar.forwarder", level="ERROR"):
            snapshot = store.record(sent=4, failed=0)

        self.assertEqual(snapshot.lifetime_forwarded, 4)


if __name__ == "__main__":
    unittest.main()
