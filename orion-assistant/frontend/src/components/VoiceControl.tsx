import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Mic, MicOff, Volume2, VolumeX, X } from "lucide-react";
import { api, type VoiceCommand } from "../lib/api";
import { useVoice } from "../hooks/useVoice";

/**
 * Global voice control: one microphone for the whole dashboard.
 *
 * Lives above the router so a spoken "open tools" can navigate from anywhere,
 * and exposes a context so individual pages (Chat especially) can hook into
 * dictation and playback without owning their own microphone.
 */

interface VoiceContextValue {
  listening: boolean;
  speaking: boolean;
  interim: string;
  toggle: () => void;
  speak: (text: string) => Promise<void>;
  stopSpeaking: () => void;
  ttsAvailable: boolean;
  /** Pages register handlers for commands only they can carry out. */
  registerHandler: (id: string, handler: (command: VoiceCommand) => boolean) => () => void;
  autoSpeak: boolean;
  setAutoSpeak: (on: boolean) => void;
}

const VoiceContext = createContext<VoiceContextValue | null>(null);

export function useVoiceControl() {
  const context = useContext(VoiceContext);
  if (!context) throw new Error("useVoiceControl must be used inside <VoiceProvider>");
  return context;
}

interface Pending {
  command: VoiceCommand;
  label: string;
}

export function VoiceProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [pending, setPending] = useState<Pending | null>(null);
  const [toast, setToast] = useState<{ text: string; kind: "ok" | "err" } | null>(null);
  const [autoSpeak, setAutoSpeak] = useState(false);
  const [subtitle, setSubtitle] = useState("");
  const pageHandlers = useRef(new Map<string, (command: VoiceCommand) => boolean>());

  const notify = useCallback((text: string, kind: "ok" | "err" = "ok") => {
    setToast({ text, kind });
    window.setTimeout(() => setToast(null), 3500);
  }, []);

  const registerHandler = useCallback(
    (id: string, handler: (command: VoiceCommand) => boolean) => {
      pageHandlers.current.set(id, handler);
      return () => {
        pageHandlers.current.delete(id);
      };
    },
    [],
  );

  const execute = useCallback(
    async (command: VoiceCommand) => {
      // Pages get first refusal: Chat handles dictation and send itself.
      for (const handler of pageHandlers.current.values()) {
        if (handler(command)) return;
      }

      switch (command.action) {
        case "navigate":
          if (command.target) {
            navigate(command.target);
            notify(command.say ?? `Opening ${command.target}`);
          }
          break;

        case "toggle":
          try {
            if (command.target === "kill_switch") {
              await api.killSwitch(Boolean(command.value), "voice command");
              notify(command.value ? "Kill switch engaged" : "Kill switch released");
            } else if (command.target) {
              await api.updateSettings({ [command.target]: command.value } as never);
              notify(command.say ?? "Setting updated");
            }
          } catch (err) {
            notify(err instanceof Error ? err.message : String(err), "err");
          }
          break;

        case "ui":
          // Unhandled UI actions are the responsibility of the active page;
          // if nothing claimed it, say so rather than failing silently.
          if (command.target === "stop_listening") voiceRef.current?.stop();
          else if (command.target === "stop_speaking") voiceRef.current?.stopSpeaking();
          else if (command.target === "scroll_down") window.scrollBy({ top: 400, behavior: "smooth" });
          else if (command.target === "scroll_up") window.scrollBy({ top: -400, behavior: "smooth" });
          else if (command.target === "refresh") window.location.reload();
          else notify(`"${command.transcript}" only works on another page`, "err");
          break;

        case "chat":
          // No page claimed it: send the user to chat with the text queued.
          navigate(`/chat?say=${encodeURIComponent(String(command.value ?? ""))}`);
          break;

        default:
          break;
      }
    },
    [navigate, notify],
  );

  const onCommand = useCallback(
    (command: VoiceCommand) => {
      if (command.action === "none") return;
      if (command.confirm) {
        setPending({
          command,
          label:
            command.target === "kill_switch"
              ? `${command.value ? "Engage" : "Release"} the kill switch?`
              : `${command.say ?? "Apply this change"}?`,
        });
        return;
      }
      void execute(command);
    },
    [execute],
  );

  const voice = useVoice({
    onCommand,
    onTranscript: (text, isFinal) => {
      setSubtitle(text);
      if (isFinal) window.setTimeout(() => setSubtitle((s) => (s === text ? "" : s)), 2500);
    },
    onError: (message) => notify(message, "err"),
  });
  const voiceRef = useRef(voice);
  voiceRef.current = voice;

  // Space-free global shortcut: Ctrl/Cmd + Shift + V toggles the microphone.
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === "v") {
        event.preventDefault();
        voiceRef.current.toggle();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const value = useMemo<VoiceContextValue>(
    () => ({
      listening: voice.listening,
      speaking: voice.speaking,
      interim: voice.interim,
      toggle: voice.toggle,
      speak: voice.speak,
      stopSpeaking: voice.stopSpeaking,
      ttsAvailable: Boolean(voice.status?.tts.available),
      registerHandler,
      autoSpeak,
      setAutoSpeak,
    }),
    [voice, registerHandler, autoSpeak],
  );

  const sttUnavailable = voice.status && !voice.status.stt.available;

  return (
    <VoiceContext.Provider value={value}>
      {children}

      {/* ------------------------------------------------ live subtitle */}
      {(voice.listening || subtitle) && (
        <div className={`subtitle-bar ${voice.listening ? "live" : ""}`} role="status" aria-live="polite">
          <span className="subtitle-dot" />
          <span className="subtitle-text">
            {subtitle || voice.interim || "Listening…"}
            {voice.interim && <span className="subtitle-interim-caret" />}
          </span>
          <button className="subtitle-close" onClick={voice.stop} aria-label="Stop listening">
            <X size={13} />
          </button>
        </div>
      )}

      {/* ------------------------------------------------- mic controls */}
      <div className="voice-dock">
        {voice.speaking && (
          <button className="voice-btn" onClick={voice.stopSpeaking} title="Stop speaking">
            <VolumeX size={17} />
          </button>
        )}
        <button
          className={`voice-btn mic ${voice.listening ? "active" : ""}`}
          onClick={voice.toggle}
          title={
            sttUnavailable
              ? "Speech recognition unavailable — see the Voice section in Settings"
              : `${voice.listening ? "Stop" : "Start"} listening  (Ctrl+Shift+V)`
          }
        >
          {voice.listening ? <Mic size={18} /> : <MicOff size={18} />}
        </button>
      </div>

      {/* ------------------------------------------------ confirmation */}
      {pending && (
        <div className="modal-backdrop" onClick={() => setPending(null)}>
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <h3>Confirm voice command</h3>
            <p className="muted">
              Heard: <em>“{pending.command.transcript}”</em>
            </p>
            <p>{pending.label}</p>
            <div className="row-actions">
              <button
                onClick={() => {
                  const command = pending.command;
                  setPending(null);
                  void execute(command);
                }}
              >
                Confirm
              </button>
              <button className="ghost" onClick={() => setPending(null)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div className={`toast ${toast.kind}`}>
          {toast.kind === "ok" ? <Volume2 size={14} /> : null}
          <span>{toast.text}</span>
        </div>
      )}
    </VoiceContext.Provider>
  );
}
