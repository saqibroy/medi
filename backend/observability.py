"""Safe structured request logging for the API process."""

from __future__ import annotations

import json
import logging
import sys
import time
from contextvars import ContextVar
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
request_logger = logging.getLogger("medi.request")
class JsonFormatter(logging.Formatter):
    """Format only approved operational fields and redact sensitive values."""

    converter = time.gmtime

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "event": getattr(record, "event", record.getMessage()),
            "request_id": getattr(record, "request_id", request_id_context.get()),
            "method": getattr(record, "method", None),
            "path": getattr(record, "path", None),
            "status_code": getattr(record, "status_code", None),
            "duration_ms": getattr(record, "duration_ms", None),
        }
        return json.dumps({key: value for key, value in payload.items() if value is not None}, separators=(",", ":"))


def configure_logging() -> None:
    """Install one stdout JSON handler without changing third-party loggers."""

    if request_logger.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    request_logger.addHandler(handler)
    request_logger.setLevel(logging.INFO)
    request_logger.propagate = False


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID and log request outcomes without sensitive payloads."""

    async def dispatch(self, request: Request, call_next: object) -> Response:
        request_id = uuid4().hex
        context_token = request_id_context.set(request_id)
        started_at = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)  # type: ignore[operator]
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            # Do not log exception text: validation errors can contain PHI.
            request_logger.error("request_failed", extra=_request_fields(request, request_id, status_code, started_at))
            raise
        finally:
            if status_code != 500:
                request_logger.info("request_completed", extra=_request_fields(request, request_id, status_code, started_at))
            request_id_context.reset(context_token)


def _request_fields(request: Request, request_id: str, status_code: int, started_at: float) -> dict[str, object]:
    """Return the small allowlist of fields that may leave the request boundary."""

    return {
        "event": "request_completed" if status_code < 500 else "request_failed",
        "request_id": request_id,
        "method": request.method,
        # path excludes query values, which can contain identifiers or free text.
        "path": request.url.path,
        "status_code": status_code,
        "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
    }
