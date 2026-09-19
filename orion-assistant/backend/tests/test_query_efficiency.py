"""Query-count and pagination guards.

These assert *how* the database is used, not just the result. An N+1 is
invisible in a functional test -- the response is correct, it just costs one
query per row -- so it only shows up once someone has a few hundred rows and
the page feels slow. Pinning the count catches it at the commit that adds it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event

from app.db.database import engine
from app.db.models import Conversation, Document, Message


@pytest.fixture
def count_queries():
    """Count SQL statements issued inside the block."""
    state = {"n": 0}

    def bump(*_args, **_kwargs):
        state["n"] += 1

    event.listen(engine, "before_cursor_execute", bump)
    try:
        yield state
    finally:
        event.remove(engine, "before_cursor_execute", bump)


def seed_conversations(db, count: int, messages_each: int = 5, tag: str = "conv") -> list[str]:
    """Seed and return the ids. The suite shares one database, so tests key
    off what they created rather than assuming an empty table."""
    ids = []
    for i in range(count):
        conversation = Conversation(title=f"{tag} {i}")
        db.add(conversation)
        db.flush()
        ids.append(conversation.id)
        for j in range(messages_each):
            db.add(Message(conversation_id=conversation.id, role="user", content=f"m{j}"))
    db.commit()
    return ids


def seed_documents(db, count: int, tag: str = "doc") -> None:
    import uuid

    unique = uuid.uuid4().hex[:8]
    for i in range(count):
        db.add(
            Document(
                name=f"{tag}{i}-{unique}.md", path=f"/kb/{tag}{i}-{unique}.md",
                mime_type="text/markdown", hash=f"hash-{unique}-{i}",
                size_bytes=10, chunk_count=1,
            )
        )
    db.commit()


# ------------------------------------------------------------------- N+1
def test_listing_conversations_does_not_scale_queries_with_rows(client, db, count_queries):
    """Message counts were fetched one SELECT at a time: 51 queries for 50
    conversations. The cost has to stay flat as the sidebar grows."""
    seed_conversations(db, 30)

    count_queries["n"] = 0
    response = client.get("/v1/conversations?limit=30")

    assert response.status_code == 200
    assert len(response.json()["conversations"]) == 30
    assert count_queries["n"] <= 4, (
        f"{count_queries['n']} queries for 30 conversations -- this is an N+1"
    )


def test_message_counts_are_still_correct_after_the_grouped_query(client, db):
    """Batching the counts must not silently return zeros."""
    ids = set(seed_conversations(db, 3, messages_each=7, tag="counted"))

    conversations = client.get("/v1/conversations?limit=200").json()["conversations"]
    mine = [c for c in conversations if c["id"] in ids]

    assert len(mine) == 3
    assert all(c["message_count"] == 7 for c in mine)


def test_a_conversation_with_no_messages_reports_zero_not_missing(client, db):
    """The grouped query returns no row for an empty conversation, so the
    lookup needs a default."""
    db.add(Conversation(title="empty"))
    db.commit()

    conversations = client.get("/v1/conversations").json()["conversations"]
    empty = next(c for c in conversations if c["title"] == "empty")
    assert empty["message_count"] == 0


# ------------------------------------------------------------ pagination
def test_documents_are_bounded_by_default(client, db):
    """This backs a UI list that grows with every ingest."""
    seed_documents(db, 250)

    body = client.get("/v1/knowledge/documents").json()
    assert len(body["documents"]) == 200, "the default page must be capped"
    assert body["total"] >= 250


def test_documents_report_the_true_total_so_the_ui_can_say_so(client, db):
    """Without a total the UI cannot tell the user the list is truncated."""
    seed_documents(db, 30)
    body = client.get("/v1/knowledge/documents?limit=10").json()
    assert len(body["documents"]) == 10
    assert body["total"] > len(body["documents"])


def test_documents_paginate(client, db):
    seed_documents(db, 20)
    first = client.get("/v1/knowledge/documents?limit=5").json()["documents"]
    second = client.get("/v1/knowledge/documents?limit=5&offset=5").json()["documents"]
    assert {d["id"] for d in first}.isdisjoint({d["id"] for d in second})


def test_an_absurd_limit_is_refused_rather_than_honoured(client):
    """Otherwise ?limit=10000000 is a trivial memory-exhaustion request."""
    assert client.get("/v1/knowledge/documents?limit=99999").status_code == 422
    assert client.get("/v1/knowledge/documents?limit=0").status_code == 422
    assert client.get("/v1/knowledge/documents?offset=-1").status_code == 422


def test_listing_documents_is_a_constant_number_of_queries(client, db, count_queries):
    seed_documents(db, 40)

    count_queries["n"] = 0
    client.get("/v1/knowledge/documents")

    assert count_queries["n"] <= 3, f"{count_queries['n']} queries to list documents"
