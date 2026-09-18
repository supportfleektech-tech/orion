"""Skill learning -- how ORION gets better at your work over time.

The loop is deliberately simple and inspectable rather than magical:

1.  Every agent run is *observed*. Runs that succeeded with a non-trivial tool
    sequence become skill **candidates**.
2.  A candidate is distilled by the local model into a named, reusable
    procedure (name, description, trigger keywords, step-by-step instructions).
3.  Relevant skills are **retrieved** by keyword overlap and injected into the
    system prompt for later requests, so the assistant reuses what worked.
4.  Outcomes and explicit user feedback move a skill's confidence up or down.
    Skills that keep failing are auto-disabled.

Everything a skill "knows" is plain text in the database: you can read it,
edit it, or delete it. There is no opaque fine-tuned state.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Feedback, Skill

log = logging.getLogger(__name__)

MIN_STEPS_TO_LEARN = 2          # a single tool call is not a "skill"
MAX_SKILLS_IN_PROMPT = 3
PROMOTE_AT = 0.75
DISABLE_BELOW = 0.2
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "your", "you", "are", "was", "how",
    "what", "when", "where", "which", "into", "about", "please", "can", "could", "would",
    "should", "does", "did", "have", "has", "will", "then", "them", "they", "its", "it's",
}


def _keywords(text: str, limit: int = 12) -> list[str]:
    words = re.findall(r"[a-z0-9][a-z0-9_\-]{2,}", (text or "").lower())
    seen: dict[str, int] = {}
    for word in words:
        if word in STOPWORDS:
            continue
        seen[word] = seen.get(word, 0) + 1
    return [w for w, _ in sorted(seen.items(), key=lambda kv: -kv[1])][:limit]


def _serialize(skill: Skill, score: float | None = None) -> dict[str, Any]:
    total = skill.successes + skill.failures
    data = {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "instructions": skill.instructions,
        "trigger_keywords": list(skill.trigger_keywords or []),
        "source": skill.source,
        "status": skill.status,
        "confidence": round(skill.confidence, 3),
        "uses": skill.uses,
        "successes": skill.successes,
        "failures": skill.failures,
        "success_rate": round(skill.successes / total, 3) if total else None,
        "last_used_at": skill.last_used_at.isoformat() if skill.last_used_at else None,
        "created_at": skill.created_at.isoformat() if skill.created_at else None,
    }
    if score is not None:
        data["relevance"] = round(score, 3)
    return data


# --------------------------------------------------------------------- CRUD
def list_skills(db: Session, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    stmt = select(Skill)
    if status:
        stmt = stmt.where(Skill.status == status)
    stmt = stmt.order_by(Skill.confidence.desc(), Skill.created_at.desc()).limit(limit)
    return [_serialize(s) for s in db.scalars(stmt).all()]


def get_skill(db: Session, skill_id: str) -> dict[str, Any] | None:
    skill = db.get(Skill, skill_id)
    return _serialize(skill) if skill else None


def upsert_skill(
    db: Session,
    *,
    name: str,
    description: str,
    instructions: str,
    trigger_keywords: list[str] | None = None,
    source: str = "user",
    status: str = "active",
    confidence: float = 0.5,
) -> dict[str, Any]:
    """Create a skill, or merge into the existing one with the same name."""
    name = name.strip()[:120]
    keywords = trigger_keywords if trigger_keywords is not None else _keywords(f"{name} {description}")
    existing = db.scalar(select(Skill).where(Skill.name == name))
    if existing:
        existing.description = description
        existing.instructions = instructions
        existing.trigger_keywords = sorted(set(list(existing.trigger_keywords or []) + list(keywords)))
        existing.status = status
        existing.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(existing)
        return _serialize(existing)

    skill = Skill(
        name=name,
        description=description,
        instructions=instructions,
        trigger_keywords=list(keywords),
        source=source,
        status=status,
        confidence=confidence,
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)
    log.info("Learned new skill: %s (source=%s)", name, source)
    return _serialize(skill)


def set_status(db: Session, skill_id: str, status: str) -> dict[str, Any] | None:
    skill = db.get(Skill, skill_id)
    if not skill:
        return None
    skill.status = status
    db.commit()
    db.refresh(skill)
    return _serialize(skill)


def delete_skill(db: Session, skill_id: str) -> bool:
    skill = db.get(Skill, skill_id)
    if not skill:
        return False
    db.delete(skill)
    db.commit()
    return True


# ---------------------------------------------------------------- retrieval
def relevant_skills(db: Session, query: str, limit: int = MAX_SKILLS_IN_PROMPT) -> list[dict[str, Any]]:
    """Keyword-overlap match, weighted by how well the skill has performed."""
    query_words = set(_keywords(query, limit=24))
    if not query_words:
        return []
    scored: list[tuple[float, Skill]] = []
    for skill in db.scalars(select(Skill).where(Skill.status == "active")).all():
        triggers = set(skill.trigger_keywords or [])
        if not triggers:
            continue
        overlap = len(query_words & triggers)
        if not overlap:
            continue
        score = (overlap / len(triggers)) * (0.5 + skill.confidence)
        scored.append((score, skill))
    scored.sort(key=lambda pair: -pair[0])
    return [_serialize(skill, score) for score, skill in scored[:limit]]


def skills_prompt_block(db: Session, query: str) -> str:
    """Render relevant skills for injection into the system prompt."""
    matches = relevant_skills(db, query)
    if not matches:
        return ""
    lines = [
        "## Learned skills",
        "You previously worked out how to handle requests like this. Reuse these "
        "procedures when they apply, and say so when you do:",
        "",
    ]
    for skill in matches:
        lines.append(f"### {skill['name']} (confidence {skill['confidence']:.0%})")
        lines.append(skill["description"])
        lines.append(skill["instructions"].strip())
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------- reinforce
def record_use(db: Session, skill_ids: list[str], success: bool) -> None:
    """Update confidence after a run that used these skills."""
    for skill_id in skill_ids:
        skill = db.get(Skill, skill_id)
        if not skill:
            continue
        skill.uses += 1
        skill.last_used_at = datetime.now(UTC)
        if success:
            skill.successes += 1
            skill.confidence = min(1.0, skill.confidence + 0.08)
        else:
            skill.failures += 1
            skill.confidence = max(0.0, skill.confidence - 0.15)
        if skill.confidence < DISABLE_BELOW and skill.failures >= 3:
            skill.status = "disabled"
            log.info("Auto-disabled underperforming skill: %s", skill.name)
        elif skill.confidence >= PROMOTE_AT and skill.status == "candidate":
            skill.status = "active"
    db.commit()


def record_feedback(
    db: Session, *, rating: str, run_id: str | None = None, message_id: str | None = None,
    comment: str | None = None,
) -> dict[str, Any]:
    entry = Feedback(run_id=run_id, message_id=message_id, rating=rating, comment=comment)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {
        "id": entry.id,
        "run_id": entry.run_id,
        "message_id": entry.message_id,
        "rating": entry.rating,
        "comment": entry.comment,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


def feedback_stats(db: Session) -> dict[str, Any]:
    rows = db.scalars(select(Feedback)).all()
    up = sum(1 for r in rows if r.rating == "up")
    down = sum(1 for r in rows if r.rating == "down")
    return {
        "total": len(rows),
        "up": up,
        "down": down,
        "satisfaction": round(up / (up + down), 3) if (up + down) else None,
    }


# ------------------------------------------------------------------- learn
DISTILL_PROMPT = """You are reviewing a successful task run to extract a reusable skill.

USER REQUEST:
{request}

TOOLS USED (in order):
{tools}

FINAL ANSWER:
{answer}

Write a reusable procedure so this class of task can be handled faster next time.
Respond with ONLY a JSON object, no prose, no code fences:
{{"name": "short imperative name, max 8 words",
  "description": "one sentence on when to use this",
  "trigger_keywords": ["5-10", "lowercase", "words"],
  "instructions": "numbered steps referencing the tools by name"}}

If this run is too trivial or too one-off to generalise, respond exactly: {{"skip": true}}"""


def _parse_json_object(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def is_learnable(tool_names: list[str], success: bool) -> bool:
    return bool(success and len(tool_names) >= MIN_STEPS_TO_LEARN)


async def learn_from_run(
    db: Session, *, request: str, tool_names: list[str], answer: str, success: bool = True,
) -> dict[str, Any] | None:
    """Distil a completed run into a skill. Returns the skill, or None if skipped.

    Failures here are always swallowed: learning is a background nicety and must
    never break the user's actual request.
    """
    if not is_learnable(tool_names, success):
        return None

    from app.services.model_router import router

    prompt = DISTILL_PROMPT.format(
        request=request[:1500],
        tools=", ".join(tool_names) or "(none)",
        answer=(answer or "")[:1500],
    )
    try:
        result = await router.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
    except Exception as exc:
        log.info("Skill distillation unavailable (%s); run not learned.", exc)
        return None

    if result.degraded or result.error:
        log.info("Skill distillation skipped: model unavailable (%s).", result.error or "degraded")
        return None
    parsed = _parse_json_object(result.text or "")
    if not parsed or parsed.get("skip") or not parsed.get("name") or not parsed.get("instructions"):
        return None

    keywords = parsed.get("trigger_keywords")
    if not isinstance(keywords, list) or not keywords:
        keywords = _keywords(f"{request} {parsed['name']}")
    keywords = [str(k).lower().strip() for k in keywords if str(k).strip()][:12]

    return upsert_skill(
        db,
        name=str(parsed["name"]),
        description=str(parsed.get("description") or "Learned from a successful run."),
        instructions=str(parsed["instructions"]),
        trigger_keywords=keywords,
        source="learned",
        status="candidate",
        confidence=0.5,
    )
