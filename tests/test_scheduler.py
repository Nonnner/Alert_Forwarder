import unittest
from datetime import datetime, timedelta, timezone

from domain.services.forward_service import ForwardSummary, IncompleteForwardError
from scheduler.scheduler import Scheduler, resolve_initial_start

TZ = timezone(timedelta(hours=7))
INTERVAL = timedelta(minutes=5)


class FakeService:
    def __init__(self, failures=0):
        self.failures = failures
        self.calls = []

    def forward_window(self, start_time, end_time, inclusive_start=True):
        self.calls.append((start_time, end_time, inclusive_start))
        if self.failures:
            self.failures -= 1
            raise IncompleteForwardError(ForwardSummary(1, 0, 1))
        return ForwardSummary(0, 0, 0)


class StopLoop(Exception):
    pass


class SequenceClock:
    def __init__(self, *moments):
        self._moments = list(moments)

    def __call__(self):
        if len(self._moments) > 1:
            return self._moments.pop(0)
        return self._moments[0]


class SchedulerTest(unittest.TestCase):
    def test_run_once_forwards_the_initial_window_inclusively(self):
        started = datetime(2026, 10, 21, 8, 0, tzinfo=TZ)
        service = FakeService()
        scheduler = Scheduler(
            service=service,
            interval=INTERVAL,
            time_zone=TZ,
            initial_start=started - timedelta(hours=1),
            run_once=True,
            clock=lambda: started,
        )

        scheduler.run()

        self.assertEqual(service.calls, [(started - timedelta(hours=1), started, True)])

    def test_failed_cycle_retries_the_same_window(self):
        started = datetime(2026, 10, 21, 8, 0, tzinfo=TZ)
        service = FakeService(failures=1)
        sleeps = []

        def sleep(delay):
            sleeps.append(delay)
            if len(sleeps) == 2:
                raise StopLoop()

        scheduler = Scheduler(
            service=service,
            interval=INTERVAL,
            time_zone=TZ,
            initial_start=started,
            clock=lambda: started,
            sleep=sleep,
        )

        with self.assertRaises(StopLoop):
            scheduler.run()

        self.assertEqual(
            service.calls, [(started, started, True), (started, started, True)]
        )

    def test_successful_cycle_advances_the_window_exclusively(self):
        first = datetime(2026, 10, 21, 8, 0, tzinfo=TZ)
        second = first + INTERVAL
        service = FakeService()
        sleeps = []

        def sleep(delay):
            sleeps.append(delay)
            if len(sleeps) == 2:
                raise StopLoop()

        scheduler = Scheduler(
            service=service,
            interval=INTERVAL,
            time_zone=TZ,
            initial_start=first,
            clock=SequenceClock(first, first, second, second),
            sleep=sleep,
        )

        with self.assertRaises(StopLoop):
            scheduler.run()

        self.assertEqual(
            service.calls,
            [(first, first, True), (first, second, False)],
        )

    def test_run_once_cycle_failure_is_raised(self):
        started = datetime(2026, 10, 21, 8, 0, tzinfo=TZ)
        scheduler = Scheduler(
            service=FakeService(failures=1),
            interval=INTERVAL,
            time_zone=TZ,
            initial_start=started,
            run_once=True,
            clock=lambda: started,
        )

        with self.assertRaises(IncompleteForwardError):
            scheduler.run()

    def test_resolve_initial_start_prefers_explicit_timestamp(self):
        now = datetime(2026, 10, 21, 8, 0, tzinfo=TZ)
        explicit = datetime(2026, 10, 21, 0, 0)

        self.assertEqual(
            resolve_initial_start(explicit, None, INTERVAL, now),
            explicit.replace(tzinfo=TZ),
        )

    def test_resolve_initial_start_uses_lookback_or_interval(self):
        now = datetime(2026, 10, 21, 8, 0, tzinfo=TZ)

        self.assertEqual(
            resolve_initial_start(None, 60, INTERVAL, now),
            now - timedelta(minutes=60),
        )
        self.assertEqual(
            resolve_initial_start(None, None, INTERVAL, now),
            now - INTERVAL,
        )


if __name__ == "__main__":
    unittest.main()
