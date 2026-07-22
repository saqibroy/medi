"""Database infrastructure for the FastAPI medical annotation backend.

This module owns the SQLAlchemy engine, session factory, and declarative Base.
Keeping this in one place makes the rest of the app depend on a small, testable
database boundary instead of constructing database connections inside routers.
"""

from collections.abc import Generator
from time import perf_counter
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .observability import database_logger
from .settings import Settings, get_settings


def _database_operation(context: Any) -> str:
    """Return a bounded operation label without inspecting or logging SQL text."""

    for attribute, operation in (("isinsert", "insert"), ("isupdate", "update"), ("isdelete", "delete")):
        if getattr(context, attribute, False):
            return operation
    compiled_statement = getattr(getattr(context, "compiled", None), "statement", None)
    if getattr(compiled_statement, "is_select", False):
        return "select"
    return "other"


def install_database_observability(database_engine: Engine, slow_query_threshold_ms: int) -> None:
    """Emit duration-only slow-query signals with no SQL, values, or table names."""

    @event.listens_for(database_engine, "before_cursor_execute")
    def remember_query_start(
        _connection: object,
        _cursor: object,
        _statement: str,
        _parameters: object,
        context: Any,
        _executemany: bool,
    ) -> None:
        context.medi_query_started_at = perf_counter()

    @event.listens_for(database_engine, "after_cursor_execute")
    def report_slow_query(
        _connection: object,
        _cursor: object,
        _statement: str,
        _parameters: object,
        context: Any,
        _executemany: bool,
    ) -> None:
        started_at = getattr(context, "medi_query_started_at", None)
        if started_at is None:
            return
        duration_ms = (perf_counter() - started_at) * 1000
        if duration_ms < slow_query_threshold_ms:
            return
        database_logger.warning(
            "database_slow_query",
            extra={
                "event": "database_slow_query",
                "duration_ms": round(duration_ms, 2),
                "database_operation": _database_operation(context),
            },
        )


def create_database_engine(settings: Settings, *, observe: bool = True) -> Engine:
    """Create the application engine with bounded PostgreSQL runtime controls."""

    engine_options: dict[str, object] = {"echo": False}
    if settings.database_url.startswith("sqlite"):
        # SQLite remains a local/test fallback and does not support PostgreSQL's
        # per-connection statement timeout option.
        engine_options["connect_args"] = {"check_same_thread": False}
    else:
        engine_options.update(
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout_seconds,
            pool_pre_ping=True,
        )
        if settings.database_url.startswith("postgresql"):
            engine_options["connect_args"] = {
                "options": f"-c statement_timeout={settings.database_statement_timeout_ms}",
            }

    database_engine = create_engine(settings.database_url, **engine_options)
    if observe:
        install_database_observability(database_engine, settings.database_slow_query_threshold_ms)
    return database_engine


class Base(DeclarativeBase):
    """Base class that all ORM models inherit from.

    SQLAlchemy uses this registry to discover mapped tables for Alembic
    migrations and focused test database setup.
    """


_settings = get_settings()
DATABASE_URL = _settings.database_url
engine = create_database_engine(_settings)

SessionLocal = sessionmaker(
    autocommit=False,  # Each request should decide when a transaction commits.
    autoflush=False,  # Avoid surprise writes before service code is ready.
    bind=engine,
    class_=Session,
)


async def get_db() -> Generator[Session, None, None]:
    """Yield one SQLAlchemy Session per request using FastAPI dependency injection.

    FastAPI sees this function in Depends(get_db), runs it before the endpoint,
    gives the yielded Session to the route handler, then resumes the function
    after the response is built so the finally block can close the connection.
    """

    db = SessionLocal()
    try:
        yield db
    finally:
        # Closing returns the connection to SQLAlchemy's pool. Without this,
        # busy APIs eventually exhaust available PostgreSQL connections.
        db.close()
