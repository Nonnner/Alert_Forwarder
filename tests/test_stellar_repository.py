import unittest
from datetime import datetime, timedelta, timezone

from domain.entities.event import Event
from infrastructure.stellar.query_builder import StellarSearchQueryBuilder
from infrastructure.stellar.stellar_repository import StellarRepository
from infrastructure.stellar.event_extractor import EventExtractor

TZ = timezone(timedelta(hours=7))


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.token_requests = 0
        self.search_calls = []

    def get_access_token(self):
        self.token_requests += 1
        return "access-1"

    def search(self, query, access_token):
        self.search_calls.append((query, access_token))
        return self.payload


class StellarRepositoryTest(unittest.TestCase):
    def test_queries_with_the_configured_window(self):
        client = FakeClient({"hits": {"hits": [{"_source": {"UNIT_ID": "u1"}}]}})
        repository = StellarRepository(
            client, StellarSearchQueryBuilder("+07:00"), EventExtractor()
        )
        start = datetime(2026, 10, 21, 1, 0, tzinfo=TZ)
        end = start + timedelta(minutes=5)

        events = repository.get_events(start, end, inclusive_start=False)

        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], Event)
        self.assertEqual(events[0].data, {"UNIT_ID": "u1"})
        self.assertEqual(client.token_requests, 1)
        query, access_token = client.search_calls[0]
        self.assertEqual(access_token, "access-1")
        timestamp_range = query["query"]["bool"]["filter"][1]["range"]["timestamp"]
        self.assertEqual(timestamp_range["gt"], "2026-10-21T01:00:00.000")
        self.assertEqual(timestamp_range["lte"], "2026-10-21T01:05:00.000")


if __name__ == "__main__":
    unittest.main()
