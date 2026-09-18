"""Skill learning: retrieval, reinforcement, distillation, and the REST surface."""

from __future__ import annotations

import pytest

from app.db.models import Skill
from app.services import skills as sk


@pytest.fixture(autouse=True)
def clean_skills(db):
    db.query(Skill).delete()
    db.commit()
    yield
    db.query(Skill).delete()
    db.commit()


def make(db, name, keywords, confidence=0.5, status="active"):
    return sk.upsert_skill(
        db,
        name=name,
        description=f"How to {name}",
        instructions="1. do the thing\n2. verify it",
        trigger_keywords=keywords,
        confidence=confidence,
        status=status,
    )


# ------------------------------------------------------------------- basics
def test_keywords_drop_stopwords_and_short_words():
    words = sk._keywords("How can I deploy the ORION backend to production?")
    assert "deploy" in words
    assert "orion" in words
    assert "the" not in words
    assert "i" not in words


def test_upsert_creates_then_merges(db):
    first = make(db, "deploy backend", ["deploy", "backend"])
    second = sk.upsert_skill(
        db, name="deploy backend", description="updated", instructions="new steps",
        trigger_keywords=["docker"],
    )
    assert first["id"] == second["id"]
    assert second["description"] == "updated"
    assert set(second["trigger_keywords"]) >= {"deploy", "backend", "docker"}
    assert len(sk.list_skills(db)) == 1


def test_auto_keywords_when_none_given(db):
    skill = sk.upsert_skill(
        db, name="summarise invoices", description="condense invoice PDFs", instructions="steps",
    )
    assert skill["trigger_keywords"]


# ---------------------------------------------------------------- retrieval
def test_relevant_skills_match_on_overlap(db):
    make(db, "deploy backend", ["deploy", "backend", "docker"])
    make(db, "bake bread", ["bread", "flour", "oven"])
    matches = sk.relevant_skills(db, "how do I deploy the backend with docker")
    assert [m["name"] for m in matches] == ["deploy backend"]


def test_no_match_returns_empty(db):
    make(db, "bake bread", ["bread", "flour"])
    assert sk.relevant_skills(db, "configure kubernetes ingress") == []


def test_disabled_skills_are_never_retrieved(db):
    make(db, "deploy backend", ["deploy", "backend"], status="disabled")
    assert sk.relevant_skills(db, "deploy the backend") == []


def test_higher_confidence_ranks_first(db):
    make(db, "weak approach", ["deploy"], confidence=0.1)
    make(db, "proven approach", ["deploy"], confidence=0.9)
    matches = sk.relevant_skills(db, "deploy")
    assert matches[0]["name"] == "proven approach"


def test_prompt_block_contains_instructions(db):
    make(db, "deploy backend", ["deploy", "backend"])
    block = sk.skills_prompt_block(db, "deploy the backend")
    assert "Learned skills" in block
    assert "deploy backend" in block
    assert "do the thing" in block


def test_prompt_block_empty_without_matches(db):
    assert sk.skills_prompt_block(db, "totally unrelated request") == ""


# -------------------------------------------------------------- reinforcement
def test_success_raises_confidence(db):
    skill = make(db, "deploy backend", ["deploy"], confidence=0.5)
    sk.record_use(db, [skill["id"]], success=True)
    updated = sk.get_skill(db, skill["id"])
    assert updated["confidence"] > 0.5
    assert updated["successes"] == 1
    assert updated["uses"] == 1


def test_failure_lowers_confidence(db):
    skill = make(db, "deploy backend", ["deploy"], confidence=0.5)
    sk.record_use(db, [skill["id"]], success=False)
    assert sk.get_skill(db, skill["id"])["confidence"] < 0.5


def test_repeated_failure_auto_disables(db):
    skill = make(db, "flaky skill", ["flaky"], confidence=0.4)
    for _ in range(3):
        sk.record_use(db, [skill["id"]], success=False)
    updated = sk.get_skill(db, skill["id"])
    assert updated["status"] == "disabled"
    assert updated["failures"] == 3


def test_candidate_promotes_to_active_on_success(db):
    skill = make(db, "promising", ["promising"], confidence=0.7, status="candidate")
    sk.record_use(db, [skill["id"]], success=True)
    assert sk.get_skill(db, skill["id"])["status"] == "active"


def test_confidence_is_clamped(db):
    skill = make(db, "great skill", ["great"], confidence=0.98)
    for _ in range(5):
        sk.record_use(db, [skill["id"]], success=True)
    assert sk.get_skill(db, skill["id"])["confidence"] == 1.0


def test_record_use_ignores_unknown_ids(db):
    sk.record_use(db, ["does-not-exist"], success=True)  # must not raise


# ---------------------------------------------------------------- distillation
def test_is_learnable_requires_multiple_steps():
    assert sk.is_learnable(["a", "b"], True) is True
    assert sk.is_learnable(["a"], True) is False
    assert sk.is_learnable(["a", "b"], False) is False


@pytest.mark.parametrize(
    "raw,expected_name",
    [
        ('{"name": "plain json", "instructions": "x"}', "plain json"),
        ('```json\n{"name": "fenced", "instructions": "x"}\n```', "fenced"),
        ('Here you go: {"name": "prefixed", "instructions": "x"} cheers', "prefixed"),
    ],
)
def test_json_parsing_tolerates_model_formatting(raw, expected_name):
    assert sk._parse_json_object(raw)["name"] == expected_name


def test_json_parsing_returns_none_on_garbage():
    assert sk._parse_json_object("no json at all") is None
    assert sk._parse_json_object('{"broken": ') is None


@pytest.mark.anyio
async def test_learn_from_run_skips_trivial_runs(db):
    assert await sk.learn_from_run(db, request="hi", tool_names=["calculate"], answer="4") is None


@pytest.mark.anyio
async def test_learn_from_run_creates_skill(db, monkeypatch):
    class FakeResponse:
        degraded = False
        error = None
        text = (
            '{"name": "audit disk usage", "description": "when disk fills up",'
            ' "trigger_keywords": ["disk", "usage"], "instructions": "1. run shell df"}'
        )

    async def fake_chat(**kwargs):
        return FakeResponse()

    monkeypatch.setattr("app.services.model_router.router.chat", fake_chat)
    skill = await sk.learn_from_run(
        db, request="check why the disk is full", tool_names=["run_shell", "read_file"],
        answer="/var was full",
    )
    assert skill["name"] == "audit disk usage"
    assert skill["source"] == "learned"
    assert skill["status"] == "candidate"
    assert "disk" in skill["trigger_keywords"]


@pytest.mark.anyio
async def test_learn_from_run_honours_model_skip(db, monkeypatch):
    class FakeResponse:
        degraded = False
        error = None
        text = '{"skip": true}'

    async def fake_chat(**kwargs):
        return FakeResponse()

    monkeypatch.setattr("app.services.model_router.router.chat", fake_chat)
    assert await sk.learn_from_run(
        db, request="x", tool_names=["a", "b"], answer="y"
    ) is None


@pytest.mark.anyio
async def test_learn_from_run_skips_when_model_degraded(db, monkeypatch):
    class FakeResponse:
        degraded = True
        error = "offline"
        text = ""

    async def fake_chat(**kwargs):
        return FakeResponse()

    monkeypatch.setattr("app.services.model_router.router.chat", fake_chat)
    assert await sk.learn_from_run(
        db, request="x", tool_names=["a", "b"], answer="y"
    ) is None


@pytest.mark.anyio
async def test_learn_from_run_survives_model_exception(db, monkeypatch):
    async def boom(**kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("app.services.model_router.router.chat", boom)
    assert await sk.learn_from_run(
        db, request="x", tool_names=["a", "b"], answer="y"
    ) is None


# -------------------------------------------------------------------- feedback
def test_feedback_stats(db, client):
    client.post("/v1/feedback", json={"rating": "up"})
    client.post("/v1/feedback", json={"rating": "up"})
    client.post("/v1/feedback", json={"rating": "down"})
    stats = client.get("/v1/feedback/stats").json()
    assert stats["up"] >= 2
    assert stats["down"] >= 1
    assert 0 < stats["satisfaction"] < 1


def test_feedback_rejects_bad_rating(client):
    assert client.post("/v1/feedback", json={"rating": "sideways"}).status_code == 422


# ------------------------------------------------------------------- endpoints
def test_skill_crud_via_api(client):
    created = client.post(
        "/v1/skills",
        json={
            "name": "triage failing ci",
            "description": "when CI goes red",
            "instructions": "1. read the log\n2. rerun",
            "trigger_keywords": ["ci", "failing", "pipeline"],
        },
    )
    assert created.status_code == 200
    skill_id = created.json()["id"]

    assert any(s["id"] == skill_id for s in client.get("/v1/skills").json()["skills"])
    assert client.get(f"/v1/skills/{skill_id}").json()["name"] == "triage failing ci"

    disabled = client.patch(f"/v1/skills/{skill_id}", json={"status": "disabled"})
    assert disabled.json()["status"] == "disabled"

    relevant = client.get("/v1/skills/relevant", params={"q": "my ci pipeline is failing"}).json()
    assert relevant["skills"] == []  # disabled skills stay out

    assert client.delete(f"/v1/skills/{skill_id}").status_code == 200
    assert client.get(f"/v1/skills/{skill_id}").status_code == 404


def test_relevant_endpoint_returns_matches(client):
    client.post(
        "/v1/skills",
        json={
            "name": "rotate api keys",
            "description": "credential rotation",
            "instructions": "steps",
            "trigger_keywords": ["rotate", "credentials", "keys"],
        },
    )
    matches = client.get("/v1/skills/relevant", params={"q": "rotate the api keys"}).json()["skills"]
    assert matches and matches[0]["name"] == "rotate api keys"
    assert matches[0]["relevance"] > 0


def test_unknown_skill_404s(client):
    assert client.get("/v1/skills/nope").status_code == 404
    assert client.patch("/v1/skills/nope", json={"status": "active"}).status_code == 404
    assert client.delete("/v1/skills/nope").status_code == 404


# ------------------------------------------- feedback actually moves confidence
def test_thumbs_down_lowers_the_confidence_of_the_skills_that_were_used(client, db):
    """The end-to-end path the README promises.

    /v1/feedback looks up the run, reads which skills shaped the answer out of
    the persisted trace, and reinforces them. That only works if the agent
    writes skill_ids into the trace -- it did not, so the whole branch was
    unreachable and thumbs up/down changed nothing.
    """
    from app.db.models import AgentRun

    skill = Skill(
        name="deploy-backend", description="deploy the backend",
        instructions="1. run CI", trigger_keywords=["deploy"],
        confidence=0.5, status="active",
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)

    run = AgentRun(
        task="deploy the backend", state="succeeded", provider="local", model="m",
        result="done", duration_ms=10,
        trace=[{"step": 0, "skill_ids": [skill.id], "tool_calls": []}],
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    before = skill.confidence
    response = client.post("/v1/feedback", json={"rating": "down", "run_id": run.id})
    assert response.status_code == 200

    db.refresh(skill)
    assert skill.confidence < before, "a thumbs-down must reduce the skill's confidence"
    assert skill.failures == 1


def test_thumbs_up_raises_confidence(client, db):
    from app.db.models import AgentRun

    skill = Skill(
        name="s2", description="d", instructions="i", trigger_keywords=[],
        confidence=0.5, status="active",
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)

    run = AgentRun(
        task="t", state="succeeded", provider="local", model="m", result="ok", duration_ms=5,
        trace=[{"step": 0, "skill_ids": [skill.id]}],
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    client.post("/v1/feedback", json={"rating": "up", "run_id": run.id})
    db.refresh(skill)
    assert skill.confidence > 0.5
    assert skill.successes == 1


def test_the_agent_records_which_skills_it_used_in_the_trace():
    """Guard the contract the feedback route depends on."""
    source = (
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "app" / "services" / "agent_runtime.py"
    ).read_text()
    assert source.count('"skill_ids": skill_ids') == 2, (
        "both the buffered and streaming loops must record skill_ids, "
        "or thumbs up/down silently stops working on that path"
    )
