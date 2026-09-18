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


def test_router_is_past_the_known_advisories():
    """react-router 6.x carries two moderate CVEs (open redirect via backslash
    in <Link>, and constructor injection in deserializeErrors). Pin the major
    so a careless `npm install` cannot walk back into them."""
    import json

    pkg = json.loads((FRONTEND.parent / "package.json").read_text())
    spec = pkg["dependencies"]["react-router-dom"]
    major = int(spec.lstrip("^~>=< ").split(".")[0])
    assert major >= 7, f"react-router-dom {spec} is affected by GHSA-wrjc-x8rr-h8h6"


def test_motion_library_is_declared():
    """The UI imports framer-motion everywhere; an undeclared dependency would
    build locally from a transitive copy and fail in a clean install."""
    import json

    pkg = json.loads((FRONTEND.parent / "package.json").read_text())
    assert "framer-motion" in pkg["dependencies"]


# ------------------------------------------------------------------ contrast
def _luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


# The effective panel colour once the gradient sits over the backdrop.
PANEL = "#101722"


@pytest.mark.parametrize(
    "token",
    ["--text", "--text-dim", "--muted", "--muted-deep", "--accent", "--ok", "--warn", "--err", "--info"],
)
def test_text_tokens_meet_wcag_aa(token):
    """Every colour used for text must clear 4.5:1 on a panel.

    Dark themes make it easy to pick a grey that looks tasteful in a mockup and
    is unreadable on a laptop at an angle. --muted-deep was 3.18:1 and is used
    for real copy (empty states, palette hints), so it was lightened.
    """
    tokens = (STYLE_DIR / "tokens.css").read_text()
    match = re.search(rf"{token}:\s*(#[0-9a-fA-F]{{6}})", tokens)
    assert match, f"{token} is not defined as a hex colour"

    ratio = _contrast(match.group(1), PANEL)
    assert ratio >= 4.5, f"{token} is {ratio:.2f}:1 on panels, below the 4.5:1 AA floor"


def test_buttons_are_styled():
    """A <button> with no class renders as a raw browser button.

    It type-checks, it builds, and it looks broken -- a grey OS-native control
    in the middle of a dark themed page. This found four, including the
    primary action on the MCP form and the Confirm in the voice dialog.
    """
    # These are styled by a parent selector rather than their own class.
    parent_styled = {".convo-item > button", ".attachment-chip button"}
    assert all(sel in all_css() for sel in parent_styled), "parent-scoped button styles went missing"

    offenders: list[str] = []
    for path in list(FRONTEND.glob("pages/*.tsx")) + list(FRONTEND.glob("components/*.tsx")):
        source = path.read_text()
        for match in re.finditer(r"<button\b([^>]*)>", source):
            if "className" in match.group(1):
                continue
            line = source[: match.start()].count("\n") + 1
            # Allow the two parent-styled cases, identified by their container.
            context = source[max(0, match.start() - 400) : match.start()]
            if "convo-item" in context or "attachment-chip" in context:
                continue
            offenders.append(f"{path.name}:{line}")

    assert not offenders, f"unstyled buttons: {offenders}"
