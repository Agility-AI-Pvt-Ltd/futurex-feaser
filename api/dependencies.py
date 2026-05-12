from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, Response
from jose import JWTError, jwt

from core.config import settings
from core.database import get_db
from core.rate_limiter import check_api_rate_limit, resolve_rate_limit_identity

logger = logging.getLogger(__name__)


def _resolve_internal_auth_key() -> str:
    algorithm = settings.INTERNAL_AUTH_ALGORITHM.upper()
    if algorithm.startswith("RS"):
        key = settings.INTERNAL_AUTH_JWT_PUBLIC_KEY.strip()
        if not key:
            raise HTTPException(status_code=503, detail="Internal auth public key is not configured.")
        return key.replace("\\n", "\n")

    key = settings.INTERNAL_AUTH_JWT_SECRET.strip()
    if not key:
        raise HTTPException(status_code=503, detail="Internal auth secret is not configured.")
    return key


def verify_internal_service_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            _resolve_internal_auth_key(),
            algorithms=[settings.INTERNAL_AUTH_ALGORITHM],
            issuer=settings.INTERNAL_AUTH_ISSUER,
            audience=settings.INTERNAL_AUTH_AUDIENCE,
        )
    except JWTError as exc:
        logger.warning("internal_auth.invalid_jwt: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid token.") from exc

    required_service = (settings.INTERNAL_AUTH_REQUIRED_SERVICE or "").strip()
    if required_service and payload.get("service") != required_service:
        logger.warning(
            "internal_auth.invalid_service_claim service=%s required=%s",
            payload.get("service"),
            required_service,
        )
        raise HTTPException(status_code=401, detail="Invalid token.")

    return payload


def require_internal_service_auth(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not settings.INTERNAL_AUTH_ENABLED:
        return {}

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header.")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Invalid Authorization header.")

    return verify_internal_service_token(token.strip())


async def enforce_api_rate_limit(
    request: Request,
    response: Response,
    auth_payload: dict[str, Any] = Depends(require_internal_service_auth),
) -> dict[str, Any]:
    if not settings.API_RATE_LIMIT_ENABLED:
        return auth_payload

    if request.method.upper() in {"HEAD", "OPTIONS"}:
        return auth_payload

    limit = max(0, settings.api_rate_limit_requests)
    window_seconds = max(1, settings.api_rate_limit_window_seconds)
    if limit == 0:
        return auth_payload

    identity = resolve_rate_limit_identity(request, auth_payload)
    allowed, retry_after, remaining = await check_api_rate_limit(identity)

    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Window"] = str(window_seconds)

    if allowed:
        return auth_payload

    logger.warning("api_rate_limit.exceeded identity=%s retry_after=%s", identity, retry_after)
    raise HTTPException(
        status_code=429,
        detail=f"API rate limit exceeded. Max {limit} requests per {window_seconds} seconds.",
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Window": str(window_seconds),
        },
    )
