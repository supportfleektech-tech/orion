import { useEffect, useState } from "react";
import { Settings2 } from "lucide-react";
import { api, AppSettings } from "../lib/api";
import { useAsync, useToast } from "../hooks/useApi";
import { Badge, ErrorBlock, Loading, PageTitle, Panel, Toast, Toggle } from "../components/ui";
import { VoicePanel } from "../components/VoicePanel";

const FLAGS: { key: keyof AppSettings; label: string; hint: string }[] = [
  { key: "local_only", label: "Local only", hint: "Never call cloud providers, even for heavy tasks." },
  { key: "cloud_escalation_enabled", label: "Cloud escalation", hint: "Route complex tasks to OpenRouter when configured." },
  { key: "enable_web_search", label: "Web search", hint: "Allow the SearXNG-backed web_search tool." },
  { key: "allow_network_tool", label: "Network tools", hint: "Allow HTTP requests and page fetching." },
  { key: "allow_shell_tool", label: "Shell sandbox", hint: "Allow sandboxed shell commands in the knowledge directory." },
  { key: "allow_browser_tool", label: "Browser automation", hint: "Allow headless Playwright browsing." },
];

export function Settings() {
  const { data, error, loading, reload } = useAsync(() => api.settings(), []);
  const { data: status } = useAsync(() => api.status(), [], 15000);
  const [local, setLocal] = useState<AppSettings | null>(null);
  const { toast, notify } = useToast();

  useEffect(() => {
    if (data) setLocal(data);
  }, [data]);

  async function update(patch: Partial<AppSettings>) {
    try {
      const next = await api.updateSettings(patch);
      setLocal(next);
      notify("Settings updated");
      void reload();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "err");
    }
  }

  if (loading && !local) return <div className="page"><Loading /></div>;
  if (error && !local) return <div className="page"><ErrorBlock message={error} /></div>;
  if (!local) return null;

  return (
    <div className="page">
      <PageTitle icon={Settings2} title="Settings" subtitle="RUNTIME CONFIGURATION" />

      <Panel subtitle="CAPABILITIES" title="Policy flags">
        <p className="muted small">
          Changes apply immediately to the running process. Persist them in <code>.env</code> for restarts.
        </p>
        <div className="flag-grid">
          {FLAGS.map((f) => (
            <div className="flag" key={f.key}>
              <div>
                <strong>{f.label}</strong>
                <span className="muted small">{f.hint}</span>
              </div>
              <Toggle checked={Boolean(local[f.key])} onChange={(v) => void update({ [f.key]: v } as Partial<AppSettings>)} />
            </div>
          ))}
        </div>
      </Panel>

      <div className="grid-two">
        <Panel subtitle="MODELS" title="Routing">
          <label className="field">
            Local model (Ollama)
            <input
              value={local.ollama_model}
              onChange={(e) => setLocal({ ...local, ollama_model: e.target.value })}
              onBlur={() => void update({ ollama_model: local.ollama_model })}
            />
          </label>
          <label className="field">
            Cloud model (OpenRouter)
            <input
              value={local.openrouter_model}
              onChange={(e) => setLocal({ ...local, openrouter_model: e.target.value })}
              onBlur={() => void update({ openrouter_model: local.openrouter_model })}
            />
          </label>
          <label className="field">
            Max tool loops per run
            <input
              type="number"
              min={1}
              max={20}
              value={local.max_tool_loops}
              onChange={(e) => setLocal({ ...local, max_tool_loops: Number(e.target.value) })}
              onBlur={() => void update({ max_tool_loops: local.max_tool_loops })}
            />
          </label>
        </Panel>

        <VoicePanel />

        <Panel subtitle="RUNTIME" title="Environment">
          <div className="kv">
            <div><span>Version</span><strong>{status?.version ?? "—"}</strong></div>
            <div><span>Environment</span><strong>{local.environment}</strong></div>
            <div><span>Auth</span><strong>{local.auth_enabled ? "bearer token" : "disabled (local)"}</strong></div>
            <div>
              <span>Local provider</span>
              <strong><Badge tone={status?.providers.local.reachable ? "ok" : "warn"}>{status?.providers.local.reachable ? "online" : "offline"}</Badge></strong>
            </div>
            <div>
              <span>Cloud provider</span>
              <strong>
                <Badge tone={status?.providers.cloud.reachable ? "ok" : status?.providers.cloud.configured ? "warn" : "info"}>
                  {status?.providers.cloud.reachable ? "online" : status?.providers.cloud.configured ? "unreachable" : "not configured"}
                </Badge>
              </strong>
            </div>
            <div><span>Uptime</span><strong>{Math.floor((status?.uptime_seconds ?? 0) / 60)} min</strong></div>
          </div>
        </Panel>
      </div>
      <Toast toast={toast} />
    </div>
  );
}
