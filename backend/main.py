"""FastAPI entry point for the medical image annotation backend.

This file wires together cross-cutting application concerns: CORS for the React
dev server and router registration for scans and annotations. Database schema
changes are owned by Alembic migrations.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .audit_middleware import SecurityAuditMiddleware
from .observability import RequestLoggingMiddleware, configure_logging
from .rate_limit import RequestRateLimitMiddleware
from .routers import annotations, audit_events, auth, health, projects, scans, users
from .settings import get_settings


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    A factory function makes tests easier because each test can construct a fresh
    app without importing a process-global ASGI object.
    """

    settings = get_settings()
    configure_logging()
    app = FastAPI(
        title="Medical Image Annotation Learning API",
        description="Educational FastAPI backend for scan metadata and annotations.",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        # Development defaults are deliberately local-only. Production must set
        # an exact, reviewed origin list through CORS_ORIGINS.
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        RequestRateLimitMiddleware,
        login_limit=settings.login_rate_limit_per_minute,
        sensitive_limit=settings.sensitive_rate_limit_per_minute,
    )
    app.add_middleware(SecurityAuditMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    app.include_router(auth.router)
    app.include_router(audit_events.router)
    app.include_router(health.router)
    app.include_router(projects.router)
    app.include_router(scans.router)
    app.include_router(annotations.router)
    app.include_router(users.router)
    return app


app = create_app()
