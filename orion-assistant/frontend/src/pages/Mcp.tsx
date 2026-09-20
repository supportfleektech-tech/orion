import { useState } from "react";
import { Plug, Plus, RefreshCw, Trash2, Wrench } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { api, type McpServerInfo, type McpServerInput } from "../lib/api";
import { useAsync, useToast } from "../hooks/useApi";
import {
  Badge,
  EmptyBlock,
  ErrorBlock,
  Loading,
  PageTitle,
  Panel,
  Toast,
  Toggle,
  riskTone,
  timeAgo,
} from "../components/ui";

const BLANK: McpServerInput = {
  name: "",
  description: "",
  transport: "stdio",
  command: "",
  url: "",
  risk: "medium",
  requires_confirmation: true,
  enabled: true,
};

function statusTone(status: McpServerInfo["status"]) {
  if (status === "ok") return "ok" as const;
  if (status === "error") return "err" as const;
  if (status === "disabled") return "default" as const;
  return "info" as const;
}

/**
 * MCP servers: external tool providers ORION can borrow capabilities from.
 *
 * Tools discovered here are namespaced as <server>.<tool> and pass through the
 * same policy gate as builtins, so a remote server can never grant itself more
 * privilege than the risk level configured on this page.
 */
export function Mcp() {
  const { data, loading, error, reload } = useAsync(() => api.mcpServers(), []);
  const { toast, notify } = useToast();
  const [draft, setDraft] = useState<McpServerInput | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  async function run(id: string, action: () => Promise<unknown>, message: string) {
    setBusy(id);
    try {
      await action();
      notify(message);
      reload();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "err");
    } finally {
      setBusy(null);
    }
  }

  async function create() {
    if (!draft) return;
    if (!draft.name.trim()) return notify("A name is required", "err");
    if (draft.transport === "stdio" && !draft.command?.trim())
      return notify("stdio servers need a command", "err");
    if (draft.transport === "http" && !draft.url?.trim())
      return notify("http servers need a URL", "err");

    setBusy("new");
    try {
      await api.createMcpServer(draft);
      setDraft(null);
      notify("Server added — discovering tools");
      reload();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "err");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="page">
      <PageTitle
        icon={Plug}
        title="MCP servers"
        subtitle="Borrow tools from external Model Context Protocol servers"
        actions={
          <>
            <button
              className="ghost"
              disabled={busy !== null}
              onClick={() => run("all", () => api.refreshMcp(), "Reconnected to all servers")}
            >
              <RefreshCw size={14} /> Refresh all
            </button>
            <button className="primary" onClick={() => setDraft(draft ? null : { ...BLANK })}>
              <Plus size={14} /> Add server
            </button>
          </>
        }
      />

      {loading && <Loading />}
      {error && <ErrorBlock message={error} />}

      {data && !data.sdk_available && (
        <div className="notice">
          <div>
            <strong>The MCP SDK is not installed.</strong>
            <br />
            {data.sdk_hint} Servers can still be configured here; their tools become
            available once the SDK is present.
          </div>
        </div>
      )}

      {draft && (
        <Panel subtitle="NEW" title="Add an MCP server">
          <div className="form-grid">
            <label>
              Name
              <input
                value={draft.name}
                placeholder="filesystem"
                onChange={(e) => setDraft({ ...draft, name: e.target.value.toLowerCase() })}
              />
              <small className="muted">
                Lowercase. Tools appear as <code>{draft.name || "name"}.tool</code>.
              </small>
            </label>

            <label>
              Transport
              <select
                value={draft.transport}
                onChange={(e) =>
                  setDraft({ ...draft, transport: e.target.value as "stdio" | "http" })
                }
              >
                <option value="stdio">stdio (local process)</option>
                <option value="http">http (remote endpoint)</option>
              </select>
            </label>

            {draft.transport === "stdio" ? (
              <label className="span-2">
                Command
                <input
                  value={draft.command}
                  placeholder="npx -y @modelcontextprotocol/server-filesystem /home/me/docs"
                  onChange={(e) => setDraft({ ...draft, command: e.target.value })}
                />
              </label>
            ) : (
              <label className="span-2">
                URL
                <input
                  value={draft.url}
                  placeholder="https://example.com/mcp"
                  onChange={(e) => setDraft({ ...draft, url: e.target.value })}
                />
              </label>
            )}

            <label>
              Risk level
              <select value={draft.risk} onChange={(e) => setDraft({ ...draft, risk: e.target.value })}>
                <option value="low">low — run freely</option>
                <option value="medium">medium</option>
                <option value="high">high</option>
                <option value="destructive">destructive</option>
              </select>
              <small className="muted">Applied to every tool this server provides.</small>
            </label>

            <label className="span-2">
              Description
              <input
                value={draft.description}
                placeholder="What this server is for"
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              />
            </label>
          </div>

          <div className="toggle-label">
            <Toggle
              checked={draft.requires_confirmation ?? true}
              onChange={(v) => setDraft({ ...draft, requires_confirmation: v })}
              label="Require approval before each call"
            />
          </div>

          <div className="row-actions">
            <button className="primary" disabled={busy === "new"} onClick={create}>
              {busy === "new" ? "Connecting…" : "Add and connect"}
            </button>
            <button className="ghost" onClick={() => setDraft(null)}>
              Cancel
            </button>
          </div>
        </Panel>
      )}

      {data && data.servers.length === 0 && !draft && (
        <EmptyBlock
          icon={Plug}
          title="No MCP servers configured"
          hint="Connect a Model Context Protocol server to give ORION tools it does not ship with — filesystems, issue trackers, databases, or your own."
        />
      )}

      {data?.servers.map((server, idx) => (
        <Panel
          key={server.id}
          delay={Math.min(idx, 6) * 0.05}
          interactive
          subtitle={server.transport.toUpperCase()}
          title={server.name}
          right={
            <div className="row-actions">
              <Badge tone={statusTone(server.status)}>{server.status}</Badge>
              <Badge tone={riskTone(server.risk)}>{server.risk}</Badge>
              <Badge tone="info">{server.tool_count} tools</Badge>
            </div>
          }
        >
          {server.description && <p className="muted">{server.description}</p>}

          <div className="kv">
            <div>
              <span>{server.transport === "http" ? "Endpoint" : "Command"}</span>
              <strong className="mono">{server.url || server.command}</strong>
            </div>
            <div>
              <span>Last connected</span>
              <strong>{server.last_connected_at ? timeAgo(server.last_connected_at) : "never"}</strong>
            </div>
            <div>
              <span>Approval</span>
              <strong>{server.requires_confirmation ? "required per call" : "not required"}</strong>
            </div>
          </div>

          {server.last_error && (
            <div className="notice err">
              <div>
                <strong>Connection failed.</strong>
                <br />
                <span className="mono small">{server.last_error}</span>
              </div>
            </div>
          )}

          {server.tools.length > 0 && (
            <>
              <button
                className="ghost"
                onClick={() => setExpanded(expanded === server.id ? null : server.id)}
              >
                <Wrench size={13} />
                {expanded === server.id ? "Hide" : "Show"} {server.tools.length} tools
              </button>
              <AnimatePresence initial={false}>
                {expanded === server.id && (
                  <motion.ul
                    className="mcp-tools"
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}
                    style={{ overflow: "hidden" }}
                  >
                    {server.tools.map((tool, i) => (
                      <motion.li
                        key={tool.name}
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: Math.min(i, 10) * 0.03 }}
                      >
                        <code>
                          {server.name}.{tool.name}
                        </code>
                        <span className="muted">{tool.description || "No description provided"}</span>
                      </motion.li>
                    ))}
                  </motion.ul>
                )}
              </AnimatePresence>
            </>
          )}

          <div className="row-actions">
            <Toggle
              checked={server.enabled}
              onChange={(enabled) =>
                run(
                  server.id,
                  () => api.updateMcpServer(server.id, { enabled }),
                  enabled ? "Server enabled" : "Server disabled",
                )
              }
              label="Enabled"
            />
            <button
              className="ghost"
              disabled={busy === server.id}
              onClick={() =>
                run(server.id, () => api.refreshMcpServer(server.id), "Reconnected")
              }
            >
              <RefreshCw size={13} /> {busy === server.id ? "Connecting…" : "Reconnect"}
            </button>
            <button
              className="ghost danger"
              disabled={busy === server.id}
              onClick={() => {
                if (!confirm(`Remove "${server.name}" and all of its tools?`)) return;
                void run(server.id, () => api.deleteMcpServer(server.id), "Server removed");
              }}
            >
              <Trash2 size={13} /> Remove
            </button>
          </div>
        </Panel>
      ))}

      <Toast toast={toast} />
    </div>
  );
}
