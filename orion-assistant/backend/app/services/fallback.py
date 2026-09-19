from __future__ import annotations

import re

from app.services.embeddings import keyword_score

_SENT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[a-z0-9]+")

#: Words that carry no topical signal. Overlap on these alone made unrelated
#: text look relevant: "what is the airspeed velocity of an unladen swallow?"
#: scored 0.22 against a database runbook purely on "is" and "the", clearing
#: the 0.15 threshold and producing a confidently irrelevant answer.
_STOPWORDS = frozenset("""
a an and are as at be been but by can could did do does for from had has have
how i if in into is it its me my of on or our should so than that the their
them then there these they this to was we were what when where which who why
will with would you your
""".split())


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_RE.split(text) if len(s.strip()) > 15]


def _stem(word: str) -> str:
    """Crude suffix stripping so "units" matches "unit" and "prefers" matches
    "preference". Not linguistically correct, but this only decides whether
    two pieces of text are about the same thing, and a real stemmer is not
    worth a dependency for that."""
    for suffix in ("ences", "ence", "ing", "ers", "er", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _content_words(text: str) -> set[str]:
    return {
        _stem(w) for w in _WORD_RE.findall(text.lower())
        if w not in _STOPWORDS and len(w) > 1
    }


def _content_overlap(task: str, sentence: str) -> float:
    """Fraction of the query's *meaningful* words present in the sentence.

    keyword_score counts every token, which is fine for ranking candidates
    against each other but useless as an absolute relevance test. Here the
    question is "is this related at all?", so stopwords have to be excluded.
    """
    query_words = _content_words(task)
    if not query_words:
        return 0.0
    return len(query_words & _content_words(sentence)) / len(query_words)


def extractive_answer(task: str, memories: list[dict], knowledge: list[dict]) -> str | None:
    """Compose a grounded answer from retrieved context when no LLM is reachable.

    This keeps ORION useful offline: it cannot reason, but it can surface the most
    relevant stored evidence and say exactly what it is doing.
    """
    candidates: list[tuple[float, str, str]] = []
    for memory in memories:
        for sentence in _sentences(memory["content"]) or [memory["content"]]:
            candidates.append((keyword_score(task, sentence) + 0.2 * float(memory.get("score", 0)), sentence, f"memory/{memory['kind']}"))
    for hit in knowledge:
        for sentence in _sentences(hit["content"]) or [hit["content"]]:
            candidates.append((keyword_score(task, sentence) + 0.2 * float(hit.get("score", 0)), sentence, f"knowledge/{hit.get('name') or 'document'}"))

    # Rank by the blended score, but only keep sentences that actually share
    # meaningful words with the question. Without this second gate the answer
    # is assembled from whatever happens to be stored, which reads as a
    # confident non-sequitur rather than an honest "I do not know".
    candidates = [c for c in candidates if c[0] > 0.15 and _content_overlap(task, c[1]) >= 0.2]
    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    seen: set[str] = set()
    lines: list[str] = []
    for _score, sentence, source in candidates:
        key = sentence[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- {sentence.strip()}  \n  _source: {source}_")
        if len(lines) >= 5:
            break

    return (
        "No language model is reachable, so this is a **retrieval-only answer** "
        "assembled directly from stored context:\n\n"
        + "\n".join(lines)
        + "\n\nStart Ollama or configure `OPENROUTER_API_KEY` for full reasoning."
    )
