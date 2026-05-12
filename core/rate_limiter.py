from __future__ import annotations

import logging
import threading
from collections import defaultdict, deque
from time import time
from typing import Any

from fastapi import Request

from core.config import settings
from core.redis_client import get_redis

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int, int]:
        now = time()
        window_start = now - window_seconds

        with self._lock:
            timestamps = self._requests[key]
            while timestamps and timestamps[0] <= window_start:
                timestamps.popleft()

            if len(timestamps) >= limit:
                retry_after = max(1, int(timestamps[0] + window_seconds - now))
                return False, retry_after, 0

            timestamps.append(now)
            remaining = max(0, limit - len(timestamps))
            return True, 0, remaining


in_memory_rate_limiter = InMemoryRateLimiter()


def _extract_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("x-real-ip", "").strip()
    if real_ip:
        return real_ip

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


def resolve_rate_limit_identity(request: Request, auth_payload: dict[str, Any] | None = None) -> str:
    payload = auth_payload or {}
    service_name = (
        str(payload.get("service") or payload.get("sub") or payload.get("iss") or "anonymous")
        .strip()
        .lower()
    )
    client_ip = _extract_client_ip(request)
    return f"{service_name}:{client_ip}"


async def _check_redis_rate_limit(
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> tuple[bool, int, int] | None:
    redis = get_redis()
    if redis is None:
        return None

    bucket_key = f"futurex:api-rate-limit:{key}"

    try:
        current_count = await redis.incr(bucket_key)
        if current_count == 1:
            await redis.expire(bucket_key, window_seconds)

        ttl = await redis.ttl(bucket_key)
    except Exception as exc:
        logger.warning("api_rate_limit.redis_fallback key=%s error=%s", key, exc)
        return None

    retry_after = max(1, ttl if ttl and ttl > 0 else window_seconds)
    remaining = max(0, limit - int(current_count))

    if current_count > limit:
        return False, retry_after, 0

    return True, 0, remaining


async def check_api_rate_limit(key: str) -> tuple[bool, int, int]:
    limit = max(0, settings.api_rate_limit_requests)
    window_seconds = max(1, settings.api_rate_limit_window_seconds)

    if limit == 0:
        return True, 0, 0

    redis_result = await _check_redis_rate_limit(
        key=key,
        limit=limit,
        window_seconds=window_seconds,
    )
    if redis_result is not None:
        return redis_result

    return in_memory_rate_limiter.check(
        key,
        limit=limit,
        window_seconds=window_seconds,
    )


class AuthorRateLimiter:
    def check(self, author_id: str) -> tuple[bool, int]:
        allowed, retry_after, _remaining = in_memory_rate_limiter.check(
            author_id,
            limit=max(0, settings.LLM_RATE_LIMIT_REQUESTS),
            window_seconds=max(1, settings.LLM_RATE_LIMIT_WINDOW_SECONDS),
        )
        return allowed, retry_after


author_rate_limiter = AuthorRateLimiter()
