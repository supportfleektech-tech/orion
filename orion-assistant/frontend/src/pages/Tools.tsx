import { useState } from "react";
import { Play, TerminalSquare } from "lucide-react";
import { AnimatePresence } from "framer-motion";
import { api, Tool } from "../lib/api";
import { useAsync, useToast } from "../hooks/useApi";
import { Badge, ErrorBlock, Loading, PageTitle, Panel, Toast, Toggle, riskTone, timeAgo, Row } from "../components/ui";

export function Tools() {
  const { data, error, loading, reload } = useAsync(() => api.tools(), []);
  const { data: runs, reload: reloadRuns } = useAsync(() => api.toolRuns(), [], 10000);
  const [selected, setSelected] = useState<Tool | null>(null);
  const [args, setArgs] = useState("{}");
  const [output, setOutput] = useState<string>("");
  const { toast, notify } = useToast();

  async function run() {
    if (!selected) return;
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(args || "{}");
    } catch {
      return notify("Arguments must be valid JSON", "err");
    }
    try {
      const res = await api.runTool(selected.name, parsed);
      setOutput(JSON.stringify(res, null, 2));
      if (res.approval_required) notify("Approval required — see Security page", "err");
      else notify("Tool executed");
      void reloadRuns();
    } catch (err) {
      setOutput(String(err));
      notify(err instanceof Error ? err.message : String(err), "err");
    }
  }

  const tools = data?.tools ?? [];
  const categories = Array.from(new Set(tools.map((t) => t.category)));

  return (
    <div className="page">
      <PageTitle icon={TerminalSquare} title="Tools" subtitle="CAPABILITY GATEWAY" />
      {loading && <Loading />}
      {error && <ErrorBlock message={error} />}

      <div className="grid-two">
        <div>
          {categories.map((cat) => (
            <Panel key={cat} subtitle={cat.toUpperCase()} title={`${tools.filter((t) => t.category === cat).length} tools`}>
              <div className="list">
                {tools
                  .filter((t) => t.category === cat)
                  .map((t, ti) => (
                    <Row key={t.name} index={ti} className={`tool-row ${selected?.name === t.name ? "active" : ""}`}>
                      <button
                        className="tool-main"
                        onClick={() => {
                          setSelected(t);
                          setOutput("");
                          const props = (t.parameters?.properties ?? {}) as Record<string, any>;
                          const template = Object.fromEntries(
                            Object.keys(props).map((k) => [k, props[k].default ?? ""]),
                          );
                          setArgs(JSON.stringify(template, null, 2));
                        }}
                      >
                        <div className="row-top">
                          <strong>{t.name}</strong>
                          <Badge tone={riskTone(t.risk)}>{t.risk}</Badge>
                          {t.requires_confirmation && <Badge tone="warn">approval</Badge>}
                          {!t.allowed && <Badge tone="err">blocked</Badge>}
                        </div>
                        <p className="muted small">{t.description}</p>
                        {!t.allowed && <p className="muted small">{t.policy_reason}</p>}
                      </button>
                      <Toggle
                        checked={t.enabled}
                        onChange={async (v) => {
                          await api.toggleTool(t.name, v);
                          void reload();
                        }}
                      />
                    </Row>
                  ))}
              </div>
            </Panel>
          ))}
        </div>

        <div>
          <Panel subtitle="RUNNER" title={selected ? selected.name : "Select a tool"}>
            {selected ? (
              <>
                <p className="muted small">{selected.description}</p>
                <textarea rows={8} value={args} onChange={(e) => setArgs(e.target.value)} className="code" />
                <button className="primary" onClick={() => void run()}>
                  <Play size={14} /> Execute
                </button>
                {output && <pre className="output">{output}</pre>}
              </>
            ) : (
              <p className="muted small">Pick a tool from the registry to inspect its schema and run it manually.</p>
            )}
          </Panel>

          <Panel subtitle="HISTORY" title="Recent executions">
            <div className="list">
              <AnimatePresence mode="popLayout">
                {(runs?.runs ?? []).slice(0, 12).map((r, idx) => (
                  <Row key={r.id} index={idx}>
                    <div>
                      <div className="row-top">
                        <strong>{r.tool_name}</strong>
                        <Badge tone={r.status === "succeeded" ? "ok" : "err"}>{r.status}</Badge>
                        <span className="muted small">{r.duration_ms}ms · {timeAgo(r.created_at)}</span>
                      </div>
                      {r.error && <p className="muted small">{r.error}</p>}
                    </div>
                  </Row>
                ))}
              </AnimatePresence>
              {(runs?.runs ?? []).length === 0 && <p className="muted small">No executions yet.</p>}
            </div>
          </Panel>
        </div>
      </div>
      <Toast toast={toast} />
    </div>
  );
}
