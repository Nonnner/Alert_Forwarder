"""Converts a Stellar search response into Event entities."""

from __future__ import annotations

from typing import Any, Mapping

from domain.entities.event import Event
from domain.errors import EventSourceError


class EventExtractor:
    """Extracts the ``_source`` documents of a Stellar search response."""

    @staticmethod
    def extract(payload: Mapping[str, Any]) -> list[Event]:
        if not isinstance(payload, Mapping):
            raise EventSourceError("Stellar response is not a JSON object")

        hits = payload.get("hits", {})
        if not isinstance(hits, Mapping):
            raise EventSourceError("Stellar response has an invalid 'hits' object")

        records = hits.get("hits", [])
        if not isinstance(records, list):
            raise EventSourceError(
                "Stellar response has an invalid 'hits.hits' list"
            )

        events: list[Event] = []
        for record in records:
            if not isinstance(record, Mapping):
                raise EventSourceError(
                    "Stellar response contains a non-object record"
                )

            source = record.get("_source", record)
            if not isinstance(source, Mapping):
                raise EventSourceError(
                    "Stellar record has an invalid '_source' object"
                )

            events.append(Event(EventExtractor._normalize_source(source)))

        return events

    @staticmethod
    def _normalize_source(source: Mapping[str, Any]) -> dict[str, Any]:
        """Flatten the nested payload used by events from the ``json`` source."""
        message_origin = source.get("msg_origin")
        source_name = (
            message_origin.get("source")
            if isinstance(message_origin, Mapping)
            else None
        )
        if source_name != "json":
            return dict(source)

        syslogjson = source.get("syslogjson")
        if not isinstance(syslogjson, Mapping):
            return dict(source)

        normalized = dict(source)
        normalized.pop("syslogjson", None)
        normalized.update(syslogjson)
        return normalized
