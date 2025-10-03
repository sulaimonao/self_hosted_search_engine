const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");

function api(path: string) {
  if (!API_BASE) return path;
  return `${API_BASE}${path}`;
}

import type {
  ChatMessage,
  ChatResponsePayload,
  CrawlScope,
  SeedRegistryResponse,
  JobStatusSummary,
  ModelStatus,
  OllamaStatus,
  SelectionActionPayload,
  SearchHit,
  SearchIndexResponse,
  LlmModelsResponse,
  ConfiguredModels,
  LlmHealth,
  PageExtractResponse,
  ShadowStatus,
  DiscoveryPreview,
  DiscoveryItem,
} from "@/lib/types";

const JSON_HEADERS = {
  "Content-Type": "application/json",
  Accept: "application/json",
};

export interface IndexStats {
  documents: number;
  indexedDocuments?: number | null;
  pending?: number | null;
  lastUpdatedAt?: number | null;
}

export interface SearchIndexOptions {
  signal?: AbortSignal;
  limit?: number;
  useLlm?: boolean;
  model?: string | null;
}

function coerceNumber(input: unknown): number | null {
  if (typeof input === "number" && Number.isFinite(input)) {
    return input;
  }
  if (typeof input === "string") {
    const parsed = Number.parseFloat(input);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function coerceBoolean(input: unknown): boolean {
  if (typeof input === "boolean") return input;
  if (typeof input === "number") return input !== 0;
  if (typeof input === "string") {
    const normalized = input.trim().toLowerCase();
    return normalized === "1" || normalized === "true" || normalized === "yes";
  }
  return false;
}

export async function fetchIndexStats(): Promise<IndexStats> {
  const response = await fetch(api("/api/index/stats"));
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Index stats request failed (${response.status})`);
  }

  const payload = (await response.json()) as Record<string, unknown>;
  const documents =
    coerceNumber(payload.documents) ??
    coerceNumber(payload.indexed_documents) ??
    coerceNumber(payload.indexedDocs) ??
    0;
  const pending =
    coerceNumber(payload.pending) ??
    coerceNumber(payload.pending_documents ?? payload.pendingDocuments) ??
    null;
  const lastUpdated =
    coerceNumber(payload.updated_at ?? payload.updatedAt ?? payload.last_updated ?? payload.lastUpdated) ??
    null;

  return {
    documents,
    indexedDocuments: documents,
    pending,
    lastUpdatedAt: lastUpdated,
  };
}

const SHADOW_STATES = new Set(["idle", "queued", "running", "done", "error"]);

export interface DiscoverySubscription {
  close: () => void;
}

export interface IndexUpsertOptions {
  url?: string | null;
  title?: string | null;
  meta?: Record<string, unknown>;
}

function normalizeShadowStatus(
  payload: Record<string, unknown>,
  fallbackUrl: string,
): ShadowStatus {
  const url = typeof payload.url === "string" && payload.url.trim().length > 0 ? payload.url.trim() : fallbackUrl;
  const rawState = typeof payload.state === "string" ? payload.state.trim().toLowerCase() : "idle";
  const state = SHADOW_STATES.has(rawState) ? (rawState as ShadowStatus["state"]) : "idle";
  const jobIdRaw =
    typeof payload.job_id === "string"
      ? payload.job_id.trim()
      : typeof payload.jobId === "string"
      ? payload.jobId.trim()
      : "";
  const jobId = jobIdRaw.length > 0 ? jobIdRaw : undefined;
  const title = typeof payload.title === "string" ? payload.title : null;
  const chunks = coerceNumber(payload.chunks);
  const error = typeof payload.error === "string" ? payload.error : null;
  const errorKind = typeof payload.error_kind === "string" ? payload.error_kind : null;
  const updatedAt = coerceNumber(payload.updated_at ?? payload.updatedAt) ?? undefined;

  return {
    url,
    state,
    jobId,
    job_id: jobId,
    title,
    chunks: typeof chunks === "number" ? chunks : null,
    error,
    error_kind: errorKind,
    updatedAt,
    updated_at: updatedAt,
  };
}

export async function queueShadowIndex(url: string): Promise<ShadowStatus> {
  const normalized = url.trim();
  if (!normalized) {
    throw new Error("URL is required");
  }

  const response = await fetch(api("/api/shadow/queue"), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ url: normalized }),
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Shadow queue failed (${response.status})`);
  }

  const payload = (await response.json()) as Record<string, unknown>;
  return normalizeShadowStatus(payload, normalized);
}

export async function fetchShadowStatus(url: string): Promise<ShadowStatus> {
  const normalized = url.trim();
  if (!normalized) {
    throw new Error("URL is required");
  }

  const params = new URLSearchParams({ url: normalized });
  const response = await fetch(api(`/api/shadow/status?${params.toString()}`));
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Shadow status failed (${response.status})`);
  }

  const payload = (await response.json()) as Record<string, unknown>;
  return normalizeShadowStatus(payload, normalized);
}

export function subscribeDiscoveryEvents(
  onEvent: (event: DiscoveryPreview) => void,
  onError?: (error: unknown) => void,
): DiscoverySubscription | null {
  if (typeof window === "undefined" || typeof EventSource === "undefined") {
    return null;
  }

  const source = new EventSource(api("/api/discovery/events"));
  source.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data) as DiscoveryPreview;
      if (payload && typeof payload.id === "string") {
        onEvent(payload);
      }
    } catch (error) {
      if (onError) onError(error);
    }
  };
  if (onError) {
    source.onerror = (event) => onError(event);
  }

  return {
    close: () => {
      source.close();
    },
  };
}

export async function fetchDiscoveryItem(id: string): Promise<DiscoveryItem> {
  const trimmed = id.trim();
  if (!trimmed) {
    throw new Error("id is required");
  }

  const response = await fetch(api(`/api/discovery/item/${encodeURIComponent(trimmed)}`));
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Discovery item fetch failed (${response.status})`);
  }

  const payload = (await response.json()) as DiscoveryItem;
  return payload;
}

export async function confirmDiscoveryItem(id: string, action: string = "included"): Promise<void> {
  const trimmed = id.trim();
  if (!trimmed) {
    throw new Error("id is required");
  }

  const response = await fetch(api("/api/discovery/confirm"), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ id: trimmed, action }),
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Discovery confirm failed (${response.status})`);
  }
}

export async function upsertIndexDocument(
  text: string,
  options: IndexUpsertOptions = {},
): Promise<Record<string, unknown>> {
  const trimmed = text.trim();
  if (!trimmed) {
    throw new Error("text is required");
  }

  const body: Record<string, unknown> = { text: trimmed };
  if (options.url) {
    body.url = options.url;
  }
  if (options.title) {
    body.title = options.title;
  }
  if (options.meta) {
    body.meta = options.meta;
  }

  const response = await fetch(api("/api/index/upsert"), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Index upsert failed (${response.status})`);
  }

  const payload = (await response.json()) as Record<string, unknown>;
  return payload;
}

export async function searchIndex(
  query: string,
  options: SearchIndexOptions = {},
): Promise<SearchIndexResponse> {
  const trimmed = query.trim();
  if (!trimmed) {
    throw new Error("Search query is required");
  }

  const params = new URLSearchParams({ q: trimmed });
  if (typeof options.limit === "number" && Number.isFinite(options.limit)) {
    params.set("limit", String(options.limit));
  }
  if (typeof options.useLlm === "boolean") {
    params.set("llm", options.useLlm ? "1" : "0");
  }
  if (options.model) {
    params.set("model", options.model);
  }

  let payload: Record<string, unknown> | null = null;
  let fallbackReason: string | null = null;

  try {
    const response = await fetch(api(`/api/search?${params.toString()}`), {
      signal: options.signal,
    });

    if (response.ok) {
      payload = (await response.json()) as Record<string, unknown>;
    } else {
      const message = await response.text();
      const status = response.status;
      const shouldFallback = status === 404 || status === 405 || status === 500 || status === 501;
      if (shouldFallback) {
        fallbackReason = message || `GET /api/search returned ${status}`;
      } else {
        throw new Error(message || `Search request failed (${status})`);
      }
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    fallbackReason =
      error instanceof Error ? error.message : String(error ?? "GET /api/search unavailable");
  }

  if (!payload) {
    const abortSignal = options.signal;
    if (abortSignal?.aborted) {
      throw new DOMException("The operation was aborted", "AbortError");
    }

    const body: Record<string, unknown> = { query: trimmed };
    if (typeof options.limit === "number" && Number.isFinite(options.limit)) {
      body.limit = options.limit;
    }
    if (typeof options.useLlm === "boolean") {
      body.use_llm = options.useLlm;
      body.llm = options.useLlm;
    }
    if (options.model) {
      body.model = options.model;
    }

    const postResponse = await fetch(api("/api/search"), {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
      signal: abortSignal,
    });

    if (!postResponse.ok) {
      const detail = await postResponse.text();
      const message = detail || fallbackReason;
      throw new Error(message || `Search request failed (${postResponse.status})`);
    }

    payload = (await postResponse.json()) as Record<string, unknown>;
  }

  const rawResults = Array.isArray(payload.results)
    ? payload.results
    : Array.isArray(payload.hits)
    ? payload.hits
    : [];

  const hits: SearchHit[] = [];
  rawResults.forEach((item, index) => {
    if (!item || typeof item !== "object") {
      return;
    }
    const entry = item as Record<string, unknown>;
    const url = typeof entry.url === "string" ? entry.url.trim() : "";
    const titleRaw = typeof entry.title === "string" ? entry.title.trim() : "";
    const snippet = typeof entry.snippet === "string" ? entry.snippet : "";
    const score = coerceNumber(entry.score);
    const blended = coerceNumber(entry.blended_score ?? entry.blendedScore);
    const lang = typeof entry.lang === "string" ? entry.lang : null;
    const identifierCandidate =
      typeof entry.id === "string" && entry.id.trim().length > 0
        ? entry.id.trim()
        : url
        ? `${url}#${index}`
        : `hit-${index}`;

    const title = titleRaw || url || "Untitled";

    hits.push({
      id: identifierCandidate,
      title,
      url,
      snippet,
      score,
      blendedScore: blended,
      lang,
    });
  });

  const status = typeof payload.status === "string" ? payload.status : "ok";
  const jobIdValue =
    typeof payload.job_id === "string"
      ? payload.job_id
      : typeof payload.jobId === "string"
      ? payload.jobId
      : undefined;
  const lastIndexTime = coerceNumber(payload.last_index_time ?? payload.lastIndexTime) ?? undefined;
  const confidence = coerceNumber(payload.confidence) ?? undefined;
  const seedCount = coerceNumber(payload.seed_count ?? payload.seedCount);
  const triggerReason =
    typeof payload.trigger_reason === "string"
      ? payload.trigger_reason
      : typeof payload.triggerReason === "string"
      ? payload.triggerReason
      : undefined;
  const detail = typeof payload.detail === "string" ? payload.detail : undefined;
  const error = typeof payload.error === "string" ? payload.error : undefined;
  const code = typeof payload.code === "string" ? payload.code : undefined;
  const action = typeof payload.action === "string" ? payload.action : undefined;
  const candidates = Array.isArray(payload.candidates)
    ? payload.candidates.filter((candidate): candidate is Record<string, unknown> =>
        candidate !== null && typeof candidate === "object"
      )
    : [];
  const embedderStatus =
    payload.embedder_status && typeof payload.embedder_status === "object"
      ? (payload.embedder_status as Record<string, unknown>)
      : undefined;

  return {
    status,
    hits,
    llmUsed: coerceBoolean(payload.llm_used ?? payload.llmUsed),
    jobId: jobIdValue,
    lastIndexTime,
    confidence,
    triggerReason,
    seedCount: seedCount ?? undefined,
    detail,
    error,
    code,
    action,
    candidates,
    embedderStatus,
  };
}

interface SerializableMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

function serializeMessages(history: ChatMessage[], nextUser: string): SerializableMessage[] {
  const values: SerializableMessage[] = [];
  for (const message of history) {
    if (message.role === "agent") {
      values.push({ role: "system", content: message.content });
      continue;
    }
    if (message.role === "system" || message.role === "assistant" || message.role === "user") {
      values.push({ role: message.role, content: message.content });
    }
  }
  values.push({ role: "user", content: nextUser });
  return values;
}

export class ChatRequestError extends Error {
  status: number;
  traceId: string | null;
  code?: string;
  hint?: string;
  tried?: string[];

  constructor(
    message: string,
    options: {
      status: number;
      traceId: string | null;
      code?: string;
      hint?: string;
      tried?: string[];
    },
  ) {
    super(message);
    this.name = "ChatRequestError";
    this.status = options.status;
    this.traceId = options.traceId;
    this.code = options.code;
    this.hint = options.hint;
    this.tried = options.tried;
  }
}

export interface ChatSendOptions {
  model?: string | null;
  url?: string | null;
  textContext?: string | null;
  imageContext?: string | null;
  signal?: AbortSignal;
}

export interface ChatSendResult {
  payload: ChatResponsePayload;
  traceId: string | null;
  model: string | null;
}

export async function sendChat(
  history: ChatMessage[],
  input: string,
  options: ChatSendOptions = {},
): Promise<ChatSendResult> {
  const response = await fetch(api("/api/chat"), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({
      messages: serializeMessages(history, input),
      model: options.model ?? undefined,
      url: options.url ?? undefined,
      text_context: options.textContext ?? undefined,
      image_context: options.imageContext ?? undefined,
    }),
    signal: options.signal,
  });

  const traceId = response.headers.get("X-Request-Id");
  const servedModel = response.headers.get("X-LLM-Model");

  if (!response.ok) {
    let payload: Record<string, unknown> | null = null;
    try {
      payload = (await response.clone().json()) as Record<string, unknown>;
    } catch (error) {
      payload = null;
    }

    const fallbackText = await response.text();
    let message = fallbackText || `Chat request failed (${response.status})`;
    let code: string | undefined;
    let hint: string | undefined;
    let tried: string[] | undefined;
    if (payload) {
      if (typeof payload.error === "string" && payload.error.trim()) {
        code = payload.error.trim();
      }
      if (typeof payload.hint === "string" && payload.hint.trim()) {
        hint = payload.hint.trim();
        message = hint;
      }
      if (Array.isArray(payload.tried)) {
        tried = payload.tried.filter((item): item is string => typeof item === "string");
      }
      const messageValue = payload["message"];
      const detailValue =
        typeof messageValue === "string"
          ? messageValue
          : (payload["detail"] as unknown);
      const detail = typeof detailValue === "string" ? detailValue : null;
      if (typeof detail === "string" && detail.trim()) {
        message = detail.trim();
      } else if (!hint && typeof payload.error === "string" && payload.error.trim()) {
        message = payload.error.trim();
      }
    }

    throw new ChatRequestError(message, {
      status: response.status,
      traceId,
      code,
      hint,
      tried,
    });
  }

  const data = (await response.json()) as Record<string, unknown>;
  const payload: ChatResponsePayload = {
    reasoning: typeof data.reasoning === "string" ? data.reasoning : "",
    answer: typeof data.answer === "string" ? data.answer : "",
    citations: Array.isArray(data.citations)
      ? data.citations.filter((item): item is string => typeof item === "string")
      : [],
    model: typeof data.model === "string" ? data.model : options.model ?? null,
    trace_id: typeof data.trace_id === "string" ? data.trace_id : traceId ?? null,
  };

  return {
    payload,
    traceId: payload.trace_id ?? traceId,
    model: payload.model ?? servedModel ?? options.model ?? null,
  };
}

export interface CrawlJobRequest {
  url: string;
  scope: CrawlScope;
  maxPages?: number;
  maxDepth?: number;
  notes?: string;
}

export interface CrawlJobResponse {
  jobId?: string;
  status?: string;
  deduplicated?: boolean;
}

export async function startCrawlJob(request: CrawlJobRequest): Promise<CrawlJobResponse> {
  const payload = {
    query: request.url,
    force: true,
    use_llm: false,
    seeds: [request.url],
    budget: request.maxPages ?? 20,
    depth: request.maxDepth ?? 2,
  };
  const response = await fetch(api("/api/refresh"), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const reason = await response.text();
    throw new Error(reason || "Unable to queue crawl job");
  }
  return response.json();
}

export interface RefreshOptions {
  query?: string;
  useLlm?: boolean;
  force?: boolean;
  model?: string | null;
}

export async function triggerRefresh(
  options: RefreshOptions = {},
): Promise<Record<string, unknown> | null> {
  const body: Record<string, unknown> = {};
  if (typeof options.query === "string" && options.query.trim().length > 0) {
    body.query = options.query.trim();
  }
  if (typeof options.useLlm === "boolean") {
    body.use_llm = options.useLlm;
    body.llm = options.useLlm;
  }
  if (typeof options.force === "boolean") {
    body.force = options.force;
  }
  if (typeof options.model === "string" && options.model.trim().length > 0) {
    body.model = options.model.trim();
  }

  const response = await fetch(api("/api/refresh"), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Refresh request failed (${response.status})`);
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return null;
  }
  return (await response.json()) as Record<string, unknown>;
}

export async function reindexUrl(url: string): Promise<unknown> {
  const response = await fetch(api("/api/tools/reindex"), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ batch: [url] }),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export interface JobStatusPayload {
  state: string;
  logs_tail?: string[];
  error?: string;
  result?: unknown;
}

export async function fetchJobStatus(jobId: string): Promise<JobStatusPayload> {
  const response = await fetch(api(`/api/jobs/${jobId}/status`));
  if (!response.ok) {
    throw new Error(`Unable to fetch job status (${response.status})`);
  }
  return response.json();
}

export interface JobSubscriptionHandlers {
  onStatus: (status: JobStatusSummary) => void;
  onLog?: (entry: string) => void;
  onError?: (error: Error) => void;
}

export function subscribeJob(jobId: string, handlers: JobSubscriptionHandlers) {
  let active = true;
  const previousLogs = new Set<string>();

  const poll = async () => {
    while (active) {
      try {
        const payload = await fetchJobStatus(jobId);
        const rawState = typeof payload.state === "string" ? payload.state : "unknown";
        const normalizedState: JobStatusSummary["state"] =
          rawState === "queued"
            ? "queued"
            : rawState === "running"
            ? "running"
            : rawState === "done"
            ? "done"
            : rawState === "error"
            ? "error"
            : "running";
        const progress =
          normalizedState === "done"
            ? 100
            : normalizedState === "running"
            ? 65
            : normalizedState === "queued"
            ? 15
            : normalizedState === "error"
            ? 100
            : 0;
        handlers.onStatus({
          jobId,
          state: normalizedState,
          progress,
          description: `Job ${jobId}`,
          lastUpdated: new Date().toISOString(),
          error: payload.error ?? undefined,
        });
        const logs = payload.logs_tail ?? [];
        for (const line of logs) {
          if (!previousLogs.has(line)) {
            previousLogs.add(line);
            handlers.onLog?.(line);
          }
        }
        if (normalizedState === "done" || normalizedState === "error") {
          break;
        }
      } catch (error) {
        handlers.onError?.(error instanceof Error ? error : new Error(String(error)));
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  };

  poll();

  return () => {
    active = false;
  };
}

export interface ModelInventory {
  status: OllamaStatus;
  models: ModelStatus[];
  chatModels: string[];
  configured: ConfiguredModels;
  embedder: string | null;
  health: LlmHealth;
  reachable: boolean;
}

function normalizeModelName(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export async function fetchModelInventory(): Promise<ModelInventory> {
  const [modelsResponse, healthResponse] = await Promise.all([
    fetch(api("/api/llm/models")),
    fetch(api("/api/llm/health")),
  ]);

  if (!modelsResponse.ok) {
    throw new Error("Unable to retrieve model list");
  }
  if (!healthResponse.ok) {
    throw new Error("Unable to reach Ollama health endpoint");
  }

  const modelsPayload = (await modelsResponse.json()) as LlmModelsResponse;
  const healthPayload = (await healthResponse.json()) as LlmHealth;

  const chatModels = Array.isArray(modelsPayload.chat_models)
    ? modelsPayload.chat_models
        .map((entry) => normalizeModelName(entry))
        .filter((entry): entry is string => typeof entry === "string")
    : [];

  const available = Array.isArray((modelsPayload as Record<string, unknown>).available)
    ? ((modelsPayload as Record<string, unknown>).available as unknown[])
        .map((entry) => normalizeModelName(entry))
        .filter((entry): entry is string => typeof entry === "string")
    : [...chatModels];

  const configuredRaw = modelsPayload.configured ?? ({} as ConfiguredModels);
  const configured: ConfiguredModels = {
    primary: normalizeModelName(configuredRaw.primary) ?? null,
    fallback: normalizeModelName(configuredRaw.fallback) ?? null,
    embedder: normalizeModelName(modelsPayload.embedder) ?? null,
  };

  const status: OllamaStatus = {
    installed: chatModels.length > 0,
    running: !!healthPayload.reachable,
    host: normalizeModelName(modelsPayload.ollama_host) ?? "",
  };

  const candidates = new Set<string>();
  if (configured.primary) candidates.add(configured.primary);
  if (configured.fallback) candidates.add(configured.fallback);
  if (configured.embedder) candidates.add(configured.embedder);
  for (const name of available) {
    candidates.add(name);
  }
  for (const name of chatModels) {
    candidates.add(name);
  }
  if (configured.embedder) {
    candidates.add(configured.embedder);
  }

  const asArray = Array.from(candidates);
  const weight = (model: ModelStatus): number => {
    switch (model.role) {
      case "primary":
        return 0;
      case "fallback":
        return 1;
      case "embedding":
        return 2;
      default:
        return 3;
    }
  };

  const models: ModelStatus[] = asArray
    .map((name) => {
      const isPrimary = configured.primary === name;
      const role: ModelStatus["role"] = isPrimary
        ? "primary"
        : configured.fallback === name
        ? "fallback"
        : configured.embedder === name
        ? "embedding"
        : "extra";
      const installed = available.includes(name) || chatModels.includes(name);
      const isEmbedding = role === "embedding" || name === configured.embedder;
      return {
        model: name,
        kind: isEmbedding ? "embedding" : "chat",
        role,
        isPrimary,
        installed,
        available: installed && !!healthPayload.reachable,
      } satisfies ModelStatus;
    })
    .sort((a, b) => {
      const diff = weight(a) - weight(b);
      if (diff !== 0) return diff;
      return a.model.localeCompare(b.model);
    });

  return {
    status,
    models,
    chatModels,
    configured,
    embedder: configured.embedder,
    health: healthPayload,
    reachable: Boolean(modelsPayload.reachable ?? healthPayload.reachable),
  };
}

export interface AutopullResponse {
  started: boolean;
  model?: string | null;
  reason?: string | null;
  pid?: number;
}

export async function autopullModels(candidates: string[]): Promise<AutopullResponse> {
  if (!Array.isArray(candidates) || candidates.length === 0) {
    throw new Error("At least one candidate model is required");
  }
  const response = await fetch(api("/api/llm/autopull"), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ candidates }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Autopull failed (${response.status})`);
  }
  return response.json();
}

export interface ExtractOptions {
  vision?: boolean;
  signal?: AbortSignal;
}

export async function extractPage(
  url: string,
  options: ExtractOptions = {},
): Promise<PageExtractResponse> {
  if (!url || !url.trim()) {
    throw new Error("URL is required for extraction");
  }
  const params = new URLSearchParams();
  if (options.vision) {
    params.set("vision", "1");
  }
  const query = params.toString();
  const response = await fetch(api(`/api/extract${query ? `?${query}` : ""}`), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ url }),
    signal: options.signal,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Extraction failed (${response.status})`);
  }
  return (await response.json()) as PageExtractResponse;
}

export interface SaveSeedRequest {
  action: "create" | "update" | "delete";
  revision: string;
  seed: {
    id?: string;
    url?: string;
    scope?: CrawlScope;
    notes?: string;
  };
}

export async function fetchSeeds(): Promise<SeedRegistryResponse> {
  const response = await fetch(api("/api/seeds"));
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Unable to fetch seeds (${response.status})`);
  }
  return response.json();
}

export async function saveSeed(request: SaveSeedRequest): Promise<SeedRegistryResponse> {
  const { action, revision, seed } = request;
  let method: "POST" | "PUT" | "DELETE";
  let path = "/api/seeds";
  let body: Record<string, unknown> = { revision };

  if (action === "create") {
    method = "POST";
    if (!seed.url || !seed.scope) {
      throw new Error("Seed url and scope are required to create a seed");
    }
    body = { ...body, url: seed.url, scope: seed.scope, notes: seed.notes ?? undefined, id: seed.id };
  } else if (action === "update") {
    method = "PUT";
    if (!seed.id) {
      throw new Error("Seed id is required to update a seed");
    }
    path = `/api/seeds/${encodeURIComponent(seed.id)}`;
    body = { ...body };
    if (typeof seed.url !== "undefined") {
      body.url = seed.url;
    }
    if (typeof seed.scope !== "undefined") {
      body.scope = seed.scope;
    }
    if (typeof seed.notes !== "undefined") {
      body.notes = seed.notes;
    }
  } else {
    method = "DELETE";
    if (!seed.id) {
      throw new Error("Seed id is required to delete a seed");
    }
    path = `/api/seeds/${encodeURIComponent(seed.id)}`;
    body = { revision };
  }

  const response = await fetch(api(path), {
    method,
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const text = await response.text();
    let message = text || `Seed ${action} failed (${response.status})`;
    let revisionHint: string | undefined;
    try {
      const parsed = text ? (JSON.parse(text) as { error?: string; revision?: string }) : null;
      if (parsed?.error) {
        message = parsed.error;
      }
      if (parsed?.revision) {
        revisionHint = parsed.revision;
      }
    } catch {
      // ignore
    }
    const error = new Error(message) as Error & { status?: number; revision?: string };
    error.status = response.status;
    if (revisionHint) {
      error.revision = revisionHint;
    }
    throw error;
  }

  return response.json();
}

export interface SeedEnqueueResult {
  registry: SeedRegistryResponse | null;
  duplicate: boolean;
  message?: string | null;
}

export async function createDomainSeed(url: string): Promise<SeedEnqueueResult> {
  const normalized = url.trim();
  if (!normalized) {
    throw new Error("URL is required");
  }

  const requestBody = { urls: [normalized], scope: "domain" };
  try {
    const response = await fetch(api("/api/seeds"), {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(requestBody),
    });

    if (response.ok) {
      const contentType = response.headers.get("content-type") ?? "";
      if (contentType.includes("application/json")) {
        const payload = (await response.json()) as Record<string, unknown>;
        if (typeof payload.revision === "string" && Array.isArray(payload.seeds)) {
          return {
            registry: payload as SeedRegistryResponse,
            duplicate: false,
          };
        }
      }
      return { registry: null, duplicate: false };
    }

    const raw = await response.text();
    let message = raw;
    try {
      const parsed = raw ? (JSON.parse(raw) as { error?: string }) : null;
      if (parsed?.error) {
        message = parsed.error;
      }
    } catch {
      // ignore JSON parse errors
    }

    if (response.status === 409) {
      return { registry: null, duplicate: true, message };
    }

    if (response.status === 400 && message.toLowerCase().includes("revision")) {
      const snapshot = await fetchSeeds();
      try {
        const registry = await saveSeed({
          action: "create",
          revision: snapshot.revision,
          seed: { url: normalized, scope: "domain" },
        });
        return { registry, duplicate: false };
      } catch (error) {
        const status = (error as { status?: number }).status;
        if (status === 409) {
          return { registry: null, duplicate: true, message: (error as Error).message };
        }
        throw error;
      }
    }

    throw new Error(message || `Seed request failed (${response.status})`);
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }
    throw new Error(String(error ?? "Unable to queue domain seed"));
  }
}

export interface SelectionResult {
  text: string;
  raw?: unknown;
}

async function requestSelectionResult(
  path: string,
  body: Record<string, unknown>,
  errorMessage: string
): Promise<SelectionResult> {
  const response = await fetch(api(path), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });

  const contentType = response.headers.get("content-type") ?? "";
  let payload: unknown;
  try {
    if (contentType.includes("application/json")) {
      payload = await response.json();
    } else {
      payload = await response.text();
    }
  } catch (error) {
    throw new Error(`${errorMessage}: Unable to parse response`);
  }

  if (!response.ok) {
    const detail = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
    throw new Error(detail || errorMessage);
  }

  if (typeof payload === "string") {
    const trimmed = payload.trim();
    if (!trimmed) {
      throw new Error(`${errorMessage}: Empty response`);
    }
    return { text: trimmed, raw: payload };
  }

  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    const candidate = [
      record.summary,
      record.result,
      record.text,
      record.content,
      record.output,
    ].find((value) => typeof value === "string" && value.trim().length > 0) as string | undefined;
    if (candidate) {
      return { text: candidate.trim(), raw: payload };
    }
    return { text: JSON.stringify(payload, null, 2), raw: payload };
  }

  throw new Error(`${errorMessage}: Unsupported response shape`);
}

export async function summarizeSelection(payload: SelectionActionPayload): Promise<SelectionResult> {
  return requestSelectionResult(
    "/api/research",
    {
      query: payload.selection,
      model: "gpt-oss",
      url: payload.url,
      context: payload.context,
    },
    "Failed to summarize selection"
  );
}

export async function extractSelection(payload: SelectionActionPayload): Promise<SelectionResult> {
  return requestSelectionResult(
    "/api/tools/extract",
    {
      url: payload.url,
      selection: payload.selection,
      context: payload.context,
      boundingRect: payload.boundingRect,
    },
    "Failed to extract selection"
  );
}
