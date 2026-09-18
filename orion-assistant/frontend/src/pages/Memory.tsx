import { FormEvent, useState } from "react";
import { Brain, Pin, PinOff, Search, Trash2 } from "lucide-react";
import { api, MemoryItem } from "../lib/api";
import { useAsync, useToast } from "../hooks/useApi";
import { Badge, EmptyBlock, ErrorBlock, Loading, PageTitle, Panel, Toast, timeAgo } from "../components/ui";

export function Memory() {
  const { data, error, loading, reload } = useAsync(() => api.memories(), []);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MemoryItem[] | null>(null);
  const [form, setForm] = useState({ content: "", kind: "fact", key: "", confidence: 0.8 });
  const { toast, notify } = useToast();

  async function search(e: FormEvent) {
    e.preventDefault();
    if (!query.trim()) {
      setResults(null);
      return;
    }
    try {
      setResults((await api.searchMemory(query)).results);
    } catch (err) {
      notify(String(err), "err");
    }
  }

  async function add(e: FormEvent) {
    e.preventDefault();
    if (!form.content.trim()) return;
    try {
      await api.addMemory({
        content: form.content,
        kind: form.kind,
        key: form.key || undefined,
        confidence: Number(form.confidence),
      });
      setForm({ content: "", kind: "fact", key: "", confidence: 0.8 });
      notify("Memory stored");
      void reload();
    } catch (err) {
      notify(String(err), "err");
    }
  }

  const items = results ?? data?.memories ?? [];

  return (
    <div className="page">
      <PageTitle icon={Brain} title="Memory" subtitle="LONG-TERM STATE" />
      <div className="grid-two">
        <Panel subtitle="STORE" title="Add a durable memory">
          <form className="form" onSubmit={add}>
            <textarea
              placeholder="e.g. The user prefers concise, technical answers."
              value={form.content}
              onChange={(e) => setForm({ ...form, content: e.target.value })}
              rows={4}
            />
            <div className="form-row">
              <label>
                Kind
                <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                  {["fact", "preference", "project_fact", "person", "procedure", "interaction_summary"].map((k) => (
                    <option key={k} value={k}>{k}</option>
                  ))}
                </select>
              </label>
              <label>
                Key (optional, upserts)
                <input value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value })} placeholder="ui.theme" />
              </label>
              <label>
                Confidence
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  value={form.confidence}
                  onChange={(e) => setForm({ ...form, confidence: Number(e.target.value) })}
                />
              </label>
            </div>
            <button className="primary" disabled={!form.content.trim()}>Store memory</button>
          </form>
        </Panel>

        <Panel subtitle="RETRIEVE" title="Hybrid semantic search">
          <form className="inline-form" onSubmit={search}>
            <div className="search inline">
              <Search size={15} />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="What does ORION remember about…" />
            </div>
            <button className="primary">Search</button>
            {results && (
              <button type="button" className="ghost" onClick={() => { setResults(null); setQuery(""); }}>
                Clear
              </button>
            )}
          </form>
          <p className="muted small">
            Retrieval blends vector similarity, keyword overlap, stored confidence and pinning.
          </p>
        </Panel>
      </div>

      <Panel subtitle={results ? "SEARCH RESULTS" : "ALL MEMORIES"} title={`${items.length} entries`}>
        {loading && <Loading />}
        {error && <ErrorBlock message={error} />}
        {!loading && items.length === 0 && <EmptyBlock icon={Brain} title="No memories yet" hint="Store a fact above or start a conversation." />}
        <div className="list">
          {items.map((m) => (
            <div className="list-row" key={m.id}>
              <div>
                <div className="row-top">
                  <Badge tone="info">{m.kind}</Badge>
                  {m.key && <code>{m.key}</code>}
                  {m.pinned && <Badge tone="warn">pinned</Badge>}
                  {results && <Badge tone="ok">score {m.score}</Badge>}
                  <span className="muted small">conf {m.confidence.toFixed(2)} · {timeAgo(m.created_at)}</span>
                </div>
                <p>{m.content}</p>
              </div>
              <div className="row-actions">
                <button
                  className="icon"
                  title={m.pinned ? "Unpin" : "Pin"}
                  onClick={async () => {
                    await api.pinMemory(m.id, !m.pinned);
                    setResults(null);
                    void reload();
                  }}
                >
                  {m.pinned ? <PinOff size={14} /> : <Pin size={14} />}
                </button>
                <button
                  className="icon danger"
                  title="Delete"
                  onClick={async () => {
                    await api.deleteMemory(m.id);
                    notify("Memory deleted");
                    setResults(null);
                    void reload();
                  }}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </Panel>
      <Toast toast={toast} />
    </div>
  );
}
