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


def client_key(request: Request) -> str:
    """Identify the caller for rate limiting.

    Behind the bundled nginx every request arrives from the proxy container,
    so keying on the socket address puts all users in one bucket -- one busy
    client then throttles everyone else. X-Forwarded-For fixes that, but only
    a proxy that *overwrites* the header can be believed; otherwise a caller
    forges it and gets a fresh bucket per request. Hence opt-in, and we take
    the last hop rather than the client-controlled head of the list.
    """
    peer = request.client.host if request.client else "unknown"
    if not settings.trust_proxy_headers:
        return peer

    forwarded = request.headers.get("x-forwarded-for", "")
    hops = [h.strip() for h in forwarded.split(",") if h.strip()]
    return hops[-1] if hops else peer


async def rate_limit(request: Request) -> None:
    limit = settings.rate_limit_per_minute
    if limit <= 0:
        return
    key = client_key(request)
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
