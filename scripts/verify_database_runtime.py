#!/usr/bin/env python3
"""Verify application PostgreSQL pool bounds and statement cancellation safely."""

from __future__ import annotations

from time import perf_counter

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.pool import QueuePool

from backend.database import engine
from backend.settings import get_settings


def main() -> None:
    settings = get_settings()
    if settings.is_production:
        raise SystemExit("Database runtime verification must not run with APP_ENV=production")
    database_name = make_url(settings.database_url).database or ""
    if not database_name.startswith("medi_migration_"):
        raise SystemExit("Database runtime verification is restricted to disposable medi_migration_ databases")
    if settings.database_statement_timeout_ms > 2000:
        raise SystemExit("Database runtime verification requires DATABASE_STATEMENT_TIMEOUT_MS <= 2000")
    if not isinstance(engine.pool, QueuePool):
        raise SystemExit("Application PostgreSQL engine must use a bounded QueuePool")
    if engine.pool.size() != settings.database_pool_size:
        raise SystemExit("Configured database pool size was not applied")
    if getattr(engine.pool, "_max_overflow", None) != settings.database_max_overflow:
        raise SystemExit("Configured database pool overflow bound was not applied")
    if engine.pool.timeout() != settings.database_pool_timeout_seconds:
        raise SystemExit("Configured database pool acquisition timeout was not applied")

    with engine.connect() as connection:
        effective_timeout_ms = int(
            connection.scalar(
                text("SELECT EXTRACT(EPOCH FROM current_setting('statement_timeout')::interval) * 1000")
            )
        )
        if effective_timeout_ms != settings.database_statement_timeout_ms:
            raise SystemExit("Configured PostgreSQL statement timeout was not applied")

        started_at = perf_counter()
        try:
            connection.execute(text("SELECT pg_sleep(:seconds)"), {"seconds": settings.database_statement_timeout_ms / 1000 + 1})
        except DBAPIError as error:
            if getattr(error.orig, "sqlstate", None) != "57014":
                raise SystemExit("Synthetic statement failed for a reason other than PostgreSQL cancellation") from None
            elapsed_ms = (perf_counter() - started_at) * 1000
            if elapsed_ms > settings.database_statement_timeout_ms + 1500:
                raise SystemExit("PostgreSQL did not cancel the synthetic slow statement within the expected bound")
        else:
            raise SystemExit("PostgreSQL did not cancel the synthetic slow statement")
        finally:
            connection.rollback()

    held_connections = [
        engine.connect()
        for _ in range(settings.database_pool_size + settings.database_max_overflow)
    ]
    started_at = perf_counter()
    try:
        try:
            unexpected_connection = engine.connect()
        except SQLAlchemyTimeoutError:
            elapsed_seconds = perf_counter() - started_at
            if elapsed_seconds > settings.database_pool_timeout_seconds + 1:
                raise SystemExit("Database connection acquisition did not fail within the expected bound")
        else:
            unexpected_connection.close()
            raise SystemExit("Database pool exceeded its configured connection bound")
    finally:
        for connection in held_connections:
            connection.close()

    engine.dispose()
    print("PostgreSQL application pool, acquisition-timeout, and statement-timeout verification passed.")


if __name__ == "__main__":
    main()
