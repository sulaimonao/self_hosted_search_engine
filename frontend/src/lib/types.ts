import type { DirectivePayload } from "@/lib/io/self_heal";
import type { Verb } from "@/autopilot/executor";

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
  message?: string | null;
  citations?: string[];
  traceId?: string | null;
  model?: string | null;
  autopilot?: AutopilotDirective | null;
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
  message: string;
  citations: string[];
  model?: string | null;
  trace_id?: string | null;
  autopilot?: AutopilotDirective | null;
}

export interface DomainSnapshotKpis {
  pages: number;
  edges: number;
  queue: number;
  first_seen: number | null;
  last_seen: number | null;
}

export interface DomainSnapshotPage {
  id: number | null;
  domain_id: number | null;
  url: string | null;
  title?: string | null;
  tokens?: number | null;
  word_count?: number | null;
  text_preview?: string | null;
  headings?: string[];
  meta?: Record<string, unknown>;
  first_seen?: number | null;
  last_seen?: number | null;
  status?: string | null;
  is_sample?: boolean;
}

export interface DomainQueueEntry {
  url: string;
  priority: number;
  attempts: number;
  enqueued_at: number | null;
  status?: string | null;
}

export interface DomainSnapshot {
  host: string;
  found: boolean;
  kpis: DomainSnapshotKpis;
  top_pages: DomainSnapshotPage[];
  key_terms: string[];
  recent: Array<{ url: string; title: string | null; last_seen: number | null; status?: string | null }>;
  queue_entries: DomainQueueEntry[];
}

export interface DomainGraphNode {
  id: number;
  url: string;
  title?: string | null;
  score?: number | null;
  last_seen?: number | null;
}

export interface DomainGraphEdge {
  id: number;
  source: number | null;
  target: number | null;
  url: string;
  host?: string | null;
  weight?: number | null;
  last_seen?: number | null;
}

export interface DomainGraphTimeseriesEntry {
  day: string;
  pages_delta: number;
  edges_delta: number;
  bytes_delta: number;
}

export interface DomainGraphResponse {
  host: string;
  nodes: DomainGraphNode[];
  edges: DomainGraphEdge[];
  timeseries: DomainGraphTimeseriesEntry[];
}

export interface PageSnapshot {
  found: boolean;
  url: string;
  host: string;
  id?: number | null;
  title?: string | null;
  text_preview?: string | null;
  summary?: string | null;
  headings?: string[];
  meta?: Record<string, unknown>;
  word_count?: number | null;
  tokens?: number | null;
  first_seen?: number | null;
  last_seen?: number | null;
}

export interface ChatToolDefinition {
  name: string;
  description?: string | null;
  input_schema?: Record<string, unknown> | null;
}

export type AutopilotMode = "browser" | "tools" | "multi";

export interface AutopilotDirective {
  mode: AutopilotMode;
  query?: string | null;
  reason?: string | null;
  tools?: AutopilotToolDirective[] | null;
  directive?: DirectivePayload | null;
  steps?: Verb[] | null;
}

export interface AutopilotToolDirective {
  label: string;
  endpoint: string;
  method?: "GET" | "POST";
  payload?: Record<string, unknown>;
  description?: string | null;
}

export type ChatStreamEvent =
  | {
      type: "metadata";
      attempt: number;
      model: string | null;
      trace_id: string | null;
    }
  | {
      type: "delta";
      answer?: string | null;
      reasoning?: string | null;
      citations?: string[] | null;
      delta?: string | null;
      autopilot?: AutopilotDirective | null;
    }
  | {
      type: "complete";
      payload: ChatResponsePayload;
    }
  | {
      type: "error";
      error: string;
      hint?: string | null;
      trace_id?: string | null;
    };

export interface PageExtractResponse {
  url: string;
  title?: string | null;
  text: string;
  lang?: string | null;
  screenshot_b64?: string | null;
  metadata?: Record<string, unknown>;
}

export interface DiagnosticsCheckSummary {
  id: string;
  status: string;
  detail?: string | null;
  critical?: boolean;
}

export interface DiagnosticsSummary {
  status: string;
  summary: string;
  traceId?: string | null;
  checks?: DiagnosticsCheckSummary[] | null;
}

export type ChatContext = {
  page?: PageExtractResponse | null;
  diagnostics?: DiagnosticsSummary | null;
  db?: { enabled: boolean } | null;
  tools?: { allowIndexing: boolean } | null;
  domainSnapshot?: DomainSnapshot | null;
  pageSnapshot?: PageSnapshot | null;
};

export function createDefaultChatContext(): ChatContext {
  return {
    page: null,
    diagnostics: null,
    db: { enabled: false },
    tools: { allowIndexing: false },
    domainSnapshot: null,
    pageSnapshot: null,
  };
}

export interface EmbeddingCapabilityStatus {
  model?: string;
  ready?: boolean;
  available?: boolean;
  autopull_started?: boolean;
  last_error?: string | null;
}

export interface CapabilitySnapshot {
  generated_at: string;
  llm: {
    health: boolean;
    list_models: boolean;
    chat: boolean;
    models: string[];
  };
  search: {
    bm25: boolean;
    vector: boolean;
    hybrid: boolean;
    embedding: EmbeddingCapabilityStatus | null;
  };
  shadow: {
    config: boolean;
    toggle: boolean;
  };
  discovery: {
    events_stream: boolean;
  };
  diagnostics: boolean;
  progress_stream: boolean;
}

export interface MetaHealthResponse {
  ok: boolean;
  generated_at?: string;
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
  // Which endpoint produced the results
  source?: "hybrid" | "keyword" | "legacy";
  // Correlation id from the backend (if provided)
  traceId?: string | null;
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

export interface ShadowStatusDoc {
  id: string;
  title: string;
  tokens: number;
}

export interface ShadowStatusError {
  stage: string;
  message: string;
}

export interface ShadowStatusMetrics {
  fetch_ms?: number;
  extract_ms?: number;
  embed_ms?: number;
  index_ms?: number;
}

export interface ShadowStatus {
  jobId: string;
  url?: string | null;
  state: "queued" | "running" | "done" | "error";
  phase: string;
  message?: string | null;
  etaSeconds?: number | null;
  docs: ShadowStatusDoc[];
  errors: ShadowStatusError[];
  metrics?: ShadowStatusMetrics | null;
  updatedAt?: number | null;
  progress?: number | null;
  title?: string | null;
  chunks?: number | null;
  error?: string | null;
  errorKind?: string | null;
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

export interface ShadowRateLimit {
  concurrency: number;
  delay_ms: number;
}

export interface ShadowPolicy {
  policy_id: string;
  enabled: boolean;
  obey_robots: boolean;
  include_patterns: string[];
  exclude_patterns: string[];
  js_render: boolean;
  rag: boolean;
  training: boolean;
  ttl_days: number;
  ttl_seconds?: number;
  rate_limit: ShadowRateLimit;
}

export interface ShadowArtifact {
  kind: string;
  path: string | null;
  bytes: number;
  mime?: string | null;
  download_url?: string | null;
  local_path?: string | null;
}

export interface ShadowSnapshotDocument {
  id: string;
  url: string;
  canonical_url: string;
  domain: string;
  observed_at: string;
}

export interface ShadowSnapshotResponse {
  ok: boolean;
  policy: ShadowPolicy;
  document: ShadowSnapshotDocument;
  artifacts: ShadowArtifact[];
  rag_indexed: boolean;
  pending_embedding: boolean;
  token_count?: number;
  bytes?: number;
  training_record?: { path: string } | null;
  rag_error?: string;
}

export interface ShadowPolicyResponse {
  policy: ShadowPolicy;
  inherited?: boolean;
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

export type SystemCheckStatus = 'pass' | 'fail' | 'warn' | 'timeout' | 'skip' | 'queued' | string;

export interface SystemCheckItem {
  id: string;
  title: string;
  status: SystemCheckStatus;
  detail?: string | null;
  critical?: boolean;
  duration_ms?: number | null;
}

export interface SystemCheckBackend {
  status: SystemCheckStatus;
  checks: SystemCheckItem[];
}

export interface SystemCheckDiagnostics {
  status: SystemCheckStatus;
  job_id: string;
  duration_ms?: number | null;
  detail?: string | null;
  result?: Record<string, unknown> | null;
}

export interface SystemCheckLlm {
  status: SystemCheckStatus;
  reachable?: boolean;
  detail?: string | null;
  critical?: boolean;
  duration_ms?: number | null;
  payload?: Record<string, unknown> | null;
}

export interface SystemCheckSummary {
  critical_failures?: boolean;
  warmup_job_id?: string | null;
}

export interface SystemCheckResponse {
  generated_at?: string;
  backend: SystemCheckBackend;
  diagnostics: SystemCheckDiagnostics;
  llm: SystemCheckLlm;
  summary: SystemCheckSummary;
  // Correlation id from the backend (if provided)
  traceId?: string | null;
}

export type BrowserDiagnosticsStatus = 'pass' | 'fail' | 'warn' | 'timeout' | string;

export interface BrowserDiagnosticsCheck {
  id: string;
  title: string;
  status: BrowserDiagnosticsStatus;
  detail?: string | null;
  critical?: boolean;
  durationMs?: number | null;
}

export interface BrowserDiagnosticsTraceEvent {
  timestamp: string;
  type: string;
  id?: string;
  title?: string;
  status?: BrowserDiagnosticsStatus;
  detail?: string | null;
  durationMs?: number | null;
  outcome?: string;
  context?: Record<string, unknown> | null;
  critical?: boolean;
  expectFailure?: boolean;
  timeoutMs?: number;
  error?: string | null;
  [key: string]: unknown;
}

export interface BrowserDiagnosticsLogEntry {
  timestamp: string;
  level: string;
  message: string;
  data?: Record<string, unknown> | null;
}

export interface BrowserDiagnosticsMetadata {
  electron: string | null;
  chrome: string | null;
  node: string | null;
  platform: string;
  arch: string;
  release: string | null;
  appVersion: string | null;
  [key: string]: unknown;
}

export interface BrowserDiagnosticsReport {
  generatedAt: string;
  timeoutMs: number;
  checks: BrowserDiagnosticsCheck[];
  summary: { status: BrowserDiagnosticsStatus; criticalFailures: boolean };
  durationMs?: number | null;
  trace?: BrowserDiagnosticsTraceEvent[];
  logs?: BrowserDiagnosticsLogEntry[];
  metadata?: BrowserDiagnosticsMetadata;
  artifactPath?: string | null;
}
