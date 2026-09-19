"""Degraded mode: the offline answer path.

README promises ORION stays useful with no model reachable. That promise is
only worth anything if the retrieval-only answer is *relevant* -- assembling
whatever happens to be stored and presenting it as an answer is worse than
admitting ignorance, because the user cannot tell the difference.
"""

from __future__ import annotations

import pytest

from app.services.fallback import _content_overlap, extractive_answer

RUNBOOK = [
    {
        "content": (
            "The staging database is restored from the nightly snapshot in S3. "
            "To roll back a deploy, revert to the previous image tag and restart "
            "the api service. Contact the on-call engineer via the ops channel."
        ),
        "name": "runbook.md",
        "score": 0.4,
    }
]


# --------------------------------------------------------------- relevance
def test_a_relevant_question_is_answered_from_stored_context():
    answer = extractive_answer("how do I roll back a deploy?", [], RUNBOOK)

    assert answer is not None
    assert "revert to the previous image tag" in answer
    assert "runbook.md" in answer, "the source has to be attributed"


def test_an_unrelated_question_returns_nothing_rather_than_a_non_sequitur():
    """This was the bug. 'what is the airspeed velocity of an unladen
    swallow?' scored 0.22 against a database runbook on the overlap of "is"
    and "the" alone, clearing the threshold and producing a confident,
    completely irrelevant answer."""
    assert extractive_answer(
        "what is the airspeed velocity of an unladen swallow?", [], RUNBOOK
    ) is None


@pytest.mark.parametrize(
    "question",
    [
        "what is the weather in Nairobi tomorrow",
        "who won the 1998 world cup",
        "can you write me a poem about autumn",
    ],
)
def test_other_unrelated_questions_are_also_refused(question):
    assert extractive_answer(question, [], RUNBOOK) is None


def test_stopwords_alone_never_constitute_a_match():
    assert _content_overlap("what is the of an and to", "The database is restored.") == 0.0


def test_a_real_term_match_scores():
    assert _content_overlap("how do I roll back a deploy?", "To roll back a deploy, revert.") > 0.5


# ------------------------------------------------------------------ shape
def test_memories_are_searched_too():
    memories = [
        {"content": "The user prefers metric units in all answers.", "kind": "preference", "score": 0.9}
    ]
    answer = extractive_answer("what unit preference do I have?", memories, [])

    assert answer is not None
    assert "metric" in answer
    assert "memory/preference" in answer


def test_the_answer_says_plainly_that_no_model_is_running():
    """A retrieval-only answer must not be mistaken for a reasoned one."""
    answer = extractive_answer("how do I roll back a deploy?", [], RUNBOOK)
    assert "retrieval-only" in answer
    assert "No language model is reachable" in answer


def test_nothing_stored_means_no_answer():
    assert extractive_answer("anything at all", [], []) is None


def test_duplicate_sentences_appear_once():
    duplicated = [dict(RUNBOOK[0]), dict(RUNBOOK[0])]
    answer = extractive_answer("how do I roll back a deploy?", [], duplicated)
    assert answer.count("revert to the previous image tag") == 1


def test_the_answer_is_capped():
    """Otherwise a large knowledge base produces a wall of text."""
    many = [
        {"content": f"Deploy rollback procedure number {i} uses the image tag.", "name": f"d{i}.md", "score": 0.5}
        for i in range(30)
    ]
    answer = extractive_answer("deploy rollback image tag procedure", [], many)
    assert answer.count("\n- ") <= 5


def test_an_empty_question_is_not_answered():
    assert extractive_answer("", [], RUNBOOK) is None


# =====================================================================
# Offline retrieval quality
#
# With no embedding model reachable, retrieval falls back to a hashed
# bag-of-ngrams. These guard the two defects that made that path miss
# obviously-relevant text.
# =====================================================================

from app.services.embeddings import cosine, hashed_embedding, keyword_score  # noqa: E402


def test_cosine_never_returns_a_negative_score():
    """A negative cosine from the hashed embedder is a hash-collision
    artefact, not evidence of opposite meaning. It was subtracting from the
    blended score and pushing related text below the retrieval threshold."""
    a = hashed_embedding("what unit preference do I have?")
    b = hashed_embedding("The user prefers metric units in all answers.")
    assert cosine(a, b) >= 0.0

    # Explicitly opposed vectors still clamp rather than going negative.
    assert cosine([1.0, 0.0], [-1.0, 0.0]) == 0.0


def test_morphological_variants_match():
    """Offline scoring compares exact tokens, so "units" vs "unit" and
    "prefers" vs "preference" scored zero -- retrieval only found text worded
    exactly like the question."""
    assert keyword_score("what unit preference do I have?",
                         "The user prefers metric units in all answers.") > 0


@pytest.mark.parametrize(
    ("query", "content"),
    [
        ("deploy rollback", "rolling back the deploys"),
        ("user preference", "the user prefers this"),
        ("running a container", "run the containers"),
    ],
)
def test_common_suffixes_do_not_block_a_match(query, content):
    assert keyword_score(query, content) > 0


def test_stemming_does_not_collapse_unrelated_short_words():
    """The stemmer is crude, so check it has not made everything match."""
    assert keyword_score("cat", "dog") == 0.0
    assert keyword_score("bus", "bu") == 0.0


def test_an_unrelated_query_still_scores_zero_after_stemming():
    assert keyword_score("unladen swallow airspeed",
                         "The user prefers metric units in all answers.") == 0.0
