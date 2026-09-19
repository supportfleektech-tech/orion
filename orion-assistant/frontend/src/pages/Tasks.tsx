import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  CheckCircle2,
  ChevronRight,
  Clock,
  ListTodo,
  Play,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { api, type ApprovalItem, type AutomationItem, type RunItem } from "../lib/api";
import { useAsync, useToast } from "../hooks/useApi";
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
  Toast,
  timeAgo,
} from "../components/ui";
import { riseIn, stagger } from "../lib/motion";

/**
 * Tasks: everything ORION is doing, waiting on, or has just done.
 *
 * The underlying records already existed but were split across three pages --
 * approvals under Security, schedules under Automations, history under
 * Observability. That is the right grouping when you are administering each
 * subsystem, and the wrong one when the question is simply "what is my
 * assistant working on?". This page answers that, and links back to the
 * specialist page for anything deeper.
 */

type Filter = "all" | "waiting" | "scheduled" | "recent" | "failed";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "Everything" },
  { id: "waiting", label: "Waiting on me" },
  { id: "scheduled", label: "Scheduled" },
  { id: "recent", label: "Recent" },
  { id: "failed", label: "Failed" },
];

function humanInterval(seconds: number) {
  if (seconds % 86400 === 0) return `every ${seconds / 86400}d`;
  if (seconds % 3600 === 0) return `every ${seconds / 3600}h`;
  if (seconds % 60 === 0) return `every ${seconds / 60}m`;
  return `every ${seconds}s`;
}

export function Tasks() {
  const navigate = useNavigate();
  const { toast, notify } = useToast();
  const [filter, setFilter] = useState<Filter>("all");
  const [openRun, setOpenRun] = useState<RunItem | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // Poll: this is a live operations view, so staleness is the main failure.
  const approvals = useAsync(() => api.approvals("pending"), [], 8000);
  const automations = useAsync(() => api.automations(), [], 15000);
  const runs = useAsync(() => api.runs(), [], 8000);

  const pending: ApprovalItem[] = approvals.data?.approvals ?? [];
  const scheduled: AutomationItem[] = automations.data?.automations ?? [];
  const history: RunItem[] = runs.data?.runs ?? [];
  const failed = useMemo(() => history.filter((r) => r.state !== "succeeded"), [history]);

  const loading = approvals.loading && automations.loading && runs.loading;
  const error = approvals.error ?? automations.error ?? runs.error;

  async function decide(id: string, approve: boolean) {
    setBusy(id);
    try {
      await api.resolveApproval(id, approve);
      notify(approve ? "Approved and executed" : "Rejected");
      void approvals.reload();
      void runs.reload();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "err");
    } finally {
      setBusy(null);
    }
  }

  async function runNow(automation: AutomationItem) {
    setBusy(automation.id);
    try {
      await api.runAutomation(automation.id);
      notify(`Ran “${automation.name}”`);
      void automations.reload();
      void runs.reload();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "err");
    } finally {
      setBusy(null);
    }
  }

  const show = (section: Filter) => filter === "all" || filter === section;

  return (
    <div className="page">
      <PageTitle
        icon={ListTodo}
        title="Tasks"
        subtitle="WHAT ORION IS WORKING ON"
        actions={
          pending.length > 0 ? (
            <Badge tone="warn" pulse>
              {pending.length} waiting
            </Badge>
          ) : (
            <Badge tone="ok">nothing blocked</Badge>
          )
        }
      />

      <motion.section className="metric-grid" variants={stagger(0.05)} initial="initial" animate="animate">
        <Tile icon={ShieldAlert} label="Waiting on me" n={pending.length} tone={pending.length ? "warn" : "ok"} />
        <Tile icon={Clock} label="Scheduled" n={scheduled.filter((a) => a.enabled).length} />
        <Tile icon={Activity} label="Runs recorded" n={history.length} />
        <Tile icon={XCircle} label="Failed" n={failed.length} tone={failed.length ? "err" : "ok"} />
      </motion.section>

      <div className="filter-bar">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            className={`filter-chip ${filter === f.id ? "on" : ""}`}
            onClick={() => setFilter(f.id)}
          >
            {filter === f.id && <motion.span layoutId="filter-pill" className="filter-pill" />}
            <span>{f.label}</span>
          </button>
        ))}
      </div>

      {loading && <Loading label="Gathering tasks…" />}
      {error && !loading && <ErrorBlock message={error} />}

      {/* ------------------------------------------------- waiting on me */}
      {show("waiting") && (
        <Panel
          subtitle="BLOCKED"
          title="Waiting for your approval"
          right={<button className="ghost" onClick={() => navigate("/security")}>Policy <ChevronRight size={13} /></button>}
        >
          {pending.length === 0 ? (
            <EmptyBlock
              icon={CheckCircle2}
              title="Nothing is blocked"
              hint="High-risk tool calls pause here for review instead of running unattended."
            />
          ) : (
            <div className="list">
              <AnimatePresence mode="popLayout">
                {pending.map((a, idx) => (
                  <Row key={a.id} index={idx}>
                    <div style={{ minWidth: 0 }}>
                      <div className="row-top">
                        <strong>{a.tool_name}</strong>
                        <Badge tone="warn">needs approval</Badge>
                        <span className="muted small">{timeAgo(a.created_at)}</span>
                      </div>
                      <p>{a.reason}</p>
                      <pre className="output small">{JSON.stringify(a.arguments, null, 2)}</pre>
                    </div>
                    <div className="row-actions">
                      <button className="primary" disabled={busy === a.id} onClick={() => void decide(a.id, true)}>
                        Approve
                      </button>
                      <button className="ghost danger" disabled={busy === a.id} onClick={() => void decide(a.id, false)}>
                        Reject
                      </button>
                    </div>
                  </Row>
                ))}
              </AnimatePresence>
            </div>
          )}
        </Panel>
      )}

      {/* ---------------------------------------------------- scheduled */}
      {show("scheduled") && (
        <Panel
          subtitle="RECURRING"
          title="Scheduled work"
          right={<button className="ghost" onClick={() => navigate("/automations")}>Manage <ChevronRight size={13} /></button>}
        >
          {scheduled.length === 0 ? (
            <EmptyBlock icon={Clock} title="No scheduled tasks" hint="Automations run agent work on a timer." />
          ) : (
            <div className="list">
              <AnimatePresence mode="popLayout">
                {scheduled.map((a, idx) => (
                  <Row key={a.id} index={idx}>
                    <div style={{ minWidth: 0 }}>
                      <div className="row-top">
                        <strong>{a.name}</strong>
                        <Badge tone={a.enabled ? "ok" : "default"}>{a.enabled ? humanInterval(a.schedule_seconds) : "paused"}</Badge>
                        {a.last_status && (
                          <Badge tone={a.last_status === "succeeded" ? "ok" : "err"}>{a.last_status}</Badge>
                        )}
                        <span className="muted small">
                          {a.last_run_at ? `last ran ${timeAgo(a.last_run_at)}` : "never run"}
                        </span>
                      </div>
                      <p>{a.prompt}</p>
                    </div>
                    <div className="row-actions">
                      <button className="icon" title="Run now" disabled={busy === a.id} onClick={() => void runNow(a)}>
                        <Play size={13} />
                      </button>
                    </div>
                  </Row>
                ))}
              </AnimatePresence>
            </div>
          )}
        </Panel>
      )}

      {/* ------------------------------------------------------- history */}
      {(show("recent") || filter === "failed") && (
        <Panel
          subtitle={filter === "failed" ? "FAILURES" : "HISTORY"}
          title={filter === "failed" ? `${failed.length} failed runs` : "Recently completed"}
          right={<button className="ghost" onClick={() => navigate("/observability")}>Traces <ChevronRight size={13} /></button>}
        >
          {(filter === "failed" ? failed : history).length === 0 ? (
            <EmptyBlock
              icon={Activity}
              title={filter === "failed" ? "Nothing has failed" : "No runs yet"}
              hint="Every conversation, tool call and automation is recorded."
            />
          ) : (
            <div className="list">
              <AnimatePresence mode="popLayout">
                {(filter === "failed" ? failed : history).slice(0, 25).map((r, idx) => (
                  <Row key={r.id} index={idx}>
                    <button className="tool-main" onClick={() => setOpenRun(r)}>
                      <div className="row-top">
                        <strong>{r.task.slice(0, 80) || "(empty task)"}</strong>
                        <Badge tone={r.state === "succeeded" ? "ok" : "err"}>{r.state}</Badge>
                        <span className="muted small">
                          {r.provider}/{r.model} · {r.duration_ms}ms · {timeAgo(r.created_at)}
                        </span>
                      </div>
                      <p className="muted small">{r.result?.slice(0, 160)}</p>
                    </button>
                  </Row>
                ))}
              </AnimatePresence>
            </div>
          )}
        </Panel>
      )}

      <Modal open={Boolean(openRun)} onClose={() => setOpenRun(null)} title={openRun?.task}>
        <div className="row-top" style={{ marginBottom: 10 }}>
          <Badge tone={openRun?.state === "succeeded" ? "ok" : "err"}>{openRun?.state}</Badge>
          <span className="muted small">
            {openRun?.provider}/{openRun?.model} · {openRun?.duration_ms}ms
          </span>
        </div>
        <pre className="output">{openRun?.result || "(no output)"}</pre>
        <div className="row-actions" style={{ marginTop: 12 }}>
          <button className="primary" onClick={() => navigate("/observability")}>
            Open full trace
          </button>
          <button className="ghost" onClick={() => setOpenRun(null)}>Close</button>
        </div>
      </Modal>

      <Toast toast={toast} />
    </div>
  );
}

function Tile({
  icon: Icon,
  label,
  n,
  tone,
}: {
  icon: any;
  label: string;
  n: number;
  tone?: "ok" | "warn" | "err";
}) {
  const colour = tone === "err" ? "var(--err)" : tone === "warn" ? "var(--warn)" : undefined;
  return (
    <motion.div className="metric" variants={riseIn} whileHover={{ y: -3 }}>
      <Icon size={17} style={colour ? { color: colour } : undefined} />
      <span>{label}</span>
      <strong style={colour ? { color: colour } : undefined}>
        <Counter value={n} />
      </strong>
    </motion.div>
  );
}
