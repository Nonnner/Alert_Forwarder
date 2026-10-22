"""Builds Stellar Cyber search request bodies."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from domain.errors import ConfigurationError

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.000"
TIME_ZONE_FORMAT_HINT = "SEARCH_TIME_ZONE must use the +HH:MM offset format"
_OFFSET_PATTERN = re.compile(r"^(?P<sign>[+-])(?P<hours>\d{2}):(?P<minutes>\d{2})$")


def parse_utc_offset(raw: str) -> timezone:
    """Parse a ``+07:00`` style offset into a fixed-offset timezone."""
    match = _OFFSET_PATTERN.match(raw or "")
    if not match:
        raise ConfigurationError(TIME_ZONE_FORMAT_HINT)

    hours = int(match.group("hours"))
    minutes = int(match.group("minutes"))
    if minutes > 59:
        raise ConfigurationError(TIME_ZONE_FORMAT_HINT)

    sign = -1 if match.group("sign") == "-" else 1
    try:
        return timezone(sign * timedelta(hours=hours, minutes=minutes))
    except ValueError as exc:
        raise ConfigurationError(TIME_ZONE_FORMAT_HINT) from exc


def format_query_time(moment: datetime, time_zone: timezone) -> str:
    return moment.astimezone(time_zone).strftime(TIMESTAMP_FORMAT)


class StellarSearchQueryBuilder:
    """Builds the query document consumed by the Stellar data API."""

    def __init__(self, time_zone_offset: str = "+07:00", size: int = 1000) -> None:
        self._offset = time_zone_offset
        self._time_zone = parse_utc_offset(time_zone_offset)
        self._size = size

    @property
    def time_zone(self) -> timezone:
        return self._time_zone

    def build(
        self,
        start_time: datetime,
        end_time: datetime,
        inclusive_start: bool = True,
    ) -> dict:
        start_key = "gte" if inclusive_start else "gt"

        return {
            "size": self._size,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"msg_origin.source.keyword": "httpjson"}},
                        {
                            "range": {
                                "timestamp": {
                                    start_key: format_query_time(
                                        start_time, self._time_zone
                                    ),
                                    "lte": format_query_time(
                                        end_time, self._time_zone
                                    ),
                                    "time_zone": self._offset,
                                }
                            }
                        },
                        {
                            "bool": {
                                "should": [
                                    {"exists": {"field": "unit_id"}},
                                    {"exists": {"field": "UNIT_ID"}},
                                ],
                                "minimum_should_match": 1,
                            }
                        },
                    ]
                }
            },
            "sort": [{"timestamp": {"order": "asc"}}],
        }
