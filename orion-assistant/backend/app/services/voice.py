"""Local speech: text-to-speech and speech-to-text.

Both directions run on-device. Nothing is sent to a cloud API.

* **TTS — Supertonic** (Supertone, MIT code / OpenRAIL-M weights). A ~99M
  parameter ONNX model: CPU-only, no GPU, fast enough for real-time on modest
  hardware. Weights are fetched from Hugging Face on first use.
* **STT — faster-whisper**. CTranslate2 Whisper, int8 on CPU.

Both are optional. If a backend is missing or its weights cannot be downloaded,
the relevant capability reports itself unavailable with the exact command needed
to fix it — ORION never pretends it spoke or heard something it did not.
"""

from __future__ import annotations

import asyncio
import io
import logging
import wave
from dataclasses import dataclass
from typing import Any

from app.core.config import settings

log = logging.getLogger(__name__)

SAMPLE_RATE = 44100  # Supertonic output rate

_tts_engine: Any = None
_tts_error: str | None = None
_stt_engine: Any = None
_stt_error: str | None = None

# Supertonic preset voices. M = masculine, F = feminine.
VOICE_PRESETS = ["F1", "F2", "F3", "F4", "F5", "M1", "M2", "M3", "M4", "M5"]


@dataclass
class Transcript:
    text: str
    language: str | None = None
    duration_s: float = 0.0
    segments: list[dict[str, Any]] | None = None


# --------------------------------------------------------------------- TTS
def load_tts() -> Any:
    """Load Supertonic once. Returns None (and records why) on failure."""
    global _tts_engine, _tts_error
    if _tts_engine is not None or _tts_error is not None:
        return _tts_engine
    try:
        from supertonic import TTS
    except ImportError:
        _tts_error = (
            "Supertonic is not installed. Run: pip install -r backend/requirements-optional.txt"
        )
        return None
    try:
        # First call downloads ~99M of ONNX weights from Hugging Face.
        _tts_engine = TTS(auto_download=True)
        log.info("Supertonic TTS loaded")
    except Exception as exc:
        _tts_error = (
            f"Supertonic could not load its model: {exc}. "
            "This usually means Hugging Face is unreachable from this machine."
        )
        log.warning("Supertonic unavailable: %s", exc)
    return _tts_engine


def tts_available() -> bool:
    return load_tts() is not None


def _wav_bytes(samples: Any) -> bytes:
    """Encode float32 [-1, 1] samples as a 16-bit PCM WAV."""
    import numpy as np

    audio = np.asarray(samples).squeeze()
    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767).astype("<i2")

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm.tobytes())
    return buffer.getvalue()


def _synthesize_sync(text: str, voice: str, speed: float) -> bytes:
    engine = load_tts()
    if engine is None:
        raise RuntimeError(_tts_error or "TTS unavailable")
    style = engine.get_voice_style(voice_name=voice)
    wav, _duration = engine.synthesize(
        text=text,
        lang=settings.tts_language,
        voice_style=style,
        total_steps=settings.tts_quality_steps,
        speed=speed,
    )
    return _wav_bytes(wav)


async def synthesize(text: str, voice: str | None = None, speed: float | None = None) -> bytes:
    """Render text to WAV bytes. Raises RuntimeError when TTS is unavailable."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Nothing to speak")
    if len(text) > settings.tts_max_chars:
        text = text[: settings.tts_max_chars]

    voice = voice or settings.tts_voice
    if voice not in VOICE_PRESETS:
        raise ValueError(f"Unknown voice '{voice}'. Options: {', '.join(VOICE_PRESETS)}")

    # ONNX inference is blocking and CPU-bound; keep the event loop free.
    return await asyncio.to_thread(_synthesize_sync, text, voice, speed or settings.tts_speed)


# --------------------------------------------------------------------- STT
def load_stt() -> Any:
    """Load faster-whisper once. Returns None (and records why) on failure."""
    global _stt_engine, _stt_error
    if _stt_engine is not None or _stt_error is not None:
        return _stt_engine
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        _stt_error = (
            "faster-whisper is not installed. Run: "
            "pip install -r backend/requirements-optional.txt"
        )
        return None
    try:
        _stt_engine = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
        log.info("Whisper STT loaded: %s", settings.whisper_model)
    except Exception as exc:
        _stt_error = f"Whisper could not load '{settings.whisper_model}': {exc}"
        log.warning("Whisper unavailable: %s", exc)
    return _stt_engine


def stt_available() -> bool:
    return load_stt() is not None


def _transcribe_sync(data: bytes, suffix: str, language: str | None) -> Transcript:
    import tempfile

    engine = load_stt()
    if engine is None:
        raise RuntimeError(_stt_error or "STT unavailable")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as handle:
        handle.write(data)
        handle.flush()
        segments, info = engine.transcribe(
            handle.name,
            beam_size=1,
            language=language,
            vad_filter=True,  # skip silence; big speedup on live mic chunks
        )
        collected = [
            {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
            for s in segments
        ]
    return Transcript(
        text=" ".join(s["text"] for s in collected).strip(),
        language=info.language,
        duration_s=round(info.duration, 2),
        segments=collected,
    )


async def transcribe(data: bytes, suffix: str = ".wav", language: str | None = None) -> Transcript:
    """Transcribe audio bytes. Raises RuntimeError when STT is unavailable."""
    if not data:
        raise ValueError("No audio provided")
    return await asyncio.to_thread(_transcribe_sync, data, suffix, language)


# ------------------------------------------------------------------ status
def voice_status() -> dict[str, Any]:
    """Honest report of what voice features actually work right now."""
    tts_ready = tts_available()
    stt_ready = stt_available()
    return {
        "tts": {
            "available": tts_ready,
            "engine": "supertonic",
            "voice": settings.tts_voice,
            "voices": VOICE_PRESETS,
            "language": settings.tts_language,
            "speed": settings.tts_speed,
            "error": None if tts_ready else _tts_error,
        },
        "stt": {
            "available": stt_ready,
            "engine": "faster-whisper",
            "model": settings.whisper_model,
            "error": None if stt_ready else _stt_error,
        },
        "voice_commands_enabled": settings.voice_commands_enabled,
        "wake_word": settings.wake_word,
    }


def reset_engines() -> None:
    """Drop cached engines so settings changes take effect. Used by tests."""
    global _tts_engine, _tts_error, _stt_engine, _stt_error
    _tts_engine = _tts_error = _stt_engine = _stt_error = None
