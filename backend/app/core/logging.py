"""Structured logging configuration.

Local development gets human readable output; non-local environments emit JSON so
logs can be shipped to an enterprise log platform. A request-scoped correlation id is
attached to every record via a ContextVar.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_principal: ContextVar[str | None] = ContextVar("principal", default=None)

_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


def set_request_context(request_id: str | None = None, principal: str | None = None) -> None:
    """Bind correlation values for the current async context."""
    if request_id is not None:
        _request_id.set(request_id)
    if principal is not None:
        _principal.set(principal)


def get_request_id() -> str | None:
    return _request_id.get()


class ContextFilter(logging.Filter):
    """Inject correlation values into every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get() or "-"
        record.principal = _principal.get() or "-"
        record.service = settings.app_name
        record.env = settings.app_env
        return True


class JsonFormatter(logging.Formatter):
    """Minimal dependency-free JSON formatter."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "principal": getattr(record, "principal", "-"),
            "env": getattr(record, "env", "-"),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Initialise root logging. Safe to call multiple times."""
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(ContextFilter())

    if settings.log_json or settings.is_production:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-7s [%(name)s] (req=%(request_id)s) %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level)

    # Third-party noise control.
    for noisy in ("uvicorn.access", "neo4j", "httpx", "httpcore", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.db_echo else logging.WARNING
    )


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger."""
    return logging.getLogger(name)
