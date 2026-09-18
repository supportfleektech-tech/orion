"""Exercise the real agent tool-calling loop against a mock OpenAI-compatible model.

This is the core feature of the product and cannot be covered by the degraded
path, so it gets a scripted model that speaks the real protocol.
"""

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.policy import set_kill_switch
from app.db.models import AgentRun, Approval, ToolRun
from app.services import model_router as router_module
from app.services.agent_runtime import run_agent
from tests.mock_llm import MockLLM


@pytest.fixture(scope="module")
def mock_llm():
    mock = MockLLM()
    base_url = mock.start()
    original_url, original_local_only = settings.ollama_base_url, settings.local_only
    settings.ollama_base_url = base_url
    settings.local_only = True  # keep every call on the mock
    router_module.router._local = None  # force client rebuild against the mock
    try:
        yield mock
    finally:
        mock.stop()
        settings.ollama_base_url = original_url
        settings.local_only = original_local_only
        router_module.router._local = None


@pytest.fixture(autouse=True)
def _fresh_client(mock_llm):
    """Rebuild the async client per test.

    AsyncOpenAI holds an httpx connection pool bound to the event loop that
    created it; pytest-asyncio gives each test a fresh loop, so a cached client
    would fail with 'Event loop is closed'.
    """
    router_module.router._local = None
    yield
    router_module.router._local = None


async def test_plain_answer_without_tools(db, mock_llm):
    mock_llm.reset([{"content": "Paris is the capital of France."}])
    out = await run_agent(db, "What is the capital of France?")

    assert out["result"] == "Paris is the capital of France."
    assert out["degraded"] is False
    assert out["provider"] == "local"
    assert len(mock_llm.calls) == 1, "should not loop when no tools are requested"


async def test_single_tool_call_executes_and_feeds_result_back(db, mock_llm):
    mock_llm.reset([
        {"tool_calls": [{"name": "calculate", "arguments": {"expression": "6*7"}}]},
        {"content": "The answer is 42."},
    ])
    out = await run_agent(db, "What is six times seven?")

    assert out["result"] == "The answer is 42."
    assert len(mock_llm.calls) == 2, "model must be called again with the tool result"

    # The tool result must actually reach the model.
    followup = mock_llm.messages_at(1)
    tool_messages = [m for m in followup if m.get("role") == "tool"]
    assert tool_messages, "tool result was never sent back to the model"
    assert "42" in tool_messages[0]["content"]

    # And it must be recorded.
    run = db.scalar(select(ToolRun).where(ToolRun.tool_name == "calculate").order_by(ToolRun.created_at.desc()))
    assert run.status == "succeeded"


async def test_multi_step_tool_chain(db, mock_llm):
    mock_llm.reset([
        {"tool_calls": [{"name": "current_time", "arguments": {}}]},
        {"tool_calls": [{"name": "calculate", "arguments": {"expression": "2+2"}}]},
        {"content": "Finished both steps."},
    ])
    out = await run_agent(db, "Check the time then add two and two.")

    assert out["result"] == "Finished both steps."
    assert len(mock_llm.calls) == 3
    tools_used = [t["tool"] for t in out["trace"] if "tool" in t]
    assert tools_used == ["current_time", "calculate"]


async def test_parallel_tool_calls_in_one_turn(db, mock_llm):
    mock_llm.reset([
        {"tool_calls": [
            {"name": "calculate", "arguments": {"expression": "1+1"}},
            {"name": "current_time", "arguments": {}},
        ]},
        {"content": "Both done."},
    ])
    out = await run_agent(db, "Do two things at once.")

    assert out["result"] == "Both done."
    tool_messages = [m for m in mock_llm.messages_at(1) if m.get("role") == "tool"]
    assert len(tool_messages) == 2, "each parallel call needs its own tool message"


async def test_loop_is_bounded(db, mock_llm):
    """A model that never stops calling tools must not spin forever."""
    mock_llm.reset([{"tool_calls": [{"name": "calculate", "arguments": {"expression": "1+1"}}]}] * 50)
    original = settings.max_tool_loops
    settings.max_tool_loops = 3
    try:
        await run_agent(db, "Loop forever.")
        assert len(mock_llm.calls) == 3, "loop must stop at max_tool_loops"
    finally:
        settings.max_tool_loops = original


async def test_failing_tool_is_reported_to_model_not_raised(db, mock_llm):
    mock_llm.reset([
        {"tool_calls": [{"name": "calculate", "arguments": {"expression": "this is not math"}}]},
        {"content": "That expression was invalid."},
    ])
    out = await run_agent(db, "Calculate nonsense.")

    assert out["result"] == "That expression was invalid."
    tool_messages = [m for m in mock_llm.messages_at(1) if m.get("role") == "tool"]
    assert '"ok": false' in tool_messages[0]["content"].replace('"ok":false', '"ok": false')


async def test_unknown_tool_is_handled_gracefully(db, mock_llm):
    mock_llm.reset([
        {"tool_calls": [{"name": "no_such_tool", "arguments": {}}]},
        {"content": "I could not use that tool."},
    ])
    out = await run_agent(db, "Use a tool that does not exist.")
    assert out["result"] == "I could not use that tool."


async def test_malformed_tool_arguments_do_not_crash(db, mock_llm):
    """Models sometimes emit invalid JSON for arguments."""
    mock_llm.reset([
        {"tool_calls": [{"name": "calculate", "arguments": {}}]},  # missing 'expression'
        {"content": "Recovered."},
    ])
    out = await run_agent(db, "Calculate with no arguments.")
    assert out["result"] == "Recovered."


async def test_high_risk_tool_creates_approval_instead_of_executing(db, mock_llm):
    mock_llm.reset([
        {"tool_calls": [{"name": "write_file", "arguments": {"path": "loop.txt", "content": "x"}}]},
        {"content": "I need approval first."},
    ])
    before = len(db.scalars(select(Approval)).all())
    out = await run_agent(db, "Write a file.")

    after = db.scalars(select(Approval).where(Approval.tool_name == "write_file")).all()
    assert len(after) > before - before, "an approval request must be created"
    assert out["result"] == "I need approval first."
    tool_messages = [m for m in mock_llm.messages_at(1) if m.get("role") == "tool"]
    assert "approval_required" in tool_messages[0]["content"]


async def test_disallowed_tools_are_not_advertised(db, mock_llm):
    """Tools blocked by policy must never be offered to the model."""
    mock_llm.reset([{"content": "ok"}])
    await run_agent(db, "Anything.")

    offered = mock_llm.tools_offered
    assert "calculate" in offered
    assert "shell_exec" not in offered, "shell is disabled by default and must be hidden"
    assert "http_request" not in offered, "network is disabled by default and must be hidden"


async def test_kill_switch_blocks_tool_execution_mid_loop(db, mock_llm):
    mock_llm.reset([
        {"tool_calls": [{"name": "calculate", "arguments": {"expression": "1+1"}}]},
        {"content": "Tool was blocked."},
    ])
    set_kill_switch(True, "test halt")
    try:
        out = await run_agent(db, "Try to use a tool.")
        tool_messages = [m for m in mock_llm.messages_at(1) if m.get("role") == "tool"]
        assert "Kill switch" in tool_messages[0]["content"]
        assert out["result"] == "Tool was blocked."
    finally:
        set_kill_switch(False)


async def test_provider_failure_falls_back_to_degraded(db, mock_llm):
    mock_llm.reset([{"content": "never reached"}])
    mock_llm.fail_times = 10
    out = await run_agent(db, "This should degrade.")
    assert out["degraded"] is True


async def test_run_is_persisted_with_trace(db, mock_llm):
    mock_llm.reset([
        {"tool_calls": [{"name": "calculate", "arguments": {"expression": "3*3"}}]},
        {"content": "Nine."},
    ])
    out = await run_agent(db, "Three squared?")

    stored = db.get(AgentRun, out["run_id"])
    assert stored.state == "succeeded"
    assert stored.result == "Nine."
    assert stored.provider == "local"
    assert any("tool" in entry for entry in stored.trace)
    assert stored.duration_ms >= 0


def test_conversation_history_is_sent_to_model(db, mock_llm, client):
    """A second turn must include the first turn's context."""
    mock_llm.reset([{"content": "First reply."}, {"content": "Second reply."}])
    first = client.post("/v1/chat", json={"message": "Remember: my code word is falcon."}).json()
    client.post("/v1/chat", json={"message": "What is my code word?", "conversation_id": first["conversation_id"]})

    second_turn_messages = mock_llm.messages_at(1)
    combined = " ".join(str(m.get("content", "")) for m in second_turn_messages)
    assert "falcon" in combined, "prior turn must be replayed as history"


