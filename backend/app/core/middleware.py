"""Request ID, body-size limit and baseline security headers.

Caddy sets the full header set (CSP, HSTS...) in production. The API repeats the
headers that matter for JSON responses so it stays safe even when reached directly.
"""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.errors import problem_response
from app.core.logging import request_id_var

logger = logging.getLogger("app.request")

_API_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        super().__init__(app)
        self.max_body_bytes = max_body_bytes

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _is_uuid(incoming) else str(uuid.uuid4())
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            length = request.headers.get("content-length")
            if length is not None and (not length.isdigit() or int(length) > self.max_body_bytes):
                response: Response = problem_response(
                    413, "PAYLOAD_TOO_LARGE", "Tijelo zahtjeva je preveliko."
                )
            else:
                response = await call_next(request)
            for name, value in _API_HEADERS.items():
                response.headers.setdefault(name, value)
            response.headers["X-Request-ID"] = request_id
            if request.url.path.startswith("/api/"):
                response.headers.setdefault("Cache-Control", "no-store")
            logger.info(
                "request",
                extra={
                    "extra_fields": {
                        "method": request.method,
                        "path": request.url.path,
                        "status": response.status_code,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    }
                },
            )
            return response
        finally:
            request_id_var.reset(token)


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True
