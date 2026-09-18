import { useCallback, useEffect, useRef, useState } from "react";
import { Cpu, Download, HardDrive, RefreshCw } from "lucide-react";
import { api, type ModelStatus, type ModelTier, type ProvisionResult } from "../lib/api";
import { Badge, ErrorBlock, Loading, PageTitle, Panel, Toast } from "../components/ui";
import { useToast } from "../hooks/useApi";

export function Models() {
  const [status, setStatus] = useState<ModelStatus | null>(null);
  const [catalog, setCatalog] = useState<ModelTier[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const { toast, notify } = useToast();
  const poll = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, c] = await Promise.all([api.modelStatus(), api.modelCatalog()]);
      setStatus(s);
      setCatalog(c.tiers);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Keep refreshing only while a download is actually running.
  useEffect(() => {
    const pulling = Object.values(status?.pulls ?? {}).some((p) => p.status === "pulling");
    if (pulling && poll.current === null) {
      poll.current = window.setInterval(() => void load(), 1500);
    } else if (!pulling && poll.current !== null) {
      window.clearInterval(poll.current);
      poll.current = null;
    }
    return () => {
      if (poll.current !== null) {
        window.clearInterval(poll.current);
        poll.current = null;
      }
    };
  }, [status, load]);

  async function provision(model: string) {
    setBusy(model);
    try {
      const result: ProvisionResult = await api.provisionModel(model);
      notify(result.ok ? `${result.model} is ready.` : result.message ?? "Provisioning failed.", result.ok ? "ok" : "err");
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "err");
    } finally {
      setBusy(null);
      void load();
    }
  }

  if (loading) return <div className="page"><Loading label="Inspecting local model stack…" /></div>;

  const hw = status?.hardware;
  const pulls = Object.values(status?.pulls ?? {});

  return (
    <div className="page">
      <PageTitle
        icon={Cpu}
        title="Models"
        subtitle="LOCAL INFERENCE"
        actions={
          <button className="ghost" onClick={() => void load()}>
            <RefreshCw size={14} /> Refresh
          </button>
        }
      />

      {error && <ErrorBlock message={error} />}

      {status && (
        <Panel title="Runtime" subtitle="CURRENT STATE">
          <div className="kv">
            <div className="row-top">
              <strong>Ollama</strong>
              <Badge tone={status.ollama_running ? "ok" : "err"}>
                {status.ollama_running ? "running" : "not reachable"}
              </Badge>
              <span className="muted small">{status.host}</span>
            </div>
            <div className="row-top">
              <strong>Active model</strong>
              <Badge tone={status.active_model_present ? "ok" : "warn"}>{status.active_model}</Badge>
              <span className="muted small">
                {status.active_model_present ? "downloaded" : "not downloaded on this machine"}
              </span>
            </div>
            <div className="row-top">
              <strong>Vision</strong>
              <Badge tone={status.vision_capable ? "ok" : "warn"}>
                {status.vision_capable ? "images supported" : "text only"}
              </Badge>
            </div>
            <div className="row-top">
              <strong>Embeddings</strong>
              <Badge tone={status.embed_model_present ? "ok" : "warn"}>{status.embed_model}</Badge>
            </div>
          </div>

          {!status.ollama_running && (
            <div className="notice">
              <div>
                Ollama is not reachable, so no real model can run yet. Run{" "}
                <code>./scripts/setup-local-model.sh</code> from the project root — it installs
                Ollama, picks the best model for this hardware, downloads it, and writes the
                settings into <code>.env</code>.
              </div>
            </div>
          )}
        </Panel>
      )}

      {hw && (
        <Panel title="This machine" subtitle="HARDWARE" right={<HardDrive size={16} />}>
          <div className="metric-grid">
            <div className="metric"><strong>{hw.total_ram_gb} GB</strong><em>total RAM</em></div>
            <div className="metric"><strong>{hw.available_ram_gb} GB</strong><em>available RAM</em></div>
            <div className="metric"><strong>{hw.cpu_count}</strong><em>CPU cores</em></div>
            <div className="metric"><strong>{hw.free_disk_gb} GB</strong><em>free disk</em></div>
            <div className="metric"><strong>{hw.gpu_detected ? "Yes" : "No"}</strong><em>GPU</em></div>
            <div className="metric"><strong>{hw.recommended.model}</strong><em>recommended</em></div>
          </div>
          <p className="muted small">{hw.recommended.note}</p>
          {!hw.disk_sufficient && (
            <div className="notice">
              <div>
                Not enough free disk for the recommended model: it needs about{" "}
                {hw.disk_needed_gb} GB and only {hw.free_disk_gb} GB is available.
              </div>
            </div>
          )}
        </Panel>
      )}

      {pulls.length > 0 && (
        <Panel title="Downloads" subtitle="IN PROGRESS">
          {pulls.map((pull) => (
            <div key={pull.model} className="list-row">
              <div style={{ flex: 1 }}>
                <div className="row-top">
                  <strong>{pull.model}</strong>
                  <Badge tone={pull.status === "ready" ? "ok" : pull.status === "failed" ? "err" : "info"}>
                    {pull.status}
                  </Badge>
                  <span className="muted small">{pull.percent}%</span>
                </div>
                <div className="progress">
                  <div className="progress-fill" style={{ width: `${Math.min(100, pull.percent)}%` }} />
                </div>
                <span className="muted small">{pull.error ?? pull.detail}</span>
              </div>
            </div>
          ))}
        </Panel>
      )}

      <Panel
        title="Model catalog"
        subtitle="PICK A MODEL"
        right={<span className="muted small">sized against this machine</span>}
      >
        <div className="model-grid">
          {catalog.map((tier) => {
            const installed = status?.installed_models.some(
              (m) => m.name.split(":")[0] === tier.model.split(":")[0],
            );
            return (
              <article key={tier.model} className={`model-card ${tier.fits ? "" : "dimmed"}`}>
                <div className="row-top">
                  <strong>{tier.model}</strong>
                  <Badge tone={tier.fits ? "ok" : "warn"}>{tier.fits ? tier.name : "too large"}</Badge>
                </div>
                <div className="model-specs">
                  <span>{tier.download_gb} GB download</span>
                  <span>~{tier.min_ram_gb} GB RAM</span>
                  <span>{tier.context} context</span>
                  <span>{tier.multimodal ? "multimodal" : "text only"}</span>
                  <span className={tier.tools ? "" : "flag"}>
                    {tier.tools ? "tool calling" : "no tool calling"}
                  </span>
                </div>
                <p className="muted small">{tier.note}</p>
                <div className="row-actions">
                  {installed ? (
                    <Badge tone="ok">installed</Badge>
                  ) : (
                    <button
                      className="ghost"
                      disabled={busy !== null || !status?.ollama_running}
                      onClick={() => void provision(tier.model)}
                    >
                      <Download size={14} />
                      {busy === tier.model ? "Downloading…" : "Download"}
                    </button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      </Panel>

      <Toast toast={toast} />
    </div>
  );
}
