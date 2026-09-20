"""Cover the SSE streaming endpoint, including incremental event ordering."""

import json

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.models import Conversation, Message
from app.services import model_router as router_module
from tests.mock_llm import MockLLM


@pytest.fixture(scope="module")
def stream_llm():
    mock = MockLLM()
    base_url = mock.start()
    original_url, original_local_only = settings.ollama_base_url, settings.local_only
    settings.ollama_base_url = base_url
    settings.local_only = True
    router_module.router._local = None
    try:
        yield mock
    finally:
        mock.stop()
        settings.ollama_base_url = original_url
        settings.local_only = original_local_only
        router_module.router._local = None


@pytest.fixture(autouse=True)
def _fresh_client(stream_llm):
    router_module.router._local = None
    yield
    router_module.router._local = None


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        name = payload = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:].strip()
            elif line.startswith("data: "):
                payload = json.loads(line[6:])
        if name:
            events.append((name, payload or {}))
    return events


def test_stream_emits_expected_event_sequence(client, stream_llm):
    stream_llm.reset([{"content": "Streamed reply."}])
    r = client.post("/v1/chat/stream", json={"message": "hello stream"})

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")

    events = parse_sse(r.text)
    names = [n for n, _ in events]

    assert names[0] == "start"
    assert "context" in names
    assert "trace" in names
    assert names[-2:] == ["message", "done"]

    message = next(p for n, p in events if n == "message")
    assert message["content"] == "Streamed reply."


def test_stream_returns_conversation_id_first(client, stream_llm):
    stream_llm.reset([{"content": "ok"}])
    events = parse_sse(client.post("/v1/chat/stream", json={"message": "hi"}).text)
    name, payload = events[0]
    assert name == "start"
    assert payload["conversation_id"]


def test_stream_persists_both_messages(client, stream_llm, db):
    stream_llm.reset([{"content": "Persisted answer."}])
    events = parse_sse(client.post("/v1/chat/stream", json={"message": "save me"}).text)
    conversation_id = events[0][1]["conversation_id"]

    messages = db.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
    ).all()
    roles = [m.role for m in messages]
    assert roles == ["user", "assistant"]
    assert messages[1].content == "Persisted answer."
    assert messages[1].provider == "local"


def test_stream_emits_tool_events_incrementally(client, stream_llm):
    """Tool activity must stream as it happens, before the final message."""
    stream_llm.reset([
        {"tool_calls": [{"name": "calculate", "arguments": {"expression": "8*8"}}]},
        {"content": "Sixty-four."},
    ])
    events = parse_sse(client.post("/v1/chat/stream", json={"message": "8 times 8"}).text)
    names = [n for n, _ in events]

    assert "tool_start" in names, "tool invocation must be streamed"
    assert "tool_result" in names, "tool outcome must be streamed"
    # Ordering is the whole point of streaming.
    assert names.index("tool_start") < names.index("tool_result") < names.index("message")

    tool_start = next(p for n, p in events if n == "tool_start")
    assert tool_start["tool"] == "calculate"
    assert next(p for n, p in events if n == "tool_result")["result_ok"] is True


def test_stream_reports_failing_tool_without_dying(client, stream_llm):
    stream_llm.reset([
        {"tool_calls": [{"name": "calculate", "arguments": {"expression": "bad"}}]},
        {"content": "That failed."},
    ])
    events = parse_sse(client.post("/v1/chat/stream", json={"message": "break it"}).text)

    result = next(p for n, p in events if n == "tool_result")
    assert result["result_ok"] is False
    assert result["error"]
    assert next(p for n, p in events if n == "message")["content"] == "That failed."


def test_stream_continues_existing_conversation(client, stream_llm, db):
    stream_llm.reset([{"content": "First."}, {"content": "Second."}])
    first = parse_sse(client.post("/v1/chat/stream", json={"message": "one"}).text)
    conversation_id = first[0][1]["conversation_id"]

    client.post("/v1/chat/stream", json={"message": "two", "conversation_id": conversation_id})

    count = len(db.scalars(select(Message).where(Message.conversation_id == conversation_id)).all())
    assert count == 4, "two turns should yield four messages"
    assert db.get(Conversation, conversation_id) is not None


def test_stream_records_a_run_with_trace(client, stream_llm):
    stream_llm.reset([{"content": "Traced."}])
    events = parse_sse(client.post("/v1/chat/stream", json={"message": "trace me"}).text)
    done = next(p for n, p in events if n == "done")

    assert done["run_id"]
    assert done["provider"] == "local"
    assert done["degraded"] is False

    detail = client.get(f"/v1/runs/{done['run_id']}").json()
    assert detail["state"] == "succeeded"
    assert detail["trace"]
