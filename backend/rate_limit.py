"""Small request-rate baseline for authentication and high-cost API routes."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    limit: int
    window_seconds: int


class SlidingWindowLimiter:
    """Thread-safe process-local sliding-window counter."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def consume(self, key: str, rule: RateLimitRule, now: float | None = None) -> int | None:
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


class RequestRateLimitMiddleware(BaseHTTPMiddleware):
    """Rate-limit login and expensive write/export paths by network peer."""

    def __init__(self, app: object, login_limit: int, sensitive_limit: int, window_seconds: int = 60) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.limiter = SlidingWindowLimiter()
        self.login_rule = RateLimitRule("login", login_limit, window_seconds)
        self.sensitive_rule = RateLimitRule("sensitive", sensitive_limit, window_seconds)

    async def dispatch(self, request: Request, call_next: object) -> Response:
        rule = self._rule_for(request)
        if rule is not None:
            peer = request.client.host if request.client is not None else "unknown"
            retry_after = self.limiter.consume(peer, rule)
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
        if request.method in {"POST", "PATCH", "DELETE"} and ("/upload" in path or "/reprocess" in path or "/export" in path):
            return self.sensitive_rule
        if request.method == "GET" and "/export" in path:
            return self.sensitive_rule
        return None
