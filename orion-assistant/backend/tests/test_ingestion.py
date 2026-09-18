from pathlib import Path
from app.services.ingestion import chunk_text, read_source


def test_chunk_overlap():
    chunks = chunk_text("a" * 2500)
    assert len(chunks) >= 2
    assert all(chunks)


def test_read_markdown(tmp_path: Path):
    p = tmp_path / "x.md"
    p.write_text("hello", encoding="utf-8")
    assert read_source(p) == "hello"
