import unittest
from datetime import datetime, timedelta, timezone

from domain.entities.event import Event
from domain.errors import DeliveryError, EventSourceError
from domain.repositories.destination import Destination
from domain.repositories.event_source import EventSource
from domain.services.forward_service import (
    ForwardService,
    ForwardSummary,
    IncompleteForwardError,
)

START = datetime(2026, 10, 21, 0, 0, tzinfo=timezone.utc)
END = START + timedelta(minutes=5)


class FakeSource(EventSource):
    def __init__(self, events=None, error=None):
        self.events = events or []
        self.error = error
        self.calls = []

    def get_events(self, start_time, end_time, inclusive_start=True):
        self.calls.append((start_time, end_time, inclusive_start))
        if self.error:
            raise self.error
        return self.events


class FakeDestination(Destination):
    def __init__(self, failing_ids=()):
        self.failing_ids = set(failing_ids)
        self.sent = []

    def send(self, event):
        if event.data.get("id") in self.failing_ids:
            raise DeliveryError(f"cannot deliver {event.data.get('id')}")
        self.sent.append(event.data["id"])


class FakeStats:
    def __init__(self):
        self.calls = []

    def record(self, sent, failed):
        self.calls.append((sent, failed))


class ForwardServiceTest(unittest.TestCase):
    def test_forwards_every_event_of_the_window(self):
        source = FakeSource([Event({"id": "1"}), Event({"id": "2"})])
        destination = FakeDestination()
        service = ForwardService(source, destination)

        summary = service.forward_window(START, END)

        self.assertEqual(summary, ForwardSummary(total=2, sent=2, failed=0))
        self.assertEqual(destination.sent, ["1", "2"])
        self.assertEqual(source.calls, [(START, END, True)])

    def test_continues_after_failure_and_reports_incomplete_window(self):
        source = FakeSource([Event({"id": "1"}), Event({"id": "2"}), Event({"id": "3"})])
        destination = FakeDestination(failing_ids={"2"})
        service = ForwardService(source, destination)

        with self.assertRaises(IncompleteForwardError) as context:
            service.forward_window(START, END, inclusive_start=False)

        self.assertEqual(
            context.exception.summary,
            ForwardSummary(total=3, sent=2, failed=1),
        )
        self.assertEqual(destination.sent, ["1", "3"])
        self.assertEqual(source.calls, [(START, END, False)])

    def test_source_errors_propagate(self):
        source = FakeSource(error=EventSourceError("boom"))
        service = ForwardService(source, FakeDestination())

        with self.assertRaises(EventSourceError):
            service.forward_window(START, END)

    def test_records_forwarded_totals(self):
        stats = FakeStats()
        source = FakeSource([Event({"id": "1"}), Event({"id": "2"})])
        service = ForwardService(
            source, FakeDestination(), stats=stats
        )

        service.forward_window(START, END)

        self.assertEqual(stats.calls, [(2, 0)])

    def test_records_totals_when_a_window_is_incomplete(self):
        stats = FakeStats()
        source = FakeSource(
            [Event({"id": "1"}), Event({"id": "2"}), Event({"id": "3"})]
        )
        service = ForwardService(
            source, FakeDestination(failing_ids={"2"}), stats=stats
        )

        with self.assertRaises(IncompleteForwardError):
            service.forward_window(START, END)

        self.assertEqual(stats.calls, [(2, 1)])

    def test_retried_events_are_counted_once(self):
        stats = FakeStats()
        destination = FakeDestination(failing_ids={"2"})
        source = FakeSource(
            [Event({"id": "1"}), Event({"id": "2"}), Event({"id": "3"})]
        )
        service = ForwardService(source, destination, stats=stats)

        with self.assertRaises(IncompleteForwardError):
            service.forward_window(START, END)

        destination.failing_ids.clear()
        summary = service.forward_window(START, END)

        self.assertEqual(summary.sent, 3)
        self.assertEqual(stats.calls, [(2, 1), (1, 0)])
        self.assertEqual(sum(count for count, _ in stats.calls), 3)

    def test_duplicate_records_of_a_window_are_counted_once(self):
        stats = FakeStats()
        source = FakeSource(
            [
                Event({"id": "1", "stellar_uuid": "doc-1"}),
                Event({"id": "1", "stellar_uuid": "doc-1"}),
            ]
        )
        service = ForwardService(source, FakeDestination(), stats=stats)

        summary = service.forward_window(START, END)

        self.assertEqual(summary.sent, 2)
        self.assertEqual(stats.calls, [(1, 0)])

    def test_next_window_counts_events_again(self):
        stats = FakeStats()
        source = FakeSource([Event({"id": "1"})])
        service = ForwardService(source, FakeDestination(), stats=stats)

        service.forward_window(START, END)
        service.forward_window(
            END, END + timedelta(minutes=5), inclusive_start=False
        )

        self.assertEqual(stats.calls, [(1, 0), (1, 0)])


if __name__ == "__main__":
    unittest.main()
