import logging
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from core.config import settings

try:
    import redis.asyncio as aioredis
    _REDIS_AVAILABLE = True
except ImportError:
    aioredis = None  # type: ignore[assignment]
    _REDIS_AVAILABLE = False

_redis_client: Optional[object] = None
logger = logging.getLogger(__name__)


def _redact_redis_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        username = f"{parsed.username}:***@" if parsed.username else "***@"
        netloc = f"{username}{host}{port}" if parsed.password or parsed.username else parsed.netloc
        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        return "<invalid redis url>"


def get_redis():
    """Return an async Redis client, or None if redis package is not installed."""
    global _redis_client
    if not settings.redis_enabled:
        return None
    if not _REDIS_AVAILABLE:
        if settings.REDIS_REQUIRED:
            raise RuntimeError("redis[asyncio] is not installed, but REDIS_REQUIRED=true.")
        return None
    if _redis_client is None:
        url = settings.REDIS_URL or "redis://localhost:6379"
        max_connections = max(1, settings.REDIS_MAX_CONNECTIONS)
        pool_timeout = max(0.1, settings.REDIS_POOL_TIMEOUT_SECONDS)
        socket_connect_timeout = max(0.1, settings.REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS)
        socket_timeout = max(0.1, settings.REDIS_SOCKET_TIMEOUT_SECONDS)
        health_check_interval = max(0, settings.REDIS_HEALTH_CHECK_INTERVAL_SECONDS)
        logger.info(
            "redis.client_configured url=%s required=%s max_connections=%s pool_timeout=%s",
            _redact_redis_url(url),
            settings.REDIS_REQUIRED,
            max_connections,
            pool_timeout,
        )
        pool = aioredis.BlockingConnectionPool.from_url(
            url,
            decode_responses=True,
            max_connections=max_connections,
            timeout=pool_timeout,
            socket_connect_timeout=socket_connect_timeout,
            socket_timeout=socket_timeout,
            health_check_interval=health_check_interval,
        )
        _redis_client = aioredis.Redis(connection_pool=pool)
    return _redis_client


async def verify_redis_connection() -> bool:
    if not settings.redis_enabled:
        logger.info("redis.disabled")
        return False

    client = get_redis()
    if client is None:
        logger.warning("redis.unavailable package_missing=true")
        return False

    try:
        await client.ping()
        logger.info("redis.ping_ok url=%s", _redact_redis_url(settings.REDIS_URL))
        return True
    except Exception as exc:
        logger.error("redis.ping_failed error=%s", exc)
        if settings.REDIS_REQUIRED:
            raise RuntimeError(
                "Redis connection failed and REDIS_REQUIRED=true. "
                "Check REDIS_URL, network access, TLS mode, username, and password."
            ) from exc
        return False


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception:
            pass
        _redis_client = None
