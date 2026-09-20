"""The evaluation harness: loading suites, grading, and running cases."""

from __future__ import annotations

import asyncio
import json

import pytest

from app.services import evaluation
from app.services.evaluation import grade, list_suites, load_suite


# ------------------------------------------------------------------ loading
def test_loads_a_yaml_suite(tmp_path):
    path = tmp_path / "demo.yaml"
    path.write_text(
        "name: demo\n"
        "description: a suite\n"
        "cases:\n"
        "  - id: one\n"
        "    task: say hi\n"
        "    expect:\n"
        "      contains: hi\n"
    )

    suite = load_suite(path)

    assert suite["name"] == "demo"
    assert suite["cases"][0]["id"] == "one"
    assert suite["cases"][0]["expect"]["contains"] == "hi"


def test_loads_a_json_suite(tmp_path):
    path = tmp_path / "demo.json"
    path.write_text(json.dumps({"cases": [{"task": "hello"}]}))

    suite = load_suite(path)

    assert suite["name"] == "demo", "the filename should be the fallback name"
    assert suite["cases"][0]["id"] == "case-1", "cases should be auto-numbered"


def test_a_case_without_a_task_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"cases": [{"expect": {"contains": "x"}}]}))

    with pytest.raises(ValueError, match="no task"):
        load_suite(path)


def test_a_suite_that_is_not_a_mapping_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(["not", "a", "mapping"]))

    with pytest.raises(ValueError, match="mapping"):
        load_suite(path)


def test_cases_must_be_a_list(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"cases": {"nope": True}}))

    with pytest.raises(ValueError, match="must be a list"):
        load_suite(path)


def test_an_empty_suite_is_allowed(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("{}")
    assert load_suite(path)["cases"] == []


def test_listing_reports_a_broken_suite_instead_of_raising(tmp_path):
    (tmp_path / "good.json").write_text(json.dumps({"cases": [{"task": "x"}]}))
    (tmp_path / "broken.json").write_text("{not json")

    suites = {s["name"]: s for s in list_suites(tmp_path)}

    assert suites["good"]["error"] is None
    assert suites["good"]["case_count"] == 1
    assert suites["broken"]["error"], "a malformed suite should report why"


def test_listing_ignores_unrelated_files(tmp_path):
    (tmp_path / "notes.txt").write_text("hello")
    (tmp_path / "real.json").write_text(json.dumps({"cases": []}))

    assert [s["name"] for s in list_suites(tmp_path)] == ["real"]


def test_listing_a_missing_directory_is_empty(tmp_path):
    assert list_suites(tmp_path / "nope") == []


# ------------------------------------------------------------------ grading
def test_contains_is_case_insensitive():
    checks = grade({"contains": "Hello"}, "well, hello there", [], 0)
    assert checks[0].passed


def test_contains_failure_explains_itself():
    checks = grade({"contains": "893"}, "I don't know", [], 0)
    assert not checks[0].passed
    assert checks[0].detail


def test_not_contains():
    assert grade({"not_contains": "error"}, "all good", [], 0)[0].passed
    assert not grade({"not_contains": "error"}, "an error happened", [], 0)[0].passed


def test_a_list_of_expectations_becomes_one_check_each():
    checks = grade({"contains": ["a", "b", "c"]}, "a and b", [], 0)
    assert [c.passed for c in checks] == [True, True, False]


def test_regex_matching():
    assert grade({"regex": r"\d{3}"}, "the answer is 893", [], 0)[0].passed
    assert not grade({"regex": r"\d{4}"}, "the answer is 893", [], 0)[0].passed


def test_regex_spans_newlines():
    assert grade({"regex": r"start.*end"}, "start\nmiddle\nend", [], 0)[0].passed


def test_an_invalid_regex_fails_the_check_rather_than_crashing():
    check = grade({"regex": "([unclosed"}, "anything", [], 0)[0]
    assert not check.passed
    assert "invalid pattern" in check.detail


def test_tools_used():
    assert grade({"tools_used": "calculate"}, "", ["calculate"], 0)[0].passed
    check = grade({"tools_used": "calculate"}, "", ["web_search"], 0)[0]
    assert not check.passed
    assert "web_search" in check.detail, "the failure should say what was actually called"


def test_tools_used_failure_names_the_empty_case():
    assert "none" in grade({"tools_used": "calculate"}, "", [], 0)[0].detail


def test_tools_not_used():
    assert grade({"tools_not_used": "shell"}, "", ["calculate"], 0)[0].passed
    assert not grade({"tools_not_used": "shell"}, "", ["shell"], 0)[0].passed


def test_duration_ceiling():
    assert grade({"max_duration_ms": 1000}, "", [], 900)[0].passed
    check = grade({"max_duration_ms": 1000}, "", [], 1500)[0]
    assert not check.passed
    assert "1500" in check.detail


def test_duration_exactly_at_the_ceiling_passes():
    assert grade({"max_duration_ms": 1000}, "", [], 1000)[0].passed


def test_no_expectations_means_no_checks():
    assert grade({}, "anything at all", [], 0) == []


def test_an_empty_answer_fails_a_contains_check():
    assert not grade({"contains": "x"}, "", [], 0)[0].passed


def test_a_non_string_expectation_is_compared_as_text():
    """YAML turns bare `yes` and `123` into a bool and an int; both must work."""
    assert grade({"contains": 893}, "the answer is 893", [], 0)[0].passed
    assert grade({"contains": True}, "the value is true", [], 0)[0].passed


# ------------------------------------------------------------------ running
def test_a_case_passes_when_every_check_holds(db, monkeypatch):
    async def fake_run(*_args, **_kwargs):
        return {
            "result": "47 * 19 = 893",
            "trace": [{"tool": "calculate"}],
            "duration_ms": 12,
            "provider": "local",
            "model": "test-model",
            "degraded": False,
        }

    monkeypatch.setattr("app.services.agent_runtime.run_agent", fake_run)

    result = asyncio.run(
        evaluation.run_case(db, {"id": "c1", "task": "what is 47 * 19?",
                                 "expect": {"contains": "893", "tools_used": "calculate"}})
    )

    assert result.passed
    assert result.tools_used == ["calculate"]
    assert result.model == "test-model"


def test_a_case_fails_when_one_check_fails(db, monkeypatch):
    async def fake_run(*_args, **_kwargs):
        return {"result": "I don't know", "trace": [], "duration_ms": 5}

    monkeypatch.setattr("app.services.agent_runtime.run_agent", fake_run)

    result = asyncio.run(
        evaluation.run_case(db, {"id": "c1", "task": "x",
                                 "expect": {"contains": ["893", "also missing"]}})
    )

    assert not result.passed
    assert sum(1 for c in result.checks if not c.passed) == 2


def test_a_crashing_case_is_recorded_as_a_failure(db, monkeypatch):
    """One broken case must not abort the rest of the suite."""

    async def boom(*_args, **_kwargs):
        raise RuntimeError("the model exploded")

    monkeypatch.setattr("app.services.agent_runtime.run_agent", boom)

    result = asyncio.run(evaluation.run_case(db, {"id": "c1", "task": "x", "expect": {}}))

    assert not result.passed
    assert "exploded" in result.error


def test_evaluations_bypass_the_approval_queue(db, monkeypatch):
    """A suite that blocked on approvals could never finish unattended."""
    seen = {}

    async def fake_run(_db, _task, **kwargs):
        seen.update(kwargs)
        return {"result": "ok", "trace": [], "duration_ms": 1}

    monkeypatch.setattr("app.services.agent_runtime.run_agent", fake_run)
    asyncio.run(evaluation.run_case(db, {"id": "c1", "task": "x", "expect": {}}))

    assert seen["auto_approve"] is True


def test_running_a_suite_summarises_and_records_it(db, tmp_path, monkeypatch):
    (tmp_path / "s.yaml").write_text(
        "name: s\n"
        "cases:\n"
        "  - id: good\n"
        "    task: t\n"
        "    expect:\n"
        '      contains: "yes"\n'
        "  - id: bad\n"
        "    task: t\n"
        "    expect:\n"
        "      contains: absolutely not present\n"
    )

    async def fake_run(*_args, **_kwargs):
        return {"result": "yes", "trace": [], "duration_ms": 3, "model": "m"}

    monkeypatch.setattr("app.services.agent_runtime.run_agent", fake_run)

    summary = asyncio.run(evaluation.run_suite(db, "s", directory=tmp_path))

    assert summary["total"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["pass_rate"] == 0.5

    runs = evaluation.history(db)
    assert runs, "the run should be recorded in history"
    assert runs[0]["suite"] == "s"
    assert runs[0]["failures"] == ["bad"]


def test_an_empty_suite_reports_a_zero_pass_rate(db, tmp_path):
    (tmp_path / "empty.json").write_text(json.dumps({"cases": []}))
    summary = asyncio.run(evaluation.run_suite(db, "empty", directory=tmp_path))
    assert summary["total"] == 0
    assert summary["pass_rate"] == 0.0


def test_an_unknown_suite_raises_not_found(db, tmp_path):
    with pytest.raises(FileNotFoundError):
        asyncio.run(evaluation.run_suite(db, "nope", directory=tmp_path))


def test_a_suite_name_cannot_escape_the_directory(db, tmp_path):
    """A path-traversal name must not read arbitrary files."""
    outside = tmp_path.parent / "secret.json"
    outside.write_text(json.dumps({"cases": []}))

    with pytest.raises((FileNotFoundError, ValueError)):
        asyncio.run(evaluation.run_suite(db, "../secret", directory=tmp_path))


def test_a_name_with_an_extension_still_resolves(db, tmp_path, monkeypatch):
    (tmp_path / "s.json").write_text(json.dumps({"cases": [{"task": "t"}]}))

    async def fake_run(*_args, **_kwargs):
        return {"result": "", "trace": [], "duration_ms": 1}

    monkeypatch.setattr("app.services.agent_runtime.run_agent", fake_run)

    assert asyncio.run(evaluation.run_suite(db, "s.json", directory=tmp_path))["total"] == 1


# ----------------------------------------------------------- shipped suites
def test_the_shipped_suites_are_valid():
    """The suites in evals/ must parse and have real assertions."""
    suites = list_suites()
    assert suites, "expected evaluation suites to ship with the app"

    for summary in suites:
        assert summary["error"] is None, f"{summary['name']}: {summary['error']}"
        suite = load_suite(evaluation.Path(summary["path"]))
        assert suite["cases"], f"{summary['name']} has no cases"
        for case in suite["cases"]:
            assert case["expect"], f"{summary['name']}/{case['id']} asserts nothing"


def test_status_reports_the_suite_directory():
    status = evaluation.status()
    assert status["exists"] is True
    assert {"core", "safety"} <= {s["name"] for s in status["suites"]}
