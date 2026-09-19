"""Provider routing: which model gets tried, in what order, and what happens
when each one fails.

This is the chain the README leads with -- local-first, cloud burst, graceful
degradation -- and it was previously only exercised incidentally. The failure
modes here are quiet and expensive: silently reaching the cloud when the user
asked for local-only is a privacy breach, not a bug report.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.config import settings
from app.services.model_router import ModelRouter


def fake_client(*, answer: str | None = None, error: str | None = None, log: list | None = None):
    """Minimal stand-in for an AsyncOpenAI client."""

    class Completions:
        async def create(self, **kwargs):
            if log is not None:
                log.append(kwargs.get("model"))
            if error:
                raise RuntimeError(error)

            class Message:
                content = answer
                tool_calls = []

            class Choice:
                message = Message()

            class Response:
                choices = [Choice()]
                usage = None

            return Response()

    class Client:
        chat = type("Chat", (), {"completions": Completions()})()

    return Client()


@pytest.fixture
def router(monkeypatch):
    """A router with both providers present and predictable settings."""
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_fallback_models", "cloud-a,cloud-b")
    monkeypatch.setattr(settings, "ollama_model", "local-model")
    monkeypatch.setattr(settings, "local_only", False)
    monkeypatch.setattr(settings, "cloud_escalation_enabled", True)
    monkeypatch.setattr(settings, "offline_fallback_enabled", True)
    return ModelRouter()


MESSAGES = [{"role": "user", "content": "hello"}]


# ------------------------------------------------------------------- plan
def test_local_is_tried_first_by_default(router):
    assert router.plan("auto", "normal")[0][0] == "local"


def test_local_only_never_plans_a_cloud_attempt(router, monkeypatch):
    """The whole point of the flag. Reaching the cloud here would send user
    data off the machine after they explicitly said not to."""
    monkeypatch.setattr(settings, "local_only", True)
    assert [provider for provider, _ in router.plan("auto", "normal")] == ["local"]
    # Even when the caller explicitly asks for cloud.
    assert [provider for provider, _ in router.plan("cloud", "expert")] == ["local"]


def test_local_mode_pins_to_local(router):
    assert [provider for provider, _ in router.plan("local", "expert")] == ["local"]


def test_cloud_mode_prefers_cloud_but_keeps_local_as_a_backstop(router):
    providers = [provider for provider, _ in router.plan("cloud", "normal")]
    assert providers[0] == "cloud"
    assert providers[-1] == "local"


def test_heavy_work_escalates_when_escalation_is_on(router):
    assert router.plan("auto", "expert")[0][0] == "cloud"


def test_heavy_work_stays_local_when_escalation_is_off(router, monkeypatch):
    monkeypatch.setattr(settings, "cloud_escalation_enabled", False)
    assert router.plan("auto", "expert")[0][0] == "local"


def test_every_configured_fallback_model_is_planned(router):
    models = [model for provider, model in router.plan("cloud", "normal") if provider == "cloud"]
    assert models == ["cloud-a", "cloud-b"]


def test_no_cloud_configured_means_local_only_plans(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", None)
    monkeypatch.setattr(settings, "local_only", False)
    assert [p for p, _ in ModelRouter().plan("cloud", "expert")] == ["local"]


# ---------------------------------------------------------------- failover
def test_a_healthy_local_model_answers_without_touching_the_cloud(router):
    attempted: list[str] = []
    router._local = fake_client(answer="local answer", log=attempted)
    router._cloud = fake_client(answer="cloud answer", log=attempted)

    result = asyncio.run(router.chat(MESSAGES))

    assert result.provider == "local"
    assert result.text == "local answer"
    assert attempted == ["local-model"], "the cloud must not be called when local works"


def test_a_dead_local_model_falls_through_to_the_cloud(router):
    router._local = fake_client(error="connection refused")
    router._cloud = fake_client(answer="cloud answer")

    result = asyncio.run(router.chat(MESSAGES))

    assert result.provider == "cloud"
    assert result.degraded is False


def test_each_cloud_model_is_tried_in_turn(router, monkeypatch):
    """A single bad model should not burn the whole cloud tier."""
    attempted: list[str] = []
    calls = {"n": 0}

    class Completions:
        async def create(self, **kwargs):
            attempted.append(kwargs["model"])
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("that model is rate limited")

            class Message:
                content = "second model answered"
                tool_calls = []

            return type(
                "R", (), {"choices": [type("C", (), {"message": Message()})()], "usage": None}
            )()

    router._local = fake_client(error="local down")
    router._cloud = type("Client", (), {"chat": type("Chat", (), {"completions": Completions()})()})()

    result = asyncio.run(router.chat(MESSAGES))

    assert attempted == ["cloud-a", "cloud-b"]
    assert result.text == "second model answered"


def test_local_only_does_not_reach_the_cloud_even_when_local_fails(router, monkeypatch):
    """The privacy guarantee has to hold on the failure path, not just the
    happy one."""
    monkeypatch.setattr(settings, "local_only", True)
    reached: list[str] = []
    router._local = fake_client(error="local down")
    router._cloud = fake_client(answer="LEAKED", log=reached)

    result = asyncio.run(router.chat(MESSAGES))

    assert reached == [], "local_only leaked a request to the cloud provider"
    assert result.provider == "offline"


def test_everything_down_degrades_instead_of_raising(router):
    router._local = fake_client(error="local down")
    router._cloud = fake_client(error="cloud down")

    result = asyncio.run(router.chat(MESSAGES))

    assert result.provider == "offline"
    assert result.degraded is True
    assert result.text, "a degraded response still has to say something"
    assert "cloud down" in (result.error or "")


def test_degradation_can_be_turned_off_for_callers_that_want_a_hard_failure(router, monkeypatch):
    monkeypatch.setattr(settings, "offline_fallback_enabled", False)
    router._local = fake_client(error="local down")
    router._cloud = fake_client(error="cloud down")

    with pytest.raises(RuntimeError, match="All model providers failed"):
        asyncio.run(router.chat(MESSAGES))


# ------------------------------------------------------------------ stats
def test_failures_and_degradations_are_counted(router):
    router._local = fake_client(error="local down")
    router._cloud = fake_client(error="cloud down")

    before = dict(router.stats)
    asyncio.run(router.chat(MESSAGES))

    assert router.stats["calls"] == before["calls"] + 1
    assert router.stats["failures"] > before["failures"]
    assert router.stats["degraded_calls"] == before["degraded_calls"] + 1
    assert "cloud down" in router.stats["last_error"]


def test_a_successful_call_records_its_provider_and_latency(router):
    router._local = fake_client(answer="ok")

    asyncio.run(router.chat(MESSAGES))

    assert router.stats["local_calls"] >= 1
    assert router.stats["total_latency_ms"] >= 0
