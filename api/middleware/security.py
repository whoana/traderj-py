"""Security headers and logging safety middleware."""

from __future__ import annotations

import logging
import re

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

_SENSITIVE_KV = re.compile(
    r"(api[_-]?key|token|secret|password|authorization)[=:\s]+\S+",
    re.IGNORECASE,
)

_BEARER = re.compile(r"Bearer\s+\S+", re.IGNORECASE)


class SensitiveDataFilter(logging.Filter):
    """Prevent API keys and secrets from appearing in logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, "msg") and isinstance(record.msg, str):
            record.msg = _SENSITIVE_KV.sub("[REDACTED]", record.msg)
            record.msg = _BEARER.sub("[REDACTED]", record.msg)
        return True


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"

        return response
