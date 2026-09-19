import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AlertTriangle, ArrowDown, Archive, Bot, ThumbsDown, ThumbsUp, Loader2, MessageSquarePlus, Paperclip, Pencil, Pin, PinOff, Send, Trash2, UserRound, Volume2, Wrench, X } from "lucide-react";
import {
  api,
  chatStream,
  AttachmentCapabilities,
  ChatMessage,
  ChatResponse,
  ConversationSummary,
  KnowledgeHit,
  MemoryItem,
  ProcessedAttachment,
} from "../lib/api";
import { AnimatePresence, motion } from "framer-motion";
import { Badge, Toast, timeAgo } from "../components/ui";
import { spring } from "../lib/motion";
import { useToast } from "../hooks/useApi";
import { useVoiceControl } from "../components/VoiceControl";

/**
 * Three dots that rise in sequence while the agent works.
 *
 * A spinner says "busy"; this says "thinking", which is closer to the truth
 * during a multi-step tool loop.
 */
/**
 * How a staged file will be read.
 *
 * `note` is the backend's own explanation when something cannot be handled
 * (no vision model, unreadable binary), so it is shown verbatim rather than
 * reworded into something vaguer.
 */
function AttachmentHint({ state }: { state?: ProcessedAttachment | "pending" | "failed" }) {
  if (!state) return null;
  if (state === "pending") return <em className="attachment-hint">reading…</em>;
  if (state === "failed") return null;

  const problem = Boolean(state.note);
  const label = state.note
    ? state.note
    : state.handled_as === "image"
      ? "sent as an image"
      : state.handled_as === "transcribed"
        ? "transcribed"
        : `read as text · ${Number(state.meta?.characters ?? 0).toLocaleString()} chars`;

  return (
    <em className={`attachment-hint ${problem ? "warn" : ""}`} title={label}>
      {problem && <AlertTriangle size={10} />}
      {label}
    </em>
  );
}

function ThinkingDots() {
  return (
    <span className="thinking-dots" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <motion.i
          key={i}
          animate={{ y: [0, -4, 0], opacity: [0.35, 1, 0.35] }}
          transition={{ duration: 1.1, repeat: Infinity, delay: i * 0.16, ease: "easeInOut" }}
        />
      ))}
    </span>
  );
}

export function Chat() {
  const [params, setParams] = useSearchParams();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<string | undefined>(params.get("c") ?? undefined);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState("auto");
  const [lastMeta, setLastMeta] = useState<ChatResponse | null>(null);
  const [stage, setStage] = useState<string>("");
  const [liveTools, setLiveTools] = useState<{ tool: string; ok?: boolean }[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [caps, setCaps] = useState<AttachmentCapabilities | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const { toast, notify } = useToast();
  const voiceControl = useVoiceControl();
  const endRef = useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = useState(true);
  const [rated, setRated] = useState<Record<string, "up" | "down">>({});
  /** How each staged file will actually be read, keyed by name+size. */
  const [inspected, setInspected] = useState<Record<string, ProcessedAttachment | "pending" | "failed">>({});
  const [personas, setPersonas] = useState<{ id: string; label: string; description: string }[]>([]);
  const [persona, setPersona] = useState("default");

  const loadConversations = async () => {
    try {
      setConversations((await api.conversations()).conversations);
    } catch {
      /* offline-tolerant */
    }
  };

  useEffect(() => {
    void loadConversations();
  }, []);

  useEffect(() => {
    if (!conversationId) {
      setMessages([]);
      return;
    }
    api
      .conversation(conversationId)
      .then((c) => setMessages(c.messages))
      .catch(() => setMessages([]));
  }, [conversationId]);

  /**
   * Follow the conversation, but only while the user is already at the bottom.
   *
   * Auto-scrolling unconditionally yanks the view away from someone reading
   * back through history -- especially bad here, where tokens stream in and
   * would re-trigger it on every frame. When they have scrolled up we stop
   * following and offer an explicit jump button instead.
   */
  useEffect(() => {
    if (atBottom) endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy, atBottom]);

  function onMessagesScroll(event: React.UIEvent<HTMLDivElement>) {
    const el = event.currentTarget;
    // 80px of slack, so "near enough" still counts as following.
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
  }

  useEffect(() => {
    const q = params.get("q");
    if (q) {
      setInput(q);
      params.delete("q");
      setParams(params, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    api.attachmentCapabilities().then(setCaps).catch(() => setCaps(null));
    api.personas().then((r) => setPersonas(r.personas)).catch(() => setPersonas([]));
  }, []);

  /**
   * Persist the persona on the conversation.
   *
   * Personas live on the conversation rather than in component state so the
   * choice survives a reload and applies to every later turn. A brand new
   * conversation has no id yet, so we hold the value and let the first send
   * create the row; the effect below writes it once the id exists.
   */
  /**
   * Rate an answer.
   *
   * The backend reads the run's trace to find which learned skills shaped it
   * and moves their confidence, so this is what makes the assistant improve
   * from correction rather than only from whether a run crashed.
   */
  const fileKey = (file: File) => `${file.name}:${file.size}`;

  /**
   * Ask the backend how a file will be read, before anything is sent.
   *
   * Attaching a scanned PDF to a text-only model is the classic silent
   * failure: it looks attached, and the answer quietly ignores it. Showing
   * "read as text" vs "no vision model" up front turns that into something
   * the user can act on.
   */
  async function inspect(file: File) {
    const key = fileKey(file);
    setInspected((prev) => ({ ...prev, [key]: "pending" }));
    try {
      const result = await api.inspectAttachment(file);
      setInspected((prev) => ({ ...prev, [key]: result }));
    } catch {
      // Inspection is advisory; a failure must not block sending the file.
      setInspected((prev) => ({ ...prev, [key]: "failed" }));
    }
  }

  async function rate(runId: string, rating: "up" | "down") {
    setRated((r) => ({ ...r, [runId]: rating }));
    try {
      await api.sendFeedback({ rating, run_id: runId });
    } catch (err) {
      setRated((r) => {
        const next = { ...r };
        delete next[runId];
        return next;
      });
      notify(err instanceof Error ? err.message : String(err), "err");
    }
  }

  async function choosePersona(next: string) {
    setPersona(next);
    if (!conversationId) return;
    try {
      await api.updateConversation(conversationId, { persona: next });
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "err");
    }
  }

  // The first send creates the conversation; apply a non-default persona then.
  useEffect(() => {
    if (!conversationId || persona === "default") return;
    api.updateConversation(conversationId, { persona }).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  // Keep a live reference so the voice handler never closes over stale state.
  const stateRef = useRef({ input: "", busy: false, messages: [] as ChatMessage[] });
  stateRef.current = { input, busy, messages };

  /** Voice commands that only make sense on this page. */
  useEffect(
    () =>
      voiceControl.registerHandler("chat", (command) => {
        if (command.action === "chat" && command.value) {
          void sendText(String(command.value));
          return true;
        }
        if (command.action !== "ui") return false;
        switch (command.target) {
          case "set_input":
            setInput(String(command.value ?? ""));
            return true;
          case "send":
            if (stateRef.current.input.trim()) void sendText(stateRef.current.input.trim());
            return true;
          case "new_conversation":
            setConversationId(undefined);
            setMessages([]);
            setLastMeta(null);
            return true;
          case "read_last": {
            const last = [...stateRef.current.messages].reverse().find((m) => m.role === "assistant");
            if (last) void voiceControl.speak(last.content);
            else notify("Nothing to read back yet", "err");
            return true;
          }
          default:
            return false;
        }
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [voiceControl],
  );

  // A spoken question from another page arrives as ?say=...
  useEffect(() => {
    const queued = params.get("say");
    if (queued) {
      setParams({}, { replace: true });
      void sendText(queued);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Attachments cannot be streamed as multipart, so uploads use the JSON path. */
  async function sendWithFiles(text: string) {
    const pending = files;
    setFiles([]);
    setMessages((m) => [
      ...m,
      { role: "user", content: text || `(${pending.length} file(s) attached)` },
    ]);
    setBusy(true);
    setStage("Reading attachments…");
    try {
      const res = await api.chatWithFiles({
        message: text,
        conversationId,
        mode,
        files: pending,
      });
      setConversationId(res.conversation_id);
      setLastMeta(res);
      const skipped = res.attachments.filter((a: ProcessedAttachment) => a.note);
      if (skipped.length > 0) {
        notify(`${skipped[0].name}: ${skipped[0].note}`, "err");
      }
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: res.result || "No response returned.",
          provider: res.provider,
          model: res.model,
        },
      ]);
      void loadConversations();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      notify(message, "err");
      setMessages((m) => [...m, { role: "assistant", content: `Request failed: ${message}` }]);
    } finally {
      setBusy(false);
      setStage("");
    }
  }

  async function send() {
    const text = input.trim();
    if ((!text && files.length === 0) || busy) return;
    setInput("");
    if (files.length > 0) {
      await sendWithFiles(text);
      return;
    }
    await sendText(text);
  }

  async function sendText(text: string) {
    if (!text.trim() || stateRef.current.busy) return;
    setMessages((m) => [...m, { role: "user", content: text }]);
    setBusy(true);
    setLiveTools([]);
    setStage("Retrieving context…");

    let streamedContext: { memories: MemoryItem[]; knowledge: KnowledgeHit[] } = { memories: [], knowledge: [] };
    let answered = false;

    try {
      const convo = await chatStream(text, conversationId, mode, {
        onContext: (ctx) => {
          streamedContext = ctx;
          setStage("Reasoning…");
        },
        onStatus: (s) => {
          if (s.stage === "reasoning") setStage(s.step ? `Reasoning (step ${s.step + 1})…` : "Reasoning…");
        },
        onToolStart: (t) => {
          setStage(`Running ${t.tool}…`);
          setLiveTools((prev) => [...prev, { tool: t.tool }]);
        },
        onToolResult: (t) => {
          setLiveTools((prev) =>
            prev.map((x, i) => (i === prev.length - 1 && x.tool === t.tool ? { ...x, ok: t.result_ok } : x)),
          );
        },
        onToken: (text) => {
          // First token replaces the thinking indicator with a live bubble.
          setStage("");
          setMessages((m) => {
            const last = m[m.length - 1];
            if (last?.role === "assistant" && last.streaming) {
              return [...m.slice(0, -1), { ...last, content: last.content + text }];
            }
            return [...m, { role: "assistant", content: text, streaming: true }];
          });
        },
        onMessage: (content, alreadyStreamed) => {
          answered = true;
          if (voiceControl.autoSpeak && content) void voiceControl.speak(content);
          setMessages((m) => {
            const last = m[m.length - 1];
            if (last?.role === "assistant" && last.streaming) {
              // Settle the streamed bubble; trust the final text as canonical.
              return [...m.slice(0, -1), { ...last, content: content || last.content, streaming: false }];
            }
            if (alreadyStreamed && content) return m;
            return [...m, { role: "assistant", content: content || "No response returned." }];
          });
        },
        onDone: (info) => {
          setMessages((m) => {
            const copy = [...m];
            for (let i = copy.length - 1; i >= 0; i -= 1) {
              if (copy[i].role === "assistant") {
                copy[i] = { ...copy[i], run_id: info.run_id };
                break;
              }
            }
            return copy;
          });
          setLastMeta({
            conversation_id: conversationId ?? "",
            run_id: info.run_id,
            result: "",
            provider: info.provider,
            model: info.model,
            degraded: info.degraded,
            duration_ms: info.duration_ms,
            trace: [],
            memories: streamedContext.memories ?? [],
            knowledge: streamedContext.knowledge ?? [],
          });
        },
        onError: (message) => notify(message, "err"),
      });

      if (convo) setConversationId(convo);
      if (!answered) throw new Error("Stream ended without a reply");
      void loadConversations();
    } catch (err) {
      // Streaming can be blocked by proxies that buffer responses; fall back.
      try {
        const res = await api.chat(text, conversationId, mode);
        setConversationId(res.conversation_id);
        setLastMeta(res);
        setMessages((m) => [
          ...m,
          { role: "assistant", content: res.result || "No response returned.", provider: res.provider, model: res.model },
        ]);
        void loadConversations();
      } catch (fallbackErr) {
        const message = fallbackErr instanceof Error ? fallbackErr.message : String(fallbackErr);
        notify(message, "err");
        setMessages((m) => [...m, { role: "assistant", content: `Request failed: ${message}` }]);
      }
    } finally {
      setBusy(false);
      setStage("");
      setLiveTools([]);
    }
  }

  const usedTools = useMemo(
    () => Array.from(new Set((lastMeta?.trace ?? []).flatMap((t) => t.tool ?? t.tool_calls ?? []))),
    [lastMeta],
  );

  function submit(e: FormEvent) {
    e.preventDefault();
    void send();
  }

  return (
    <div className="page chat-layout">
      <aside className="convo-rail">
        <button
          className="primary full"
          onClick={() => {
            setConversationId(undefined);
            setMessages([]);
            setLastMeta(null);
          }}
        >
          <MessageSquarePlus size={15} /> New conversation
        </button>
        <div className="convo-list">
          {conversations.map((c) => (
            <div key={c.id} className={`convo-item ${c.id === conversationId ? "active" : ""}`}>
              <button onClick={() => setConversationId(c.id)}>
                <strong>{c.pinned ? "📌 " : ""}{c.title || "Untitled"}</strong>
                <span>{c.message_count} msgs · {timeAgo(c.updated_at)}</span>
              </button>
              <div className="convo-actions">
                <button
                  className="icon"
                  title={c.pinned ? "Unpin" : "Pin"}
                  onClick={async () => {
                    await api.updateConversation(c.id, { pinned: !c.pinned });
                    void loadConversations();
                  }}
                >
                  {c.pinned ? <PinOff size={12} /> : <Pin size={12} />}
                </button>
                <button
                  className="icon"
                  title="Rename"
                  onClick={async () => {
                    const title = window.prompt("Rename conversation", c.title);
                    if (title?.trim()) {
                      await api.updateConversation(c.id, { title: title.trim() });
                      void loadConversations();
                    }
                  }}
                >
                  <Pencil size={12} />
                </button>
                <button
                  className="icon"
                  title="Archive"
                  onClick={async () => {
                    await api.updateConversation(c.id, { archived: true });
                    if (c.id === conversationId) {
                      setConversationId(undefined);
                      setMessages([]);
                    }
                    notify("Conversation archived");
                    void loadConversations();
                  }}
                >
                  <Archive size={12} />
                </button>
                <button
                  className="icon danger"
                  title="Delete"
                  onClick={async () => {
                    await api.deleteConversation(c.id);
                    if (c.id === conversationId) {
                      setConversationId(undefined);
                      setMessages([]);
                    }
                    void loadConversations();
                  }}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
          ))}
          {conversations.length === 0 && <p className="muted small">No conversations yet.</p>}
        </div>
      </aside>

      <div className="chat-shell">
        <div className="chat-head">
          <div>
            <div className="eyebrow">CONVERSATION</div>
            <h2>ORION</h2>
          </div>
          <div className="chat-head-right">
            {personas.length > 0 && (
              <select
                value={persona}
                onChange={(e) => void choosePersona(e.target.value)}
                title={personas.find((p) => p.id === persona)?.description ?? "Conversation persona"}
              >
                {personas.map((p) => (
                  <option key={p.id} value={p.id}>{p.label}</option>
                ))}
              </select>
            )}
            <select value={mode} onChange={(e) => setMode(e.target.value)} title="Routing mode">
              <option value="auto">Auto routing</option>
              <option value="local">Local only</option>
              <option value="cloud">Cloud preferred</option>
            </select>
            {lastMeta && (
              <Badge tone={lastMeta.degraded ? "warn" : "ok"}>
                {lastMeta.provider} · {lastMeta.model}
              </Badge>
            )}
          </div>
        </div>

        <div className="messages" onScroll={onMessagesScroll}>
          {messages.length === 0 && !busy ? (
            <motion.div
              className="empty-chat"
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
            >
              <motion.div
                animate={{ y: [0, -7, 0] }}
                transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
              >
                <Bot size={40} />
              </motion.div>
              <h3>Ready when you are.</h3>
              <p>Ask anything. ORION retrieves memory and knowledge, then chooses the appropriate execution path.</p>
            </motion.div>
          ) : (
            messages.map((m, i) => (
              <motion.div
                key={i}
                className={`msg ${m.role}`}
                initial={{ opacity: 0, y: 14, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.34, ease: [0.22, 1, 0.36, 1] }}
              >
                <div className="msg-icon">{m.role === "user" ? <UserRound size={16} /> : <Bot size={16} />}</div>
                <div>
                  <div className="msg-role">
                    {m.role}
                    {m.model ? ` · ${m.model}` : ""}
                    {m.role === "assistant" && !m.streaming && m.run_id && (
                      <span className="msg-feedback">
                        <button
                          className={`rate ${rated[m.run_id] === "up" ? "on" : ""}`}
                          title="This answer was good"
                          aria-label="Good answer"
                          onClick={() => void rate(m.run_id!, "up")}
                        >
                          <ThumbsUp size={12} />
                        </button>
                        <button
                          className={`rate ${rated[m.run_id] === "down" ? "on down" : ""}`}
                          title="This answer was wrong or unhelpful"
                          aria-label="Bad answer"
                          onClick={() => void rate(m.run_id!, "down")}
                        >
                          <ThumbsDown size={12} />
                        </button>
                      </span>
                    )}
                    {m.role === "assistant" && !m.streaming && m.content && voiceControl.ttsAvailable && (
                      <button
                        className="speak-btn"
                        title="Read this aloud"
                        onClick={() => void voiceControl.speak(m.content)}
                      >
                        <Volume2 size={12} />
                      </button>
                    )}
                  </div>
                  <div className="msg-body">
                    {m.content}
                    {m.streaming && <span className="caret" aria-hidden="true" />}
                  </div>
                </div>
              </motion.div>
            ))
          )}
          <AnimatePresence>
          {busy && (
            <motion.div
              className="msg assistant"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.25 }}
            >
              <motion.div
                className="msg-icon"
                animate={{ boxShadow: ["0 0 0 0 rgba(124,167,255,0)", "0 0 0 6px rgba(124,167,255,0)", "0 0 0 0 rgba(124,167,255,0)"] }}
                transition={{ duration: 2, repeat: Infinity }}
              >
                <Bot size={16} />
              </motion.div>
              <div>
                <div className="msg-role">assistant</div>
                <div className="msg-body thinking">
                    <ThinkingDots />
                    <AnimatePresence mode="wait">
                      <motion.span
                        key={stage}
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        transition={{ duration: 0.18 }}
                      >
                        {stage || "Working…"}
                      </motion.span>
                    </AnimatePresence>
                  </div>
                  {liveTools.length > 0 && (
                    <div className="live-tools">
                      <AnimatePresence>
                        {liveTools.map((t, i) => (
                          <motion.span
                            key={`${t.tool}-${i}`}
                            className={t.ok === undefined ? "running" : t.ok ? "ok" : "err"}
                            initial={{ opacity: 0, scale: 0.8, y: 6 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            transition={spring}
                          >
                            <Wrench size={11} /> {t.tool}
                          </motion.span>
                        ))}
                      </AnimatePresence>
                    </div>
                  )}
              </div>
            </motion.div>
          )}
          </AnimatePresence>
          <div ref={endRef} />
        </div>

        <AnimatePresence>
          {!atBottom && (
            <motion.button
              className="jump-bottom"
              onClick={() => {
                setAtBottom(true);
                endRef.current?.scrollIntoView({ behavior: "smooth" });
              }}
              initial={{ opacity: 0, y: 8, scale: 0.9 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.9 }}
              transition={spring}
            >
              <ArrowDown size={14} /> Jump to latest
            </motion.button>
          )}
        </AnimatePresence>

        {lastMeta && (lastMeta.memories.length > 0 || lastMeta.knowledge.length > 0 || usedTools.length > 0) && (
          <div className="context-strip">
            {usedTools.length > 0 && (
              <span><Wrench size={12} /> {usedTools.join(", ")}</span>
            )}
            {lastMeta.memories.length > 0 && <span>{lastMeta.memories.length} memories used</span>}
            {lastMeta.knowledge.length > 0 && <span>{lastMeta.knowledge.length} knowledge chunks</span>}
            <span>{lastMeta.duration_ms} ms</span>
          </div>
        )}

        {files.length > 0 && (
          <motion.div className="attachment-tray" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}>
            <AnimatePresence mode="popLayout">
            {files.map((file, index) => (
              <motion.span
                key={`${file.name}-${index}`}
                className="attachment-chip"
                layout
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                transition={spring}
              >
                <span className="attachment-name">{file.name}</span>
                <AttachmentHint state={inspected[fileKey(file)]} />
                <button
                  type="button"
                  aria-label={`Remove ${file.name}`}
                  onClick={() => setFiles((f) => f.filter((_, i) => i !== index))}
                >
                  <X size={12} />
                </button>
              </motion.span>
            ))}
            </AnimatePresence>
          </motion.div>
        )}

        <form onSubmit={submit} className="composer">
          <input
            ref={fileRef}
            type="file"
            multiple
            hidden
            onChange={(e) => {
              const picked = Array.from(e.target.files ?? []);
              const limit = (caps?.max_upload_mb ?? 25) * 1024 * 1024;
              const tooBig = picked.filter((f) => f.size > limit);
              if (tooBig.length > 0) {
                notify(`${tooBig[0].name} is larger than ${caps?.max_upload_mb ?? 25} MB`, "err");
              }
              const accepted = picked.filter((p) => p.size <= limit);
              setFiles((f) => [...f, ...accepted]);
              accepted.forEach((file) => void inspect(file));
              e.target.value = "";
            }}
          />
          <button
            type="button"
            className="attach-btn"
            title={
              caps
                ? `Images ${caps.formats.images.supported ? "" : "(no vision model)"}, PDFs, Office docs, audio, code`
                : "Attach files"
            }
            onClick={() => fileRef.current?.click()}
          >
            <Paperclip size={17} />
          </button>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Give ORION a task…  (Enter to send, Shift+Enter for newline)"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
          />
          <motion.button
            className="send"
            disabled={busy || (!input.trim() && files.length === 0)}
            whileHover={{ scale: busy ? 1 : 1.05 }}
            whileTap={{ scale: 0.93 }}
          >
            {busy ? <Loader2 size={17} className="spin" /> : <Send size={17} />}
          </motion.button>
        </form>
      </div>
      <Toast toast={toast} />
    </div>
  );
}
