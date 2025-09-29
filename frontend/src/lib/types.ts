export type Role = "user" | "assistant" | "system" | "agent";

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  createdAt: string;
  streaming?: boolean;
  proposedActions?: ProposedAction[];
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

export interface JobStatusSummary {
  jobId: string;
  state: "idle" | "queued" | "running" | "done" | "error";
  progress: number;
  etaSeconds?: number;
  error?: string;
  description?: string;
  lastUpdated: string;
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
  available: string[];
  configured: ConfiguredModels;
  ollama_host: string;
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

export interface ChatStreamChunk {
  type: "token" | "done" | "error" | "action";
  content?: string;
  action?: ProposedAction;
  total_duration?: number;
  load_duration?: number;
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
