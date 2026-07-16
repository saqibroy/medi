"""Shared production and bounded local request-rate enforcement."""

from __future__ import annotations

import hashlib
import hmac
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from typing import Protocol

from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    limit: int
    window_seconds: int


class AsyncLimiter(Protocol):
    async def consume(self, key: str, rule: RateLimitRule) -> int | None: ...


class SlidingWindowLimiter:
    """Thread-safe process-local fallback for development and unit tests."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    async def consume(self, key: str, rule: RateLimitRule, now: float | None = None) -> int | None:
        timestamp = time.monotonic() if now is None else now
        cutoff = timestamp - rule.window_seconds
        bucket_key = f"{rule.name}:{key}"
        with self._lock:
            events = self._events[bucket_key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= rule.limit:
                return max(1, int(rule.window_seconds - (timestamp - events[0])))
            events.append(timestamp)
        return None


class RedisFixedWindowLimiter:
    """Atomic shared counter suitable for multiple API processes."""

    _SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local ttl = redis.call('TTL', KEYS[1])
return {count, ttl}
"""

    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def consume(self, key: str, rule: RateLimitRule) -> int | None:
        result = await self.redis.eval(self._SCRIPT, 1, f"medi:rate:{rule.name}:{key}", rule.window_seconds)
        count, ttl = int(result[0]), int(result[1])
        return max(1, ttl) if count > rule.limit else None


class RequestRateLimitMiddleware(BaseHTTPMiddleware):
    """Rate-limit login and high-cost routes without storing raw peer addresses."""

    def __init__(
        self,
        app: object,
        login_limit: int,
        sensitive_limit: int,
        window_seconds: int = 60,
        backend: str = "memory",
        redis_url: str | None = None,
        identity_secret: str = "development-rate-limit-key",
        limiter: AsyncLimiter | None = None,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        if limiter is not None:
            self.limiter = limiter
        elif backend == "redis" and redis_url is not None:
            self.limiter = RedisFixedWindowLimiter(Redis.from_url(redis_url, decode_responses=False))
        else:
            self.limiter = SlidingWindowLimiter()
        self.fail_closed = backend == "redis"
        self.identity_secret = identity_secret.encode()
        self.login_rule = RateLimitRule("login", login_limit, window_seconds)
        self.sensitive_rule = RateLimitRule("sensitive", sensitive_limit, window_seconds)

    async def dispatch(self, request: Request, call_next: object) -> Response:
        rule = self._rule_for(request)
        if rule is not None:
            peer = request.client.host if request.client is not None else "unknown"
            identity = hmac.new(self.identity_secret, f"rate-limit-peer:{peer}".encode(), hashlib.sha256).hexdigest()
            try:
                retry_after = await self.limiter.consume(identity, rule)
            except (RedisError, OSError, TimeoutError):
                if self.fail_closed:
                    return JSONResponse(status_code=503, content={"detail": "Rate limit service unavailable"})
                retry_after = None
            if retry_after is not None:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests"},
                    headers={"Retry-After": str(retry_after), "X-RateLimit-Policy": f"{rule.limit};w={rule.window_seconds}"},
                )
        return await call_next(request)  # type: ignore[operator]

    def _rule_for(self, request: Request) -> RateLimitRule | None:
        path = request.url.path
        if request.method == "POST" and path == "/auth/login":
            return self.login_rule
        if request.method == "POST" and (
            path.endswith("/releases")
            or path.endswith("/revoke")
            or path.startswith("/governance/")
        ):
            return self.sensitive_rule
        if request.method in {"POST", "PATCH", "DELETE"} and ("/upload" in path or "/reprocess" in path or "/export" in path):
            return self.sensitive_rule
        if request.method == "GET" and "/export" in path:
            return self.sensitive_rule
        return None
