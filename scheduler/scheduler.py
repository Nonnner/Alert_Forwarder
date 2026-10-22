"""Runs the forward use case on a fixed interval."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, tzinfo
from typing import Callable

from domain.errors import ForwarderError
from domain.services.forward_service import ForwardService

_logger = logging.getLogger("stellar.forwarder")


def resolve_initial_start(
    initial_start: datetime | None,
    lookback_minutes: int | None,
    interval: timedelta,
    now: datetime,
) -> datetime:
    """Determine the start of the very first forwarding window."""
    if initial_start is not None:
        return (
            initial_start
            if initial_start.tzinfo
            else initial_start.replace(tzinfo=now.tzinfo)
        )

    lookback = (
        timedelta(minutes=lookback_minutes) if lookback_minutes else interval
    )
    return now - lookback


class Scheduler:
    """Repeatedly forwards consecutive, non-overlapping time windows."""

    def __init__(
        self,
        service: ForwardService,
        interval: timedelta,
        time_zone: tzinfo,
        initial_start: datetime,
        run_once: bool = False,
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        logger: logging.Logger | None = None,
    ) -> None:
        self._service = service
        self._interval = interval
        self._time_zone = time_zone
        self._initial_start = initial_start
        self._run_once = run_once
        self._clock = clock or (lambda: datetime.now(time_zone))
        self._sleep = sleep
        self._logger = logger or _logger

    def run(self) -> None:
        window_start = self._initial_start
        inclusive_start = True

        self._logger.info(
            "Scheduler started: interval=%d minute(s), first window from %s%s",
            int(self._interval.total_seconds() // 60),
            window_start.isoformat(timespec="seconds"),
            ", single run" if self._run_once else "",
        )

        while True:
            cycle_started = self._clock()
            try:
                self._service.forward_window(
                    window_start, cycle_started, inclusive_start
                )
            except ForwarderError as exc:
                self._logger.error(
                    "Cycle failed: %s: %s", type(exc).__name__, exc
                )
                if self._run_once:
                    raise
                self._logger.warning(
                    "Keeping window start %s so the same range is retried",
                    window_start.isoformat(timespec="seconds"),
                )
            else:
                window_start = cycle_started
                inclusive_start = False

            if self._run_once:
                break

            next_run = cycle_started + self._interval
            delay = (next_run - self._clock()).total_seconds()
            if delay > 0:
                self._logger.info(
                    "Next run at %s", next_run.isoformat(timespec="seconds")
                )
                self._sleep(delay)
