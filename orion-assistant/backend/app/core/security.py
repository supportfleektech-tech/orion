from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request, status

from app.core.config import settings

_buckets: dict[str, deque[float]] = defaultdict(deque)


def require_auth(authorization: str | None = Header(default=None)) -> str:
    """Bearer-token gate. Disabled by default for local-first single-user use."""
    if not settings.auth_enabled:
        return "local"
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if token != settings.admin_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid token")
    return "admin"


async def rate_limit(request: Request) -> None:
    limit = settings.rate_limit_per_minute
    if limit <= 0:
        return
    key = request.client.host if request.client else "unknown"
    now = time.time()
    bucket = _buckets[key]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded")
    bucket.append(now)
