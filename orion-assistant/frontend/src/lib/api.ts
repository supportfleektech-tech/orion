const RAW = (import.meta.env.VITE_API_URL ?? "").trim();
export const API_BASE = RAW.replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(init?.headers ?? {}),
      },
    });
  } catch (cause) {
    // fetch only rejects when the request never reached a server: the backend
    // is down, the port is wrong, or the network is gone. The browser's own
    // "Failed to fetch" is accurate and useless, so say what to actually do.
    throw new Error(
      "Cannot reach the ORION backend. Start it with ./scripts/run-backend.sh, " +
        "or check that it is listening on the expected port.",
      { cause },
    );
  }

  if (res.status === 401 || res.status === 403) {
    throw new Error("Not authorised. Set ORION_AUTH_TOKEN, or disable AUTH_ENABLED for local use.");
  }

  if (res.status >= 500) {
    // A 5xx body is usually a stack trace or empty; neither helps here.
    let detail = "";
    try {
      detail = (await res.json()).detail ?? "";
    } catch {
      /* no JSON body */
    }
    throw new Error(detail || `The backend failed with HTTP ${res.status}. Check its logs.`);
  }

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
const patch_ = <T>(p: string, body: unknown) => request<T>(p, { method: "PATCH", body: JSON.stringify(body) });
const del = <T>(p: string) => request<T>(p, { method: "DELETE" });

/* ----------------------------------------------------------------- types */
export interface ModelTier {
  name: string;
  model: string;
  min_ram_gb: number;
  download_gb: number;
  multimodal: boolean;
  tools: boolean;
  context: string;
  note: string;
  fits: boolean;
}
export interface HardwareReport {
  platform: string;
  cpu_count: number;
  total_ram_gb: number;
  available_ram_gb: number;
  free_disk_gb: number;
  gpu_detected: boolean;
  recommended: ModelTier;
  disk_sufficient: boolean;
  disk_needed_gb: number;
  tiers: ModelTier[];
}
export interface PullState {
  model: string;
  status: string;
  percent: number;
  detail: string;
  error: string | null;
}
export interface ModelStatus {
  ollama_installed: boolean;
  ollama_running: boolean;
  host: string;
  active_model: string;
  active_model_present: boolean;
  embed_model: string;
  embed_model_present: boolean;
  installed_models: { name: string; size?: number }[];
  vision_capable: boolean;
  pulls: Record<string, PullState>;
  hardware: HardwareReport;
}
export interface ProvisionResult {
  ok: boolean;
  model?: string;
  stage?: string;
  message?: string;
  results?: Record<string, PullState | { status: string }>;
}
export interface SkillItem {
  id: string;
  name: string;
  description: string;
  instructions: string;
  trigger_keywords: string[];
  source: string;
  status: string;
  confidence: number;
  uses: number;
  successes: number;
  failures: number;
  success_rate: number | null;
  last_used_at: string | null;
  created_at: string | null;
  relevance?: number;
}
export interface FeedbackStats {
  total: number;
  up: number;
  down: number;
  satisfaction: number | null;
}
export interface ProcessedAttachment {
  name: string;
  media_type: string;
  mime: string | null;
  size_bytes: number;
  handled_as: string;
  note: string | null;
  has_image: boolean;
  text_preview: string | null;
  meta: Record<string, unknown>;
}
export interface FormatSupport {
  supported: boolean;
  extensions: string[];
  how: string;
}
export interface AttachmentCapabilities {
  active_model: string;
  max_upload_mb: number;
  formats: Record<string, FormatSupport>;
}

export interface VoiceBackend {
  available: boolean;
  engine: string;
  error: string | null;
  voice?: string;
  voices?: string[];
  language?: string;
  speed?: number;
  model?: string;
}
export interface VoiceStatus {
  tts: VoiceBackend;
  stt: VoiceBackend;
  voice_commands_enabled: boolean;
  wake_word: string;
}
export interface VoiceCommand {
  action: "navigate" | "toggle" | "tool" | "chat" | "ui" | "none";
  target: string | null;
  value: unknown;
  confidence: number;
  confirm: boolean;
  transcript: string;
  say: string | null;
  params: Record<string, unknown>;
}
export interface VoiceCatalog {
  enabled: boolean;
  wake_word: string;
  require_wake_word: boolean;
  catalog: { category: string; examples: string[] }[];
  routes: string[];
  toggles: string[];
}
export interface TranscriptResult {
  text: string;
  language: string | null;
  duration_s: number;
  segments: { start: number; end: number; text: string }[] | null;
  command?: VoiceCommand;
}

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
/** A single file: the shape returned when `path` points at one document. */
export interface IngestedDocument {
  document_id: string;
  name: string;
  chunks: number;
  status: "ingested" | "unchanged" | string;
}

/** A directory ingest returns a batch summary instead. */
export interface IngestBatch {
  status: "batch";
  count: number;
  results: IngestedDocument[];
}

export type IngestResult = IngestedDocument | IngestBatch;

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
  router: {
    calls: number;
    local_calls: number;
    cloud_calls: number;
    failures: number;
    degraded_calls: number;
    total_latency_ms: number;
    last_error: string | null;
  };
  timeline: { id: string; task: string; state: string; provider: string; model: string; duration_ms: number; created_at: string }[];
}
export interface ConversationSummary {
  id: string;
  title: string;
  pinned: boolean;
  archived?: boolean;
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
  /** True while tokens are still arriving for this bubble. */
  streaming?: boolean;
  /** The agent run behind this answer, so feedback can be attributed to it. */
  run_id?: string;
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
export interface StreamHandlers {
  onContext?: (ctx: { memories: MemoryItem[]; knowledge: KnowledgeHit[] }) => void;
  onTrace?: (entry: TraceEntry) => void;
  onToolStart?: (info: { tool: string; arguments: Record<string, unknown> }) => void;
  onToolResult?: (info: { tool: string; result_ok: boolean; error?: string }) => void;
  onStatus?: (info: { stage: string; step?: number }) => void;
  onToken?: (text: string, step: number) => void;
  onMessage?: (content: string, alreadyStreamed: boolean) => void;
  onDone?: (info: { run_id: string; provider: string; model: string; degraded: boolean; duration_ms: number }) => void;
  onError?: (message: string) => void;
}

/**
 * Stream a chat turn over SSE, surfacing tool activity as it happens.
 * Falls back to the caller's error handler if the stream cannot be opened.
 */
export async function chatStream(
  message: string,
  conversationId: string | undefined,
  mode: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<string | undefined> {
  const res = await fetch(`${API_BASE}/v1/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, conversation_id: conversationId, mode }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`Stream failed: ${res.status} ${res.statusText}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let conversation: string | undefined = conversationId;

  const dispatch = (event: string, data: string) => {
    let payload: any = {};
    try {
      payload = JSON.parse(data);
    } catch {
      return;
    }
    switch (event) {
      case "start":
        conversation = payload.conversation_id;
        break;
      case "context":
        handlers.onContext?.(payload);
        break;
      case "status":
        handlers.onStatus?.(payload);
        break;
      case "trace":
        handlers.onTrace?.(payload);
        break;
      case "tool_start":
        handlers.onToolStart?.(payload);
        break;
      case "tool_result":
        handlers.onToolResult?.(payload);
        break;
      case "token":
        handlers.onToken?.(payload.text ?? "", payload.step ?? 0);
        break;
      case "message":
        handlers.onMessage?.(payload.content ?? "", Boolean(payload.already_streamed));
        break;
      case "done":
        handlers.onDone?.(payload);
        break;
      case "error":
        handlers.onError?.(payload.message ?? "Unknown streaming error");
        break;
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let split: number;
    while ((split = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      let event = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7).trim();
        else if (line.startsWith("data: ")) data = line.slice(6);
      }
      if (data) dispatch(event, data);
    }
  }
  return conversation;
}

export interface ConnectorInfo {
  id: string;
  name: string;
  category: string;
  summary: string;
  status: "connected" | "unreachable" | "not_configured" | "disabled";
  detail: string;
  endpoint: string | null;
  required: boolean;
  docs: string | null;
  env_keys: string[] | null;
}

export interface ConnectorStatus {
  connectors: ConnectorInfo[];
  connected: number;
  total: number;
  local_only: boolean;
}

export interface EvalSuiteSummary {
  name: string;
  description: string;
  path: string;
  case_count: number;
  error: string | null;
}

export interface EvalStatus {
  directory: string;
  exists: boolean;
  suites: EvalSuiteSummary[];
  model: string;
}

export interface EvalCheck {
  kind: string;
  expected: unknown;
  passed: boolean;
  detail: string;
}

export interface EvalCase {
  id: string;
  task: string;
  passed: boolean;
  answer: string;
  checks: EvalCheck[];
  tools_used: string[];
  duration_ms: number;
  provider: string;
  model: string;
  degraded: boolean;
  error: string | null;
}

export interface EvalRun {
  suite: string;
  description: string;
  total: number;
  passed: number;
  failed: number;
  pass_rate: number;
  duration_ms: number;
  degraded: boolean;
  model: string;
  ran_at: string;
  cases: EvalCase[];
}

export interface EvalHistoryEntry {
  suite: string;
  ran_at: string;
  total: number;
  passed: number;
  failed: number;
  pass_rate: number;
  duration_ms: number;
  model: string;
  degraded: boolean;
  failures: string[];
}

export interface McpTool {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

export interface McpServerInfo {
  id: string;
  name: string;
  description: string;
  transport: "stdio" | "http";
  command: string;
  url: string;
  env_keys: string[];
  enabled: boolean;
  risk: "low" | "medium" | "high" | "destructive";
  requires_confirmation: boolean;
  tools: McpTool[];
  tool_count: number;
  status: "unknown" | "ok" | "error" | "disabled";
  last_error: string | null;
  last_connected_at: string | null;
  created_at: string;
}

export interface McpServerList {
  servers: McpServerInfo[];
  sdk_available: boolean;
  sdk_hint: string | null;
}

export interface McpServerInput {
  name: string;
  description?: string;
  transport: "stdio" | "http";
  command?: string;
  url?: string;
  env?: Record<string, string>;
  enabled?: boolean;
  risk?: string;
  requires_confirmation?: boolean;
}

export const api = {
  status: () => get<SystemStatus>("/v1/system/status"),
  metrics: () => get<Metrics>("/v1/system/metrics"),

  chat: (message: string, conversationId?: string, mode = "auto") =>
    post<ChatResponse>("/v1/chat", { message, conversation_id: conversationId, mode }),
  conversations: () => get<{ conversations: ConversationSummary[] }>("/v1/conversations"),
  conversation: (id: string) => get<{ id: string; title: string; messages: ChatMessage[] }>(`/v1/conversations/${id}`),
  deleteConversation: (id: string) => del<{ deleted: boolean }>(`/v1/conversations/${id}`),
  updateConversation: (
    id: string,
    patch: { title?: string; pinned?: boolean; archived?: boolean; persona?: string; system_prompt?: string },
  ) =>
    patch_<ConversationSummary>(`/v1/conversations/${id}`, patch),

  memories: (kind?: string) => get<{ memories: MemoryItem[] }>(`/v1/memory${kind ? `?kind=${kind}` : ""}`),
  searchMemory: (q: string) => get<{ results: MemoryItem[] }>(`/v1/memory/search?q=${encodeURIComponent(q)}`),
  addMemory: (body: { content: string; kind: string; key?: string; confidence: number }) =>
    post<{ id: string }>("/v1/memory", body),
  pinMemory: (id: string, pinned: boolean) => post<unknown>(`/v1/memory/${id}/pin?pinned=${pinned}`),
  deleteMemory: (id: string) => del<unknown>(`/v1/memory/${id}`),

  documents: () => get<{ documents: DocumentItem[] }>("/v1/knowledge/documents"),
  ingestText: (name: string, content: string) => post<unknown>("/v1/knowledge/ingest-text", { name, content }),
  ingestPath: (path: string) => post<IngestResult>("/v1/knowledge/ingest", { path }),
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

  // ---- models
  modelStatus: () => get<ModelStatus>("/v1/models/status"),
  modelCatalog: () => get<{ recommended: ModelTier; tiers: ModelTier[] }>("/v1/models/catalog"),
  provisionModel: (model?: string) => post<ProvisionResult>("/v1/models/provision", { model }),

  // ---- skills
  skills: (status?: string) =>
    get<{ skills: SkillItem[] }>(`/v1/skills${status ? `?status=${status}` : ""}`),
  createSkill: (body: {
    name: string;
    description: string;
    instructions: string;
    trigger_keywords?: string[];
  }) => post<SkillItem>("/v1/skills", body),
  setSkillStatus: (id: string, status: string) => patch_<SkillItem>(`/v1/skills/${id}`, { status }),
  deleteSkill: (id: string) => del<unknown>(`/v1/skills/${id}`),
  relevantSkills: (q: string) =>
    get<{ skills: SkillItem[] }>(`/v1/skills/relevant?q=${encodeURIComponent(q)}`),

  // ---- feedback
  sendFeedback: (body: { rating: "up" | "down"; run_id?: string; comment?: string }) =>
    post<unknown>("/v1/feedback", body),
  feedbackStats: () => get<FeedbackStats>("/v1/feedback/stats"),

  // ---- attachments
  /** Show how a file will be read before it is sent. */
  inspectAttachment: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ProcessedAttachment>("/v1/attachments/inspect", { method: "POST", body: form });
  },

  attachmentCapabilities: () => get<AttachmentCapabilities>("/v1/attachments/capabilities"),
  chatWithFiles: (body: {
    message: string;
    conversationId?: string | null;
    mode?: string;
    files: File[];
  }) => {
    const form = new FormData();
    form.append("message", body.message);
    if (body.conversationId) form.append("conversation_id", body.conversationId);
    form.append("mode", body.mode ?? "auto");
    body.files.forEach((file) => form.append("files", file));
    return request<ChatResponse & { attachments: ProcessedAttachment[] }>("/v1/chat/upload", {
      method: "POST",
      body: form,
    });
  },

  // ---- voice
  voiceStatus: () => get<VoiceStatus>("/v1/voice/status"),
  voiceCatalog: () => get<VoiceCatalog>("/v1/voice/commands"),
  interpretVoice: (transcript: string) =>
    post<VoiceCommand>("/v1/voice/interpret", { transcript }),
  transcribe: (blob: Blob, interpret = true) => {
    const form = new FormData();
    form.append("file", blob, "clip.webm");
    form.append("interpret", String(interpret));
    return request<TranscriptResult>("/v1/voice/transcribe", { method: "POST", body: form });
  },
  /** Returns WAV audio, or throws with the backend's reason if TTS is down. */
  speak: async (text: string, voice?: string): Promise<Blob> => {
    const response = await fetch(`${API_BASE}/v1/voice/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice }),
    });
    if (!response.ok) {
      let detail = `Speech failed (${response.status})`;
      try {
        detail = (await response.json()).detail ?? detail;
      } catch {
        /* keep the status-code message */
      }
      throw new Error(detail);
    }
    return response.blob();
  },

  connectors: () => get<ConnectorStatus>("/v1/connectors"),

  evaluations: () => get<EvalStatus>("/v1/evaluations"),
  evaluationHistory: () => get<{ runs: EvalHistoryEntry[] }>("/v1/evaluations/history"),
  runEvaluation: (name: string) => post<EvalRun>(`/v1/evaluations/${name}/run`, {}),

  mcpServers: () => get<McpServerList>("/v1/mcp/servers"),
  createMcpServer: (body: McpServerInput) => post<McpServerInfo>("/v1/mcp/servers", body),
  updateMcpServer: (id: string, body: Partial<McpServerInput>) =>
    patch_<McpServerInfo>(`/v1/mcp/servers/${id}`, body),
  deleteMcpServer: (id: string) => del<{ deleted: boolean; tools_removed: number }>(`/v1/mcp/servers/${id}`),
  refreshMcpServer: (id: string) => post<McpServerInfo>(`/v1/mcp/servers/${id}/refresh`, {}),
  refreshMcp: () => post<{ servers: unknown[]; sdk_available: boolean }>("/v1/mcp/refresh", {}),

  personas: () => get<{ personas: { id: string; label: string; description: string }[] }>("/v1/personas"),

  settings: () => get<AppSettings>("/v1/settings"),
  updateSettings: (body: Partial<AppSettings>) => patch_<AppSettings>("/v1/settings", body),
  killSwitch: (enabled: boolean, reason = "") =>
    post<{ enabled: boolean; reason: string }>("/v1/security/kill-switch", { enabled, reason }),
};
