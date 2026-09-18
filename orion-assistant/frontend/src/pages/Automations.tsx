import { FormEvent, useState } from "react";
import { Activity, Play, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { useAsync, useToast } from "../hooks/useApi";
import { Badge, EmptyBlock, ErrorBlock, Loading, PageTitle, Panel, Toast, timeAgo } from "../components/ui";

const INTERVALS = [
  { label: "Every 5 minutes", value: 300 },
  { label: "Hourly", value: 3600 },
  { label: "Every 6 hours", value: 21600 },
  { label: "Daily", value: 86400 },
  { label: "Weekly", value: 604800 },
];

export function Automations() {
  const { data, error, loading, reload } = useAsync(() => api.automations(), [], 20000);
  const [form, setForm] = useState({ name: "", prompt: "", schedule_seconds: 3600 });
  const [running, setRunning] = useState<string | null>(null);
  const { toast, notify } = useToast();

  async function create(e: FormEvent) {
    e.preventDefault();
    if (!form.name.trim() || !form.prompt.trim()) return;
    try {
      await api.createAutomation({ ...form, enabled: true });
      setForm({ name: "", prompt: "", schedule_seconds: 3600 });
      notify("Automation scheduled");
      void reload();
    } catch (err) {
      notify(String(err), "err");
    }
  }

  const automations = data?.automations ?? [];

  return (
    <div className="page">
      <PageTitle icon={Activity} title="Automations" subtitle="RECURRING AGENT WORK" />
      <div className="grid-two">
        <Panel subtitle="CREATE" title="Schedule a recurring task">
          <form className="form" onSubmit={create}>
            <label>
              Name
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Morning knowledge digest" />
            </label>
            <label>
              Prompt
              <textarea
                rows={4}
                value={form.prompt}
                onChange={(e) => setForm({ ...form, prompt: e.target.value })}
                placeholder="Summarize anything new in my knowledge base and list open questions."
              />
            </label>
            <label>
              Interval
              <select
                value={form.schedule_seconds}
                onChange={(e) => setForm({ ...form, schedule_seconds: Number(e.target.value) })}
              >
                {INTERVALS.map((i) => (
                  <option key={i.value} value={i.value}>{i.label}</option>
                ))}
              </select>
            </label>
            <button className="primary" disabled={!form.name.trim() || !form.prompt.trim()}>Create automation</button>
          </form>
          <p className="muted small">The in-process scheduler runs due automations every 30 seconds.</p>
        </Panel>

        <Panel subtitle="ACTIVE" title={`${automations.length} automations`}>
          {loading && <Loading />}
          {error && <ErrorBlock message={error} />}
          {!loading && automations.length === 0 && (
            <EmptyBlock icon={Activity} title="No automations" hint="Create one to run agent tasks on a schedule." />
          )}
          <div className="list">
            {automations.map((a) => (
              <div className="list-row" key={a.id}>
                <div>
                  <div className="row-top">
                    <strong>{a.name}</strong>
                    <Badge tone={a.enabled ? "ok" : "warn"}>{a.enabled ? "enabled" : "paused"}</Badge>
                    {a.last_status && <Badge tone={a.last_status === "succeeded" ? "ok" : "warn"}>{a.last_status}</Badge>}
                    <span className="muted small">every {Math.round(a.schedule_seconds / 60)}m · last {timeAgo(a.last_run_at)}</span>
                  </div>
                  <p className="muted small">{a.prompt}</p>
                  {a.last_result && <pre className="output small">{a.last_result.slice(0, 400)}</pre>}
                </div>
                <div className="row-actions">
                  <button
                    className="icon"
                    title="Run now"
                    disabled={running === a.id}
                    onClick={async () => {
                      setRunning(a.id);
                      try {
                        await api.runAutomation(a.id);
                        notify("Automation executed");
                        void reload();
                      } catch (err) {
                        notify(String(err), "err");
                      } finally {
                        setRunning(null);
                      }
                    }}
                  >
                    <Play size={14} />
                  </button>
                  <button
                    className="icon danger"
                    onClick={async () => {
                      await api.deleteAutomation(a.id);
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
      </div>
      <Toast toast={toast} />
    </div>
  );
}
