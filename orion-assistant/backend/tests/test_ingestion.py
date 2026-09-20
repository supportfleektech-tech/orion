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


# =====================================================================
# Format handling
#
# The feature matrix promises txt, md, pdf, docx, html, csv, json and code.
# Each claim gets a test, because a format that silently indexes garbage is
# worse than one that is honestly unsupported.
# =====================================================================

def test_html_is_parsed_to_prose_not_indexed_as_markup(tmp_path):
    """.html is in TEXT_SUFFIXES, so the text branch used to match first and
    the parser below it was unreachable. Pages were indexed as raw tags, and
    a search for 'script' matched every page on the site."""
    page = tmp_path / "page.html"
    page.write_text(
        "<html><head><title>T</title></head><body>"
        "<h1>Quarterly report</h1>"
        "<script>var tracking = 1;</script>"
        "<style>.x { color: red }</style>"
        "<p>Revenue grew by twelve percent.</p>"
        "</body></html>"
    )

    text = read_source(page)

    assert "Revenue grew by twelve percent." in text
    assert "<" not in text, "markup leaked into the indexed text"
    assert "tracking" not in text, "inline JavaScript was indexed as prose"
    assert "color: red" not in text, "CSS was indexed as prose"


def test_htm_extension_is_treated_the_same(tmp_path):
    page = tmp_path / "old.htm"
    page.write_text("<html><body><p>Still HTML.</p></body></html>")
    assert read_source(page).strip() == "Still HTML."


def test_plain_text_is_read_verbatim(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("# Heading\n\nBody text.")
    assert read_source(note) == "# Heading\n\nBody text."


def test_source_code_keeps_its_structure(tmp_path):
    """Code is indexed as-is: indentation and symbols carry meaning."""
    code = tmp_path / "mod.py"
    code.write_text("def add(a, b):\n    return a + b\n")
    assert "return a + b" in read_source(code)


def test_csv_and_json_are_read_as_text(tmp_path):
    csv = tmp_path / "rows.csv"
    csv.write_text("name,total\nwidget,12\n")
    assert "widget,12" in read_source(csv)

    blob = tmp_path / "data.json"
    blob.write_text('{"key": "value"}')
    assert '"key": "value"' in read_source(blob)


def test_an_unsupported_type_fails_with_a_useful_message(tmp_path):
    binary = tmp_path / "archive.zip"
    binary.write_bytes(b"PK\x03\x04")
    with pytest.raises(ValueError, match="Unsupported file type"):
        read_source(binary)


def test_a_file_with_no_extension_is_reported_by_name(tmp_path):
    odd = tmp_path / "Makefile"
    odd.write_text("all:\n\techo hi")
    with pytest.raises(ValueError, match="Makefile"):
        read_source(odd)


def test_invalid_utf8_is_replaced_rather_than_crashing(tmp_path):
    """A single bad byte in a log file must not abort an entire batch."""
    rough = tmp_path / "broken.log"
    rough.write_bytes(b"valid start \xff\xfe still readable")
    text = read_source(rough)
    assert "valid start" in text
    assert "still readable" in text


def test_pdf_text_is_extracted(tmp_path):
    """Guards the pypdf wiring, not pypdf itself."""
    pypdf = pytest.importorskip("pypdf")

    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    target = tmp_path / "doc.pdf"
    with target.open("wb") as handle:
        writer.write(handle)

    # A blank page yields no text, but it must not raise.
    assert isinstance(read_source(target), str)


def test_docx_paragraphs_are_extracted(tmp_path):
    docx = pytest.importorskip("docx")

    document = docx.Document()
    document.add_paragraph("First paragraph.")
    document.add_paragraph("Second paragraph.")
    target = tmp_path / "doc.docx"
    document.save(str(target))

    text = read_source(target)
    assert "First paragraph." in text
    assert "Second paragraph." in text
