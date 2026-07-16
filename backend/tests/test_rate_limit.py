"""Tests for the process-local rate-limit safety baseline."""

import httpx
import pytest
from fastapi import FastAPI

from backend.rate_limit import RequestRateLimitMiddleware


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_login_limit_returns_safe_429_and_retry_header() -> None:
    app = FastAPI()
    app.add_middleware(RequestRateLimitMiddleware, login_limit=2, sensitive_limit=2, window_seconds=60)

    @app.post("/auth/login")
    async def login() -> dict[str, bool]:
        return {"ok": True}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/auth/login")).status_code == 200
        assert (await client.post("/auth/login")).status_code == 200
        limited = await client.post("/auth/login")

    assert limited.status_code == 429
    assert limited.json() == {"detail": "Too many requests"}
    assert limited.headers["Retry-After"]
    assert limited.headers["X-RateLimit-Policy"] == "2;w=60"


@pytest.mark.anyio
async def test_health_and_normal_reads_are_not_rate_limited() -> None:
    app = FastAPI()
    app.add_middleware(RequestRateLimitMiddleware, login_limit=1, sensitive_limit=1, window_seconds=60)

    @app.get("/health/live")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        responses = [await client.get("/health/live") for _ in range(3)]

    assert [response.status_code for response in responses] == [200, 200, 200]
