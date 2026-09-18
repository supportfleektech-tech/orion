import { useCallback, useEffect, useRef, useState } from "react";
import { api, type TranscriptResult, type VoiceCommand, type VoiceStatus } from "../lib/api";

/**
 * Speech recognition with two backends, chosen automatically:
 *
 *  1. The browser's Web Speech API when available (Chrome/Edge). This gives
 *     genuinely live interim results, which is what makes the subtitle feel
 *     real-time rather than chunked.
 *  2. MediaRecorder + the local Whisper endpoint everywhere else (Firefox,
 *     Safari). Audio is captured in short segments and transcribed on the
 *     server, so it still works — just with per-segment latency instead of
 *     word-by-word.
 *
 * Nothing is sent to a cloud service in either case: option 2 hits ORION's own
 * /v1/voice/transcribe. Option 1 uses the browser's built-in recogniser, which
 * on Chrome may use Google's service — the UI says so explicitly.
 */

type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: any) => void) | null;
  onerror: ((event: any) => void) | null;
  onend: (() => void) | null;
};

function getRecognitionCtor(): (new () => SpeechRecognitionLike) | null {
  const w = window as any;
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export const browserSpeechAvailable = () => getRecognitionCtor() !== null;

const SEGMENT_MS = 4000; // server-side fallback: transcribe every 4s of speech

export interface UseVoiceOptions {
  /** Fires for every completed utterance, after command interpretation. */
  onCommand?: (command: VoiceCommand) => void;
  /** Fires on each transcript update, final or interim — drives the subtitle. */
  onTranscript?: (text: string, isFinal: boolean) => void;
  onError?: (message: string) => void;
}

export function useVoice(options: UseVoiceOptions = {}) {
  const [status, setStatus] = useState<VoiceStatus | null>(null);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [interim, setInterim] = useState("");
  const [finalText, setFinalText] = useState("");
  const [engine, setEngine] = useState<"browser" | "server" | null>(null);

  const recognition = useRef<SpeechRecognitionLike | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const shouldListen = useRef(false);
  // Keep callbacks in refs so restarting recognition never uses stale closures.
  const handlers = useRef(options);
  handlers.current = options;

  useEffect(() => {
    api.voiceStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  const handleUtterance = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setFinalText(trimmed);
    handlers.current.onTranscript?.(trimmed, true);
    try {
      const command = await api.interpretVoice(trimmed);
      handlers.current.onCommand?.(command);
    } catch (err) {
      handlers.current.onError?.(err instanceof Error ? err.message : String(err));
    }
  }, []);

  // ------------------------------------------------------------- browser STT
  const startBrowser = useCallback(() => {
    const Ctor = getRecognitionCtor();
    if (!Ctor) return false;

    const rec = new Ctor();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-US";

    rec.onresult = (event: any) => {
      let live = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        const text = result[0].transcript;
        if (result.isFinal) {
          void handleUtterance(text);
          live = "";
        } else {
          live += text;
        }
      }
      setInterim(live);
      if (live) handlers.current.onTranscript?.(live, false);
    };

    rec.onerror = (event: any) => {
      // "no-speech" and "aborted" are routine; only surface real problems.
      if (event.error && !["no-speech", "aborted"].includes(event.error)) {
        handlers.current.onError?.(`Microphone: ${event.error}`);
      }
    };

    rec.onend = () => {
      // Chrome stops after a pause; restart while the user still wants to talk.
      if (shouldListen.current) {
        try {
          rec.start();
        } catch {
          /* already restarting */
        }
      } else {
        setListening(false);
        setInterim("");
      }
    };

    recognition.current = rec;
    rec.start();
    setEngine("browser");
    return true;
  }, [handleUtterance]);

  // -------------------------------------------------------------- server STT
  const startServer = useCallback(async () => {
    const media = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.current = media;

    const rec = new MediaRecorder(media);
    const chunks: Blob[] = [];

    rec.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    };

    rec.onstop = async () => {
      const blob = new Blob(chunks.splice(0), { type: rec.mimeType || "audio/webm" });
      if (blob.size > 1200) {
        try {
          const result: TranscriptResult = await api.transcribe(blob, true);
          if (result.text?.trim()) {
            setFinalText(result.text);
            handlers.current.onTranscript?.(result.text, true);
            if (result.command) handlers.current.onCommand?.(result.command);
          }
        } catch (err) {
          handlers.current.onError?.(err instanceof Error ? err.message : String(err));
        }
      }
      // Loop: start the next segment while the user is still holding the mic on.
      if (shouldListen.current && recorder.current) {
        try {
          recorder.current.start();
          window.setTimeout(() => {
            if (recorder.current?.state === "recording") recorder.current.stop();
          }, SEGMENT_MS);
        } catch {
          /* recorder torn down */
        }
      }
    };

    recorder.current = rec;
    rec.start();
    window.setTimeout(() => {
      if (recorder.current?.state === "recording") recorder.current.stop();
    }, SEGMENT_MS);
    setEngine("server");
  }, []);

  // ------------------------------------------------------------------ control
  const start = useCallback(async () => {
    if (shouldListen.current) return;
    shouldListen.current = true;
    setListening(true);
    setFinalText("");
    try {
      if (!startBrowser()) await startServer();
    } catch (err) {
      shouldListen.current = false;
      setListening(false);
      const message = err instanceof Error ? err.message : String(err);
      handlers.current.onError?.(
        message.includes("Permission") || message.includes("denied")
          ? "Microphone access was denied. Enable it in your browser's site settings."
          : message,
      );
    }
  }, [startBrowser, startServer]);

  const stop = useCallback(() => {
    shouldListen.current = false;
    setListening(false);
    setInterim("");
    recognition.current?.stop();
    recognition.current = null;
    if (recorder.current?.state === "recording") recorder.current.stop();
    recorder.current = null;
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  }, []);

  const toggle = useCallback(() => {
    if (shouldListen.current) stop();
    else void start();
  }, [start, stop]);

  // ---------------------------------------------------------------- speaking
  const stopSpeaking = useCallback(() => {
    if (audio.current) {
      audio.current.pause();
      URL.revokeObjectURL(audio.current.src);
      audio.current = null;
    }
    setSpeaking(false);
  }, []);

  const speak = useCallback(
    async (text: string) => {
      if (!text.trim()) return;
      stopSpeaking();
      try {
        const blob = await api.speak(text);
        const element = new Audio(URL.createObjectURL(blob));
        audio.current = element;
        element.onended = () => {
          URL.revokeObjectURL(element.src);
          setSpeaking(false);
        };
        setSpeaking(true);
        await element.play();
      } catch (err) {
        setSpeaking(false);
        handlers.current.onError?.(err instanceof Error ? err.message : String(err));
      }
    },
    [stopSpeaking],
  );

  useEffect(() => () => {
    shouldListen.current = false;
    recognition.current?.abort();
    if (recorder.current?.state === "recording") recorder.current.stop();
    stream.current?.getTracks().forEach((track) => track.stop());
    if (audio.current) audio.current.pause();
  }, []);

  return {
    status,
    listening,
    speaking,
    interim,
    finalText,
    engine,
    start,
    stop,
    toggle,
    speak,
    stopSpeaking,
  };
}
