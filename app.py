"""Composition root for the Stellar Cyber alert forwarder."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from dotenv import load_dotenv

from config.settings import Settings
from domain.errors import ConfigurationError, ForwarderError
from domain.services.forward_service import ForwardService
from infrastructure.destination.http_destination import HttpDestination
from infrastructure.logging.logger import configure_logging, get_logger
from infrastructure.stats.forward_stats import ForwardStatsStore
from infrastructure.stellar.query_builder import StellarSearchQueryBuilder
from infrastructure.stellar.stellar_client import StellarClient
from infrastructure.stellar.stellar_repository import StellarRepository
from scheduler.scheduler import Scheduler, resolve_initial_start

logger = get_logger()


def build_destination(settings: Settings) -> HttpDestination:
    return HttpDestination(
        url=settings.destination.url,
        api_key=settings.destination.api_key,
        sensor_id=settings.destination.sensor_id,
        request_timeout=settings.destination.request_timeout,
        log_request=settings.logging.log_request,
        log_response=settings.logging.log_response,
    )


def build_stats(settings: Settings) -> ForwardStatsStore | None:
    if not settings.stats.enabled:
        return None
    return ForwardStatsStore(
        path=settings.stats.file,
        retention_days=settings.stats.retention_days,
    )


def build_scheduler(
    settings: Settings,
    destination: HttpDestination,
    stats: ForwardStatsStore | None = None,
) -> Scheduler:
    query_builder = StellarSearchQueryBuilder(settings.stellar.search_time_zone)
    client = StellarClient(
        host=settings.stellar.host,
        refresh_token=settings.stellar.refresh_token,
        verify_tls=settings.stellar.verify_tls,
        request_timeout=settings.stellar.request_timeout,
    )
    source = StellarRepository(client, query_builder)
    service = ForwardService(source, destination, stats=stats)

    time_zone = query_builder.time_zone
    interval = timedelta(minutes=settings.scheduler.run_interval_minutes)
    initial_start = resolve_initial_start(
        settings.scheduler.initial_start_time,
        settings.scheduler.initial_lookback_minutes,
        interval,
        datetime.now(time_zone),
    )

    return Scheduler(
        service=service,
        interval=interval,
        time_zone=time_zone,
        initial_start=initial_start,
        run_once=settings.scheduler.run_once,
    )


def log_run_summary(stats: ForwardStatsStore | None) -> None:
    if stats is None:
        return

    snapshot = stats.snapshot()
    logger.info(
        "Run summary: forwarded today=%d, lifetime=%d, "
        "failed today=%d, lifetime=%d",
        snapshot.today_forwarded,
        snapshot.lifetime_forwarded,
        snapshot.today_failed,
        snapshot.lifetime_failed,
    )


def main() -> int:
    load_dotenv()

    try:
        settings = Settings.from_env()
    except ConfigurationError as exc:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        logger.error("Configuration error: %s", exc)
        return 1

    configure_logging(
        settings.logging.log_file,
        level=settings.logging.level,
        enabled=settings.logging.enabled,
        retention_days=settings.logging.retention_days,
    )

    stats = build_stats(settings)

    try:
        with build_destination(settings) as destination:
            try:
                build_scheduler(settings, destination, stats).run()
            finally:
                log_run_summary(stats)
    except ForwarderError as exc:
        logger.error("Forwarder stopped: %s: %s", type(exc).__name__, exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
