"""Structured JSON logging without secrets, tokens or raw IP addresses (NF05, NF17)."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_REDACTED_KEYS = {"password", "token", "cookie", "authorization", "secret", "csrf"}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("[redacted]" if any(s in k.lower() for s in _REDACTED_KEYS) else _redact(v))
            for k, v in value.items()
        }
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(_redact(extra))
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str) -> None:
    # stderr: CLI commands write data to stdout ('geocode-review > d11.csv'); logs must not mix in.
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Uvicorn's access log prints client IPs; we log requests ourselves instead.
    logging.getLogger("uvicorn.access").disabled = True
