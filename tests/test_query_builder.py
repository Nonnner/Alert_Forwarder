import unittest
from datetime import datetime, timedelta, timezone

from domain.errors import ConfigurationError
from infrastructure.stellar.query_builder import (
    StellarSearchQueryBuilder,
    format_query_time,
    parse_utc_offset,
)


class ParseUtcOffsetTest(unittest.TestCase):
    def test_positive_offset(self):
        self.assertEqual(parse_utc_offset("+07:00"), timezone(timedelta(hours=7)))

    def test_negative_offset(self):
        self.assertEqual(
            parse_utc_offset("-05:30"),
            timezone(-timedelta(hours=5, minutes=30)),
        )

    def test_invalid_offset_is_rejected(self):
        for raw in ("", "07:00", "+7", "+7:00", "abc", "+07:xx", "+07:99", "+24:00"):
            with self.subTest(raw=raw), self.assertRaises(ConfigurationError):
                parse_utc_offset(raw)


class FormatQueryTimeTest(unittest.TestCase):
    def test_converts_to_configured_offset_with_milliseconds(self):
        moment = datetime(2026, 10, 21, 0, 0, tzinfo=timezone.utc)

        self.assertEqual(
            format_query_time(moment, timezone(timedelta(hours=7))),
            "2026-10-21T07:00:00.000",
        )


class StellarSearchQueryBuilderTest(unittest.TestCase):
    def setUp(self):
        self.builder = StellarSearchQueryBuilder("+07:00")
        self.start = datetime(2026, 10, 21, 0, 0, tzinfo=parse_utc_offset("+07:00"))
        self.end = self.start + timedelta(minutes=5)

    def test_query_matches_stellar_filters(self):
        query = self.builder.build(self.start, self.end)

        self.assertEqual(query["size"], 1000)
        filters = query["query"]["bool"]["filter"]

        self.assertEqual(
            filters[0], {"term": {"msg_origin.source.keyword": "httpjson"}}
        )
        self.assertEqual(
            filters[1]["range"]["timestamp"],
            {
                "gte": "2026-10-21T00:00:00.000",
                "lte": "2026-10-21T00:05:00.000",
                "time_zone": "+07:00",
            },
        )
        self.assertEqual(
            filters[2]["bool"]["should"],
            [
                {"exists": {"field": "unit_id"}},
                {"exists": {"field": "UNIT_ID"}},
            ],
        )
        self.assertEqual(filters[2]["bool"]["minimum_should_match"], 1)
        self.assertEqual(query["sort"], [{"timestamp": {"order": "asc"}}])

    def test_exclusive_start_uses_gt(self):
        query = self.builder.build(self.start, self.end, inclusive_start=False)

        timestamp_range = query["query"]["bool"]["filter"][1]["range"]["timestamp"]
        self.assertIn("gt", timestamp_range)
        self.assertNotIn("gte", timestamp_range)

    def test_time_zone_is_exposed_for_scheduling(self):
        self.assertEqual(
            self.builder.time_zone, timezone(timedelta(hours=7))
        )


if __name__ == "__main__":
    unittest.main()
