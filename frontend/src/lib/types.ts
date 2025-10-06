export type Role = "user" | "assistant" | "system" | "agent";

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  createdAt: string;
  streaming?: boolean;
  proposedActions?: ProposedAction[];
  reasoning?: string | null;
  answer?: string | null;
  citations?: string[];
  traceId?: string | null;
  model?: string | null;
}

export type ActionStatus = "proposed" | "approved" | "dismissed" | "executing" | "done" | "error";

export type ActionKind = "crawl" | "index" | "add_seed" | "extract" | "summarize" | "queue";

export interface ProposedAction {
  id: string;
  kind: ActionKind;
  title: string;
  description?: string;
  payload: Record<string, unknown>;
  status: ActionStatus;
  metadata?: Record<string, unknown>;
}

export interface SelectionActionPayload {
  selection: string;
  url: string;
  context?: string;
  boundingRect?: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
}

export interface AgentLogEntry {
  id: string;
  timestamp: string;
  label: string;
  detail?: string;
  status?: "info" | "success" | "warning" | "error";
  meta?: Record<string, unknown>;
}

export interface JobStatusStats {
  pagesFetched: number;
  normalizedDocs: number;
  docsIndexed: number;
  skipped: number;
  deduped: number;
  embedded: number;
}

export interface JobStatusSummary {
  jobId: string;
  state: "idle" | "queued" | "running" | "done" | "error";
  phase: string;
  progress: number;
  etaSeconds?: number;
  stats: JobStatusStats;
  error?: string;
  message?: string;
  description?: string;
  lastUpdated: string;
  stepsTotal?: number;
  stepsCompleted?: number;
  retries?: number;
  url?: string;
}

export interface CrawlQueueItem {
  id: string;
  url: string;
  scope: CrawlScope;
  notes?: string;
  directory?: string;
  editable?: boolean;
  entrypoints?: string[];
  createdAt?: string;
  updatedAt?: string;
  extras?: Record<string, unknown>;
}

export type CrawlScope = "page" | "domain" | "allowed-list" | "custom";

export interface SeedRecord {
  id: string;
  directory: string;
  entrypoints: string[];
  url: string | null;
  scope: CrawlScope;
  notes?: string | null;
  editable: boolean;
  created_at?: string;
  updated_at?: string;
  extras?: Record<string, unknown>;
}

export interface SeedRegistryResponse {
  revision: string;
  seeds: SeedRecord[];
}

export interface ModelStatus {
  model: string;
  installed?: boolean;
  available?: boolean;
  isPrimary?: boolean;
  kind: "chat" | "embedding";
  role?: "primary" | "fallback" | "embedding" | "extra";
}

export interface ConfiguredModels {
  primary: string | null;
  fallback: string | null;
  embedder: string | null;
}

export interface LlmModelsResponse {
  chat_models: string[];
  configured: {
    primary: string | null;
    fallback: string | null;
  };
  embedder: string | null;
  ollama_host: string;
  reachable?: boolean;
  error?: string;
  available?: string[] | null;
}

export interface LlmHealth {
  reachable: boolean;
  model_count: number;
  duration_ms: number;
  host?: string;
}

export interface OllamaStatus {
  installed: boolean;
  running: boolean;
  host: string;
}

export interface ChatResponsePayload {
  reasoning: string;
  answer: string;
  citations: string[];
  model?: string | null;
  trace_id?: string | null;
}

export interface PageExtractResponse {
  url: string;
  title?: string | null;
  text: string;
  lang?: string | null;
  screenshot_b64?: string | null;
  metadata?: Record<string, unknown>;
}

export type SearchResponseStatus = "ok" | "focused_crawl_running" | "warming" | string;

export interface SearchHit {
  id: string;
  title: string;
  url: string;
  snippet: string;
  score?: number | null;
  blendedScore?: number | null;
  lang?: string | null;
}

export interface SearchIndexResponse {
  status: SearchResponseStatus;
  hits: SearchHit[];
  llmUsed: boolean;
  jobId?: string;
  lastIndexTime?: number;
  confidence?: number;
  triggerReason?: string;
  seedCount?: number;
  detail?: string;
  error?: string;
  code?: string;
  action?: string;
  candidates?: Array<Record<string, unknown>>;
  embedderStatus?: Record<string, unknown>;
}

export interface JobLogEvent {
  type: "log" | "status" | "error";
  message?: string;
  state?: string;
  progress?: number;
  timestamp: string;
}

export interface ShadowStatus {
  url: string;
  state: "idle" | "queued" | "running" | "done" | "error";
  jobId?: string;
  job_id?: string;
  title?: string | null;
  chunks?: number | null;
  error?: string | null;
  error_kind?: string | null;
  updatedAt?: number;
  updated_at?: number;
  phase?: string | null;
  statusMessage?: string | null;
  pendingEmbedding?: boolean;
}

export interface ShadowConfig {
  enabled: boolean;
  queued?: number;
  running?: number;
  lastUrl?: string | null;
  lastState?: string | null;
  updatedAt?: number | null;
  lastUpdatedAt?: number | null;
}

export interface DiscoveryPreview {
  id: string;
  path: string;
  name: string;
  ext: string;
  size: number;
  mtime: number;
  createdAt: number;
  preview: string;
}

export interface DiscoveryItem extends DiscoveryPreview {
  text: string;
}

export interface PendingDocument {
  docId: string;
  url?: string | null;
  title?: string | null;
  retryCount: number;
  lastError?: string | null;
  updatedAt?: number | null;
}
