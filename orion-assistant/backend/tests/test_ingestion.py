from pathlib import Path

import pytest

from app.services.ingestion import chunk_text, ingest_text, read_source, search_chunks


def test_chunk_overlap():
    chunks = chunk_text("a" * 2500)
    assert len(chunks) >= 2 and all(chunks)


def test_chunk_empty():
    assert chunk_text("   ") == []


def test_read_markdown(tmp_path: Path):
    p = tmp_path / "x.md"
    p.write_text("hello", encoding="utf-8")
    assert read_source(p) == "hello"


def test_unsupported_type(tmp_path: Path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"\x00")
    with pytest.raises(ValueError):
        read_source(p)


@pytest.mark.asyncio
async def test_ingest_and_search(db):
    out = await ingest_text(db, "notes.md", "ORION stores durable memories in PostgreSQL or SQLite.")
    assert out["chunks"] >= 1
    results = await search_chunks(db, "where are memories stored", limit=3)
    assert results and "ORION" in results[0]["content"]
