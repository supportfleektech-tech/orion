from __future__ import annotations

import hashlib
import logging
import math
import re

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_cache: dict[str, list[float]] = {}
_provider_state = {"remote_ok": True}


def _stem(word: str) -> str:
    """Strip the common English suffixes so morphological variants collide.

    The hashed embedder and keyword_score both compare exact tokens, so
    without this "units" and "unit", or "prefers" and "preference", score zero
    against each other -- offline retrieval only found text worded exactly
    like the question. Not a real stemmer, deliberately: this needs to be
    cheap, dependency-free and deterministic, and it only has to make related
    words hash to the same bucket.
    """
    for suffix in ("ences", "ence", "ing", "ers", "er", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _tokens(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN_RE.findall(text.lower())]


def hashed_embedding(text: str, dim: int | None = None) -> list[float]:
    """Deterministic local embedding (hashed bag of n-grams).

    Used when no embedding model is reachable so retrieval always works.
    Quality is lower than a neural embedder but it is fast, free and offline.
    """
    dim = dim or settings.embedding_dim
    vec = [0.0] * dim
    toks = _tokens(text)
    grams = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]
    if not grams:
        return vec
    for gram in grams:
        h = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        sign = 1.0 if h[4] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


async def _remote_embedding(text: str) -> list[float] | None:
    base = settings.ollama_base_url.removesuffix("/v1")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{base}/api/embed",
                json={"model": settings.ollama_embed_model, "input": text},
            )
            r.raise_for_status()
            data = r.json()
        embeddings = data.get("embeddings") or []
        if not embeddings:
            return None
        _provider_state["remote_ok"] = True
        return [float(x) for x in embeddings[0]]
    except Exception as exc:  # offline / model missing
        if _provider_state["remote_ok"]:
            log.warning("Embedding backend unavailable (%s); using local hashed embeddings", exc)
        _provider_state["remote_ok"] = False
        return None


async def embed_text(text: str) -> list[float]:
    text = (text or "").strip()
    if not text:
        return [0.0] * settings.embedding_dim
    key = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if key in _cache:
        return _cache[key]
    vec = await _remote_embedding(text)
    if vec is None:
        vec = hashed_embedding(text)
    if len(_cache) > 4000:
        _cache.clear()
    _cache[key] = vec
    return vec


async def embed_many(texts: list[str]) -> list[list[float]]:
    return [await embed_text(t) for t in texts]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    similarity = dot / (na * nb)
    # Clamp to [0, 1]. A negative cosine is meaningless for the hashed
    # fallback -- it is an artefact of random sign collisions between hash
    # buckets, not evidence of opposite meaning -- and it was actively
    # subtracting from the blended score, pushing genuinely related text below
    # the retrieval threshold when no embedding model was reachable.
    return max(0.0, similarity)


def keyword_score(query: str, content: str) -> float:
    q = set(_tokens(query))
    if not q:
        return 0.0
    c = set(_tokens(content))
    return len(q & c) / len(q)
