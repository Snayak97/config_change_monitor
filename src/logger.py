"""
Structured logging module for Configuration Change Monitoring System.
Supports JSON logging for production observability and formatted console output.
"""

import sys
import json
import logging
from loguru import logger
from src.config import get_settings


def serialize_json_log(record) -> str:
    """Format Loguru record as JSON for structured log aggregators."""
    log_entry = {
        "timestamp": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "level": record["level"].name,
        "message": record["message"],
        "module": record["module"],
        "function": record["function"],
        "line": record["line"],
        "extra": record["extra"]
    }
    if record["exception"]:
        log_entry["exception"] = {
            "type": record["exception"].type.__name__ if record["exception"].type else "Exception",
            "value": str(record["exception"].value),
            "traceback": record["exception"].traceback is not None
        }
    return json.dumps(log_entry)


class InterceptHandler(logging.Handler):
    """Intercept standard Python logging and redirect through Loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging():
    """Configure Loguru structured logging based on application settings."""
    settings = get_settings()
    logger.remove()

    if settings.log_format.lower() == "json":
        # Structured JSON Sink
        logger.add(
            sys.stdout,
            level=settings.log_level.upper(),
            format="{message}",
            serialize=True
        )
    else:
        # Human-friendly Colored Sink
        logger.add(
            sys.stdout,
            level=settings.log_level.upper(),
            colorize=True,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        )

    # Intercept standard library logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for uvicorn_logger in ("uvicorn", "uvicorn.error", "uvicorn.access", "watchdog"):
        _log = logging.getLogger(uvicorn_logger)
        _log.handlers = [InterceptHandler()]
        _log.propagate = False

    return logger
