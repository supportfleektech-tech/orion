import { useEffect, useState } from "react";
import { AudioLines } from "lucide-react";
import { api, type VoiceCatalog, type VoiceStatus } from "../lib/api";
import { Badge, Panel, Toggle } from "./ui";
import { useVoiceControl } from "./VoiceControl";
import { browserSpeechAvailable } from "../hooks/useVoice";

/** Voice status and the spoken-command reference, shown in Settings. */
export function VoicePanel() {
  const [status, setStatus] = useState<VoiceStatus | null>(null);
  const [catalog, setCatalog] = useState<VoiceCatalog | null>(null);
  const { autoSpeak, setAutoSpeak, speak, ttsAvailable } = useVoiceControl();

  useEffect(() => {
    api.voiceStatus().then(setStatus).catch(() => setStatus(null));
    api.voiceCatalog().then(setCatalog).catch(() => setCatalog(null));
  }, []);

  return (
    <Panel
      subtitle="VOICE"
      title="Speech and voice control"
      right={<AudioLines size={16} />}
    >
      <div className="kv">
        <div>
          <span>Speech to text</span>
          <strong>
            <Badge tone={status?.stt.available ? "ok" : "warn"}>
              {status?.stt.available ? `${status.stt.engine} · ${status.stt.model}` : "unavailable"}
            </Badge>
          </strong>
        </div>
        <div>
          <span>Text to speech</span>
          <strong>
            <Badge tone={status?.tts.available ? "ok" : "warn"}>
              {status?.tts.available ? `${status.tts.engine} · ${status.tts.voice}` : "unavailable"}
            </Badge>
          </strong>
        </div>
        <div>
          <span>Live dictation</span>
          <strong>
            <Badge tone={browserSpeechAvailable() ? "ok" : "info"}>
              {browserSpeechAvailable() ? "browser (word-by-word)" : "server (per phrase)"}
            </Badge>
          </strong>
        </div>
        <div>
          <span>Wake word</span>
          <strong>{status?.wake_word ?? "—"} (optional)</strong>
        </div>
      </div>

      {status && !status.stt.available && (
        <div className="notice">
          <div>
            <strong>Speech recognition is not available on the server.</strong>
            <br />
            {status.stt.error}
            <br />
            {browserSpeechAvailable()
              ? "Your browser has its own recogniser, so the microphone still works here — note that Chrome's recogniser is a cloud service, unlike the rest of ORION."
              : "Install the optional extras to enable local transcription."}
          </div>
        </div>
      )}

      {status && !status.tts.available && (
        <div className="notice">
          <div>
            <strong>Spoken replies are unavailable.</strong>
            <br />
            {status.tts.error}
          </div>
        </div>
      )}

      <div className="toggle-label" style={{ marginTop: 10 }}>
        <Toggle
          checked={autoSpeak}
          onChange={setAutoSpeak}
          label="Speak replies automatically"
        />
        {ttsAvailable && (
          <button className="ghost" onClick={() => void speak("Voice output is working correctly.")}>
            Test voice
          </button>
        )}
      </div>

      {catalog && (
        <div className="voice-help" style={{ marginTop: 14 }}>
          <p className="muted small">
            Press the microphone (or <code>Ctrl+Shift+V</code>) and say any of these. Commands that
            grant a capability ask for confirmation first.
          </p>
          {catalog.catalog.map((group) => (
            <div key={group.category} className="voice-help-group">
              <strong>{group.category}</strong>
              <ul>
                {group.examples.map((example) => (
                  <li key={example}>“{example}”</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}
