"""Use case: forward one window of events from a source to a destination."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from domain.errors import DeliveryError, ForwarderError
from domain.repositories.destination import Destination
from domain.repositories.event_source import EventSource
from domain.repositories.forward_stats import ForwardStatsRecorder

_logger = logging.getLogger("stellar.forwarder")


@dataclass(frozen=True)
class ForwardSummary:
    """Outcome of forwarding a single window."""

    total: int
    sent: int
    failed: int

    @property
    def has_failures(self) -> bool:
        return self.failed > 0


class IncompleteForwardError(ForwarderError):
    """Raised when at least one event of a window could not be delivered."""

    def __init__(self, summary: ForwardSummary) -> None:
        super().__init__(f"{summary.failed} record(s) failed to forward")
        self.summary = summary


class ForwardService:
    """Reads a window of events and forwards each of them."""

    def __init__(
        self,
        source: EventSource,
        destination: Destination,
        logger: logging.Logger | None = None,
        stats: ForwardStatsRecorder | None = None,
    ) -> None:
        self._source = source
        self._destination = destination
        self._logger = logger or _logger
        self._stats = stats
        # Fingerprints delivered while the current window is still unfinished.
        # A failed window is retried as a whole, so this keeps the counters
        # reflecting unique events instead of every delivery attempt.
        self._counted: set[str] = set()

    def forward_window(
        self,
        start_time: datetime,
        end_time: datetime,
        inclusive_start: bool = True,
    ) -> ForwardSummary:
        self._logger.info(
            "Querying records from %s to %s (start is %s)",
            start_time.isoformat(timespec="seconds"),
            end_time.isoformat(timespec="seconds"),
            "inclusive" if inclusive_start else "exclusive",
        )
        events = self._source.get_events(start_time, end_time, inclusive_start)
        self._logger.info("Query returned %d record(s)", len(events))

        sent = 0
        failed = 0
        unique_sent = 0
        for index, event in enumerate(events, start=1):
            fingerprint = event.fingerprint()
            counted_before = fingerprint in self._counted
            try:
                self._destination.send(event)
            except DeliveryError as exc:
                failed += 1
                self._logger.error("Forward failed for record %d: %s", index, exc)
                continue

            sent += 1
            if not counted_before:
                self._counted.add(fingerprint)
                unique_sent += 1
            self._logger.info("Forwarded record %d", index)

        summary = ForwardSummary(total=len(events), sent=sent, failed=failed)
        self._logger.info(
            "Window completed: total=%d, sent=%d, failed=%d",
            summary.total,
            summary.sent,
            summary.failed,
        )

        if sent > unique_sent:
            self._logger.info(
                "%d record(s) were re-sent from an unfinished window and "
                "are not counted again",
                sent - unique_sent,
            )

        if self._stats is not None:
            self._stats.record(sent=unique_sent, failed=failed)

        if not summary.has_failures:
            self._counted.clear()

        if summary.has_failures:
            raise IncompleteForwardError(summary)

        return summary
