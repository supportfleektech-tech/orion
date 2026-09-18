const RAW = (import.meta.env.VITE_API_URL ?? "").trim();
export const API_BASE = RAW.replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

const get = <T>(p: string) => request<T>(p);
const post = <T>(p: string, body?: unknown) =>
  request<T>(p, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const patch = <T>(p: string, body: unknown) => request<T>(p, { method: "PATCH", body: JSON.stringify(body) });
const del = <T>(p: string) => request<T>(p, { method: "DELETE" });

/* ----------------------------------------------------------------- types */
export interface ChatResponse {
  conversation_id: string;
  run_id: string;
  result: string;
  provider: string;
  model: string;
  degraded: boolean;
  duration_ms: number;
  trace: TraceEntry[];
  memories: MemoryItem[];
  knowledge: KnowledgeHit[];
}
export interface TraceEntry {
  step: number;
  provider?: string;
  model?: string;
  latency_ms?: number;
  text?: string;
  tool?: string;
  tool_calls?: string[];
  arguments?: Record<string, unknown>;
  result_ok?: boolean;
}
export interface MemoryItem {
  id: string;
  kind: string;
  key: string | null;
  content: string;
  source: string;
  confidence: number;
  pinned: boolean;
  score: number;
  created_at: string | null;
}
export interface KnowledgeHit {
  id: string;
  document_id: string;
  name: string | null;
  chunk_index: number;
  content: string;
  score: number;
}
export interface DocumentItem {
  id: string;
  name: string;
  path: string;
  mime_type: string | null;
  size_bytes: number;
  chunks: number;
  created_at: string | null;
}
export interface Tool {
  name: string;
  description: string;
  risk: "low" | "medium" | "high" | "destructive";
  category: string;
  tags: string[];
  enabled: boolean;
  requires_confirmation: boolean;
  allowed: boolean;
  policy_reason: string;
  parameters: Record<string, unknown>;
}
export interface SystemStatus {
  version: string;
  environment: string;
  uptime_seconds: number;
  degraded: boolean;
  providers: {
    local: { configured: boolean; reachable: boolean; model: string; error?: string };
    cloud: { configured: boolean; reachable: boolean; model: string; error?: string };
  };
  counts: Record<string, number>;
  tools: { total: number; enabled: number };
  router_stats: Record<string, unknown>;
  kill_switch: { enabled: boolean; reason: string };
  flags: Record<string, boolean>;
  models: { local: string; cloud: string };
}
export interface Metrics {
  agent_runs_recent: number;
  agent_success_rate: number;
  avg_run_ms: number;
  tool_success_rate: number;
  router: Record<string, number | string | null>;
  timeline: { id: string; task: string; state: string; provider: string; model: string; duration_ms: number; created_at: string }[];
}
export interface ConversationSummary {
  id: string;
  title: string;
  pinned: boolean;
  updated_at: string;
  message_count: number;
}
export interface ChatMessage {
  id?: number;
  role: string;
  content: string;
  provider?: string | null;
  model?: string | null;
  created_at?: string | null;
  pending?: boolean;
}
export interface ApprovalItem {
  id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  reason: string;
  status: string;
  created_at: string;
}
export interface AutomationItem {
  id: string;
  name: string;
  prompt: string;
  schedule_seconds: number;
  enabled: boolean;
  last_run_at: string | null;
  last_status: string | null;
  last_result: string;
}
export interface AuditItem {
  id: number;
  event_type: string;
  actor: string;
  summary: string;
  details: Record<string, unknown>;
  created_at: string;
}
export interface ToolRunItem {
  id: string;
  tool_name: string;
  status: string;
  risk: string;
  duration_ms: number;
  error: string | null;
  arguments: Record<string, unknown>;
  created_at: string;
}
export interface RunItem {
  id: string;
  task: string;
  state: string;
  provider: string;
  model: string;
  duration_ms: number;
  result: string;
  created_at: string;
}
export interface AppSettings {
  local_only: boolean;
  cloud_escalation_enabled: boolean;
  enable_web_search: boolean;
  allow_shell_tool: boolean;
  allow_browser_tool: boolean;
  allow_network_tool: boolean;
  ollama_model: string;
  openrouter_model: string;
  max_tool_loops: number;
  auth_enabled: boolean;
  environment: string;
}

/* -------------------------------------------------------------- endpoints */
export const api = {
  status: () => get<SystemStatus>("/v1/system/status"),
  metrics: () => get<Metrics>("/v1/system/metrics"),

  chat: (message: string, conversationId?: string, mode = "auto") =>
    post<ChatResponse>("/v1/chat", { message, conversation_id: conversationId, mode }),
  conversations: () => get<{ conversations: ConversationSummary[] }>("/v1/conversations"),
  conversation: (id: string) => get<{ id: string; title: string; messages: ChatMessage[] }>(`/v1/conversations/${id}`),
  deleteConversation: (id: string) => del<{ deleted: boolean }>(`/v1/conversations/${id}`),

  memories: (kind?: string) => get<{ memories: MemoryItem[] }>(`/v1/memory${kind ? `?kind=${kind}` : ""}`),
  searchMemory: (q: string) => get<{ results: MemoryItem[] }>(`/v1/memory/search?q=${encodeURIComponent(q)}`),
  addMemory: (body: { content: string; kind: string; key?: string; confidence: number }) =>
    post<{ id: string }>("/v1/memory", body),
  pinMemory: (id: string, pinned: boolean) => post<unknown>(`/v1/memory/${id}/pin?pinned=${pinned}`),
  deleteMemory: (id: string) => del<unknown>(`/v1/memory/${id}`),

  documents: () => get<{ documents: DocumentItem[] }>("/v1/knowledge/documents"),
  ingestText: (name: string, content: string) => post<unknown>("/v1/knowledge/ingest-text", { name, content }),
  ingestPath: (path: string) => post<unknown>("/v1/knowledge/ingest", { path }),
  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ document_id: string; chunks: number }>("/v1/knowledge/upload", { method: "POST", body: form });
  },
  searchKnowledge: (q: string) => get<{ results: KnowledgeHit[] }>(`/v1/knowledge/search?q=${encodeURIComponent(q)}`),
  deleteDocument: (id: string) => del<unknown>(`/v1/knowledge/documents/${id}`),

  tools: () => get<{ tools: Tool[] }>("/v1/tools"),
  runTool: (name: string, args: Record<string, unknown>, autoApprove = false) =>
    post<{ ok: boolean; result?: unknown; error?: string; approval_required?: boolean; approval_id?: string }>(
      "/v1/tools/run",
      { name, arguments: args, auto_approve: autoApprove },
    ),
  toggleTool: (name: string, enabled: boolean) => post<unknown>(`/v1/tools/${name}/toggle`, { enabled }),
  toolRuns: () => get<{ runs: ToolRunItem[] }>("/v1/tools/runs"),

  approvals: (status = "pending") => get<{ approvals: ApprovalItem[] }>(`/v1/approvals?status_filter=${status}`),
  resolveApproval: (id: string, approve: boolean) =>
    post<{ id: string; status: string; result: unknown }>(`/v1/approvals/${id}`, { approve, execute: true }),

  automations: () => get<{ automations: AutomationItem[] }>("/v1/automations"),
  createAutomation: (body: { name: string; prompt: string; schedule_seconds: number; enabled: boolean }) =>
    post<{ id: string }>("/v1/automations", body),
  runAutomation: (id: string) => post<{ result: string }>(`/v1/automations/${id}/run`),
  deleteAutomation: (id: string) => del<unknown>(`/v1/automations/${id}`),

  runs: () => get<{ runs: RunItem[] }>("/v1/runs"),
  run: (id: string) => get<{ id: string; task: string; trace: TraceEntry[]; result: string }>(`/v1/runs/${id}`),
  audit: () => get<{ events: AuditItem[] }>("/v1/audit"),

  settings: () => get<AppSettings>("/v1/settings"),
  updateSettings: (body: Partial<AppSettings>) => patch<AppSettings>("/v1/settings", body),
  killSwitch: (enabled: boolean, reason = "") =>
    post<{ enabled: boolean; reason: string }>("/v1/security/kill-switch", { enabled, reason }),
};
