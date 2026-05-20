"""Structured logging with structlog, JSON output, trace_id injection."""
from __future__ import annotations

import structlog


def setup_logging(*, json_output: bool = True) -> None:
    """Configure structlog for the application.

    Args:
        json_output: If True, output JSON lines. If False, use console renderer.
    """
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_output:
        processors.append(structlog.processors.JSONRenderer(ensure_ascii=False))
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a bound logger instance."""
    return structlog.get_logger(name)
