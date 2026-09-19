"""Auth is off by default for local use; these tests verify it actually works when on."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture()
def secured_client():
    settings.auth_enabled = True
    settings.admin_token = "unit-test-token"
    try:
        with TestClient(app) as c:
            yield c
    finally:
        settings.auth_enabled = False


AUTH = {"Authorization": "Bearer unit-test-token"}


def test_mutating_endpoint_requires_token(secured_client):
    assert secured_client.post("/v1/chat", json={"message": "hi"}).status_code == 401


def test_wrong_token_is_forbidden(secured_client):
    r = secured_client.post("/v1/chat", json={"message": "hi"}, headers={"Authorization": "Bearer nope"})
    assert r.status_code == 403


def test_malformed_header_is_rejected(secured_client):
    r = secured_client.post("/v1/chat", json={"message": "hi"}, headers={"Authorization": "unit-test-token"})
    assert r.status_code == 401


def test_valid_token_is_accepted(secured_client):
    assert secured_client.post("/v1/chat", json={"message": "hi"}, headers=AUTH).status_code == 200


def test_reads_remain_public(secured_client):
    assert secured_client.get("/health").status_code == 200
    assert secured_client.get("/v1/system/status").status_code == 200


def test_destructive_endpoints_are_protected(secured_client):
    assert secured_client.delete("/v1/memory/some-id").status_code == 401
    assert secured_client.post("/v1/security/kill-switch", json={"enabled": True}).status_code == 401
    assert secured_client.patch("/v1/settings", json={"max_tool_loops": 3}).status_code == 401


# ===================================================================
# Rate limiter internals
# ===================================================================

import asyncio  # noqa: E402

from app.core import security  # noqa: E402


class _Req:
    """Minimal stand-in for a Starlette Request."""

    def __init__(self, host: str) -> None:
        self.client = type("C", (), {"host": host})()


@pytest.fixture(autouse=True)
def clean_buckets():
    security._buckets.clear()
    security._sweeps["since"] = 0
    yield
    security._buckets.clear()
    security._sweeps["since"] = 0


def call(host: str) -> None:
    asyncio.run(security.rate_limit(_Req(host)))


def test_the_limit_is_enforced_per_client(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 5)

    for _ in range(5):
        call("1.2.3.4")

    with pytest.raises(HTTPException) as excinfo:
        call("1.2.3.4")
    assert excinfo.value.status_code == 429

    # A different client is unaffected.
    call("5.6.7.8")


def test_a_limit_of_zero_disables_limiting(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 0)
    for _ in range(50):
        call("1.2.3.4")
    assert not security._buckets, "disabled limiting should not accumulate state"


def test_idle_clients_are_forgotten(monkeypatch):
    """The bucket map is keyed by address and used to grow forever: one entry
    per distinct client, never freed. 20k addresses retained ~16MB, which is a
    slow leak on a shared host and a trivial exhaustion vector on an open one.
    """
    monkeypatch.setattr(settings, "rate_limit_per_minute", 100_000)

    for i in range(1_000):
        call(f"10.0.{i // 256}.{i % 256}")
    assert len(security._buckets) == 1_000

    # Age every entry past the window, then drive enough traffic to sweep.
    for bucket in security._buckets.values():
        for index in range(len(bucket)):
            bucket[index] -= 120

    for _ in range(security._SWEEP_EVERY + 1):
        call("127.0.0.1")

    assert len(security._buckets) <= 2, (
        f"{len(security._buckets)} buckets retained after they went idle"
    )


def test_an_active_client_survives_the_sweep(monkeypatch):
    """Sweeping must not reset the window for someone still sending."""
    monkeypatch.setattr(settings, "rate_limit_per_minute", 100_000)

    for _ in range(security._SWEEP_EVERY + 10):
        call("9.9.9.9")

    assert "9.9.9.9" in security._buckets
    assert len(security._buckets["9.9.9.9"]) > 1


def test_requests_outside_the_window_stop_counting(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 3)

    for _ in range(3):
        call("4.4.4.4")
    with pytest.raises(HTTPException):
        call("4.4.4.4")

    # Move the recorded hits out of the 60s window.
    bucket = security._buckets["4.4.4.4"]
    for index in range(len(bucket)):
        bucket[index] -= 120

    call("4.4.4.4")  # allowed again


# ===================================================================
# Token comparison
# ===================================================================

def test_the_admin_token_is_compared_in_constant_time():
    """A plain != leaks the shared prefix length through timing, which is
    enough to recover a token byte by byte."""
    source = (
        __import__("pathlib").Path(security.__file__)
    ).read_text()
    assert "compare_digest" in source
    assert "token != settings.admin_token" not in source


def test_an_empty_configured_token_never_authorises(monkeypatch):
    """Otherwise an unset ADMIN_TOKEN plus an empty header would match."""
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "admin_token", "")

    with pytest.raises(HTTPException) as excinfo:
        security.require_auth("Bearer ")
    assert excinfo.value.status_code in (401, 403)
