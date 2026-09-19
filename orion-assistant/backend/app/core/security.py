from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request, status

from app.core.config import settings

_buckets: dict[str, deque[float]] = defaultdict(deque)

#: Drop idle buckets once in a while. Without this the map grows by one entry
#: per distinct client address, forever -- a slow leak on a shared host and a
#: trivial memory-exhaustion vector on an exposed one.
_SWEEP_EVERY = 500
_sweeps = {"since": 0}


def _sweep(now: float) -> None:
    """Forget clients that have not been seen inside the window."""
    stale = [key for key, seen in _buckets.items() if not seen or now - seen[-1] > 60]
    for key in stale:
        del _buckets[key]


def require_auth(authorization: str | None = Header(default=None)) -> str:
    """Bearer-token gate. Disabled by default for local-first single-user use."""
    if not settings.auth_enabled:
        return "local"
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    # compare_digest: a plain != leaks the shared prefix length through timing,
    # which is enough to recover a token byte by byte given enough attempts.
    if not settings.admin_token or not secrets.compare_digest(token, settings.admin_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid token")
    return "admin"


async def rate_limit(request: Request) -> None:
    limit = settings.rate_limit_per_minute
    if limit <= 0:
        return
    key = request.client.host if request.client else "unknown"
    now = time.time()

    _sweeps["since"] += 1
    if _sweeps["since"] >= _SWEEP_EVERY:
        _sweeps["since"] = 0
        _sweep(now)

    bucket = _buckets[key]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded")
    bucket.append(now)
