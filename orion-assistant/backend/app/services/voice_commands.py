"""Voice control of the ORION dashboard.

Turns a spoken utterance into a structured intent the UI can execute: navigate
somewhere, toggle a setting, run a tool, or fall through to the chat model.

Deliberately rule-based rather than model-driven. Dashboard control needs to be
instant, deterministic and offline-capable; asking an LLM to classify "open
settings" would add a second of latency, burn context, and occasionally get it
wrong. Anything that is *not* a recognised command falls through to the agent,
so nothing is lost.

Safety: commands that change behaviour (enabling tools, flipping the kill
switch) are matched but returned with `confirm=True`, so the UI asks before
acting. Nothing destructive happens on a single misheard phrase.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Route targets in the control plane UI.
ROUTES: dict[str, list[str]] = {
    "/": ["dashboard", "home", "command center", "command centre", "overview", "main"],
    "/chat": ["chat", "conversations", "conversation", "messages"],
    "/memory": ["memory", "memories"],
    "/skills": ["skills", "skill"],
    "/knowledge": ["knowledge", "documents", "docs", "library"],
    "/tools": ["tools", "tool"],
    "/automations": ["automations", "automation", "schedules", "tasks"],
    "/security": ["security", "approvals", "permissions"],
    "/observability": ["observability", "runs", "traces", "logs", "metrics"],
    "/mcp": ["mcp", "mcp servers", "m c p", "external tools", "tool servers"],
    "/evaluation": ["evaluation", "evaluations", "evals", "eval", "benchmarks", "regression"],
    "/models": ["models", "model"],
    "/settings": ["settings", "preferences", "configuration", "config"],
}

# Settings that can be toggled by voice, mapped to their API field.
TOGGLES: dict[str, list[str]] = {
    "enable_web_search": ["web search", "internet search", "online search"],
    "allow_shell_tool": ["shell", "shell tool", "terminal", "command line"],
    "allow_browser_tool": ["browser", "browser tool", "browser automation"],
    "allow_network_tool": ["network", "network tool", "http requests"],
    "local_only": ["local only", "offline mode", "local only mode"],
    "cloud_escalation_enabled": ["cloud", "cloud escalation", "cloud burst"],
}

ON_WORDS = {"on", "enable", "enabled", "activate", "turn on", "switch on", "start", "allow"}
OFF_WORDS = {"off", "disable", "disabled", "deactivate", "turn off", "switch off", "stop", "block"}

# Trailing [,\s] so "hey, go to settings" strips as cleanly as "hey go to settings".
FILLER = re.compile(
    r"^(please|hey|ok|okay|now|could you|can you|would you|i want to|i'd like to|let's)[,\s]+",
    re.IGNORECASE,
)


@dataclass
class VoiceCommand:
    """A recognised dashboard action."""

    action: str                       # navigate | toggle | tool | chat | ui | none
    target: str | None = None
    value: Any = None
    confidence: float = 0.0
    confirm: bool = False             # UI must ask before executing
    transcript: str = ""
    say: str | None = None            # spoken acknowledgement
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target,
            "value": self.value,
            "confidence": round(self.confidence, 3),
            "confirm": self.confirm,
            "transcript": self.transcript,
            "say": self.say,
            "params": self.params,
        }


def normalize(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[.!?,;:]+$", "", text)
    text = re.sub(r"\s+([,;:])", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    while True:
        stripped = FILLER.sub("", text)
        if stripped == text:
            return stripped.strip()
        text = stripped


def strip_wake_word(text: str, wake_word: str) -> tuple[str, bool]:
    """Remove a leading wake word. Returns (text, was_present)."""
    wake = (wake_word or "").strip().lower()
    if not wake:
        return text, False
    pattern = rf"^(hey\s+|ok\s+|okay\s+)?{re.escape(wake)}[\s,]*"
    stripped = re.sub(pattern, "", text, flags=re.IGNORECASE)
    return stripped.strip(), stripped != text


# ------------------------------------------------------------------ matchers
def match_navigation(text: str) -> VoiceCommand | None:
    verb = r"(?:open|go to|show|navigate to|take me to|switch to|display|view|bring up)"
    # "show me the evals", "take me to my settings" -- the filler between the
    # verb and the target varies, so allow the common pronouns and articles.
    filler = r"(?:me\s+|us\s+)?(?:the\s+|my\s+|a\s+)?"
    match = re.match(rf"^{verb}\s+{filler}(.+)$", text)
    phrase = match.group(1).strip() if match else text

    # Trailing words like "page"/"tab"/"screen" are noise.
    phrase = re.sub(r"\s+(page|tab|screen|section|view)$", "", phrase).strip()

    for route, aliases in ROUTES.items():
        for alias in aliases:
            if phrase == alias:
                # An exact bare noun ("tools") only counts with an explicit verb,
                # otherwise "tools are broken" would navigate away mid-sentence.
                return VoiceCommand(
                    action="navigate",
                    target=route,
                    confidence=0.95 if match else 0.6,
                    transcript=text,
                    say=f"Opening {alias}",
                )
    return None


def match_toggle(text: str) -> VoiceCommand | None:
    desired: bool | None = None
    for word in sorted(ON_WORDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(word)}\b", text):
            desired = True
            break
    if desired is None:
        for word in sorted(OFF_WORDS, key=len, reverse=True):
            if re.search(rf"\b{re.escape(word)}\b", text):
                desired = False
                break
    if desired is None:
        return None

    for field_name, aliases in TOGGLES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            if re.search(rf"\b{re.escape(alias)}\b", text):
                return VoiceCommand(
                    action="toggle",
                    target=field_name,
                    value=desired,
                    confidence=0.9,
                    # Enabling a capability is a privilege change: confirm it.
                    confirm=desired is True,
                    transcript=text,
                    say=f"{'Enabling' if desired else 'Disabling'} {alias}",
                )
    return None


def match_kill_switch(text: str) -> VoiceCommand | None:
    if re.search(r"\b(kill switch|emergency stop|stop everything|halt everything|lockdown)\b", text):
        enabling = not any(re.search(rf"\b{w}\b", text) for w in ("off", "disable", "release", "lift"))
        return VoiceCommand(
            action="toggle",
            target="kill_switch",
            value=enabling,
            confidence=0.95,
            confirm=True,  # always confirm, in both directions
            transcript=text,
            say="Engaging the kill switch" if enabling else "Releasing the kill switch",
        )
    return None


def match_ui_action(text: str) -> VoiceCommand | None:
    actions = {
        "new_conversation": r"\b(new (chat|conversation)|start (a )?(new )?(chat|conversation)|clear (the )?chat)\b",
        "send": r"^(send|submit|go ahead|send it)$",
        "stop_listening": r"\b(stop listening|stop the mic|mute the mic|stop voice)\b",
        "read_last": r"\b(read (that|it|the last (one|reply|answer)) (back|aloud|out loud)?|say that again|repeat that)\b",
        "stop_speaking": r"\b(stop (talking|speaking)|be quiet|silence)\b",
        "scroll_down": r"\b(scroll down|page down)\b",
        "scroll_up": r"\b(scroll up|page up)\b",
        "refresh": r"\b(refresh|reload)( the (page|view))?$",
    }
    for name, pattern in actions.items():
        if re.search(pattern, text):
            return VoiceCommand(action="ui", target=name, confidence=0.9, transcript=text)
    return None


def match_dictation(text: str) -> VoiceCommand | None:
    """Explicit dictation into the chat box without sending."""
    match = re.match(r"^(?:type|write|dictate|enter)\s+(.+)$", text)
    if match:
        return VoiceCommand(
            action="ui",
            target="set_input",
            value=match.group(1).strip(),
            confidence=0.85,
            transcript=text,
        )
    match = re.match(r"^(?:ask|tell|say to)\s+(?:orion\s+)?(.+)$", text)
    if match:
        return VoiceCommand(
            action="chat",
            value=match.group(1).strip(),
            confidence=0.9,
            transcript=text,
            say=None,
        )
    return None


MATCHERS = (
    match_kill_switch,   # safety first: must win over generic toggles
    match_ui_action,
    match_toggle,
    match_dictation,
    match_navigation,
)


def parse(transcript: str, wake_word: str = "", require_wake_word: bool = False) -> VoiceCommand:
    """Classify an utterance into a dashboard action.

    Falls back to `action="chat"` so unrecognised speech is still useful: it
    becomes a message to the assistant rather than being discarded.
    """
    raw = (transcript or "").strip()
    if not raw:
        return VoiceCommand(action="none", transcript="", confidence=0.0)

    text = normalize(raw)
    text, had_wake_word = strip_wake_word(text, wake_word)

    if require_wake_word and not had_wake_word:
        return VoiceCommand(
            action="none",
            transcript=raw,
            confidence=0.0,
            say=None,
        )

    if not text:
        return VoiceCommand(action="none", transcript=raw, confidence=0.0)

    for matcher in MATCHERS:
        command = matcher(text)
        if command is not None:
            command.transcript = raw
            return command

    return VoiceCommand(action="chat", value=text, confidence=0.3, transcript=raw)


def command_catalog() -> list[dict[str, Any]]:
    """Human-readable list of what can be said. Powers the UI help panel."""
    return [
        {"category": "Navigation", "examples": [
            "open tools", "go to settings", "show memory", "take me to the dashboard",
            "open evaluation", "show mcp servers",
        ]},
        {"category": "Capabilities", "examples": [
            "activate web search", "disable the shell tool", "turn on local only mode",
        ]},
        {"category": "Chat", "examples": [
            "ask what is 47 times 19", "type remind me about the deploy", "new conversation", "send",
        ]},
        {"category": "Playback", "examples": [
            "read that back", "stop speaking", "stop listening",
        ]},
        {"category": "Safety", "examples": [
            "engage the kill switch", "emergency stop",
        ]},
    ]
