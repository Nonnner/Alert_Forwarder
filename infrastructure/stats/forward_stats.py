"""Keeps forwarded event counters in a JSON file that survives log cleanup."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Mapping

DEFAULT_RETENTION_DAYS = 30

_logger = logging.getLogger("stellar.forwarder")


@dataclass(frozen=True)
class ForwardStatsSnapshot:
    """Point-in-time view of the forwarded event counters."""

    lifetime_forwarded: int
    lifetime_failed: int
    today_forwarded: int
    today_failed: int


def _count(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return value if value > 0 else 0


class ForwardStatsStore:
    """Counts forwarded and failed events for today and over the lifetime."""

    def __init__(
        self,
        path: str,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        clock: Callable[[], datetime] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._path = path
        self._retention_days = retention_days
        self._clock = clock or (lambda: datetime.now().astimezone())
        self._logger = logger or _logger
        self._lifetime = {"forwarded": 0, "failed": 0}
        self._daily: dict[str, dict[str, int]] = {}
        self._active_day: str | None = None
        self._load()

    def record(self, sent: int, failed: int) -> ForwardStatsSnapshot:
        """Add the outcome of one window to the persisted totals."""
        now = self._clock()
        day = now.date().isoformat()
        self._roll_day(day)

        today = self._daily.setdefault(day, {"forwarded": 0, "failed": 0})
        today["forwarded"] += sent
        today["failed"] += failed
        self._lifetime["forwarded"] += sent
        self._lifetime["failed"] += failed

        self._prune(now)
        snapshot = self.snapshot(now)
        self._save(now)
        self._logger.info(
            "Forward totals: today=%d, lifetime=%d, "
            "failed today=%d, lifetime=%d",
            snapshot.today_forwarded,
            snapshot.lifetime_forwarded,
            snapshot.today_failed,
            snapshot.lifetime_failed,
        )
        return snapshot

    def snapshot(self, at: datetime | None = None) -> ForwardStatsSnapshot:
        """Return the current counters without modifying them."""
        day = (at or self._clock()).date().isoformat()
        today = self._daily.get(day, {"forwarded": 0, "failed": 0})
        return ForwardStatsSnapshot(
            lifetime_forwarded=self._lifetime["forwarded"],
            lifetime_failed=self._lifetime["failed"],
            today_forwarded=today["forwarded"],
            today_failed=today["failed"],
        )

    def _roll_day(self, day: str) -> None:
        if self._active_day == day:
            return

        previous = self._daily.get(self._active_day) if self._active_day else None
        if previous is not None:
            self._logger.info(
                "Daily summary %s: forwarded=%d, failed=%d",
                self._active_day,
                previous["forwarded"],
                previous["failed"],
            )

        self._active_day = day

    def _prune(self, now: datetime) -> None:
        cutoff = (now.date() - timedelta(days=self._retention_days)).isoformat()
        for day in [day for day in self._daily if day < cutoff]:
            del self._daily[day]

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as stream:
                payload = json.load(stream)
        except FileNotFoundError:
            self._logger.info("Forward stats file %s not found yet", self._path)
            return
        except (OSError, ValueError) as exc:
            self._logger.warning(
                "Cannot read forward stats %s: %s", self._path, exc
            )
            return

        if not isinstance(payload, Mapping):
            self._logger.warning(
                "Ignoring forward stats %s: not a JSON object", self._path
            )
            return

        lifetime = payload.get("lifetime")
        if isinstance(lifetime, Mapping):
            self._lifetime = {
                "forwarded": _count(lifetime.get("forwarded")),
                "failed": _count(lifetime.get("failed")),
            }

        daily = payload.get("daily")
        if isinstance(daily, Mapping):
            self._daily = {
                str(day): {
                    "forwarded": _count(counters.get("forwarded")),
                    "failed": _count(counters.get("failed")),
                }
                for day, counters in daily.items()
                if isinstance(counters, Mapping)
            }

        days = sorted(self._daily)
        self._active_day = days[-1] if days else None
        self._prune(self._clock())
        self._logger.info(
            "Forward stats loaded from %s: lifetime forwarded=%d, failed=%d",
            self._path,
            self._lifetime["forwarded"],
            self._lifetime["failed"],
        )

    def _save(self, now: datetime) -> None:
        payload = {
            "lifetime": dict(self._lifetime),
            "daily": self._daily,
            "updated_at": now.isoformat(timespec="seconds"),
        }
        temp_path = f"{self._path}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.write("\n")
            os.replace(temp_path, self._path)
        except OSError as exc:
            self._logger.error(
                "Cannot write forward stats %s: %s", self._path, exc
            )
            try:
                os.remove(temp_path)
            except OSError:
                pass
