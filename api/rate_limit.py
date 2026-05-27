"""Sliding-window rate limiter middleware for FastAPI.

Backend: Redis (preferred) with automatic in-memory fallback.

Redis path  — uses ZSET per (ip, route) key with a Lua script for
              atomic check-and-increment. Survives worker restarts
              and is safe for multi-process / multi-container setups.

In-memory   — original defaultdict + Lock; used when Redis is
              unavailable. State is per-process and is lost on restart.

Call `set_redis(client)` from the app lifespan after Redis connects.
"""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from typing import Optional, Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# ── Configuration ─────────────────────────────────────────────────────────
_ROUTE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/recommend/":    (30,  60),   # AI endpoints — heavier compute
    "/api/backtest/":     (5,   60),   # Admin backtest — very expensive
    "/api/auth/login":    (10,  60),   # Login brute-force protection
    "/api/auth/register": (5,   60),   # Registration spam protection
}
_DEFAULT_LIMIT: tuple[int, int] = (120, 60)   # 120 req/min for everything else

# ── Lua script for atomic Redis sliding-window check ──────────────────────
# KEYS[1]  = bucket key  (string)
# ARGV[1]  = window      (seconds, integer)
# ARGV[2]  = limit       (max requests)
# ARGV[3]  = now_ms      (current epoch milliseconds)
#
# Returns: [allowed (0|1), retry_after_seconds (int)]
_RATE_LIMIT_LUA = """
local key     = KEYS[1]
local window  = tonumber(ARGV[1]) * 1000   -- convert to ms
local limit   = tonumber(ARGV[2])
local now_ms  = tonumber(ARGV[3])
local cutoff  = now_ms - window

redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
local count = redis.call('ZCARD', key)
if count < limit then
    redis.call('ZADD', key, now_ms, now_ms)
    redis.call('PEXPIRE', key, window + 1000)
    return {1, 0}
end
local oldest = tonumber(redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')[2])
local retry  = math.ceil((oldest + window - now_ms) / 1000)
return {0, retry}
"""

# ── Module-level Redis client (set from app lifespan) ─────────────────────
_redis: Optional[Any] = None
_lua_sha: Optional[str] = None    # cached SHA of loaded Lua script


def set_redis(client: Any) -> None:
    """Wire up the shared Redis client. Called once at app startup."""
    global _redis
    _redis = client


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter — Redis-backed when available."""

    def __init__(self, app: Any) -> None:
        super().__init__(app)
        # In-memory fallback state
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _client_ip(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    @staticmethod
    def _get_limit(path: str) -> tuple[int, int]:
        for prefix, limit in _ROUTE_LIMITS.items():
            if path.startswith(prefix):
                return limit
        return _DEFAULT_LIMIT

    # ── Redis path ────────────────────────────────────────────────────────

    async def _check_redis(self, bucket_key: str, max_requests: int, window: int) -> tuple[bool, int]:
        """Returns (allowed, retry_after). Falls back to True on error."""
        global _lua_sha
        if _redis is None:
            return True, 0
        try:
            now_ms = int(time.time() * 1000)
            # Load script on first call (EVALSHA is faster than EVAL)
            if _lua_sha is None:
                _lua_sha = await _redis.script_load(_RATE_LIMIT_LUA)
            result = await _redis.evalsha(
                _lua_sha, 1, bucket_key,
                window, max_requests, now_ms,
            )
            allowed, retry_after = int(result[0]), int(result[1])
            return bool(allowed), retry_after
        except Exception:
            # Redis hiccup — allow the request rather than false-positive 429
            return True, 0

    # ── In-memory fallback ────────────────────────────────────────────────

    def _check_memory(self, bucket_key: str, max_requests: int, window: int) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            cutoff = now - window
            self._buckets[bucket_key] = [t for t in self._buckets[bucket_key] if t > cutoff]
            timestamps = self._buckets[bucket_key]
            if len(timestamps) >= max_requests:
                retry_after = int(window - (now - timestamps[0])) + 1
                return False, retry_after
            timestamps.append(now)
            return True, 0

    # ── Middleware entry point ─────────────────────────────────────────────

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/static/") or path == "/api/health":
            return await call_next(request)

        client_ip = self._client_ip(request)
        max_requests, window = self._get_limit(path)
        bucket_key = f"rl:{client_ip}:{path.split('?')[0]}"

        if _redis is not None:
            allowed, retry_after = await self._check_redis(bucket_key, max_requests, window)
        else:
            allowed, retry_after = self._check_memory(bucket_key, max_requests, window)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"success": False, "error": "Quá nhiều yêu cầu. Vui lòng thử lại sau."},
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
