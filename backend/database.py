"""Database infrastructure for the FastAPI medical annotation backend.

This module owns the SQLAlchemy engine, session factory, and declarative Base.
Keeping this in one place makes the rest of the app depend on a small, testable
database boundary instead of constructing database connections inside routers.
"""

from collections.abc import Generator
from os import getenv

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# In production this would point at a managed PostgreSQL instance. The default
# keeps the learning project explicit: PostgreSQL is the intended database, and
# developers can override it with DATABASE_URL in local shells or Docker.
DATABASE_URL = getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/medical_annotations",
)


class Base(DeclarativeBase):
    """Base class that all ORM models inherit from.

    SQLAlchemy uses this registry to discover mapped tables when we call
    Base.metadata.create_all(...) in this educational project or migrations in a
    more realistic production setup.
    """


engine = create_engine(
    DATABASE_URL,
    echo=False,  # Flip to True when learning SQLAlchemy and you want SQL logs.
    # SQLite is only used as a local fallback for this runnable demo. The
    # check_same_thread flag lets FastAPI request handlers share the same engine
    # safely across worker threads.
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(
    autocommit=False,  # Each request should decide when a transaction commits.
    autoflush=False,  # Avoid surprise writes before service code is ready.
    bind=engine,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
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
