"""Fail-closed request boundary for security audit events."""

from collections.abc import Callable

from fastapi import Request
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .database import SessionLocal
from .services import audit_service
from .settings import get_settings


class SecurityAuditMiddleware(BaseHTTPMiddleware):
    """Append events for the explicitly mapped security-sensitive routes."""

    def __init__(self, app: object, session_factory: Callable[[], Session] = SessionLocal) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.session_factory = session_factory
        self.signing_key = get_settings().audit_signing_key

    async def dispatch(self, request: Request, call_next: object) -> Response:
        try:
            response = await call_next(request)  # type: ignore[operator]
        except Exception:
            route = audit_service.route_for_request(request)
            if route is not None:
                self._write(request, route, 500)
            raise

        route = audit_service.route_for_request(request)
        if route is not None:
            self._write(request, route, response.status_code)
        return response

    def _write(self, request: Request, route: audit_service.AuditRoute, status_code: int) -> None:
        with self.session_factory() as db:
            audit_service.create_event_for_request(db, request, route, status_code, self.signing_key)
