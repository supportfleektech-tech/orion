import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bot, Loader2, MessageSquarePlus, Send, Trash2, UserRound, Wrench } from "lucide-react";
import { api, ChatMessage, ChatResponse, ConversationSummary } from "../lib/api";
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
    try {
      const res = await api.chat(text, conversationId, mode);
      setConversationId(res.conversation_id);
      setLastMeta(res);
      setMessages((m) => [
        ...m,
        { role: "assistant", content: res.result || "No response returned.", provider: res.provider, model: res.model },
      ]);
      void loadConversations();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      notify(message, "err");
      setMessages((m) => [...m, { role: "assistant", content: `Request failed: ${message}` }]);
    } finally {
      setBusy(false);
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
                <strong>{c.title || "Untitled"}</strong>
                <span>{c.message_count} msgs · {timeAgo(c.updated_at)}</span>
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
                <Trash2 size={13} />
              </button>
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
                <div className="msg-body thinking"><Loader2 size={14} className="spin" /> Retrieving context and reasoning…</div>
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
