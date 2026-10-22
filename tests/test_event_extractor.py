import unittest

from domain.errors import EventSourceError
from infrastructure.stellar.event_extractor import EventExtractor


class EventExtractorTest(unittest.TestCase):
    def test_extracts_source_documents(self):
        payload = {
            "hits": {
                "hits": [
                    {"_source": {"UNIT_ID": "u1"}},
                    {"_source": {"UNIT_ID": "u2"}},
                ]
            }
        }

        events = EventExtractor.extract(payload)

        self.assertEqual([event.data for event in events], [{"UNIT_ID": "u1"}, {"UNIT_ID": "u2"}])

    def test_falls_back_to_record_when_source_is_missing(self):
        payload = {"hits": {"hits": [{"UNIT_ID": "u1"}]}}

        events = EventExtractor.extract(payload)

        self.assertEqual(events[0].data, {"UNIT_ID": "u1"})

    def test_missing_hits_yields_no_events(self):
        self.assertEqual(EventExtractor.extract({}), [])

    def test_invalid_payloads_are_rejected(self):
        invalid_payloads = [
            [],
            {"hits": []},
            {"hits": {"hits": "nope"}},
            {"hits": {"hits": ["nope"]}},
            {"hits": {"hits": [{"_source": "nope"}]}},
        ]

        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(EventSourceError):
                EventExtractor.extract(payload)


if __name__ == "__main__":
    unittest.main()
