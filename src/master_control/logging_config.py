import logging
import sys
from pathlib import Path

import structlog


def configure_logging(log_dir: Path | None = None, level: str = "INFO") -> None:
    """Configure structured logging for the orchestrator process."""
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if sys.stderr.isatty() else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(workload_name: str | None = None, **kwargs: object) -> structlog.BoundLogger:
    """Get a structured logger, optionally bound to a workload name."""
    log = structlog.get_logger()
    if workload_name:
        log = log.bind(workload=workload_name)
    if kwargs:
        log = log.bind(**kwargs)
    return log


def configure_worker_logging(
    workload_name: str, log_file: Path | None = None
) -> None:
    """Configure logging for a worker subprocess. Logs to stderr + optional file."""
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if sys.stderr.isatty() else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    structlog.contextvars.bind_contextvars(workload=workload_name)
