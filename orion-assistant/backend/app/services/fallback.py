from __future__ import annotations

import re

from app.services.embeddings import keyword_score

_SENT_RE = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_RE.split(text) if len(s.strip()) > 15]


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

    candidates = [c for c in candidates if c[0] > 0.15]
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
