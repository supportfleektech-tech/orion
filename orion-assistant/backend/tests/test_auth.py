"""Auth is off by default for local use; these tests verify it actually works when on."""

import pytest
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
