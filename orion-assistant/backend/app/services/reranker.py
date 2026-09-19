"""Second-pass reranking over first-stage retrieval hits.

First-stage retrieval optimises for recall: cast a wide net with cheap vector +
keyword scoring. That net reliably contains the right chunk but frequently does
not rank it first. Reranking re-scores a small candidate set with signals that
are too expensive to run over the whole corpus.

Two backends:

* **cross-encoder** (optional) — a real relevance model scoring (query, chunk)
  pairs jointly. Best quality, needs `sentence-transformers`.
* **lexical** (always available) — a BM25-style pass combined with coverage,
  proximity and position heuristics. No dependencies, no download, and still a
  clear improvement over raw cosine on keyword-bearing queries.

The lexical path is the default so reranking is always on. The cross-encoder is
used automatically when installed and configured.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any

from app.core.config import settings

log = logging.getLogger(__name__)

_cross_encoder: Any = None
_cross_encoder_failed = False

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "with", "is", "are",
    "was", "were", "be", "been", "it", "its", "this", "that", "these", "those", "as", "at",
    "by", "from", "how", "what", "when", "where", "which", "who", "why", "do", "does", "did",
}


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t not in STOPWORDS]


# ------------------------------------------------------------------ lexical
def bm25_scores(query: str, documents: list[str], k1: float = 1.5, b: float = 0.75) -> list[float]:
    """Classic BM25 over the candidate set.

    Scoring within the candidates (rather than the corpus) is intentional: we
    only need to order these few, and it keeps the pass dependency-free.
    """
    query_terms = tokenize(query)
    if not query_terms or not documents:
        return [0.0] * len(documents)

    tokenized = [tokenize(doc) for doc in documents]
    lengths = [len(doc) or 1 for doc in tokenized]
    avg_length = sum(lengths) / len(lengths)
    total_docs = len(tokenized)

    scores = [0.0] * total_docs
    for term in set(query_terms):
        containing = sum(1 for doc in tokenized if term in doc)
        if containing == 0:
            continue
        # BM25 inverse document frequency, floored to stay positive.
        idf = max(0.01, math.log(1 + (total_docs - containing + 0.5) / (containing + 0.5)))
        for index, doc in enumerate(tokenized):
            frequency = doc.count(term)
            if not frequency:
                continue
            denominator = frequency + k1 * (1 - b + b * lengths[index] / avg_length)
            scores[index] += idf * (frequency * (k1 + 1)) / denominator
    return scores


def coverage_score(query: str, document: str) -> float:
    """Fraction of distinct query terms present. Rewards answering everything."""
    query_terms = set(tokenize(query))
    if not query_terms:
        return 0.0
    doc_terms = set(tokenize(document))
    return len(query_terms & doc_terms) / len(query_terms)


def proximity_score(query: str, document: str) -> float:
    """Reward query terms appearing close together, not scattered."""
    query_terms = set(tokenize(query))
    doc_terms = tokenize(document)
    if len(query_terms) < 2 or not doc_terms:
        return 0.0
    positions = [i for i, term in enumerate(doc_terms) if term in query_terms]
    if len(positions) < 2:
        return 0.0
    matched = {doc_terms[i] for i in positions}
    if len(matched) < 2:
        return 0.0
    # Smallest window containing at least two distinct query terms.
    best = None
    for start in range(len(positions)):
        seen = set()
        for end in range(start, len(positions)):
            seen.add(doc_terms[positions[end]])
            if len(seen) >= min(2, len(query_terms)):
                span = positions[end] - positions[start] + 1
                best = span if best is None else min(best, span)
                break
    if best is None:
        return 0.0
    return 1.0 / (1.0 + math.log(1 + best))


def normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    low, high = min(values), max(values)
    if high - low < 1e-9:
        return [0.5] * len(values)
    return [(v - low) / (high - low) for v in values]


def lexical_rerank(query: str, candidates: list[dict]) -> list[dict]:
    """Blend first-stage score with BM25, coverage and proximity."""
    documents = [c.get("content", "") for c in candidates]
    bm25 = normalize(bm25_scores(query, documents))
    retrieval = normalize([float(c.get("score", 0.0)) for c in candidates])

    ranked = []
    for index, candidate in enumerate(candidates):
        document = documents[index]
        coverage = coverage_score(query, document)
        proximity = proximity_score(query, document)
        combined = (
            0.35 * retrieval[index]
            + 0.35 * bm25[index]
            + 0.20 * coverage
            + 0.10 * proximity
        )
        enriched = dict(candidate)
        enriched["retrieval_score"] = candidate.get("score")
        enriched["rerank_score"] = round(combined, 4)
        enriched["rerank_signals"] = {
            "bm25": round(bm25[index], 4),
            "coverage": round(coverage, 4),
            "proximity": round(proximity, 4),
        }
        ranked.append(enriched)

    ranked.sort(key=lambda c: c["rerank_score"], reverse=True)
    return ranked


# ------------------------------------------------------------ cross-encoder
def load_cross_encoder() -> Any:
    """Load the cross-encoder once. Returns None when unavailable."""
    global _cross_encoder, _cross_encoder_failed
    if _cross_encoder is not None or _cross_encoder_failed:
        return _cross_encoder
    try:
        from sentence_transformers import CrossEncoder

        _cross_encoder = CrossEncoder(settings.reranker_model)
        log.info("Cross-encoder reranker loaded: %s", settings.reranker_model)
    except Exception as exc:
        _cross_encoder_failed = True
        log.info("Cross-encoder unavailable (%s); using lexical reranker.", exc)
    return _cross_encoder


def cross_encoder_rerank(query: str, candidates: list[dict]) -> list[dict] | None:
    model = load_cross_encoder()
    if model is None:
        return None
    try:
        pairs = [(query, c.get("content", "")) for c in candidates]
        scores = normalize([float(s) for s in model.predict(pairs)])
    except Exception as exc:
        log.warning("Cross-encoder scoring failed (%s); falling back to lexical.", exc)
        return None

    ranked = []
    for index, candidate in enumerate(candidates):
        enriched = dict(candidate)
        enriched["retrieval_score"] = candidate.get("score")
        enriched["rerank_score"] = round(scores[index], 4)
        enriched["rerank_signals"] = {"cross_encoder": round(scores[index], 4)}
        ranked.append(enriched)
    ranked.sort(key=lambda c: c["rerank_score"], reverse=True)
    return ranked


# -------------------------------------------------------------------- entry
def rerank(query: str, candidates: list[dict], limit: int | None = None) -> list[dict]:
    """Reorder candidates by relevance to the query.

    Always returns a list; never raises. If reranking is disabled or the input
    is trivial, candidates are returned untouched (minus the truncation).
    """
    limit = limit or settings.max_context_chunks
    if not candidates:
        return []
    if not settings.rerank_enabled or len(candidates) == 1:
        return candidates[:limit]

    try:
        ranked = None
        if settings.reranker_backend == "cross-encoder":
            ranked = cross_encoder_rerank(query, candidates)
        if ranked is None:
            ranked = lexical_rerank(query, candidates)
        return ranked[:limit]
    except Exception:
        log.exception("Reranking failed; returning first-stage order")
        return candidates[:limit]
