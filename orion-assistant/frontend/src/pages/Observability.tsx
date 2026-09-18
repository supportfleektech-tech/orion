import { useState } from "react";
import { FlaskConical } from "lucide-react";
import { api, TraceEntry } from "../lib/api";
import { useAsync } from "../hooks/useApi";
import { Badge, EmptyBlock, ErrorBlock, Loading, PageTitle, Panel, timeAgo } from "../components/ui";

export function Observability() {
  const { data, error, loading } = useAsync(() => api.runs(), [], 10000);
  const { data: metrics } = useAsync(() => api.metrics(), [], 10000);
  const [openRun, setOpenRun] = useState<{ id: string; trace: TraceEntry[]; task: string; result: string } | null>(null);

  const runs = data?.runs ?? [];

  return (
    <div className="page">
      <PageTitle icon={FlaskConical} title="Observability" subtitle="TRACES & EVALUATION" />

      <section className="metric-grid">
        <Stat k="Recent runs" v={`${metrics?.agent_runs_recent ?? 0}`} />
        <Stat k="Agent success" v={`${Math.round((metrics?.agent_success_rate ?? 1) * 100)}%`} />
        <Stat k="Tool success" v={`${Math.round((metrics?.tool_success_rate ?? 1) * 100)}%`} />
        <Stat k="Avg duration" v={`${metrics?.avg_run_ms ?? 0} ms`} />
        <Stat k="Model calls" v={`${metrics?.router?.calls ?? 0}`} />
        <Stat k="Local calls" v={`${metrics?.router?.local_calls ?? 0}`} />
        <Stat k="Cloud calls" v={`${metrics?.router?.cloud_calls ?? 0}`} />
        <Stat k="Failures" v={`${metrics?.router?.failures ?? 0}`} />
      </section>

      <Panel subtitle="AGENT RUNS" title={`${runs.length} recorded runs`}>
        {loading && <Loading />}
        {error && <ErrorBlock message={error} />}
        {!loading && runs.length === 0 && <EmptyBlock icon={FlaskConical} title="No runs yet" hint="Every conversation and automation is traced here." />}
        <div className="list">
          {runs.map((r) => (
            <div className="list-row" key={r.id}>
              <button
                className="tool-main"
                onClick={async () => {
                  const detail = await api.run(r.id);
                  setOpenRun(detail);
                }}
              >
                <div className="row-top">
                  <strong>{r.task.slice(0, 90) || "(empty)"}</strong>
                  <Badge tone={r.state === "succeeded" ? "ok" : "err"}>{r.state}</Badge>
                  <span className="muted small">{r.provider}/{r.model} · {r.duration_ms}ms · {timeAgo(r.created_at)}</span>
                </div>
                <p className="muted small">{r.result?.slice(0, 200)}</p>
              </button>
            </div>
          ))}
        </div>
      </Panel>

      {openRun && (
        <div className="modal-backdrop" onClick={() => setOpenRun(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Run trace</h3>
            <p className="muted small">{openRun.task}</p>
            <pre className="output">{JSON.stringify(openRun.trace, null, 2)}</pre>
            <button className="primary" onClick={() => setOpenRun(null)}>Close</button>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div className="metric">
      <span>{k}</span>
      <strong>{v}</strong>
    </div>
  );
}
