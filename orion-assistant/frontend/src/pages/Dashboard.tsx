import { Link, useNavigate } from "react-router-dom";
import {
  Activity,
  ArrowUpRight,
  Brain,
  Cloud,
  Cpu,
  Database,
  Gauge,
  ShieldCheck,
  Sparkles,
  Wrench,
} from "lucide-react";
import { api } from "../lib/api";
import { useAsync } from "../hooks/useApi";
import { Badge, ErrorBlock, Loading, Panel, timeAgo } from "../components/ui";

const SUGGESTIONS = [
  "Summarize everything you know about my projects",
  "What is in my knowledge base?",
  "Plan a two-week delivery schedule",
  "List the tools you can use right now",
];

export function Dashboard() {
  const navigate = useNavigate();
  const { data: status, error, loading } = useAsync(() => api.status(), [], 15000);
  const { data: metrics } = useAsync(() => api.metrics(), [], 15000);

  if (loading && !status) return <div className="page"><Loading label="Connecting to ORION runtime…" /></div>;
  if (error && !status) return <div className="page"><ErrorBlock message={`Backend unreachable: ${error}`} /></div>;
  if (!status) return null;

  const local = status.providers.local;
  const cloud = status.providers.cloud;
  const online = local.reachable || cloud.reachable;

  return (
    <div className="page dashboard">
      <section className="hero-card">
        <div>
          <div className="eyebrow">PERSONAL AI OPERATING SYSTEM</div>
          <h1>Command the whole stack.</h1>
          <p>
            Local reasoning, persistent memory, retrieval, governed tools and cloud burst routing in one
            lightweight control plane. Version {status.version} · {status.environment} · uptime{" "}
            {Math.floor(status.uptime_seconds / 60)}m.
          </p>
          <div className="hero-actions">
            <button className="primary" onClick={() => navigate("/chat")}>
              <Sparkles size={15} /> Open conversation
            </button>
            <Link className="ghost" to="/knowledge">Ingest knowledge</Link>
          </div>
        </div>
        <div className="hero-orb">
          <div className="orb-core">O</div>
          <span style={{ color: online ? "#61dba5" : "#ffb454" }}>{online ? "READY" : "DEGRADED"}</span>
        </div>
      </section>

      {!online && (
        <div className="notice">
          <ShieldCheck size={16} />
          <div>
            <b>No model provider reachable.</b>
            <span>
              Memory, knowledge, tools and automations still work. Start Ollama or set OPENROUTER_API_KEY to
              enable generated answers.
            </span>
          </div>
        </div>
      )}

      <section className="metric-grid">
        <Metric icon={Cpu} k="Local model" v={local.model} sub={local.reachable ? "online" : "offline"} ok={local.reachable} />
        <Metric icon={Cloud} k="Cloud routing" v={cloud.configured ? cloud.model : "not configured"} sub={cloud.reachable ? "online" : cloud.configured ? "unreachable" : "add API key"} ok={cloud.reachable} />
        <Metric icon={Brain} k="Memories" v={`${status.counts.memories}`} sub={`${status.counts.conversations} conversations`} ok />
        <Metric icon={Database} k="Knowledge" v={`${status.counts.chunks} chunks`} sub={`${status.counts.documents} documents`} ok />
        <Metric icon={Wrench} k="Tools" v={`${status.tools.enabled}/${status.tools.total} allowed`} sub={`${status.counts.tool_runs} executions`} ok />
        <Metric icon={Gauge} k="Avg run" v={`${metrics?.avg_run_ms ?? 0} ms`} sub={`${metrics?.agent_runs_recent ?? 0} recent runs`} ok />
        <Metric icon={Activity} k="Success rate" v={`${Math.round((metrics?.agent_success_rate ?? 1) * 100)}%`} sub={`tools ${Math.round((metrics?.tool_success_rate ?? 1) * 100)}%`} ok />
        <Metric icon={ShieldCheck} k="Approvals" v={`${status.counts.pending_approvals} pending`} sub={status.kill_switch.enabled ? "kill switch ON" : "policies active"} ok={!status.kill_switch.enabled} />
      </section>

      <section className="grid-two">
        <Panel subtitle="COMMAND" title="What should ORION do?" right={<Sparkles size={19} />}>
          <p className="muted">Ask for research, code, file analysis, planning, automation, summaries or multi-step work.</p>
          <div className="suggestions">
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => navigate(`/chat?q=${encodeURIComponent(s)}`)}>{s}</button>
            ))}
          </div>
        </Panel>

        <Panel subtitle="LIVE TRACE" title="Recent agent runs" right={<ArrowUpRight size={19} />}>
          <div className="trace">
            {(metrics?.timeline ?? []).slice(0, 6).map((run) => (
              <div key={run.id}>
                <b title={run.task}>{run.task.slice(0, 44) || "(empty task)"}</b>
                <span>
                  <Badge tone={run.state === "succeeded" ? "ok" : "err"}>{run.state}</Badge> {run.provider} · {run.duration_ms}ms · {timeAgo(run.created_at)}
                </span>
              </div>
            ))}
            {(metrics?.timeline ?? []).length === 0 && <span className="muted">No runs yet. Start a conversation.</span>}
          </div>
        </Panel>
      </section>

      <Panel className="security-strip">
        <ShieldCheck size={20} />
        <div>
          <b>Autonomy is policy-bounded.</b>
          <span>
            Read-only tasks run automatically. External writes, shell, browser and network actions require
            explicit approval and are recorded in the audit log.
          </span>
        </div>
      </Panel>
    </div>
  );
}

function Metric({ icon: Icon, k, v, sub, ok }: { icon: any; k: string; v: string; sub: string; ok: boolean }) {
  return (
    <div className="metric">
      <Icon size={17} />
      <span>{k}</span>
      <strong>{v}</strong>
      <em className={ok ? "ok" : "warn"}>{sub}</em>
    </div>
  );
}
