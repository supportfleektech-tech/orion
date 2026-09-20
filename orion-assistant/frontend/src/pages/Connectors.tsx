import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  Cable,
  CircleSlash,
  ExternalLink,
  MinusCircle,
  RefreshCw,
} from "lucide-react";
import { motion } from "framer-motion";
import { api, type ConnectorInfo } from "../lib/api";
import { useAsync } from "../hooks/useApi";
import { Badge, ErrorBlock, Loading, PageTitle, Panel } from "../components/ui";
import { riseIn, stagger } from "../lib/motion";

/**
 * Connectors: the external services ORION can reach, probed live.
 *
 * The point is to answer "is it actually plugged in?" in one place. A wrong
 * base URL otherwise shows up much later as a vague degraded answer, and
 * "disabled by policy" looks identical to "broken" unless you say so plainly.
 */

const PRESENTATION = {
  connected: { icon: CheckCircle2, tone: "ok", label: "connected" },
  unreachable: { icon: AlertTriangle, tone: "err", label: "unreachable" },
  not_configured: { icon: MinusCircle, tone: "default", label: "not configured" },
  disabled: { icon: CircleSlash, tone: "warn", label: "disabled" },
} as const;

export function Connectors() {
  const navigate = useNavigate();
  const { data, error, loading, reload } = useAsync(() => api.connectors(), [], 30000);

  const connectors = data?.connectors ?? [];
  const byCategory = connectors.reduce<Record<string, ConnectorInfo[]>>((acc, c) => {
    (acc[c.category] ??= []).push(c);
    return acc;
  }, {});

  return (
    <div className="page">
      <PageTitle
        icon={Cable}
        title="Connectors"
        subtitle="EXTERNAL SERVICES"
        actions={
          <>
            {data && (
              <Badge tone={data.connected === data.total ? "ok" : "info"}>
                {data.connected}/{data.total} connected
              </Badge>
            )}
            {data?.local_only && <Badge tone="warn">local only</Badge>}
            <button className="ghost" onClick={() => void reload()} disabled={loading}>
              <RefreshCw size={13} className={loading ? "spin" : ""} /> Re-probe
            </button>
          </>
        }
      />

      {loading && !data && <Loading label="Probing services…" />}
      {error && <ErrorBlock message={error} />}

      <p className="muted" style={{ marginBottom: 16, maxWidth: 760 }}>
        Each service is probed live, not read from config. ORION is local-first, so every one of
        these is optional except the model runtime — and it degrades honestly rather than failing
        when something is missing.
      </p>

      {Object.entries(byCategory).map(([category, items], groupIndex) => (
        <Panel key={category} subtitle={category.toUpperCase()} title={`${items.length} services`} delay={groupIndex * 0.05}>
          <motion.div className="connector-grid" variants={stagger(0.05)} initial="initial" animate="animate">
            {items.map((c) => {
              const look = PRESENTATION[c.status] ?? PRESENTATION.not_configured;
              const Icon = look.icon;
              return (
                <motion.article key={c.id} className={`connector-card ${c.status}`} variants={riseIn} whileHover={{ y: -2 }}>
                  <div className="connector-head">
                    <Icon size={16} />
                    <strong>{c.name}</strong>
                    {c.required && <Badge tone="info">required</Badge>}
                    <Badge tone={look.tone}>{look.label}</Badge>
                  </div>

                  <p className="muted small">{c.summary}</p>
                  <p className="connector-detail">{c.detail}</p>

                  {c.endpoint && <code className="connector-endpoint">{c.endpoint}</code>}

                  {c.env_keys && c.env_keys.length > 0 && (
                    <div className="connector-env">
                      {c.env_keys.map((key) => (
                        <span key={key}>{key}</span>
                      ))}
                    </div>
                  )}

                  <div className="row-actions" style={{ marginTop: "auto", paddingTop: 10 }}>
                    {c.id === "mcp" && (
                      <button className="ghost" onClick={() => navigate("/mcp")}>
                        Manage servers
                      </button>
                    )}
                    {(c.id === "searxng" || c.id === "openrouter") && (
                      <button className="ghost" onClick={() => navigate("/settings")}>
                        Settings
                      </button>
                    )}
                    {c.id === "ollama" && (
                      <button className="ghost" onClick={() => navigate("/models")}>
                        Models
                      </button>
                    )}
                    {c.docs && (
                      <span className="muted small" style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                        <ExternalLink size={11} /> {c.docs}
                      </span>
                    )}
                  </div>
                </motion.article>
              );
            })}
          </motion.div>
        </Panel>
      ))}

      <Panel className="security-strip">
        <Cable size={20} />
        <div>
          <b>No OAuth, and no credential vault.</b>
          <span>
            Connectors are a URL you control plus, at most, one API key already in your
            environment. Holding third-party refresh tokens would make ORION a secret store — a
            very different security posture, and deliberately out of scope. To reach a service that
            needs richer auth, put it behind an MCP server you run.
          </span>
        </div>
      </Panel>
    </div>
  );
}
