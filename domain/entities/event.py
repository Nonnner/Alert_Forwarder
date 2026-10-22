"""The Event entity: a single record coming from an event source."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

# Legacy sensors publish upper-case identifiers. The destination expects the
# lower-case variants, so both keys are kept in the outgoing payload.
FIELD_ALIASES: tuple[tuple[str, str], ...] = (
    ("UNIT_ID", "unit_id"),
    ("UNIT_NAME", "unit_name"),
    ("VENDOR_ID", "vendor_id"),
)

# Document-level identifiers that stay stable across window retries.
IDENTITY_FIELDS: tuple[str, ...] = ("stellar_uuid", "_id")


@dataclass(frozen=True)
class Event:
    """A source-agnostic event record."""

    data: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.data, Mapping):
            raise ValueError("Event data must be a mapping")

    def as_payload(self, sensor_id: str) -> dict[str, Any]:
        """Build the destination payload for this event."""
        payload = dict(self.data)

        for source_name, target_name in FIELD_ALIASES:
            if target_name not in payload and source_name in payload:
                payload[target_name] = payload[source_name]

        payload["sensor_id"] = sensor_id
        return payload

    def fingerprint(self) -> str:
        """Return a stable identity for the record.

        Windows are retried as a whole, so the same document can be delivered
        more than once. The fingerprint lets callers count each document once.
        """
        for field in IDENTITY_FIELDS:
            value = self.data.get(field)
            if value not in (None, ""):
                return f"{field}:{value}"

        canonical = json.dumps(
            self.data, sort_keys=True, default=str, separators=(",", ":")
        )
        return hashlib.blake2b(canonical.encode("utf-8"), digest_size=16).hexdigest()
