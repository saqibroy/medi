"""FastAPI entry point for the medical image annotation backend.

This file wires together cross-cutting application concerns: CORS for the React
dev server, database table creation for the learning environment, and router
registration for scans and annotations.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from .routers import annotations, scans


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    A factory function makes tests easier because each test can construct a fresh
    app. In production, migrations would replace create_all, but create_all keeps
    the interview practice project easy to run locally.
    """

    Base.metadata.create_all(bind=engine)

    app = FastAPI(
        title="Medical Image Annotation Learning API",
        description="Educational FastAPI backend for scan metadata and annotations.",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(scans.router)
    app.include_router(annotations.router)
    return app


app = create_app()
