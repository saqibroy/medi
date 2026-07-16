"""Signed double-submit CSRF protection for cookie-authenticated requests."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .settings import Settings, get_settings


CSRF_HEADER_NAME = "X-CSRF-Token"


def session_cookie_name(settings: Settings | None = None) -> str:
    return "__Host-medi_session" if (settings or get_settings()).session_cookie_secure else "medi_session"


def csrf_cookie_name(settings: Settings | None = None) -> str:
    return "__Host-medi_csrf" if (settings or get_settings()).session_cookie_secure else "medi_csrf"


def create_csrf_token(binding: str, settings: Settings | None = None) -> str:
    active_settings = settings or get_settings()
    nonce = secrets.token_urlsafe(24)
    signature = hmac.new(active_settings.csrf_secret.encode(), f"{binding}.{nonce}".encode(), hashlib.sha256).hexdigest()
    return f"{nonce}.{signature}"


def verify_csrf_token(token: str, binding: str, settings: Settings | None = None) -> bool:
    try:
        nonce, supplied_signature = token.split(".", 1)
    except ValueError:
        return False
    active_settings = settings or get_settings()
    expected_signature = hmac.new(active_settings.csrf_secret.encode(), f"{binding}.{nonce}".encode(), hashlib.sha256).hexdigest()
    return bool(nonce) and hmac.compare_digest(supplied_signature, expected_signature)


def set_csrf_cookie(response: Response, token: str, settings: Settings | None = None) -> None:
    active_settings = settings or get_settings()
    response.set_cookie(
        key=csrf_cookie_name(active_settings),
        value=token,
        secure=active_settings.session_cookie_secure,
        httponly=False,
        samesite=active_settings.session_cookie_samesite,
        path="/",
    )


def set_session_cookie(response: Response, token: str, expires_at: datetime, settings: Settings | None = None) -> None:
    """Set the opaque credential using host-only browser-cookie protections."""

    active_settings = settings or get_settings()
    max_age = max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
    response.set_cookie(
        key=session_cookie_name(active_settings),
        value=token,
        max_age=max_age,
        secure=active_settings.session_cookie_secure,
        httponly=True,
        samesite=active_settings.session_cookie_samesite,
        path="/",
    )


class CsrfProtectionMiddleware(BaseHTTPMiddleware):
    """Require matching, correctly signed cookie/header tokens on unsafe requests."""

    def __init__(self, app: object, settings: Settings | None = None) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.settings = settings or get_settings()

    async def dispatch(self, request: Request, call_next: object) -> Response:
        explicit_bearer = request.headers.get("Authorization", "").startswith("Bearer ")
        if request.method in {"GET", "HEAD", "OPTIONS"} or (explicit_bearer and request.url.path != "/auth/login"):
            return await call_next(request)  # type: ignore[operator]

        session_token = request.cookies.get(session_cookie_name(self.settings))
        binding = session_token or "anonymous"
        cookie_token = request.cookies.get(csrf_cookie_name(self.settings), "")
        header_token = request.headers.get(CSRF_HEADER_NAME, "")
        if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token) or not verify_csrf_token(header_token, binding, self.settings):
            return JSONResponse(status_code=403, content={"detail": "CSRF validation failed"})
        return await call_next(request)  # type: ignore[operator]
