import { useState } from "react";
import { FlaskConical } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { api, TraceEntry } from "../lib/api";
import { useAsync } from "../hooks/useApi";
import {
  Badge,
  Counter,
  EmptyBlock,
  ErrorBlock,
  Loading,
  Modal,
  PageTitle,
  Panel,
  Row,
  Sparkline,
  timeAgo,
} from "../components/ui";
import { riseIn, stagger } from "../lib/motion";

export function Observability() {
  const { data, error, loading } = useAsync(() => api.runs(), [], 10000);
  const { data: metrics } = useAsync(() => api.metrics(), [], 10000);
  const [openRun, setOpenRun] = useState<{ id: string; trace: TraceEntry[]; task: string; result: string } | null>(null);

  const runs = data?.runs ?? [];
  // Oldest first, so the sparkline reads left-to-right in time.
  const durations = [...runs].reverse().map((r) => r.duration_ms);

  return (
    <div className="page">
      <PageTitle icon={FlaskConical} title="Observability" subtitle="TRACES & EVALUATION" />

      <motion.section className="metric-grid" variants={stagger(0.04)} initial="initial" animate="animate">
        <Stat k="Recent runs" n={metrics?.agent_runs_recent ?? 0} />
        <Stat k="Agent success" n={Math.round((metrics?.agent_success_rate ?? 1) * 100)} unit="%" />
        <Stat k="Tool success" n={Math.round((metrics?.tool_success_rate ?? 1) * 100)} unit="%" />
        <Stat k="Avg duration" n={metrics?.avg_run_ms ?? 0} unit=" ms" />
        <Stat k="Model calls" n={metrics?.router?.calls ?? 0} />
        <Stat k="Local calls" n={metrics?.router?.local_calls ?? 0} />
        <Stat k="Cloud calls" n={metrics?.router?.cloud_calls ?? 0} />
        <Stat k="Failures" n={metrics?.router?.failures ?? 0} tone={(metrics?.router?.failures ?? 0) > 0} />
      </motion.section>

      {durations.length > 1 && (
        <Panel subtitle="TREND" title="Run duration" interactive>
          <Sparkline values={durations} />
          <p className="muted small" style={{ marginTop: 6 }}>
            Oldest to newest across the last {durations.length} runs.
          </p>
        </Panel>
      )}

      <Panel subtitle="AGENT RUNS" title={`${runs.length} recorded runs`}>
        {loading && <Loading />}
        {error && <ErrorBlock message={error} />}
        {!loading && runs.length === 0 && <EmptyBlock icon={FlaskConical} title="No runs yet" hint="Every conversation and automation is traced here." />}
        <div className="list">
          <AnimatePresence mode="popLayout">
          {runs.map((r, idx) => (
            <Row key={r.id} index={idx}>
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
            </Row>
          ))}
          </AnimatePresence>
        </div>
      </Panel>

      <Modal open={Boolean(openRun)} onClose={() => setOpenRun(null)} title="Run trace">
        <p className="muted small">{openRun?.task}</p>
        <pre className="output">{JSON.stringify(openRun?.trace ?? [], null, 2)}</pre>
        <button className="primary" onClick={() => setOpenRun(null)}>Close</button>
      </Modal>
    </div>
  );
}

function Stat({ k, n, unit = "", tone = false }: { k: string; n: number; unit?: string; tone?: boolean }) {
  return (
    <motion.div className="metric" variants={riseIn} whileHover={{ y: -3 }}>
      <span>{k}</span>
      <strong style={tone ? { color: "var(--err)" } : undefined}>
        <Counter value={n} />{unit}
      </strong>
    </motion.div>
  );
}
