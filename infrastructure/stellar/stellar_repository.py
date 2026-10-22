"""EventSource implementation backed by the Stellar Cyber search API."""

from __future__ import annotations

from datetime import datetime

from domain.entities.event import Event
from domain.repositories.event_source import EventSource

from infrastructure.stellar.event_extractor import EventExtractor
from infrastructure.stellar.query_builder import StellarSearchQueryBuilder
from infrastructure.stellar.stellar_client import StellarClient


class StellarRepository(EventSource):
    """Reads events from Stellar by querying its syslog indices."""

    def __init__(
        self,
        client: StellarClient,
        query_builder: StellarSearchQueryBuilder,
        extractor: EventExtractor | None = None,
    ) -> None:
        self._client = client
        self._query_builder = query_builder
        self._extractor = extractor or EventExtractor()

    def get_events(
        self,
        start_time: datetime,
        end_time: datetime,
        inclusive_start: bool = True,
    ) -> list[Event]:
        query = self._query_builder.build(start_time, end_time, inclusive_start)
        access_token = self._client.get_access_token()
        payload = self._client.search(query, access_token)
        return self._extractor.extract(payload)
