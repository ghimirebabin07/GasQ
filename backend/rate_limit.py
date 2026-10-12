import time
from collections import defaultdict, deque
from collections.abc import Callable

from config import get_settings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        settings = get_settings()
        self.window_seconds = settings.rate_limit_window_seconds
        self.default_limit = settings.rate_limit_requests
        self.auth_limit = settings.auth_rate_limit_requests
        self.queue_limit = settings.queue_rate_limit_requests
        self.requests: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        limit = self._limit_for_path(request.url.path)
        if limit is None:
            return await call_next(request)

        client_host = request.client.host if request.client else "unknown"
        key = f"{client_host}:{request.url.path}"
        now = time.monotonic()
        timestamps = self.requests[key]
        while timestamps and now - timestamps[0] > self.window_seconds:
            timestamps.popleft()

        if len(timestamps) >= limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again shortly."},
                headers={"Retry-After": str(self.window_seconds)},
            )

        timestamps.append(now)
        return await call_next(request)

    def _limit_for_path(self, path: str) -> int | None:
        if path.startswith("/static") or path.endswith(".html") or path in {"/", "/health", "/ready"}:
            return None
        if path.endswith("/login") or path.endswith("/register"):
            return self.auth_limit
        if path.startswith("/queue"):
            return self.queue_limit
        return self.default_limit
