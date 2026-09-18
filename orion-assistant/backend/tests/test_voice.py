"""Voice: command parsing, TTS/STT plumbing, and honest unavailability."""

from __future__ import annotations

import io
import wave

import pytest

from app.core.config import settings
from app.services import voice
from app.services import voice_commands as vc


# ------------------------------------------------------------ normalisation
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Please open tools.", "open tools"),
        ("Hey, go to settings!", "go to settings"),
        ("  Could you   show   memory?  ", "show memory"),
        ("OK now open the dashboard", "open the dashboard"),
    ],
)
def test_normalize_strips_filler_and_punctuation(raw, expected):
    assert vc.normalize(raw) == expected


@pytest.mark.parametrize(
    "raw,expected,present",
    [
        ("orion open tools", "open tools", True),
        ("hey orion open tools", "open tools", True),
        ("okay orion, open tools", "open tools", True),
        ("open tools", "open tools", False),
    ],
)
def test_wake_word_stripping(raw, expected, present):
    text, had = vc.strip_wake_word(raw, "orion")
    assert (text, had) == (expected, present)


def test_wake_word_not_stripped_mid_sentence():
    text, had = vc.strip_wake_word("tell orion to open tools", "orion")
    assert had is False
    assert text == "tell orion to open tools"


# ------------------------------------------------------------- navigation
@pytest.mark.parametrize(
    "phrase,route",
    [
        ("open tools", "/tools"),
        ("go to settings", "/settings"),
        ("show memory", "/memory"),
        ("navigate to knowledge", "/knowledge"),
        ("take me to the dashboard", "/"),
        ("switch to observability", "/observability"),
        ("open the models page", "/models"),
        ("show skills", "/skills"),
        ("open security", "/security"),
        ("go to automations", "/automations"),
        ("open conversations", "/chat"),
    ],
)
def test_navigation_commands(phrase, route):
    command = vc.parse(phrase)
    assert command.action == "navigate"
    assert command.target == route
    assert command.confidence >= 0.9


def test_navigation_says_something_back():
    assert vc.parse("open tools").say


def test_bare_noun_has_lower_confidence_than_explicit_verb():
    """"tools" alone is ambiguous; "open tools" is not."""
    assert vc.parse("tools").confidence < vc.parse("open tools").confidence


def test_unknown_destination_falls_through_to_chat():
    command = vc.parse("open the pod bay doors")
    assert command.action == "chat"


# ---------------------------------------------------------------- toggles
@pytest.mark.parametrize(
    "phrase,field,value",
    [
        ("activate web search", "enable_web_search", True),
        ("enable web search", "enable_web_search", True),
        ("turn off web search", "enable_web_search", False),
        ("disable the shell tool", "allow_shell_tool", False),
        ("enable the browser tool", "allow_browser_tool", True),
        ("turn on local only mode", "local_only", True),
        ("disable cloud escalation", "cloud_escalation_enabled", False),
    ],
)
def test_toggle_commands(phrase, field, value):
    command = vc.parse(phrase)
    assert command.action == "toggle"
    assert command.target == field
    assert command.value is value


def test_enabling_a_capability_requires_confirmation():
    """Granting privileges on a single misheard phrase would be unsafe."""
    assert vc.parse("enable the shell tool").confirm is True


def test_disabling_a_capability_does_not_require_confirmation():
    """Turning something off is always safe; do not add friction."""
    assert vc.parse("disable the shell tool").confirm is False


def test_toggle_without_a_direction_is_not_a_toggle():
    assert vc.parse("web search").action != "toggle"


# ------------------------------------------------------------- kill switch
@pytest.mark.parametrize(
    "phrase", ["engage the kill switch", "emergency stop", "stop everything", "lockdown"]
)
def test_kill_switch_recognised(phrase):
    command = vc.parse(phrase)
    assert command.target == "kill_switch"
    assert command.value is True
    assert command.confirm is True, "kill switch must always confirm"


def test_kill_switch_release():
    command = vc.parse("disable the kill switch")
    assert command.target == "kill_switch"
    assert command.value is False
    assert command.confirm is True


def test_kill_switch_beats_generic_toggle_matching():
    """'disable the kill switch' contains a toggle verb; safety must win."""
    assert vc.parse("disable the kill switch").target == "kill_switch"


# ------------------------------------------------------------- ui actions
@pytest.mark.parametrize(
    "phrase,target",
    [
        ("new conversation", "new_conversation"),
        ("start a new chat", "new_conversation"),
        ("send", "send"),
        ("stop listening", "stop_listening"),
        ("read that back", "read_last"),
        ("repeat that", "read_last"),
        ("stop speaking", "stop_speaking"),
        ("scroll down", "scroll_down"),
        ("refresh", "refresh"),
    ],
)
def test_ui_actions(phrase, target):
    command = vc.parse(phrase)
    assert command.action == "ui"
    assert command.target == target


# ------------------------------------------------------------- dictation
def test_type_sets_the_input_without_sending():
    command = vc.parse("type remind me about the deploy")
    assert command.action == "ui"
    assert command.target == "set_input"
    assert command.value == "remind me about the deploy"


def test_ask_sends_to_the_model():
    command = vc.parse("ask what is 47 times 19")
    assert command.action == "chat"
    assert command.value == "what is 47 times 19"


def test_unrecognised_speech_becomes_a_chat_message():
    command = vc.parse("what were the regional revenues last quarter")
    assert command.action == "chat"
    assert command.value


def test_empty_transcript_is_a_no_op():
    assert vc.parse("").action == "none"
    assert vc.parse("   ").action == "none"


# ------------------------------------------------------------- wake word
def test_require_wake_word_rejects_bare_speech():
    command = vc.parse("open tools", wake_word="orion", require_wake_word=True)
    assert command.action == "none"


def test_require_wake_word_accepts_prefixed_speech():
    command = vc.parse("orion open tools", wake_word="orion", require_wake_word=True)
    assert command.action == "navigate"
    assert command.target == "/tools"


def test_wake_word_optional_by_default():
    assert vc.parse("open tools", wake_word="orion").action == "navigate"


# ------------------------------------------------------------- determinism
def test_parsing_is_deterministic():
    results = {vc.parse("open tools").target for _ in range(10)}
    assert results == {"/tools"}


def test_every_route_has_at_least_one_alias():
    for route, aliases in vc.ROUTES.items():
        assert aliases, f"{route} has no spoken alias"


def test_catalog_is_populated():
    catalog = vc.command_catalog()
    assert catalog
    assert all(entry["examples"] for entry in catalog)


# -------------------------------------------------------------- tts plumbing
def test_wav_encoding_roundtrip():
    import numpy as np

    samples = np.sin(np.linspace(0, 6.28, 4410)).astype("float32")
    data = voice._wav_bytes(samples)

    with wave.open(io.BytesIO(data)) as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == voice.SAMPLE_RATE
        assert handle.getnframes() == 4410


def test_wav_encoding_clips_out_of_range_samples():
    import numpy as np

    data = voice._wav_bytes(np.array([5.0, -5.0], dtype="float32"))
    with wave.open(io.BytesIO(data)) as handle:
        frames = handle.readframes(2)
    assert int.from_bytes(frames[0:2], "little", signed=True) == 32767
    assert int.from_bytes(frames[2:4], "little", signed=True) == -32767


async def test_synthesize_rejects_empty_text():
    with pytest.raises(ValueError):
        await voice.synthesize("   ")


async def test_synthesize_rejects_unknown_voice():
    with pytest.raises(ValueError, match="Unknown voice"):
        await voice.synthesize("hello", voice="Z9")


async def test_synthesize_uses_the_engine(monkeypatch):
    """With a stub engine, the full synthesis path must produce valid WAV."""
    import numpy as np

    class FakeStyle:
        pass

    class FakeEngine:
        def __init__(self):
            self.calls = []

        def get_voice_style(self, voice_name):
            self.calls.append(voice_name)
            return FakeStyle()

        def synthesize(self, **kwargs):
            self.kwargs = kwargs
            return np.zeros((1, 2205), dtype="float32"), np.array([0.05])

    engine = FakeEngine()
    monkeypatch.setattr(voice, "load_tts", lambda: engine)
    data = await voice.synthesize("hello world", voice="M1", speed=1.2)

    assert data.startswith(b"RIFF")
    assert engine.calls == ["M1"]
    assert engine.kwargs["speed"] == 1.2
    assert engine.kwargs["text"] == "hello world"


async def test_synthesize_truncates_very_long_text(monkeypatch):
    import numpy as np

    captured = {}

    class FakeEngine:
        def get_voice_style(self, voice_name):
            return object()

        def synthesize(self, **kwargs):
            captured.update(kwargs)
            return np.zeros((1, 10), dtype="float32"), np.array([0.01])

    monkeypatch.setattr(voice, "load_tts", lambda: FakeEngine())
    await voice.synthesize("x" * 99999)
    assert len(captured["text"]) == settings.tts_max_chars


async def test_synthesize_raises_when_engine_missing(monkeypatch):
    monkeypatch.setattr(voice, "load_tts", lambda: None)
    with pytest.raises(RuntimeError):
        await voice.synthesize("hello")


# -------------------------------------------------------------- stt plumbing
async def test_transcribe_rejects_empty_audio():
    with pytest.raises(ValueError):
        await voice.transcribe(b"")


async def test_transcribe_uses_the_engine(monkeypatch):
    class FakeSegment:
        def __init__(self, start, end, text):
            self.start, self.end, self.text = start, end, text

    class FakeInfo:
        language = "en"
        duration = 1.5

    class FakeEngine:
        def transcribe(self, path, **kwargs):
            assert kwargs["vad_filter"] is True
            return [FakeSegment(0.0, 1.0, " open tools ")], FakeInfo()

    monkeypatch.setattr(voice, "load_stt", lambda: FakeEngine())
    result = await voice.transcribe(b"fake audio bytes", suffix=".wav")
    assert result.text == "open tools"
    assert result.language == "en"
    assert result.duration_s == 1.5
    assert result.segments[0]["text"] == "open tools"


async def test_transcribe_raises_when_engine_missing(monkeypatch):
    monkeypatch.setattr(voice, "load_stt", lambda: None)
    with pytest.raises(RuntimeError):
        await voice.transcribe(b"audio")


# -------------------------------------------------------------- status
def test_voice_status_reports_both_directions():
    status = voice.voice_status()
    assert set(status) >= {"tts", "stt", "voice_commands_enabled", "wake_word"}
    assert status["tts"]["engine"] == "supertonic"
    assert status["stt"]["engine"] == "faster-whisper"


def test_status_explains_why_a_backend_is_unavailable():
    """If a backend is down, the reason must be actionable, not blank."""
    status = voice.voice_status()
    for direction in ("tts", "stt"):
        if not status[direction]["available"]:
            assert status[direction]["error"], f"{direction} unavailable with no explanation"


# ------------------------------------------------------------------ routes
def test_voice_status_endpoint(client):
    body = client.get("/v1/voice/status").json()
    assert "tts" in body and "stt" in body


def test_voice_commands_endpoint(client):
    body = client.get("/v1/voice/commands").json()
    assert body["catalog"]
    assert "/tools" in body["routes"]
    assert "enable_web_search" in body["toggles"]


def test_interpret_endpoint(client):
    body = client.post("/v1/voice/interpret", json={"transcript": "open settings"}).json()
    assert body["action"] == "navigate"
    assert body["target"] == "/settings"


def test_interpret_endpoint_flags_confirmation(client):
    body = client.post("/v1/voice/interpret", json={"transcript": "enable the shell tool"}).json()
    assert body["confirm"] is True


def test_interpret_rejects_empty(client):
    assert client.post("/v1/voice/interpret", json={"transcript": ""}).status_code == 422


def test_speak_endpoint_503s_when_tts_unavailable(client, monkeypatch):
    monkeypatch.setattr(voice, "load_tts", lambda: None)
    response = client.post("/v1/voice/speak", json={"text": "hello"})
    assert response.status_code == 503
    assert response.json()["detail"]


def test_speak_endpoint_returns_wav(client, monkeypatch):
    import numpy as np

    class FakeEngine:
        def get_voice_style(self, voice_name):
            return object()

        def synthesize(self, **kwargs):
            return np.zeros((1, 1000), dtype="float32"), np.array([0.02])

    monkeypatch.setattr(voice, "load_tts", lambda: FakeEngine())
    response = client.post("/v1/voice/speak", json={"text": "hello"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content.startswith(b"RIFF")


def test_speak_endpoint_validates_voice(client, monkeypatch):
    monkeypatch.setattr(voice, "load_tts", lambda: object())
    assert client.post("/v1/voice/speak", json={"text": "hi", "voice": "ZZ"}).status_code == 400


def test_transcribe_endpoint_503s_when_stt_unavailable(client, monkeypatch):
    monkeypatch.setattr(voice, "load_stt", lambda: None)
    response = client.post(
        "/v1/voice/transcribe", files={"file": ("clip.wav", b"audio", "audio/wav")}
    )
    assert response.status_code == 503


def test_transcribe_endpoint_can_interpret_commands(client, monkeypatch):
    class FakeSegment:
        start, end, text = 0.0, 1.0, "open tools"

    class FakeInfo:
        language, duration = "en", 1.0

    class FakeEngine:
        def transcribe(self, path, **kwargs):
            return [FakeSegment()], FakeInfo()

    monkeypatch.setattr(voice, "load_stt", lambda: FakeEngine())
    response = client.post(
        "/v1/voice/transcribe",
        files={"file": ("clip.wav", b"audio", "audio/wav")},
        data={"interpret": "true"},
    )
    body = response.json()
    assert body["text"] == "open tools"
    assert body["command"]["action"] == "navigate"
    assert body["command"]["target"] == "/tools"


# ------------------------------------------- every UI page is reachable by voice
def test_every_sidebar_route_can_be_reached_by_voice():
    """A page you cannot navigate to by voice is invisible to voice control."""
    import re
    from pathlib import Path

    sidebar = Path(__file__).resolve().parent.parent.parent / "frontend/src/components/Sidebar.tsx"
    routes = set(re.findall(r'\["(/[a-z]*)",', sidebar.read_text()))

    missing = routes - set(vc.ROUTES)
    assert not missing, f"these pages have no voice route: {sorted(missing)}"


@pytest.mark.parametrize(
    ("phrase", "target"),
    [
        ("open evaluation", "/evaluation"),
        ("show me the evals", "/evaluation"),
        ("go to mcp servers", "/mcp"),
        ("open external tools", "/mcp"),
    ],
)
def test_the_newer_pages_are_navigable(phrase, target):
    command = vc.parse(phrase)
    assert command.action == "navigate"
    assert command.target == target


@pytest.mark.parametrize(
    "phrase",
    [
        "show me the evals",
        "take me to my settings",
        "bring up the dashboard",
        "show me memory",
        "go to the tools page",
    ],
)
def test_natural_filler_between_verb_and_target(phrase):
    """People say "show me the X", not just "show X"."""
    assert vc.parse(phrase).action == "navigate"


@pytest.mark.parametrize("phrase", ["show me the door", "open a bank account", "take me home tonight"])
def test_filler_does_not_cause_false_navigation(phrase):
    assert vc.parse(phrase).action == "chat"
