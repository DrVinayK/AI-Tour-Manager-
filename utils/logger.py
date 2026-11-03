"""
Structured logging helper.

Replaces scattered `print()` calls with proper `logging`, formatted as one
JSON object per line (easy to grep, and drop straight into any log
aggregator — CloudWatch, Datadog, Loki, etc. — without a custom parser).

Usage:
    from utils.logger import get_logger
    log = get_logger(__name__)

    log.info("specialist_completed", extra={"agent": "weather_agent", "duration_ms": 812})
"""

import json
import logging
import os
import sys
import time


class JsonFormatter(logging.Formatter):
    """Renders each log record as a single-line JSON object."""

    # Standard LogRecord attributes we don't want echoed back as "extra"
    # noise — anything NOT in this set on the record is assumed to have
    # been passed in via `extra={...}` and gets included in the output.
    _RESERVED = set(logging.LogRecord(
        "", 0, "", 0, "", (), None
    ).__dict__.keys()) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key not in self._RESERVED:
                try:
                    json.dumps(value)  # only include JSON-serializable extras
                    payload[key] = value
                except TypeError:
                    payload[key] = str(value)

        return json.dumps(payload, default=str)


_CONFIGURED = False


def _configure_root():
    global _CONFIGURED
    if _CONFIGURED:
        return
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, level_name, logging.INFO))
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Get a module-level structured logger, configuring the root logger
    (once) the first time this is called."""
    _configure_root()
    return logging.getLogger(name)


class timed_block:
    """Small context manager for logging how long a block of code took.

    Usage:
        with timed_block(log, "weather_agent_run", agent="weather_agent") as t:
            ... do work ...
        # t.duration_ms is available after the block exits, and a log line
        # is emitted automatically.
    """

    def __init__(self, logger: logging.Logger, event: str, level: int = logging.INFO, **extra):
        self.logger = logger
        self.event = event
        self.level = level
        self.extra = extra
        self.duration_ms = None

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.duration_ms = round((time.perf_counter() - self._start) * 1000, 1)
        extra = {**self.extra, "duration_ms": self.duration_ms}
        if exc_type is not None:
            extra["status"] = "error"
            extra["error"] = str(exc)
            self.logger.error(f"{self.event}_failed", extra=extra)
        else:
            extra.setdefault("status", "ok")
            self.logger.log(self.level, self.event, extra=extra)
        return False  # never suppress the exception
