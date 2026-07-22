"""Database pool, timeout, and privacy-safe slow-query coverage."""

import json
import logging

from sqlalchemy import create_engine, literal, select

from backend import database
from backend.observability import JsonFormatter, database_logger
from backend.settings import get_settings


def test_postgresql_engine_receives_bounded_pool_and_statement_timeout(monkeypatch) -> None:
    captured: dict[str, object] = {}
    sentinel = object()

    def capture_create_engine(url: str, **options: object) -> object:
        captured["url"] = url
        captured["options"] = options
        return sentinel

    monkeypatch.setattr(database, "create_engine", capture_create_engine)
    settings = get_settings(
        {
            "DATABASE_URL": "postgresql+psycopg://medi:secret@database.example.test:5432/medi",
            "DATABASE_POOL_SIZE": "7",
            "DATABASE_MAX_OVERFLOW": "3",
            "DATABASE_POOL_TIMEOUT_SECONDS": "4",
            "DATABASE_STATEMENT_TIMEOUT_MS": "12000",
            "DATABASE_SLOW_QUERY_THRESHOLD_MS": "250",
        }
    )

    result = database.create_database_engine(settings, observe=False)

    assert result is sentinel
    assert captured["url"] == settings.database_url
    assert captured["options"] == {
        "echo": False,
        "pool_size": 7,
        "max_overflow": 3,
        "pool_timeout": 4,
        "pool_pre_ping": True,
        "connect_args": {"options": "-c statement_timeout=12000"},
    }


def test_sqlite_fallback_does_not_receive_postgresql_options(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def capture_create_engine(_url: str, **options: object) -> object:
        captured.update(options)
        return object()

    monkeypatch.setattr(database, "create_engine", capture_create_engine)

    database.create_database_engine(get_settings({"DATABASE_URL": "sqlite:///./local-dev.db"}), observe=False)

    assert captured == {"echo": False, "connect_args": {"check_same_thread": False}}


def test_slow_query_signal_contains_only_allowlisted_operational_fields(caplog) -> None:
    test_engine = create_engine("sqlite://")
    database.install_database_observability(test_engine, slow_query_threshold_ms=0)
    previous_propagation = database_logger.propagate
    database_logger.propagate = True
    try:
        with caplog.at_level(logging.WARNING, logger="medi.database"):
            with test_engine.connect() as connection:
                connection.execute(select(literal("private-patient-value"))).scalar_one()
    finally:
        database_logger.propagate = previous_propagation
        test_engine.dispose()

    record = next(record for record in caplog.records if record.name == "medi.database")
    payload = json.loads(JsonFormatter().format(record))

    assert payload["event"] == "database_slow_query"
    assert payload["database_operation"] == "select"
    assert payload["duration_ms"] >= 0
    assert set(payload) <= {"timestamp", "level", "event", "request_id", "duration_ms", "database_operation"}
    assert "private-patient-value" not in json.dumps(payload)
