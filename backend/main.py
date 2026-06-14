"""FastAPI entry point for the medical image annotation backend.

This file wires together cross-cutting application concerns: CORS for the React
dev server and router registration for scans and annotations. Database schema
changes are owned by Alembic migrations.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import annotations, auth, projects, scans


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    A factory function makes tests easier because each test can construct a fresh
    app without importing a process-global ASGI object.
    """

    app = FastAPI(
        title="Medical Image Annotation Learning API",
        description="Educational FastAPI backend for scan metadata and annotations.",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        # Vite uses 5173 by default and moves to 5174 if the first dev server is
        # already running, so both origins are allowed for local interview demos.
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(projects.router)
    app.include_router(scans.router)
    app.include_router(annotations.router)
    return app


app = create_app()
