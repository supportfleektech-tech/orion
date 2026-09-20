"""Reranking: scoring signals, ordering quality, and safe degradation."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services import reranker as rr


def candidate(content: str, score: float = 0.5, name: str = "doc") -> dict:
    return {"id": content[:8], "content": content, "score": score, "name": name, "chunk_index": 0}


# ------------------------------------------------------------------ tokens
def test_tokenize_drops_stopwords_and_punctuation():
    assert rr.tokenize("What is the deployment runbook?") == ["deployment", "runbook"]


def test_tokenize_handles_empty():
    assert rr.tokenize("") == []
    assert rr.tokenize("the and of") == []


# -------------------------------------------------------------------- bm25
def test_bm25_ranks_term_bearing_document_first():
    docs = ["nothing relevant here at all", "postgres replication lag troubleshooting"]
    scores = rr.bm25_scores("postgres replication", docs)
    assert scores[1] > scores[0]


def test_bm25_rewards_rarer_terms():
    """A term appearing in every document carries less signal than a rare one."""
    docs = ["database postgres", "database mysql", "database sqlite"]
    scores = rr.bm25_scores("postgres", docs)
    assert scores[0] > scores[1]
    assert scores[0] > scores[2]


def test_bm25_zero_for_absent_terms():
    assert rr.bm25_scores("kubernetes", ["baking sourdough bread"]) == [0.0]


def test_bm25_empty_inputs():
    assert rr.bm25_scores("", ["some text"]) == [0.0]
    assert rr.bm25_scores("query", []) == []


def test_bm25_length_normalisation_penalises_padding():
    """Stuffing a term into a huge document should not beat a focused one."""
    focused = "redis cache eviction policy"
    padded = "redis cache eviction policy " + ("filler words here " * 200)
    scores = rr.bm25_scores("redis eviction", [focused, padded])
    assert scores[0] > scores[1]


# ---------------------------------------------------------------- coverage
def test_coverage_full_and_partial():
    assert rr.coverage_score("alpha beta", "alpha beta gamma") == 1.0
    assert rr.coverage_score("alpha beta", "alpha only") == 0.5
    assert rr.coverage_score("alpha beta", "nothing") == 0.0


def test_coverage_with_no_query_terms():
    assert rr.coverage_score("the and of", "anything") == 0.0


# --------------------------------------------------------------- proximity
def test_proximity_prefers_adjacent_terms():
    near = rr.proximity_score("backup restore", "backup restore procedure")
    far = rr.proximity_score(
        "backup restore", "backup " + ("padding " * 50) + "restore"
    )
    assert near > far


def test_proximity_zero_for_single_term_query():
    assert rr.proximity_score("backup", "backup procedure") == 0.0


def test_proximity_zero_when_only_one_term_present():
    assert rr.proximity_score("backup restore", "backup only here") == 0.0


# --------------------------------------------------------------- normalize
def test_normalize_maps_to_unit_range():
    assert rr.normalize([1.0, 3.0, 5.0]) == [0.0, 0.5, 1.0]


def test_normalize_identical_values_is_neutral():
    assert rr.normalize([2.0, 2.0, 2.0]) == [0.5, 0.5, 0.5]


def test_normalize_empty():
    assert rr.normalize([]) == []


# ------------------------------------------------------------------ rerank
def test_rerank_promotes_the_actually_relevant_chunk():
    """The core claim: a strong lexical match beats a higher first-stage score."""
    candidates = [
        candidate("General notes about the company and its history.", score=0.61),
        candidate("To rotate the TLS certificate, run certbot renew and reload nginx.", score=0.58),
        candidate("Office opening hours and parking information.", score=0.55),
    ]
    ranked = rr.rerank("how do I rotate the TLS certificate", candidates, limit=3)
    assert "certbot" in ranked[0]["content"]


def test_rerank_preserves_original_score_and_adds_signals():
    ranked = rr.rerank("deployment runbook", [candidate("the deployment runbook", 0.42)], limit=5)
    # Single candidate short-circuits, so use two to exercise the full path.
    ranked = rr.rerank(
        "deployment runbook",
        [candidate("the deployment runbook", 0.42), candidate("unrelated text", 0.41)],
        limit=5,
    )
    assert ranked[0]["retrieval_score"] == 0.42
    assert "rerank_score" in ranked[0]
    assert set(ranked[0]["rerank_signals"]) == {"bm25", "coverage", "proximity"}


def test_rerank_respects_limit():
    candidates = [candidate(f"chunk number {i} about postgres", 0.5) for i in range(10)]
    assert len(rr.rerank("postgres", candidates, limit=3)) == 3


def test_rerank_empty_input():
    assert rr.rerank("anything", []) == []


def test_rerank_single_candidate_is_passed_through():
    only = [candidate("just one", 0.9)]
    assert rr.rerank("query", only, limit=5) == only


def test_rerank_disabled_preserves_order(monkeypatch):
    monkeypatch.setattr(settings, "rerank_enabled", False)
    candidates = [candidate("irrelevant", 0.9), candidate("postgres replication", 0.1)]
    ranked = rr.rerank("postgres replication", candidates, limit=2)
    assert ranked[0]["content"] == "irrelevant"
    assert "rerank_score" not in ranked[0]


def test_rerank_never_raises_on_malformed_candidates():
    """Missing content must degrade, not explode."""
    ranked = rr.rerank("query", [{"score": 0.5}, {"content": None, "score": 0.4}], limit=2)
    assert len(ranked) == 2


def test_rerank_is_deterministic():
    candidates = [candidate("postgres replication lag", 0.5), candidate("mysql tuning", 0.5)]
    first = [c["id"] for c in rr.rerank("postgres replication", candidates, limit=2)]
    second = [c["id"] for c in rr.rerank("postgres replication", candidates, limit=2)]
    assert first == second


# ---------------------------------------------------------- cross-encoder
def test_cross_encoder_backend_falls_back_when_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "reranker_backend", "cross-encoder")
    monkeypatch.setattr(rr, "load_cross_encoder", lambda: None)
    ranked = rr.rerank(
        "postgres replication",
        [candidate("unrelated", 0.9), candidate("postgres replication guide", 0.1)],
        limit=2,
    )
    assert "bm25" in ranked[0]["rerank_signals"], "should have used the lexical path"


def test_cross_encoder_is_used_when_available(monkeypatch):
    class FakeEncoder:
        def predict(self, pairs):
            # Score by whether the chunk mentions the query's key term.
            return [1.0 if "postgres" in text else 0.0 for _, text in pairs]

    monkeypatch.setattr(settings, "reranker_backend", "cross-encoder")
    monkeypatch.setattr(rr, "load_cross_encoder", lambda: FakeEncoder())
    ranked = rr.rerank(
        "replication",
        [candidate("unrelated notes", 0.9), candidate("postgres replication guide", 0.1)],
        limit=2,
    )
    assert "postgres" in ranked[0]["content"]
    assert "cross_encoder" in ranked[0]["rerank_signals"]


def test_cross_encoder_scoring_failure_falls_back(monkeypatch):
    class BrokenEncoder:
        def predict(self, pairs):
            raise RuntimeError("model blew up")

    monkeypatch.setattr(settings, "reranker_backend", "cross-encoder")
    monkeypatch.setattr(rr, "load_cross_encoder", lambda: BrokenEncoder())
    ranked = rr.rerank(
        "postgres",
        [candidate("unrelated", 0.9), candidate("postgres guide", 0.1)],
        limit=2,
    )
    assert ranked, "must still return results"
    assert "bm25" in ranked[0]["rerank_signals"]


# ------------------------------------------------------------- integration
@pytest.mark.anyio
async def test_search_chunks_applies_reranking(db):
    from app.services.ingestion import ingest_text, search_chunks

    # Each document becomes its own chunk, so reranking has a real pool to order.
    # Distinct source_path per document: ingest_text replaces documents that
    # share a path, so the default "inline" would leave only the last one.
    await ingest_text(
        db, "rerank-history", "Company history and general background information.",
        source_path="rr-history",
    )
    await ingest_text(
        db, "rerank-certs",
        "The certificate rotation procedure: run certbot renew then reload nginx.",
        source_path="rr-certs",
    )
    await ingest_text(
        db, "rerank-menu", "Cafeteria menu and opening hours for staff.",
        source_path="rr-menu",
    )
    # A query touching every document, so more than one candidate survives the
    # relevance floor and the reranking pass actually runs.
    results = await search_chunks(db, "company certificate cafeteria information", limit=3)
    assert len(results) > 1, "need a real candidate pool to rerank"
    assert "rerank_score" in results[0]
    assert "retrieval_score" in results[0]
    assert results[0]["rerank_score"] >= results[-1]["rerank_score"]


@pytest.mark.anyio
async def test_search_chunks_puts_the_answer_first(db):
    """End-to-end: the chunk that answers the question should rank first."""
    from app.services.ingestion import ingest_text, search_chunks

    await ingest_text(
        db, "ops-backup", "Backup policy: nightly snapshots are retained for 30 days.",
        source_path="ops-backup",
    )
    await ingest_text(
        db, "ops-certs", "Certificate renewal: run certbot renew, then reload nginx.",
        source_path="ops-certs",
    )
    results = await search_chunks(db, "how do I renew the certificate", limit=2)
    assert results
    assert "certbot" in results[0]["content"]
