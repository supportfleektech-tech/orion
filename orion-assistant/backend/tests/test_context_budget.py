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
