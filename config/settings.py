"""Environment-backed application settings."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from domain.errors import ConfigurationError

DEFAULT_SEARCH_TIME_ZONE = "+07:00"
DEFAULT_REQUEST_TIMEOUT = "30"
DEFAULT_RUN_INTERVAL_MINUTES = "5"
DEFAULT_LOG_FILE = "log.txt"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_RETENTION_DAYS = "7"
DEFAULT_STATS_FILE = "stats.json"
DEFAULT_STATS_RETENTION_DAYS = "30"
_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_TRUE_VALUES = ("true", "1", "yes")
_FALSE_VALUES = ("false", "0", "no")


def _read(env: Mapping[str, str], name: str, default: str = "") -> str:
    return (env.get(name, default) or "").strip()


def _read_first(env: Mapping[str, str], *names: str) -> str:
    for name in names:
        value = _read(env, name)
        if value:
            return value
    return ""


def _read_bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = _read(env, name)
    if not raw:
        return default

    normalized = raw.lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False

    raise ConfigurationError(f"{name} must be one of true/false, 1/0, yes/no")


def _parse_log_level(name: str, raw: str) -> int:
    normalized = (raw or DEFAULT_LOG_LEVEL).upper()
    if normalized not in _LOG_LEVELS:
        raise ConfigurationError(
            f"{name} must be one of " + ", ".join(_LOG_LEVELS)
        )
    return getattr(logging, normalized)


def _positive_int(name: str, raw: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"{name} must be a positive integer") from exc

    if value <= 0:
        raise ConfigurationError(f"{name} must be a positive integer")
    return value


def _non_negative_int(name: str, raw: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(
            f"{name} must be zero or a positive integer"
        ) from exc

    if value < 0:
        raise ConfigurationError(f"{name} must be zero or a positive integer")
    return value


def _parse_timestamp(name: str, raw: str) -> datetime | None:
    if not raw:
        return None

    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConfigurationError(
            f"{name} must be an ISO 8601 timestamp, "
            "e.g. 2026-10-21T00:00:00+07:00"
        ) from exc


@dataclass(frozen=True)
class StellarSettings:
    host: str
    refresh_token: str
    verify_tls: bool
    request_timeout: int
    search_time_zone: str


@dataclass(frozen=True)
class DestinationSettings:
    url: str
    api_key: str
    sensor_id: str
    request_timeout: int


@dataclass(frozen=True)
class LoggingSettings:
    log_file: str
    enabled: bool
    level: int
    log_request: bool
    log_response: bool
    retention_days: int


@dataclass(frozen=True)
class StatsSettings:
    enabled: bool
    file: str
    retention_days: int


@dataclass(frozen=True)
class SchedulerSettings:
    run_interval_minutes: int
    initial_lookback_minutes: int | None
    initial_start_time: datetime | None
    run_once: bool


@dataclass(frozen=True)
class Settings:
    stellar: StellarSettings
    destination: DestinationSettings
    logging: LoggingSettings
    stats: StatsSettings
    scheduler: SchedulerSettings

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        source = os.environ if env is None else env
        request_timeout = _positive_int(
            "REQUEST_TIMEOUT", _read(source, "REQUEST_TIMEOUT", DEFAULT_REQUEST_TIMEOUT)
        )

        host = _read(source, "STELLAR_HOST")
        if not host:
            raise ConfigurationError(
                "Missing STELLAR_HOST in environment configuration"
            )

        refresh_token = _read(source, "STELLAR_REFRESH_TOKEN")
        if not refresh_token:
            raise ConfigurationError(
                "Missing STELLAR_REFRESH_TOKEN in environment configuration"
            )

        destination_url = _read(source, "DESTINATION_API_URL")
        api_key = _read_first(source, "DESTINATION_API_KEY", "API_KEY")
        sensor_id = _read(source, "SENSOR_ID")
        missing = [
            name
            for name, value in (
                ("DESTINATION_API_URL", destination_url),
                ("API_KEY", api_key),
                ("SENSOR_ID", sensor_id),
            )
            if not value
        ]
        if missing:
            raise ConfigurationError(
                "Missing destination configuration: " + ", ".join(missing)
            )

        if not destination_url.startswith(("https://", "http://")):
            raise ConfigurationError(
                "DESTINATION_API_URL must include http:// or https://"
            )

        if any(char in api_key for char in "\r\n"):
            raise ConfigurationError("API_KEY must not contain line breaks")

        lookback_minutes = _read_first(
            source, "INITIAL_LOOKBACK_MINUTES", "INITIAL_LOOPBACK_MINUTES"
        )
        interval_minutes = (
            _read_first(source, "RUN_INTERVAL_MINUTES", "POLL_INTERVAL_MINUTES")
            or DEFAULT_RUN_INTERVAL_MINUTES
        )

        return cls(
            stellar=StellarSettings(
                host=host,
                refresh_token=refresh_token,
                verify_tls=_read(source, "STELLAR_VERIFY_TLS", "true").lower()
                in _TRUE_VALUES,
                request_timeout=request_timeout,
                search_time_zone=_read(source, "SEARCH_TIME_ZONE")
                or DEFAULT_SEARCH_TIME_ZONE,
            ),
            destination=DestinationSettings(
                url=destination_url,
                api_key=api_key,
                sensor_id=sensor_id,
                request_timeout=request_timeout,
            ),
            logging=LoggingSettings(
                log_file=_read(source, "LOG_FILE") or DEFAULT_LOG_FILE,
                enabled=_read_bool(source, "LOG_ENABLED", True),
                level=_parse_log_level(
                    "LOG_LEVEL", _read(source, "LOG_LEVEL", DEFAULT_LOG_LEVEL)
                ),
                log_request=_read_bool(source, "LOG_REQUEST", True),
                log_response=_read_bool(source, "LOG_RESPONSE", True),
                retention_days=_non_negative_int(
                    "LOG_RETENTION_DAYS",
                    _read(source, "LOG_RETENTION_DAYS", DEFAULT_LOG_RETENTION_DAYS),
                ),
            ),
            stats=StatsSettings(
                enabled=_read_bool(source, "STATS_ENABLED", True),
                file=_read(source, "STATS_FILE") or DEFAULT_STATS_FILE,
                retention_days=_positive_int(
                    "STATS_RETENTION_DAYS",
                    _read(
                        source,
                        "STATS_RETENTION_DAYS",
                        DEFAULT_STATS_RETENTION_DAYS,
                    ),
                ),
            ),
            scheduler=SchedulerSettings(
                run_interval_minutes=_positive_int(
                    "RUN_INTERVAL_MINUTES", interval_minutes
                ),
                initial_lookback_minutes=_positive_int(
                    "INITIAL_LOOKBACK_MINUTES", lookback_minutes
                )
                if lookback_minutes
                else None,
                initial_start_time=_parse_timestamp(
                    "INITIAL_START_TIME", _read(source, "INITIAL_START_TIME")
                ),
                run_once=_read(source, "RUN_ONCE", "false").lower() in _TRUE_VALUES,
            ),
        )
