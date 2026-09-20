from pathlib import Path

from app.services.agent_runtime import SYSTEM_PROMPT


def test_prompt_loaded_from_file():
    path = Path("app/prompts/system.md")
    assert path.is_file(), "system.md must ship with the package"
    assert "ORION" in SYSTEM_PROMPT


def test_prompt_has_no_markdown_title():
    assert not SYSTEM_PROMPT.startswith("#")


def test_prompt_covers_injection_and_secrets():
    lowered = SYSTEM_PROMPT.lower()
    assert "untrusted" in lowered
    assert "secret" in lowered
