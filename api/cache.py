"""
Async Redis cache layer for Brightify API.

Usage:
    from api.cache import cache_get_or_set, invalidate

    result = await cache_get_or_set("key", async_fn, ttl=300)

When Redis is unavailable the cache degrades gracefully — every call
executes the underlying function without caching. This makes Redis
an optional performance enhancement, not a hard dependency.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

_redis: Optional[Any] = None   # redis.asyncio.Redis instance, set by lifespan


def set_redis(client: Any) -> None:
    global _redis
    _redis = client


def _available() -> bool:
    return _redis is not None


def make_key(prefix: str, **params: Any) -> str:
    """Stable cache key: brightify:{prefix}:{md5(sorted params)}."""
    h = hashlib.md5(
        json.dumps(params, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    return f"brightify:{prefix}:{h}"


async def cache_get(key: str) -> Optional[Any]:
    if not _available():
        return None
    try:
        raw = await _redis.get(key)
        return json.loads(raw) if raw is not None else None
    except Exception as e:
        logger.debug(f"[cache] get {key!r}: {e}")
        return None


async def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    if not _available():
        return
    try:
        await _redis.setex(key, ttl, json.dumps(value, default=str))
    except Exception as e:
        logger.debug(f"[cache] set {key!r}: {e}")


async def cache_get_or_set(
    key: str,
    fn: Callable[[], Awaitable[Any]],
    ttl: int = 300,
) -> Any:
    """Return cached value or call fn(), cache it, and return the result."""
    cached = await cache_get(key)
    if cached is not None:
        return cached
    result = await fn()
    await cache_set(key, result, ttl)
    return result


async def invalidate(pattern: str) -> int:
    """Delete all keys matching pattern (Redis SCAN + DEL). Returns count."""
    if not _available():
        return 0
    try:
        keys = [k async for k in _redis.scan_iter(pattern)]
        if keys:
            return await _redis.delete(*keys)
        return 0
    except Exception as e:
        logger.debug(f"[cache] invalidate {pattern!r}: {e}")
        return 0
