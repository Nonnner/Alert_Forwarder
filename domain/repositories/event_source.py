"""Port for reading events from a source."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from domain.entities.event import Event


class EventSource(ABC):
    """Reads events for a time window."""

    @abstractmethod
    def get_events(
        self,
        start_time: datetime,
        end_time: datetime,
        inclusive_start: bool = True,
    ) -> list[Event]:
        """Return the events between ``start_time`` and ``end_time``.

        ``inclusive_start`` controls whether the lower bound is inclusive so a
        caller can resume right after the last processed window without
        re-reading that window's final event.
        """
