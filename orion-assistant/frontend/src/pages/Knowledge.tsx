import { FormEvent, useRef, useState } from "react";
import { Database, FileText, FolderOpen, Search, Trash2, Upload } from "lucide-react";
import { AnimatePresence } from "framer-motion";
import { api, KnowledgeHit } from "../lib/api";
import { useAsync, useToast } from "../hooks/useApi";
import { Badge, EmptyBlock, ErrorBlock, Loading, PageTitle, Panel, Toast, bytes, timeAgo, Row } from "../components/ui";

export function Knowledge() {
  const { data, error, loading, reload } = useAsync(() => api.documents(), []);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<KnowledgeHit[] | null>(null);
  const [text, setText] = useState({ name: "note.md", content: "" });
  const [uploading, setUploading] = useState(false);
  const [path, setPath] = useState("");
  const [ingestingPath, setIngestingPath] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const { toast, notify } = useToast();

  async function search(e: FormEvent) {
    e.preventDefault();
    if (!query.trim()) return setHits(null);
    try {
      setHits((await api.searchKnowledge(query)).results);
    } catch (err) {
      notify(String(err), "err");
    }
  }

  async function addText(e: FormEvent) {
    e.preventDefault();
    if (!text.content.trim()) return;
    try {
      await api.ingestText(text.name || "note.md", text.content);
      setText({ name: "note.md", content: "" });
      notify("Document ingested and indexed");
      void reload();
    } catch (err) {
      notify(String(err), "err");
    }
  }

  async function upload(file: File) {
    setUploading(true);
    try {
      const res = await api.uploadDocument(file);
      notify(`Indexed ${file.name} into ${res.chunks} chunks`);
      void reload();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "err");
    } finally {
      setUploading(false);
    }
  }

  /**
   * Index a file or whole directory already on the server's disk.
   *
   * Upload handles one file at a time from the browser; this is the path for
   * a folder of documents that already lives on the machine ORION runs on,
   * which is the common case for a local-first assistant.
   */
  async function addPath(e: FormEvent) {
    e.preventDefault();
    if (!path.trim()) return;
    setIngestingPath(true);
    try {
      // A directory returns a batch summary; a single file returns the document.
      const res = await api.ingestPath(path.trim());
      if ("results" in res) {
        const chunks = res.results.reduce((sum, d) => sum + d.chunks, 0);
        notify(`Indexed ${res.count} document${res.count === 1 ? "" : "s"} into ${chunks} chunks`);
      } else {
        notify(
          res.status === "unchanged"
            ? `${res.name} is already indexed and unchanged`
            : `Indexed ${res.name} into ${res.chunks} chunks`,
        );
      }
      setPath("");
      void reload();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "err");
    } finally {
      setIngestingPath(false);
    }
  }

  const documents = data?.documents ?? [];

  return (
    <div className="page">
      <PageTitle icon={Database} title="Knowledge" subtitle="RETRIEVAL AUGMENTED GENERATION" />

      <div className="grid-two">
        <Panel subtitle="INGEST" title="Add documents">
          <div
            className="dropzone"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const file = e.dataTransfer.files?.[0];
              if (file) void upload(file);
            }}
            onClick={() => fileRef.current?.click()}
          >
            <Upload size={22} />
            <strong>{uploading ? "Indexing…" : "Drop a file or click to upload"}</strong>
            <span>txt, md, pdf, docx, html, csv, json, source code</span>
            <input
              ref={fileRef}
              type="file"
              hidden
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void upload(file);
                e.target.value = "";
              }}
            />
          </div>
          <form className="form" onSubmit={addText} style={{ marginTop: 16 }}>
            <div className="form-row">
              <label style={{ flex: 1 }}>
                Name
                <input value={text.name} onChange={(e) => setText({ ...text, name: e.target.value })} />
              </label>
            </div>
            <textarea
              rows={5}
              placeholder="Paste text to index directly…"
              value={text.content}
              onChange={(e) => setText({ ...text, content: e.target.value })}
            />
            <button className="primary" disabled={!text.content.trim()}>Index text</button>
          </form>

          <form className="form" onSubmit={addPath} style={{ marginTop: 16 }}>
            <label>
              Or index a path inside the knowledge directory
              <input
                value={path}
                onChange={(e) => setPath(e.target.value)}
                placeholder="notes/         (a file, or a folder to batch-index)"
              />
              <small className="muted small">
                Relative to <code>KNOWLEDGE_DIR</code>. Paths outside it are refused, so a
                prompt-injected instruction cannot walk the filesystem.
              </small>
            </label>
            <button className="ghost" disabled={!path.trim() || ingestingPath}>
              <FolderOpen size={14} /> {ingestingPath ? "Indexing…" : "Index path"}
            </button>
          </form>
        </Panel>

        <Panel subtitle="SEARCH" title="Query the index">
          <form className="inline-form" onSubmit={search}>
            <div className="search inline">
              <Search size={15} />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search indexed knowledge…" />
            </div>
            <button className="primary">Search</button>
          </form>
          <div className="list" style={{ marginTop: 14 }}>
            <AnimatePresence mode="popLayout">
              {(hits ?? []).map((h, idx) => (
                <Row key={h.id} index={idx}>
                  <div>
                    <div className="row-top">
                      <Badge tone="info">{h.name ?? "document"}</Badge>
                      <Badge tone="ok">score {h.score}</Badge>
                      <span className="muted small">chunk #{h.chunk_index}</span>
                    </div>
                    <p>{h.content.slice(0, 420)}{h.content.length > 420 ? "…" : ""}</p>
                  </div>
                </Row>
              ))}
            </AnimatePresence>
            {hits && hits.length === 0 && <p className="muted small">No matches.</p>}
          </div>
        </Panel>
      </div>

      <Panel subtitle="LIBRARY" title={`${documents.length} documents`}>
        {loading && <Loading />}
        {error && <ErrorBlock message={error} />}
        {!loading && documents.length === 0 && (
          <EmptyBlock icon={FileText} title="No documents indexed" hint="Upload a file or paste text above." />
        )}
        <div className="list">
          <AnimatePresence mode="popLayout">
            {documents.map((d, idx) => (
              <Row key={d.id} index={idx}>
                <div>
                  <div className="row-top">
                    <FileText size={14} />
                    <strong>{d.name}</strong>
                    <Badge tone="info">{d.chunks} chunks</Badge>
                    <span className="muted small">{bytes(d.size_bytes)} · {timeAgo(d.created_at)}</span>
                  </div>
                  <p className="muted small">{d.path}</p>
                </div>
                <div className="row-actions">
                  <button
                    className="icon danger"
                    onClick={async () => {
                      await api.deleteDocument(d.id);
                      notify("Document removed");
                      void reload();
                    }}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </Row>
            ))}
          </AnimatePresence>
        </div>
      </Panel>
      <Toast toast={toast} />
    </div>
  );
}
