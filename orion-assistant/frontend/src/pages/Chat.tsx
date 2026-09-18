import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Archive, Bot, Loader2, MessageSquarePlus, Pencil, Pin, PinOff, Send, Trash2, UserRound, Wrench } from "lucide-react";
import { api, chatStream, ChatMessage, ChatResponse, ConversationSummary, KnowledgeHit, MemoryItem } from "../lib/api";
import { Badge, Toast, timeAgo } from "../components/ui";
import { useToast } from "../hooks/useApi";

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
  const { toast, notify } = useToast();
  const endRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  useEffect(() => {
    const q = params.get("q");
    if (q) {
      setInput(q);
      params.delete("q");
      setParams(params, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
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
        onMessage: (content) => {
          answered = true;
          setMessages((m) => [...m, { role: "assistant", content: content || "No response returned." }]);
        },
        onDone: (info) => {
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

        <div className="messages">
          {messages.length === 0 && !busy ? (
            <div className="empty-chat">
              <Bot size={40} />
              <h3>Ready when you are.</h3>
              <p>Ask anything. ORION retrieves memory and knowledge, then chooses the appropriate execution path.</p>
            </div>
          ) : (
            messages.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                <div className="msg-icon">{m.role === "user" ? <UserRound size={16} /> : <Bot size={16} />}</div>
                <div>
                  <div className="msg-role">
                    {m.role}
                    {m.model ? ` · ${m.model}` : ""}
                  </div>
                  <div className="msg-body">{m.content}</div>
                </div>
              </div>
            ))
          )}
          {busy && (
            <div className="msg assistant">
              <div className="msg-icon"><Bot size={16} /></div>
              <div>
                <div className="msg-role">assistant</div>
                <div className="msg-body thinking">
                    <Loader2 size={14} className="spin" /> {stage || "Working…"}
                  </div>
                  {liveTools.length > 0 && (
                    <div className="live-tools">
                      {liveTools.map((t, i) => (
                        <span key={`${t.tool}-${i}`} className={t.ok === undefined ? "running" : t.ok ? "ok" : "err"}>
                          <Wrench size={11} /> {t.tool}
                        </span>
                      ))}
                    </div>
                  )}
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>

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

        <form onSubmit={submit} className="composer">
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
          <button disabled={busy || !input.trim()}>{busy ? <Loader2 size={17} className="spin" /> : <Send size={17} />}</button>
        </form>
      </div>
      <Toast toast={toast} />
    </div>
  );
}
