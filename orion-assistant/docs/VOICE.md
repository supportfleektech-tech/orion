# Voice

ORION can listen and talk, and you can drive the dashboard by speaking. Like
everything else here, it works offline and degrades with an explanation rather
than failing.

```bash
pip install -r backend/requirements-optional.txt
```

That pulls `faster-whisper` (speech to text) and `supertonic` (text to speech).
Both download their model weights on first use.

---

## Using it

Click the microphone at the bottom right, or press **Ctrl/Cmd + Shift + V**.
A subtitle bar shows what ORION is hearing as you speak. Say a command, or just
talk — anything that is not recognised as a command is sent to the chat rather
than discarded.

## Speech to text: two backends

| Backend | When it is used | Trade-off |
|---|---|---|
| Browser (Web Speech API) | Chrome and Edge, automatically | Word-by-word live text, but Chrome sends audio to Google |
| Server (faster-whisper) | Everywhere else, or when no browser recogniser exists | Fully local; transcribes in ~4 second segments, so text appears per phrase |

If you want the local path unconditionally, use Firefox, or disable speech
recognition in your browser. The Settings page shows which one is active.

## Text to speech

[Supertonic](https://github.com/supertone-inc/supertonic) runs on-device via
ONNX Runtime — about 99M parameters, no GPU needed, 44.1kHz output. Voices are
`M1`–`M5` and `F1`–`F5`, configurable with `TTS_VOICE`.

Turn on **Speak replies automatically** in Settings for hands-free use, or
press the speaker icon on any individual reply.

> Supertonic's upstream repository was archived in July 2026. The code and
> weights still work and are MIT / OpenRAIL-M licensed, but there is no
> upstream support. Piper is a drop-in alternative if that matters to you.

---

## Voice commands

Say **"orion"** first if you like — the wake word is optional by default
(`REQUIRE_WAKE_WORD=true` makes it mandatory).

| Category | Examples |
|---|---|
| Navigation | "open tools", "go to settings", "show me the knowledge base" |
| Capabilities | "enable web search", "turn off the shell tool" |
| Chat | "new conversation", "send that" |
| Playback | "read that back", "stop talking" |
| Safety | "engage the kill switch", "emergency stop" |

The full list is on the Settings page, generated from
`GET /v1/voice/commands` so it can never drift from what the parser accepts.

### Safety rules

* **Granting** a capability always asks for confirmation. **Revoking** one
  never does — turning something off should be frictionless.
* The **kill switch asks in both directions**, because releasing it is as
  consequential as engaging it.
* An explicit verb ("open tools") scores higher than a bare noun ("tools"), so
  saying the word "tools" mid-sentence will not navigate you away.
* Anything unrecognised becomes a chat message. Speech is never silently
  dropped.

---

## When it is not available

Both engines fetch weights from Hugging Face on first use. On a machine with no
network access, that fails — and ORION says so explicitly, per direction, with
the command to fix it. The microphone button still works via the browser
recogniser where one exists.

Check the current state at `GET /v1/voice/status`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/voice/status` | Per-direction availability and errors |
| `GET` | `/v1/voice/commands` | The command catalogue |
| `POST` | `/v1/voice/interpret` | Parse a transcript into a command |
| `POST` | `/v1/voice/speak` | Text in, `audio/wav` out |
| `POST` | `/v1/voice/transcribe` | Audio file in, text (and optionally a command) out |

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `TTS_VOICE` | `F1` | Speaker, `M1`–`M5` / `F1`–`F5` |
| `TTS_SPEED` | `1.05` | 0.7–2.0 |
| `TTS_QUALITY_STEPS` | `8` | 5–12; higher is better and slower |
| `TTS_AUTOPLAY` | `false` | Speak every reply |
| `WAKE_WORD` | `orion` | |
| `REQUIRE_WAKE_WORD` | `false` | Ignore speech that lacks the wake word |
| `VOICE_COMMANDS_ENABLED` | `true` | Turn off spoken control entirely |
