"""Static checks on the frontend that a type-checker cannot catch.

TypeScript validates the code but says nothing about CSS. These tests guard
the two failure modes that produce a visibly broken page while every other
check stays green: a class that is styled nowhere, and a stylesheet that is
never imported.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parent.parent.parent / "frontend" / "src"
STYLE_DIR = FRONTEND / "styles"

# Modifiers only ever used in compound selectors (`.badge.ok`, `.msg.user`),
# plus classes owned by third-party or inline-styled elements.
MODIFIERS = {
    "active", "alarm", "assistant", "code", "compact", "danger", "dashboard",
    "dimmed", "err", "error", "flag", "full", "icon", "info", "inline", "live",
    "mic", "ok", "over", "primary", "running", "send", "span-2", "thinking",
    "track", "user", "warn",
}


def all_css() -> str:
    return "\n".join(p.read_text() for p in STYLE_DIR.glob("*.css"))


def defined_classes() -> set[str]:
    return set(re.findall(r"\.([a-z][a-z0-9-]*)", all_css()))


def used_classes() -> set[str]:
    used: set[str] = set()
    for path in list(FRONTEND.glob("pages/*.tsx")) + list(FRONTEND.glob("components/*.tsx")):
        for literal in re.findall(r'className="([^"{]+)"', path.read_text()):
            used.update(literal.split())
        # `className={`a b ${expr}`}` -- keep the static words, drop the
        # interpolations, whose contents are JS identifiers and not classes.
        for literal in re.findall(r"className=\{`([^`]*)`\}", path.read_text()):
            static = re.sub(r"\$\{[^}]*\}", " ", literal)
            used.update(static.split())
    return {c for c in used if re.fullmatch(r"[a-z][a-z0-9-]*", c)}


def test_every_class_used_in_a_component_is_styled():
    """A class with no rule renders as an unstyled element -- invisible in CI."""
    missing = used_classes() - defined_classes() - MODIFIERS
    assert not missing, f"these classes are used but never styled: {sorted(missing)}"


def test_the_entry_stylesheet_imports_every_layer():
    """A stylesheet nobody imports is dead weight that looks alive."""
    entry = (FRONTEND / "styles.css").read_text()
    for layer in STYLE_DIR.glob("*.css"):
        assert layer.name in entry, f"{layer.name} is never imported by styles.css"


def test_design_tokens_resolve():
    """Every var(--x) must have a definition, or it silently renders as nothing."""
    css = all_css()
    defined = set(re.findall(r"^\s*(--[a-z0-9-]+):", css, re.MULTILINE))
    referenced = set(re.findall(r"var\((--[a-z0-9-]+)", css))
    # Variables set inline by JS (the spotlight position) have fallbacks.
    runtime = {"--mx", "--my"}
    missing = referenced - defined - runtime
    assert not missing, f"undefined CSS variables: {sorted(missing)}"


@pytest.mark.parametrize("token", ["--accent", "--ease", "--d-base", "--r-md", "--ok", "--err"])
def test_core_tokens_exist(token):
    assert f"{token}:" in (STYLE_DIR / "tokens.css").read_text()


def test_reduced_motion_is_honoured():
    """Animation must be disableable: it is an accessibility requirement,
    not a preference."""
    tokens = (STYLE_DIR / "tokens.css").read_text()
    assert "prefers-reduced-motion" in tokens
    assert "animation-duration: 1ms !important" in tokens
