"""Application logging setup."""

from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler

LOGGER_NAME = "stellar.forwarder"


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def configure_logging(
    log_file: str = "log.txt",
    level: int = logging.INFO,
    enabled: bool = True,
    retention_days: int = 0,
) -> logging.Logger:
    """Configure console and file handlers once and return the logger.

    The file handler rotates at midnight into ``<log_file>.YYYY-MM-DD`` and
    deletes backups older than ``retention_days`` (0 keeps every backup).
    """
    logger = get_logger()
    if logger.handlers:
        return logger

    logger.propagate = False

    if not enabled:
        logger.disabled = True
        logger.addHandler(logging.NullHandler())
        return logger

    logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        file_handler = TimedRotatingFileHandler(
            log_file,
            when="midnight",
            backupCount=retention_days,
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Cannot write log file %s: %s", log_file, exc)
    else:
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
