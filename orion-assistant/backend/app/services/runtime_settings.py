from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Setting

log = logging.getLogger(__name__)

# Only these may be changed at runtime and persisted. Secrets and bind
# addresses are deliberately excluded: they belong in the environment.
MUTABLE_KEYS = {
    "local_only",
    "cloud_escalation_enabled",
    "enable_web_search",
    "allow_shell_tool",
    "allow_browser_tool",
    "allow_network_tool",
    "ollama_model",
    "openrouter_model",
    "max_tool_loops",
}

_STORE_KEY = "runtime_overrides"


def load_overrides(db: Session) -> dict[str, Any]:
    """Apply persisted runtime overrides onto the live settings object."""
    row = db.scalar(select(Setting).where(Setting.key == _STORE_KEY))
    if not row or not isinstance(row.value, dict):
        return {}
    applied: dict[str, Any] = {}
    for key, value in row.value.items():
        if key in MUTABLE_KEYS:
            setattr(settings, key, value)
            applied[key] = value
    if applied:
        log.info("Applied %d persisted setting override(s): %s", len(applied), ", ".join(sorted(applied)))
    return applied


def save_overrides(db: Session, changes: dict[str, Any]) -> dict[str, Any]:
    """Persist and apply runtime overrides. Returns the full override set."""
    rejected = set(changes) - MUTABLE_KEYS
    if rejected:
        raise ValueError(f"Not runtime-mutable: {', '.join(sorted(rejected))}")

    row = db.scalar(select(Setting).where(Setting.key == _STORE_KEY))
    current = dict(row.value) if row and isinstance(row.value, dict) else {}
    current.update(changes)

    if row:
        row.value = current
    else:
        db.add(Setting(key=_STORE_KEY, value=current))
    db.commit()

    for key, value in changes.items():
        setattr(settings, key, value)
    return current
