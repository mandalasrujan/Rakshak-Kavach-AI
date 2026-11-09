"""Structured JSON logging. Logs carry IDs and metadata only, never PHI or secrets."""

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

# Defence in depth: values under these keys are always masked, even if logged by mistake.
SENSITIVE_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "email",
        "token",
        "access_token",
        "jwt",
        "cookie",
        "cookies",
        "authorization",
        "secret",
        "jwt_secret_key",
        "body",
    }
)
REDACTED = "[REDACTED]"


def redact_sensitive(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict):
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = REDACTED
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_sensitive,
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "arq"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    # Access logs would include query strings; our middleware logs path-only access lines.
    logging.getLogger("uvicorn.access").disabled = True
