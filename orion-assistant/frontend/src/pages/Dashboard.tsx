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
import { motion } from "framer-motion";
import { api } from "../lib/api";
import { useAsync } from "../hooks/useApi";
import { Badge, Counter, ErrorBlock, Loading, Panel, Sparkline, timeAgo } from "../components/ui";
import { riseIn, stagger } from "../lib/motion";

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
  const timeline = metrics?.timeline ?? [];

  // Most recent runs last, so the sparkline reads left-to-right in time.
  const durations = [...timeline].reverse().map((r) => r.duration_ms);

  return (
    <div className="page dashboard">
      <motion.section
        className="hero-card"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      >
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
            <button className="ghost" onClick={() => navigate("/evaluation")}>Run evaluation</button>
          </div>
        </div>

        <div className="hero-orb">
          <motion.div
            className="orb-core"
            animate={{ scale: [1, 1.025, 1] }}
            transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
          >
            O
          </motion.div>
          <span style={{ color: online ? "var(--ok)" : "var(--warn)" }}>{online ? "READY" : "DEGRADED"}</span>
        </div>
      </motion.section>

      {!online && (
        <motion.div className="notice" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}>
          <ShieldCheck size={16} />
          <div>
            <b>No model provider reachable.</b>
            <span>
              Memory, knowledge, tools and automations still work. Start Ollama or set OPENROUTER_API_KEY to
              enable generated answers.
            </span>
          </div>
        </motion.div>
      )}

      <motion.section className="metric-grid" variants={stagger(0.05)} initial="initial" animate="animate">
        <Metric icon={Cpu} k="Local model" v={local.model} sub={local.reachable ? "online" : "offline"} ok={local.reachable} />
        <Metric icon={Cloud} k="Cloud routing" v={cloud.configured ? cloud.model : "not configured"} sub={cloud.reachable ? "online" : cloud.configured ? "unreachable" : "add API key"} ok={cloud.reachable} />
        <Metric icon={Brain} k="Memories" n={status.counts.memories} sub={`${status.counts.conversations} conversations`} ok />
        <Metric icon={Database} k="Knowledge" n={status.counts.chunks} unit=" chunks" sub={`${status.counts.documents} documents`} ok />
        <Metric icon={Wrench} k="Tools" v={`${status.tools.enabled}/${status.tools.total} allowed`} sub={`${status.counts.tool_runs} executions`} ok />
        <Metric icon={Gauge} k="Avg run" n={metrics?.avg_run_ms ?? 0} unit=" ms" sub={`${metrics?.agent_runs_recent ?? 0} recent runs`} ok />
        <Metric icon={Activity} k="Success rate" n={Math.round((metrics?.agent_success_rate ?? 1) * 100)} unit="%" sub={`tools ${Math.round((metrics?.tool_success_rate ?? 1) * 100)}%`} ok />
        <Metric icon={ShieldCheck} k="Approvals" n={status.counts.pending_approvals} unit=" pending" sub={status.kill_switch.enabled ? "kill switch ON" : "policies active"} ok={!status.kill_switch.enabled} />
      </motion.section>

      <section className="grid-two">
        <Panel subtitle="COMMAND" title="What should ORION do?" right={<Sparkles size={19} />} interactive>
          <p className="muted">Ask for research, code, file analysis, planning, automation, summaries or multi-step work.</p>
          <motion.div className="suggestions" variants={stagger(0.05, 0.1)} initial="initial" animate="animate">
            {SUGGESTIONS.map((s) => (
              <motion.button
                key={s}
                variants={riseIn}
                whileHover={{ y: -2 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => navigate(`/chat?q=${encodeURIComponent(s)}`)}
              >
                {s}
              </motion.button>
            ))}
          </motion.div>
        </Panel>

        <Panel
          subtitle="LIVE TRACE"
          title="Recent agent runs"
          right={<ArrowUpRight size={19} />}
          interactive
        >
          {durations.length > 1 && (
            <div className="spark-wrap">
              <Sparkline values={durations} />
              <span className="muted small">run duration, oldest → newest</span>
            </div>
          )}
          <motion.div className="trace" variants={stagger(0.05)} initial="initial" animate="animate">
            {timeline.slice(0, 6).map((run) => (
              <motion.div key={run.id} variants={riseIn}>
                <b title={run.task}>{run.task.slice(0, 44) || "(empty task)"}</b>
                <span>
                  <Badge tone={run.state === "succeeded" ? "ok" : "err"}>{run.state}</Badge> {run.provider} ·{" "}
                  {run.duration_ms}ms · {timeAgo(run.created_at)}
                </span>
              </motion.div>
            ))}
            {timeline.length === 0 && <span className="muted">No runs yet. Start a conversation.</span>}
          </motion.div>
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

/**
 * A single metric tile.
 *
 * Pass `n` for a numeric value and it counts up; pass `v` for text that
 * should appear immediately. Animating a model name would be silly.
 */
function Metric({
  icon: Icon,
  k,
  v,
  n,
  unit = "",
  sub,
  ok,
}: {
  icon: any;
  k: string;
  v?: string;
  n?: number;
  unit?: string;
  sub: string;
  ok: boolean;
}) {
  return (
    <motion.div className="metric" variants={riseIn} whileHover={{ y: -3 }}>
      <Icon size={17} />
      <span>{k}</span>
      <strong>
        {typeof n === "number" ? <><Counter value={n} />{unit}</> : v}
      </strong>
      <em className={ok ? "ok" : "warn"}>{sub}</em>
    </motion.div>
  );
}
