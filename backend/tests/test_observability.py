"""Tests for correlation IDs and payload-safe request logs."""

import json
import logging

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from backend.observability import JsonFormatter, RequestLoggingMiddleware, request_logger


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_request_log_excludes_query_and_authorization_values(caplog: pytest.LogCaptureFixture) -> None:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/safe")
    async def safe() -> dict[str, bool]:
        return {"ok": True}

    previous_propagation = request_logger.propagate
    request_logger.propagate = True
    try:
        with caplog.at_level(logging.INFO, logger="medi.request"):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/safe?patient_name=private", headers={"Authorization": "Bearer very-secret-token"})
    finally:
        request_logger.propagate = previous_propagation

    assert response.status_code == 200
    assert len(response.headers["X-Request-ID"]) == 32
    record = next(record for record in caplog.records if record.name == "medi.request")
    rendered = JsonFormatter().format(record)
    assert '"path":"/safe"' in rendered
    assert "patient_name" not in rendered
    assert "very-secret-token" not in rendered


def test_json_formatter_does_not_include_unapproved_log_record_fields() -> None:
    record = logging.LogRecord("medi.request", logging.INFO, __file__, 1, "request_completed", (), None)
    record.request_id = "request-1"  # type: ignore[attr-defined]
    record.path = "/health/live"  # type: ignore[attr-defined]
    record.password = "must-not-appear"  # type: ignore[attr-defined]

    payload = json.loads(JsonFormatter().format(record))

    assert payload["request_id"] == "request-1"
    assert "password" not in payload


@pytest.mark.anyio
async def test_database_exception_becomes_value_free_503(caplog: pytest.LogCaptureFixture) -> None:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/database-work")
    async def database_work() -> None:
        raise SQLAlchemyError("SELECT patient_name FROM private_table WHERE patient_name='must-not-appear'")

    previous_propagation = request_logger.propagate
    request_logger.propagate = True
    try:
        with caplog.at_level(logging.INFO, logger="medi.request"):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/database-work")
    finally:
        request_logger.propagate = previous_propagation

    assert response.status_code == 503
    assert response.json() == {"detail": "Database temporarily unavailable"}
    record = next(record for record in caplog.records if record.name == "medi.request")
    rendered = JsonFormatter().format(record)
    assert '"event":"database_unavailable"' in rendered
    assert '"status_code":503' in rendered
    assert "patient_name" not in rendered
    assert "private_table" not in rendered
    assert "must-not-appear" not in rendered
