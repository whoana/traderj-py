"""Structured logging configuration using structlog.

Provides JSON logging for production and human-readable logging for development.
Logs are written to both stderr (console) and logs/ directory (file).

File logging:
  - logs/engine.log              — today's log file
  - logs/engine.log.2026-03-02   — yesterday's log (auto-rotated at midnight)
  - Keeps last 30 days, older files are auto-deleted
  - Always JSON format for easy parsing

Console logging:
  - development: human-readable colored output
  - production:  JSON output

Environment variables:
  - TRADERJ_ENV: development | production
  - LOG_DIR: log directory path (default: logs/)
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import structlog


def _reorder_keys(
    _logger: logging.Logger, _method: str, event_dict: dict,
) -> dict:
    """Reorder event dict keys: timestamp, level, logger, event, ...rest."""
    ordered = {}
    for key in ("timestamp", "level", "logger", "event"):
        if key in event_dict:
            ordered[key] = event_dict.pop(key)
    ordered.update(event_dict)
    return ordered


def setup_logging(level: str = "INFO", log_dir: str | None = None) -> None:
    """Configure structlog for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        log_dir: Directory for log files. Defaults to LOG_DIR env or 'logs/'.
    """
    env = os.environ.get("TRADERJ_ENV", "development")
    is_production = env == "production"
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Resolve log directory
    log_path = Path(log_dir or os.environ.get("LOG_DIR", "logs"))
    log_path.mkdir(parents=True, exist_ok=True)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if is_production:
        console_processors: list[structlog.types.Processor] = [_reorder_keys, structlog.processors.JSONRenderer()]
    else:
        console_processors = [structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())]

    # File processors: reorder keys then render as JSON
    file_processors: list[structlog.types.Processor] = [_reorder_keys, structlog.processors.JSONRenderer()]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Console handler (stderr)
    console_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            *console_processors,
        ],
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)

    # File handler (TimedRotatingFileHandler: daily rotation, 30 days retention)
    file_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            *file_processors,
        ],
    )
    file_handler = TimedRotatingFileHandler(
        filename=str(log_path / "engine.log"),
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(file_formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(console_handler)
    root.addHandler(file_handler)
    root.setLevel(log_level)

    # Quiet noisy libraries
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("ccxt").setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging configured: level=%s, file=%s", level, log_path / "engine.log"
    )
