"""Evaluation harness: does the assistant still do what it used to?

A local assistant drifts. You swap the model, tune the reranker, edit the
system prompt -- and the only way to know whether things got better or worse
is to re-run a fixed set of cases and compare.

This module is deliberately unclever. Each case states a task and what a good
answer looks like; the harness runs the real agent loop and grades the result
with cheap, deterministic checks:

* ``contains`` / ``not_contains`` -- substrings that must (not) appear
* ``regex`` -- a pattern the answer must match
* ``tools_used`` / ``tools_not_used`` -- tools the run must (not) have called
* ``max_duration_ms`` -- a latency ceiling

No LLM-as-judge. A grader that is itself a language model introduces exactly
the nondeterminism an evaluation is supposed to remove, and it cannot run
offline on a laptop. The trade-off is that these checks measure behaviour that
is easy to state, not answer quality in general -- which is the right scope for
a regression suite.

Suites live in ``evals/*.yaml`` (or ``.json``) so they can be edited without
touching code, and results are persisted so you can compare runs over time.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings

log = logging.getLogger(__name__)

# Suites are data, not code, so they live outside the package.
EVAL_DIR = Path(__file__).resolve().parent.parent.parent.parent / "evals"


@dataclass
class Check:
    """One assertion about a run, and whether it held."""

    kind: str
    expected: Any
    passed: bool
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "expected": self.expected, "passed": self.passed, "detail": self.detail}


@dataclass
class CaseResult:
    id: str
    task: str
    passed: bool
    answer: str
    checks: list[Check] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    duration_ms: int = 0
    provider: str = ""
    model: str = ""
    degraded: bool = False
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "passed": self.passed,
            "answer": self.answer,
            "checks": [c.as_dict() for c in self.checks],
            "tools_used": self.tools_used,
            "duration_ms": self.duration_ms,
            "provider": self.provider,
            "model": self.model,
            "degraded": self.degraded,
            "error": self.error,
        }


# ------------------------------------------------------------------ loading


def _normalise_case(raw: dict[str, Any], index: int) -> dict[str, Any]:
    case = dict(raw)
    case.setdefault("id", f"case-{index + 1}")
    case.setdefault("expect", {})
    if not case.get("task"):
        raise ValueError(f"Case '{case['id']}' has no task")
    return case


def load_suite(path: Path) -> dict[str, Any]:
    """Read one suite file. YAML if PyYAML is present, JSON always."""
    text = path.read_text()
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - yaml ships with the app
            raise ValueError("PyYAML is required to read .yaml suites") from exc
        data = yaml.safe_load(text) or {}
    else:
        data = json.loads(text or "{}")

    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a mapping")

    cases = data.get("cases") or []
    if not isinstance(cases, list):
        raise ValueError(f"{path.name}: 'cases' must be a list")

    return {
        "name": data.get("name") or path.stem,
        "description": data.get("description", ""),
        "path": str(path),
        "cases": [_normalise_case(c, i) for i, c in enumerate(cases)],
    }


def list_suites(directory: Path | None = None) -> list[dict[str, Any]]:
    """Every readable suite. A malformed file is reported, not fatal."""
    root = directory or EVAL_DIR
    if not root.exists():
        return []

    suites = []
    for path in sorted(root.iterdir()):
        if path.suffix not in (".yaml", ".yml", ".json"):
            continue
        try:
            suite = load_suite(path)
            suite["case_count"] = len(suite["cases"])
            suite["error"] = None
            suite.pop("cases")
        except Exception as exc:  # noqa: BLE001 - surface the problem in the UI
            suite = {
                "name": path.stem,
                "description": "",
                "path": str(path),
                "case_count": 0,
                "error": str(exc),
            }
        suites.append(suite)
    return suites


# ------------------------------------------------------------------ grading


def grade(expect: dict[str, Any], answer: str, tools_used: list[str], duration_ms: int) -> list[Check]:
    """Apply every assertion in ``expect``. Case-insensitive for text."""
    checks: list[Check] = []
    haystack = (answer or "").lower()

    for needle in _as_list(expect.get("contains")):
        checks.append(
            Check("contains", needle, str(needle).lower() in haystack,
                  "" if str(needle).lower() in haystack else "not found in the answer")
        )

    for needle in _as_list(expect.get("not_contains")):
        absent = str(needle).lower() not in haystack
        checks.append(Check("not_contains", needle, absent, "" if absent else "unexpectedly present"))

    for pattern in _as_list(expect.get("regex")):
        try:
            matched = re.search(pattern, answer or "", re.IGNORECASE | re.DOTALL) is not None
            checks.append(Check("regex", pattern, matched, "" if matched else "no match"))
        except re.error as exc:
            checks.append(Check("regex", pattern, False, f"invalid pattern: {exc}"))

    used = set(tools_used)
    for tool in _as_list(expect.get("tools_used")):
        checks.append(Check("tools_used", tool, tool in used,
                            "" if tool in used else f"tools actually used: {sorted(used) or 'none'}"))

    for tool in _as_list(expect.get("tools_not_used")):
        checks.append(Check("tools_not_used", tool, tool not in used,
                            "" if tool not in used else "this tool was called"))

    ceiling = expect.get("max_duration_ms")
    if ceiling is not None:
        ok = duration_ms <= int(ceiling)
        checks.append(Check("max_duration_ms", ceiling, ok, "" if ok else f"took {duration_ms}ms"))

    return checks


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


# ------------------------------------------------------------------ running


async def run_case(db: Session, case: dict[str, Any]) -> CaseResult:
    """Run one case through the real agent loop and grade it."""
    from app.services.agent_runtime import run_agent

    task = case["task"]
    started = time.perf_counter()

    try:
        result = await run_agent(
            db,
            task,
            mode=case.get("mode", "auto"),
            auto_approve=True,  # evaluations must not block on the approval queue
        )
    except Exception as exc:  # noqa: BLE001 - a crashed case is a failed case
        log.warning("Evaluation case %s raised: %s", case["id"], exc)
        return CaseResult(
            id=case["id"],
            task=task,
            passed=False,
            answer="",
            duration_ms=int((time.perf_counter() - started) * 1000),
            error=str(exc),
        )

    answer = result.get("result") or ""
    tools_used = [
        step.get("tool")
        for step in result.get("trace") or []
        if isinstance(step, dict) and step.get("tool")
    ]
    duration_ms = int(result.get("duration_ms") or (time.perf_counter() - started) * 1000)

    checks = grade(case.get("expect") or {}, answer, tools_used, duration_ms)
    return CaseResult(
        id=case["id"],
        task=task,
        passed=all(c.passed for c in checks),
        answer=answer,
        checks=checks,
        tools_used=tools_used,
        duration_ms=duration_ms,
        provider=result.get("provider", ""),
        model=result.get("model", ""),
        degraded=bool(result.get("degraded")),
    )


async def run_suite(db: Session, name: str, directory: Path | None = None) -> dict[str, Any]:
    """Run every case in a suite sequentially and summarise.

    Sequential on purpose: a local model serves one request at a time, and
    concurrent cases would make the latency numbers meaningless.
    """
    root = directory or EVAL_DIR
    path = _resolve(root, name)
    suite = load_suite(path)

    started = time.perf_counter()
    results = [await run_case(db, case) for case in suite["cases"]]
    passed = sum(1 for r in results if r.passed)
    total = len(results)

    summary = {
        "suite": suite["name"],
        "description": suite["description"],
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 3) if total else 0.0,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "degraded": any(r.degraded for r in results),
        "model": next((r.model for r in results if r.model), ""),
        "ran_at": datetime.now(UTC).isoformat(),
        "cases": [r.as_dict() for r in results],
    }

    _persist(db, summary)
    return summary


def _resolve(root: Path, name: str) -> Path:
    """Find a suite by name, refusing anything outside the eval directory."""
    candidate = (root / name).with_suffix("") if "." not in name else root / name
    for suffix in ("", ".yaml", ".yml", ".json"):
        path = Path(str(candidate) + suffix)
        if path.is_file():
            resolved = path.resolve()
            if not str(resolved).startswith(str(root.resolve())):
                raise ValueError("Suite path escapes the evaluation directory")
            return resolved
    raise FileNotFoundError(f"No evaluation suite named '{name}'")


# --------------------------------------------------------------- history


def _persist(db: Session, summary: dict[str, Any]) -> None:
    """Record the run in the audit log so results survive a restart."""
    try:
        from app.services.agent_runtime import audit

        audit(
            db,
            "evaluation.completed",
            f"Evaluation '{summary['suite']}': {summary['passed']}/{summary['total']} passed",
            {
                "suite": summary["suite"],
                "total": summary["total"],
                "passed": summary["passed"],
                "failed": summary["failed"],
                "pass_rate": summary["pass_rate"],
                "duration_ms": summary["duration_ms"],
                "model": summary["model"],
                "degraded": summary["degraded"],
                "failures": [c["id"] for c in summary["cases"] if not c["passed"]],
            },
        )
    except Exception:  # noqa: BLE001 - never fail a run over bookkeeping
        log.debug("Could not record evaluation result", exc_info=True)


def history(db: Session, limit: int = 20) -> list[dict[str, Any]]:
    """Past evaluation runs, newest first."""
    from app.db.models import AuditEvent

    rows = (
        db.query(AuditEvent)
        .filter(AuditEvent.event_type == "evaluation.completed")
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "ran_at": row.created_at,
            **(row.details if isinstance(row.details, dict) else {}),
        }
        for row in rows
    ]


def status() -> dict[str, Any]:
    return {
        "directory": str(EVAL_DIR),
        "exists": EVAL_DIR.exists(),
        "suites": list_suites(),
        "model": settings.ollama_model,
    }
