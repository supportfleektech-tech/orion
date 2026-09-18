import pytest

from app.core.config import settings
from app.services.runtime_settings import MUTABLE_KEYS, load_overrides, save_overrides


def test_save_and_reload_override(db):
    original = settings.max_tool_loops
    try:
        save_overrides(db, {"max_tool_loops": 11})
        assert settings.max_tool_loops == 11

        # Simulate a restart: reset the live object, then reload from the DB.
        settings.max_tool_loops = original
        applied = load_overrides(db)
        assert applied["max_tool_loops"] == 11
        assert settings.max_tool_loops == 11
    finally:
        save_overrides(db, {"max_tool_loops": original})


def test_rejects_non_mutable_key(db):
    with pytest.raises(ValueError):
        save_overrides(db, {"admin_token": "hunter2"})


def test_secrets_are_not_mutable():
    for secret in ("admin_token", "jwt_secret", "openrouter_api_key", "database_url", "host"):
        assert secret not in MUTABLE_KEYS


def test_patch_endpoint_persists(client, db):
    original = settings.max_tool_loops
    try:
        body = client.patch("/v1/settings", json={"max_tool_loops": 7}).json()
        assert body["max_tool_loops"] == 7
        settings.max_tool_loops = original
        load_overrides(db)
        assert settings.max_tool_loops == 7
    finally:
        save_overrides(db, {"max_tool_loops": original})


def test_patch_rejects_unknown_field_silently(client):
    # Unknown fields are stripped by the Pydantic schema, not persisted.
    body = client.patch("/v1/settings", json={"admin_token": "nope"}).json()
    assert body["updated"] == {}
