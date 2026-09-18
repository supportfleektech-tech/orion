import { Check, Shield, X } from "lucide-react";
import { api } from "../lib/api";
import { useAsync, useToast } from "../hooks/useApi";
import { Badge, EmptyBlock, ErrorBlock, Loading, PageTitle, Panel, Toast, Toggle, timeAgo } from "../components/ui";

export function Security() {
  const { data: status, reload: reloadStatus } = useAsync(() => api.status(), [], 15000);
  const { data, error, loading, reload } = useAsync(() => api.approvals("all"), [], 10000);
  const { data: audit } = useAsync(() => api.audit(), [], 15000);
  const { toast, notify } = useToast();

  const approvals = data?.approvals ?? [];
  const pending = approvals.filter((a) => a.status === "pending");

  return (
    <div className="page">
      <PageTitle icon={Shield} title="Security" subtitle="GOVERNANCE & CONTROL" />

      <Panel subtitle="EMERGENCY" title="Global kill switch">
        <div className="kill-row">
          <div>
            <p className="muted small">
              Disables every tool immediately. The agent can still answer from memory and knowledge, but cannot act.
            </p>
            {status?.kill_switch.enabled && <Badge tone="err">ENGAGED — {status.kill_switch.reason || "no reason given"}</Badge>}
          </div>
          <Toggle
            checked={status?.kill_switch.enabled ?? false}
            label={status?.kill_switch.enabled ? "Engaged" : "Normal operation"}
            onChange={async (v) => {
              await api.killSwitch(v, v ? "Engaged from Security console" : "");
              notify(v ? "Kill switch engaged" : "Kill switch released");
              void reloadStatus();
            }}
          />
        </div>
      </Panel>

      <Panel subtitle="APPROVALS" title={`${pending.length} pending requests`}>
        {loading && <Loading />}
        {error && <ErrorBlock message={error} />}
        {!loading && approvals.length === 0 && (
          <EmptyBlock icon={Shield} title="No approval requests" hint="High-risk tool calls will appear here for review." />
        )}
        <div className="list">
          {approvals.map((a) => (
            <div className="list-row" key={a.id}>
              <div>
                <div className="row-top">
                  <strong>{a.tool_name}</strong>
                  <Badge tone={a.status === "pending" ? "warn" : a.status === "approved" ? "ok" : "err"}>{a.status}</Badge>
                  <span className="muted small">{timeAgo(a.created_at)}</span>
                </div>
                <p className="muted small">{a.reason}</p>
                <pre className="output small">{JSON.stringify(a.arguments, null, 2)}</pre>
              </div>
              {a.status === "pending" && (
                <div className="row-actions">
                  <button
                    className="icon ok"
                    title="Approve and execute"
                    onClick={async () => {
                      await api.resolveApproval(a.id, true);
                      notify("Approved and executed");
                      void reload();
                    }}
                  >
                    <Check size={15} />
                  </button>
                  <button
                    className="icon danger"
                    title="Reject"
                    onClick={async () => {
                      await api.resolveApproval(a.id, false);
                      notify("Rejected");
                      void reload();
                    }}
                  >
                    <X size={15} />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </Panel>

      <Panel subtitle="AUDIT LOG" title="Recent governed events">
        <div className="list compact">
          {(audit?.events ?? []).slice(0, 40).map((e) => (
            <div className="list-row" key={e.id}>
              <div>
                <div className="row-top">
                  <Badge tone={e.event_type.includes("denied") || e.event_type.includes("failed") ? "err" : "info"}>
                    {e.event_type}
                  </Badge>
                  <span className="muted small">{e.actor} · {timeAgo(e.created_at)}</span>
                </div>
                <p className="muted small">{e.summary}</p>
              </div>
            </div>
          ))}
          {(audit?.events ?? []).length === 0 && <p className="muted small">No audit events recorded yet.</p>}
        </div>
      </Panel>
      <Toast toast={toast} />
    </div>
  );
}
