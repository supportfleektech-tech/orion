import pytest

from app.services.embeddings import cosine, hashed_embedding
from app.services.memory import delete_memory, retrieve_memories, write_memory


def test_hashed_embedding_similarity():
    a = hashed_embedding("the sky is blue today")
    b = hashed_embedding("the sky is blue today")
    c = hashed_embedding("database migration strategy")
    assert cosine(a, b) > 0.99
    assert cosine(a, c) < 0.5


@pytest.mark.asyncio
async def test_memory_roundtrip(db):
    mid = await write_memory(db, "The user prefers dark mode interfaces.", kind="preference", key="ui.theme")
    results = await retrieve_memories(db, "what theme does the user like")
    assert any("dark mode" in r["content"] for r in results)
    assert delete_memory(db, mid) is True


@pytest.mark.asyncio
async def test_memory_upsert_by_key(db):
    first = await write_memory(db, "Timezone is UTC", key="user.tz")
    second = await write_memory(db, "Timezone is CET", key="user.tz")
    assert first == second
