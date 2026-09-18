"""Token-level streaming: delta accumulation, tool-call reassembly, SSE ordering."""

from __future__ import annotations

import json

import pytest

from app.core.config import settings
from app.services.model_router import router


@pytest.fixture(autouse=True)
def _reset_client():
    """The cached AsyncOpenAI client binds to the loop it was built in."""
    router._local = None
    yield
    router._local = None


@pytest.fixture()
def mock(monkeypatch):
    from tests.mock_llm import MockLLM

    server = MockLLM()
    url = server.start()
    monkeypatch.setattr(settings, "ollama_base_url", url)
    monkeypatch.setattr(settings, "local_only", True)
    try:
        yield server
    finally:
        server.stop()


async def collect(messages, tools=None):
    tokens: list[str] = []
    final = None
    async for kind, payload in router.chat_stream(messages, tools=tools):
        if kind == "token":
            tokens.append(payload)
        else:
            final = payload
    return tokens, final


# ------------------------------------------------------------------- tokens
async def test_prose_arrives_as_multiple_tokens(mock):
    mock.reset([{"content": "The answer is forty two."}])
    tokens, final = await collect([{"role": "user", "content": "hi"}])
    assert len(tokens) > 1, "content should stream incrementally, not as one blob"
    assert "".join(tokens) == "The answer is forty two."
    assert final.text == "The answer is forty two."
    assert final.degraded is False


async def test_exactly_one_final_event(mock):
    mock.reset([{"content": "hello there"}])
    kinds = [kind async for kind, _ in router.chat_stream([{"role": "user", "content": "hi"}])]
    assert kinds.count("final") == 1
    assert kinds[-1] == "final", "final must be the terminal event"


async def test_final_carries_provider_metadata(mock):
    mock.reset([{"content": "ok"}])
    _, final = await collect([{"role": "user", "content": "hi"}])
    assert final.provider == "local"
    assert final.latency_ms >= 0


# --------------------------------------------------------------- tool calls
async def test_tool_call_arguments_reassembled_from_fragments(mock):
    """The mock splits arguments across deltas; the router must rejoin them."""
    mock.reset([{"tool_calls": [{"name": "calculate", "arguments": {"expression": "6*7"}}]}])
    tokens, final = await collect([{"role": "user", "content": "6*7"}])
    assert tokens == [], "a pure tool-call turn emits no prose"
    assert len(final.tool_calls) == 1
    call = final.tool_calls[0]
    assert call.function.name == "calculate"
    assert json.loads(call.function.arguments) == {"expression": "6*7"}


async def test_parallel_tool_calls_keep_their_own_arguments(mock):
    mock.reset([
        {
            "tool_calls": [
                {"name": "calculate", "arguments": {"expression": "1+1"}},
                {"name": "current_time", "arguments": {}},
            ]
        }
    ])
    _, final = await collect([{"role": "user", "content": "go"}])
    assert [c.function.name for c in final.tool_calls] == ["calculate", "current_time"]
    assert json.loads(final.tool_calls[0].function.arguments) == {"expression": "1+1"}
    assert json.loads(final.tool_calls[1].function.arguments) == {}


async def test_tool_calls_have_distinct_ids(mock):
    mock.reset([
        {
            "tool_calls": [
                {"name": "calculate", "arguments": {"expression": "1+1"}},
                {"name": "calculate", "arguments": {"expression": "2+2"}},
            ]
        }
    ])
    _, final = await collect([{"role": "user", "content": "go"}])
    ids = [c.id for c in final.tool_calls]
    assert len(set(ids)) == 2


async def test_streamed_message_serialises_for_history(mock):
    """The rebuilt assistant message must round-trip into the next request."""
    mock.reset([{"tool_calls": [{"name": "calculate", "arguments": {"expression": "2+2"}}]}])
    _, final = await collect([{"role": "user", "content": "2+2"}])
    dumped = final.message.model_dump()
    assert dumped["role"] == "assistant"
    assert dumped["tool_calls"][0]["function"]["name"] == "calculate"
    assert dumped["tool_calls"][0]["type"] == "function"
    json.dumps(dumped)  # must be JSON-serialisable for the provider


async def test_content_and_tool_calls_together(mock):
    mock.reset([{"content": "Let me check.", "tool_calls": [{"name": "current_time", "arguments": {}}]}])
    tokens, final = await collect([{"role": "user", "content": "time?"}])
    assert "".join(tokens) == "Let me check."
    assert len(final.tool_calls) == 1


# ---------------------------------------------------------------- fallbacks
async def test_falls_back_to_buffered_when_streaming_fails(mock, monkeypatch):
    """A gateway that rejects streaming must not break the answer."""
    real_create = router.local.chat.completions.create

    async def reject_streaming(**kwargs):
        if kwargs.get("stream"):
            raise RuntimeError("streaming not supported by this gateway")
        return await real_create(**kwargs)

    monkeypatch.setattr(router.local.chat.completions, "create", reject_streaming)
    mock.reset([{"content": "buffered answer"}])
    tokens, final = await collect([{"role": "user", "content": "hi"}])
    assert final.text == "buffered answer"
    assert final.degraded is False
    assert "".join(tokens) == "buffered answer"


async def test_degrades_when_provider_is_down(mock):
    mock.reset([{"content": "never returned"}])
    mock.fail_times = 99
    tokens, final = await collect([{"role": "user", "content": "hi"}])
    assert final.degraded is True
    assert tokens == [], "degraded fallback text must not be streamed as tokens"


# --------------------------------------------------------------- end to end
async def test_sse_emits_token_events_before_message(client, mock):
    mock.reset([{"content": "Streaming works nicely."}])
    with client.stream("POST", "/v1/chat/stream", json={"message": "hi"}) as response:
        assert response.status_code == 200
        events = [
            line[len("event: ") :].strip()
            for line in response.iter_lines()
            if line.startswith("event: ")
        ]
    assert "token" in events
    assert events.index("token") < events.index("message")
    assert events[-1] == "done"


async def test_sse_token_payloads_reconstruct_the_answer(client, mock):
    mock.reset([{"content": "Hello from ORION."}])
    chunks: list[str] = []
    with client.stream("POST", "/v1/chat/stream", json={"message": "hi"}) as response:
        current = None
        for line in response.iter_lines():
            if line.startswith("event: "):
                current = line[len("event: ") :].strip()
            elif line.startswith("data: ") and current == "token":
                chunks.append(json.loads(line[len("data: ") :])["text"])
    assert "".join(chunks) == "Hello from ORION."


async def test_sse_marks_message_as_already_streamed(client, mock):
    """The UI needs to know not to append the answer twice."""
    mock.reset([{"content": "Done."}])
    payload = None
    with client.stream("POST", "/v1/chat/stream", json={"message": "hi"}) as response:
        current = None
        for line in response.iter_lines():
            if line.startswith("event: "):
                current = line[len("event: ") :].strip()
            elif line.startswith("data: ") and current == "message":
                payload = json.loads(line[len("data: ") :])
    assert payload["already_streamed"] is True
    assert payload["content"] == "Done."


async def test_sse_tokens_only_from_the_answering_step(client, mock):
    """Tool-call steps emit no prose, so tokens belong to the final step."""
    mock.reset([
        {"tool_calls": [{"name": "calculate", "arguments": {"expression": "8*8"}}]},
        {"content": "It is 64."},
    ])
    steps = set()
    with client.stream("POST", "/v1/chat/stream", json={"message": "8*8"}) as response:
        current = None
        for line in response.iter_lines():
            if line.startswith("event: "):
                current = line[len("event: ") :].strip()
            elif line.startswith("data: ") and current == "token":
                steps.add(json.loads(line[len("data: ") :])["step"])
    assert steps == {1}
