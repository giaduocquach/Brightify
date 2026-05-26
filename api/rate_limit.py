"""In-memory sliding-window rate limiter middleware for FastAPI."""

import time
from collections import defaultdict
from threading import Lock
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# ── Configuration ────────────────────────────────────────────────────────
# Limits: (max_requests, window_seconds)
_ROUTE_LIMITS = {
    "/api/recommend/":     (30, 60),   # AI endpoints — heavier compute
    "/api/backtest/":      (5,  60),   # Admin backtest — very expensive
    "/api/auth/login":     (10, 60),   # Login brute-force protection
    "/api/auth/register":  (5,  60),   # Registration spam protection
}
_DEFAULT_LIMIT = (120, 60)  # 120 req/min for everything else


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple sliding-window rate limiter keyed by client IP + route prefix."""

    def __init__(self, app):
        super().__init__(app)
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _get_limit(self, path: str) -> tuple[int, int]:
        for prefix, limit in _ROUTE_LIMITS.items():
            if path.startswith(prefix):
                return limit
        return _DEFAULT_LIMIT

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for static files and health checks
        path = request.url.path
        if path.startswith("/static/") or path == "/api/health":
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        max_requests, window = self._get_limit(path)
        bucket_key = f"{client_ip}:{path.split('?')[0]}"
        now = time.monotonic()

        with self._lock:
            # Prune expired timestamps
            timestamps = self._buckets[bucket_key]
            cutoff = now - window
            self._buckets[bucket_key] = [t for t in timestamps if t > cutoff]
            timestamps = self._buckets[bucket_key]

            if len(timestamps) >= max_requests:
                retry_after = int(window - (now - timestamps[0])) + 1
                return JSONResponse(
                    status_code=429,
                    content={"success": False, "error": "Quá nhiều yêu cầu. Vui lòng thử lại sau."},
                    headers={"Retry-After": str(retry_after)},
                )

            timestamps.append(now)

        return await call_next(request)
