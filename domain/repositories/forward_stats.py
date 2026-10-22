"""Abstraction for forwarded event counters."""

from __future__ import annotations

from typing import Protocol


class ForwardStatsRecorder(Protocol):
    """Records how many events a forwarding window delivered."""

    def record(self, sent: int, failed: int) -> None:
        """Add the outcome of one window to the running totals."""
