"""Prompt size limits.

The agent replays conversation history and injects retrieved memory into every
request. Both were bounded by *count* and not by size, so a handful of large
turns could push the prompt far past a local model's context window -- which
the provider rejects outright, turning a working assistant into one that fails
on exactly the conversations the user has invested the most in.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.db.models import Conversation, Message
from app.services.agent_runtime import _clip, conversation_history


def seed(db, count: int, size: int, title: str = "c") -> str:
    conversation = Conversation(title=title)
    db.add(conversation)
    db.flush()
    for i in range(count):
        db.add(
            Message(
                conversation_id=conversation.id,
                role="user" if i % 2 == 0 else "assistant",
                content="x" * size,
            )
        )
    db.commit()
    return conversation.id


def total_chars(history: list[dict]) -> int:
    return sum(len(m["content"]) for m in history)


# ------------------------------------------------------------------ history
def test_history_is_bounded_by_size_not_just_message_count(db):
    """Twenty turns that each pasted a file is ~95k tokens of history. The
    message-count cap does nothing to stop that."""
    conversation = seed(db, settings.max_history_messages + 5, 20_000)

    history = conversation_history(db, conversation)

    assert total_chars(history) <= settings.max_history_chars + 200


def test_an_ordinary_conversation_is_not_trimmed(db):
    """The budget must not degrade the common case."""
    conversation = seed(db, 12, 300)

    history = conversation_history(db, conversation)

    # 12 messages, minus the newest (the turn being answered).
    assert len(history) == 11
    assert not any("truncated" in m["content"] for m in history)


def test_the_most_recent_turns_are_the_ones_kept(db):
    """Trimming from the wrong end would drop the context the next reply
    actually depends on."""
    conversation = Conversation(title="ordered")
    db.add(conversation)
    db.flush()
    for i in range(10):
        db.add(
            Message(
                conversation_id=conversation.id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"message-{i} " + "x" * 9_000,
            )
        )
    db.commit()

    history = conversation_history(db, conversation.id)
    kept = " ".join(m["content"][:20] for m in history)

    assert "message-8" in kept, "the newest eligible turn was dropped"
    assert "message-0" not in kept, "an ancient oversized turn was kept"


def test_a_single_oversized_message_is_truncated_rather_than_dropped(db):
    """Dropping it silently hides that the turn happened at all."""
    conversation = seed(db, 3, 60_000)

    history = conversation_history(db, conversation)

    assert history, "an oversized turn should still appear, trimmed"
    assert any("truncated" in m["content"] for m in history)


def test_history_stays_in_chronological_order(db):
    conversation = Conversation(title="order")
    db.add(conversation)
    db.flush()
    for i in range(6):
        db.add(Message(conversation_id=conversation.id, role="user", content=f"turn {i}"))
    db.commit()

    history = conversation_history(db, conversation.id)
    assert [m["content"] for m in history] == [f"turn {i}" for i in range(5)]


def test_no_conversation_means_no_history(db):
    assert conversation_history(db, None) == []


def test_the_turn_being_answered_is_excluded(db):
    """It is appended separately by the caller; including it duplicates the
    question in the prompt."""
    conversation = seed(db, 4, 50)
    assert len(conversation_history(db, conversation)) == 3


def test_an_empty_message_does_not_break_the_budget(db):
    conversation = Conversation(title="empty")
    db.add(conversation)
    db.flush()
    db.add(Message(conversation_id=conversation.id, role="user", content=""))
    db.add(Message(conversation_id=conversation.id, role="assistant", content="reply"))
    db.add(Message(conversation_id=conversation.id, role="user", content="now"))
    db.commit()

    history = conversation_history(db, conversation.id)
    assert [m["content"] for m in history] == ["", "reply"]


# -------------------------------------------------------------------- clip
def test_clip_leaves_short_text_alone():
    assert _clip("short", 100) == "short"


def test_clip_marks_what_it_removed():
    clipped = _clip("y" * 500, 100)
    assert len(clipped) < 200
    assert clipped.endswith("…[truncated]")


@pytest.mark.parametrize("value", ["", None])
def test_clip_tolerates_empty_input(value):
    assert _clip(value, 10) == ""


def test_a_huge_memory_cannot_dominate_the_prompt(db, monkeypatch):
    """Memories accept up to 10k characters each and up to eight are
    retrieved, so unclipped they could contribute 80k characters on their own.
    """
    import asyncio

    from app.services import agent_runtime

    async def fake_memories(*_args, **_kwargs):
        return [{"content": "m" * 10_000, "score": 0.9, "kind": "fact"}]

    async def fake_chunks(*_args, **_kwargs):
        return []

    monkeypatch.setattr(agent_runtime, "retrieve_memories", fake_memories)
    monkeypatch.setattr(agent_runtime, "search_chunks", fake_chunks)

    _memories, _chunks, context = asyncio.run(agent_runtime.build_context(db, "anything"))

    assert len(context) < settings.max_memory_chars + 500
    assert "truncated" in context


# =====================================================================
# Tool output accumulation
#
# Each result was clipped to 8,000 characters, which is not a bound on the
# conversation: results pile up across loop iterations. Six loops returning
# large payloads grew the prompt past 10k tokens with one call per turn, and
# several times that when the model requested calls in parallel.
# =====================================================================

import asyncio  # noqa: E402
import json  # noqa: E402

from app.services import agent_runtime  # noqa: E402
from app.tools.registry import ToolDefinition, registry  # noqa: E402


class _Call:
    def __init__(self, identifier: str, name: str = "bigread") -> None:
        self.id = identifier
        self.function = type("F", (), {"name": name, "arguments": "{}"})()


class _Resp:
    def __init__(self, tool_calls: list) -> None:
        self.provider = "local"
        self.model = "m"
        self.text = "" if tool_calls else "done"
        self.degraded = False
        self.latency_ms = 1
        self.tool_calls = tool_calls
        self.message = type("M", (), {"role": "assistant", "content": "", "tool_calls": tool_calls})()


@pytest.fixture
def big_tool():
    async def handler(_args):
        return {"content": "D" * 20_000}

    registry.register(
        ToolDefinition("bigread", "returns a lot", {"type": "object"},
                       handler=handler, category="files", risk="low")
    )
    return "bigread"


def run_with(monkeypatch, db, calls_per_turn: int) -> list[int]:
    """Drive the real loop and record the prompt size at each model call."""
    sizes: list[int] = []
    turn = {"n": 0}

    async def fake_chat(messages, **_kwargs):
        sizes.append(sum(len(json.dumps(m, default=str)) for m in messages))
        turn["n"] += 1
        if turn["n"] <= settings.max_tool_loops - 1:
            return _Resp([_Call(f"{turn['n']}_{j}") for j in range(calls_per_turn)])
        return _Resp([])

    monkeypatch.setattr(agent_runtime.router, "chat", fake_chat)
    asyncio.run(agent_runtime.run_agent(db, "read the big file", auto_approve=True))
    return sizes


def test_tool_output_is_capped_across_the_whole_run(db, big_tool, monkeypatch):
    sizes = run_with(monkeypatch, db, calls_per_turn=1)
    ceiling = settings.max_tool_output_chars + settings.max_history_chars

    assert max(sizes) < ceiling, f"prompt reached {max(sizes)} chars"


def test_parallel_tool_calls_do_not_multiply_the_budget(db, big_tool, monkeypatch):
    """Five calls per turn used to mean five times the output per loop."""
    sizes = run_with(monkeypatch, db, calls_per_turn=5)
    ceiling = settings.max_tool_output_chars + settings.max_history_chars

    assert max(sizes) < ceiling, f"parallel calls reached {max(sizes)} chars"


def test_the_model_is_told_when_output_was_withheld(db):
    """Sending nothing looks like the tool returned empty, which the model
    cannot distinguish from a genuine empty result."""
    call = _Call("x")
    message, remaining = agent_runtime._tool_message(call, {"ok": True, "content": "z" * 5_000}, 0)

    assert remaining == 0
    assert "budget" in message["content"]
    assert json.loads(message["content"])["ok"] is True


def test_a_result_that_fits_is_passed_through_intact(db):
    call = _Call("x")
    message, remaining = agent_runtime._tool_message(call, {"ok": True, "result": 42}, 24_000)

    assert json.loads(message["content"])["result"] == 42
    assert remaining < 24_000


def test_an_oversized_result_is_truncated_not_dropped(db):
    call = _Call("x")
    message, _remaining = agent_runtime._tool_message(
        call, {"ok": True, "content": "z" * 50_000}, 24_000
    )

    assert len(message["content"]) <= settings.max_tool_result_chars + 32
    assert message["content"].endswith("…[truncated]")


def test_the_budget_decreases_as_results_are_consumed(db):
    call = _Call("x")
    remaining = settings.max_tool_output_chars
    seen = []
    for _ in range(4):
        _message, remaining = agent_runtime._tool_message(call, {"content": "z" * 9_000}, remaining)
        seen.append(remaining)

    assert seen == sorted(seen, reverse=True), "budget must be monotonically consumed"
    assert seen[-1] == 0


# =====================================================================
# Learned skills in the prompt
#
# Skills are injected into EVERY request, so an oversized one is a permanent
# tax on the context window rather than a per-conversation problem. Their
# instructions can also be model-generated during distillation, which means
# nobody necessarily reviewed the length before it reached the prompt.
# =====================================================================

from app.db.models import Skill  # noqa: E402
from app.services.skills import skills_prompt_block  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_skills(db):
    """The suite shares one database; skills from another test would otherwise
    match these queries and change what fits in the budget."""
    db.query(Skill).delete()
    db.commit()
    yield
    db.query(Skill).delete()
    db.commit()


def add_skill(db, name: str, instructions: str, description: str = "does a thing") -> None:
    db.add(
        Skill(
            name=name,
            description=description,
            instructions=instructions,
            trigger_keywords=["deploy", "rollback"],
            confidence=0.9,
            status="active",
        )
    )
    db.commit()


def test_the_skill_block_is_bounded(db):
    """Three matching skills with rambling instructions measured at ~98,000
    characters, about 24,500 tokens, on every single request."""
    for i in range(5):
        add_skill(db, f"deploy-{i}", "Step: roll back the deploy and restart. " * 800)

    block = skills_prompt_block(db, "how do I deploy and rollback?")

    assert len(block) <= settings.max_skill_block_chars + 200


def test_one_oversized_skill_is_truncated_and_marked(db):
    add_skill(db, "huge", "x" * 40_000)

    block = skills_prompt_block(db, "deploy rollback")

    assert "truncated" in block
    assert len(block) <= settings.max_skill_block_chars + 200


def test_an_ordinary_skill_is_passed_through_intact(db):
    add_skill(
        db,
        "rollback",
        "1. find the previous image tag\n2. redeploy it\n3. verify health",
        description="Roll back a bad deploy.",
    )

    block = skills_prompt_block(db, "how do I roll back a deploy?")

    assert "verify health" in block
    assert "truncated" not in block


def test_skills_are_dropped_whole_rather_than_cut_mid_procedure(db):
    """Half a set of steps is worse than none: the model would follow a
    truncated procedure believing it was complete."""
    add_skill(db, "first", "1. do this\n2. then this")
    for i in range(4):
        add_skill(db, f"filler-{i}", "y" * 1_900)

    block = skills_prompt_block(db, "deploy rollback")

    # Every skill that appears at all appears with its heading.
    headings = block.count("### ")
    bodies = sum(1 for line in block.splitlines() if line.strip() and not line.startswith("#"))
    assert headings >= 1
    assert bodies >= headings, "a skill heading was emitted without its content"


def test_no_matching_skills_means_no_block(db):
    assert skills_prompt_block(db, "something entirely unrelated to anything stored") == ""


def test_skill_instructions_are_bounded_at_the_api(client):
    """Distillation writes model-generated instructions straight to the DB, so
    the field needs a ceiling like every other free-text input."""
    response = client.post(
        "/v1/skills",
        json={
            "name": "oversized",
            "description": "d",
            "instructions": "z" * 20_000,
            "trigger_keywords": ["x"],
        },
    )
    assert response.status_code == 422


def test_every_free_text_field_that_reaches_a_prompt_is_bounded():
    """A guard for the whole class of bug, not another instance of it.

    Three separate overflows -- history, tool output, skills -- all came from
    bounding by count while leaving size open. This fails if a new free-text
    field is added without a max_length, so the next one is caught at the
    commit that introduces it rather than by measuring the prompt again.
    """
    from annotated_types import MaxLen

    from app.api import schemas

    # Document bodies are legitimately large and are chunked before they ever
    # reach a prompt, so they are the one deliberate exemption.
    exempt = {("IngestTextRequest", "content")}

    unbounded: list[str] = []
    for name in dir(schemas):
        model = getattr(schemas, name)
        if not (isinstance(model, type) and issubclass(model, schemas.BaseModel)):
            continue
        for field_name, field in model.model_fields.items():
            annotation = str(field.annotation)
            is_plain_string = annotation in {"<class 'str'>", "str | None"}
            if not is_plain_string or (name, field_name) in exempt:
                continue
            if field.metadata and any(isinstance(m, MaxLen) for m in field.metadata):
                continue
            # Enum-style fields constrained by pattern are bounded in practice.
            if any(getattr(m, "pattern", None) for m in field.metadata or []):
                continue
            unbounded.append(f"{name}.{field_name}")

    assert not unbounded, (
        "free-text fields with no max_length: " + ", ".join(sorted(unbounded))
    )
