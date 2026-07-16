"""Tests for local and shared rate-limit safety behavior."""

import httpx
import pytest
from fastapi import FastAPI

from redis.exceptions import ConnectionError

from backend.rate_limit import RateLimitRule, RedisFixedWindowLimiter, RequestRateLimitMiddleware


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


@pytest.mark.anyio
async def test_governance_writes_use_the_sensitive_limit() -> None:
    app = FastAPI()
    app.add_middleware(RequestRateLimitMiddleware, login_limit=5, sensitive_limit=1, window_seconds=60)

    @app.post("/governance/deletion-requests")
    async def request_deletion() -> dict[str, bool]:
        return {"ok": True}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/governance/deletion-requests")).status_code == 200
        limited = await client.post("/governance/deletion-requests")

    assert limited.status_code == 429


class FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def eval(self, _script: str, _keys: int, key: str, window: int) -> list[int]:
        self.counts[key] = self.counts.get(key, 0) + 1
        return [self.counts[key], window]


@pytest.mark.anyio
async def test_redis_limiter_shares_atomic_counters_between_instances() -> None:
    redis = FakeRedis()
    first = RedisFixedWindowLimiter(redis)  # type: ignore[arg-type]
    second = RedisFixedWindowLimiter(redis)  # type: ignore[arg-type]
    rule = RateLimitRule("login", 2, 60)

    assert await first.consume("hashed-peer", rule) is None
    assert await second.consume("hashed-peer", rule) is None
    assert await first.consume("hashed-peer", rule) == 60
    assert all("hashed-peer" in key for key in redis.counts)


class UnavailableLimiter:
    async def consume(self, _key: str, _rule: RateLimitRule) -> None:
        raise ConnectionError("private backend detail")


@pytest.mark.anyio
async def test_shared_backend_failure_is_safe_and_fails_closed() -> None:
    app = FastAPI()
    app.add_middleware(
        RequestRateLimitMiddleware,
        login_limit=2,
        sensitive_limit=2,
        backend="redis",
        redis_url="redis://unused",
        limiter=UnavailableLimiter(),
    )

    @app.post("/auth/login")
    async def login() -> dict[str, bool]:
        return {"ok": True}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/auth/login")

    assert response.status_code == 503
    assert response.json() == {"detail": "Rate limit service unavailable"}
    assert "private backend detail" not in response.text
