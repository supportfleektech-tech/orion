"""Connector probing: honest status for every external service."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.core.config import settings
from app.services import connectors


def probe(db):
    return asyncio.run(connectors.status(db))


def find(result, connector_id):
    return next(c for c in result["connectors"] if c["id"] == connector_id)


@pytest.fixture
def unreachable(monkeypatch):
    """Every outbound probe fails, as on a machine with nothing running."""

    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(connectors.httpx, "AsyncClient", Client)


@pytest.fixture
def reachable(monkeypatch):
    """Every probe answers 200 with JSON."""

    class Response:
        status_code = 200
        def json(self): return {"data": []}

    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): return Response()

    monkeypatch.setattr(connectors.httpx, "AsyncClient", Client)


# ------------------------------------------------------------------ shape
def test_every_connector_reports_a_known_status(db, reachable):
    result = probe(db)
    allowed = {"connected", "unreachable", "not_configured", "disabled"}
    assert result["connectors"]
    for connector in result["connectors"]:
        assert connector["status"] in allowed, connector
        assert connector["detail"], f"{connector['id']} gives no explanation"
        assert connector["summary"]


def test_the_model_runtime_is_the_only_required_connector(db, reachable):
    required = [c["id"] for c in probe(db)["connectors"] if c["required"]]
    assert required == ["ollama"], "ORION is local-first: nothing else may be mandatory"


def test_counts_match_the_listed_connectors(db, reachable):
    result = probe(db)
    assert result["total"] == len(result["connectors"])
    assert result["connected"] == sum(1 for c in result["connectors"] if c["status"] == "connected")


# ------------------------------------------------------------- reachability
def test_a_running_runtime_reads_as_connected(db, reachable):
    assert find(probe(db), "ollama")["status"] == "connected"


def test_a_dead_runtime_reads_as_unreachable_not_missing(db, unreachable):
    """'Unreachable' and 'not configured' are different problems with
    different fixes, so they must not collapse into one status."""
    ollama = find(probe(db), "ollama")
    assert ollama["status"] == "unreachable"
    assert "refused" in ollama["detail"].lower()


def test_embeddings_explain_the_fallback_when_the_runtime_is_down(db, unreachable):
    """Retrieval still works without a model, and the UI should say so rather
    than implying knowledge search is broken."""
    assert "falls back" in find(probe(db), "embeddings")["detail"].lower()


# ------------------------------------------------------------------- cloud
def test_cloud_without_a_key_is_not_configured_rather_than_broken(db, reachable, monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", None)
    cloud = find(probe(db), "openrouter")
    assert cloud["status"] == "not_configured"
    assert "local" in cloud["detail"].lower()


def test_cloud_is_disabled_when_local_only_is_on(db, reachable, monkeypatch):
    """A configured key that will never be used must not claim 'connected'."""
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    monkeypatch.setattr(settings, "local_only", True)
    cloud = find(probe(db), "openrouter")
    assert cloud["status"] == "disabled"
    assert "local-only" in cloud["detail"]


def test_a_rejected_key_says_so(db, monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-bad")
    monkeypatch.setattr(settings, "local_only", False)

    class Response:
        status_code = 401
        def json(self): return {}

    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): return Response()

    monkeypatch.setattr(connectors.httpx, "AsyncClient", Client)
    cloud = find(probe(db), "openrouter")
    assert cloud["status"] == "unreachable"
    assert "rejected" in cloud["detail"].lower()


# ------------------------------------------------------------- web search
def test_web_search_off_by_policy_is_disabled_not_unreachable(db, reachable, monkeypatch):
    monkeypatch.setattr(settings, "enable_web_search", False)
    search = find(probe(db), "searxng")
    assert search["status"] == "disabled"
    assert "policy" in search["detail"].lower()


def test_web_search_enabled_but_down_suggests_the_fix(db, unreachable, monkeypatch):
    monkeypatch.setattr(settings, "enable_web_search", True)
    assert "docker compose" in find(probe(db), "searxng")["detail"]


# -------------------------------------------------------------------- MCP
def test_mcp_with_no_servers_is_not_configured(db, reachable):
    assert find(probe(db), "mcp")["status"] in {"not_configured", "connected", "unreachable"}


def test_a_failing_mcp_server_is_named(db, reachable):
    from app.db.models import McpServer

    db.add(McpServer(name="broken-one", transport="stdio", command="nope", env={},
                     enabled=True, risk="low", tools=[], status="error"))
    db.commit()

    mcp = find(probe(db), "mcp")
    if mcp["status"] == "unreachable":
        assert "broken-one" in mcp["detail"], "say which server is failing, not just that one is"


# ------------------------------------------------------------------ safety
def test_no_secret_values_are_ever_returned(db, reachable, monkeypatch):
    """env_keys lists names so the UI can tell you what to set. Leaking the
    values would turn a status page into a credential dump."""
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-super-secret-value")

    payload = str(probe(db))
    assert "sk-super-secret-value" not in payload

    for connector in probe(db)["connectors"]:
        for key in connector["env_keys"] or []:
            assert key.isupper(), f"{key} looks like a value, not an env var name"


def test_a_probe_that_explodes_does_not_take_the_page_down(db, monkeypatch):
    async def boom():
        raise RuntimeError("probe exploded")

    monkeypatch.setattr(connectors, "_web_search", boom)
    result = probe(db)
    assert result["connectors"], "one bad probe must not empty the whole list"
    assert all(c["id"] != "searxng" for c in result["connectors"])


def test_the_endpoint_serves(client):
    response = client.get("/v1/connectors")
    assert response.status_code == 200
    body = response.json()
    assert "connectors" in body
    assert body["total"] >= 1
