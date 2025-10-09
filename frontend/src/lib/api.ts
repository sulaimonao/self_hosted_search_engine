const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");

function api(path: string) {
  if (!API_BASE) return path;
  return `${API_BASE}${path}`;
}

import type {
  ChatMessage,
  ChatResponsePayload,
  CrawlScope,
  SeedRecord,
  SeedRegistryResponse,
  JobStatusSummary,
  JobStatusStats,
  ModelStatus,
  OllamaStatus,
  SelectionActionPayload,
  SearchHit,
  SearchIndexResponse,
  LlmModelsResponse,
  ConfiguredModels,
  LlmHealth,
  PageExtractResponse,
  ShadowConfig,
  ShadowStatus,
  DiscoveryPreview,
  DiscoveryItem,
  PendingDocument,
  ShadowPolicy,
  ShadowPolicyResponse,
  ShadowSnapshotResponse,
} from "@/lib/types";

const JSON_HEADERS = {
  "Content-Type": "application/json",
  Accept: "application/json",
};

export interface MetaTimeResponse {
  server_time: string;
  server_time_utc: string;
  server_timezone: string;
  epoch_ms: number;
}

export async function fetchServerTime(): Promise<MetaTimeResponse> {
  const response = await fetch(api("/api/meta/time"));
  if (!response.ok) {
    throw new Error(`Unable to fetch server time (${response.status})`);
  }
  return response.json();
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

function tryParseJson(text: string): Record<string, unknown> | null {
  if (!text || !text.trim()) {
    return null;
  }
  try {
    const value = JSON.parse(text);
    if (value && typeof value === "object") {
      return value as Record<string, unknown>;
    }
  } catch {
    return null;
  }
  return null;
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

export interface ShadowSnapshotRequest {
  url: string;
  tabId: string;
  sessionId: string;
  policyId?: string | null;
  renderJs?: boolean;
  outlinks?: Array<{ url: string; same_site?: boolean }>;
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
  const phase = typeof payload.phase === "string" ? payload.phase : undefined;
  const statusMessageRaw =
    typeof payload.status_message === "string"
      ? payload.status_message
      : typeof payload.message === "string"
      ? payload.message
      : null;
  const pendingEmbedding = coerceBoolean(payload.pending_embedding ?? false);

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
    phase: phase ?? null,
    statusMessage: statusMessageRaw ?? null,
    pendingEmbedding,
  };
}

function normalizeShadowConfig(payload: Record<string, unknown>): ShadowConfig {
  const enabled = coerceBoolean(payload.enabled);
  const queued = coerceNumber(payload.queued);
  const running = coerceNumber(payload.running);
  const lastUrlRaw =
    typeof payload.last_url === "string"
      ? payload.last_url
      : typeof payload.lastUrl === "string"
      ? payload.lastUrl
      : null;
  const lastStateRaw =
    typeof payload.last_state === "string"
      ? payload.last_state
      : typeof payload.lastState === "string"
      ? payload.lastState
      : null;
  const updatedAt = coerceNumber(payload.updated_at ?? payload.updatedAt);
  const lastUpdatedAt = coerceNumber(payload.last_updated_at ?? payload.lastUpdatedAt);

  return {
    enabled,
    queued: typeof queued === "number" ? queued : undefined,
    running: typeof running === "number" ? running : undefined,
    lastUrl: lastUrlRaw ?? null,
    lastState: lastStateRaw ?? null,
    updatedAt: typeof updatedAt === "number" ? updatedAt : null,
    lastUpdatedAt: typeof lastUpdatedAt === "number" ? lastUpdatedAt : null,
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

export async function fetchShadowConfig(): Promise<ShadowConfig> {
  const response = await fetch(api("/api/shadow"), { cache: "no-store" });
  const text = await response.text();
  if (!response.ok) {
    const payload = tryParseJson(text);
    const message =
      (payload?.error && typeof payload.error === "string" && payload.error.trim())
        ? payload.error.trim()
        : text || `Shadow config fetch failed (${response.status})`;
    throw new Error(message);
  }

  const payload = tryParseJson(text) ?? {};
  return normalizeShadowConfig(payload);
}

function coerceStringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => (typeof item === "string" ? item.trim() : String(item ?? "")))
      .filter((item) => item.length > 0);
  }
  if (typeof value === "string" && value.trim()) {
    return [value.trim()];
  }
  return [];
}

function normalizeShadowPolicy(payload: Record<string, unknown>): ShadowPolicy {
  const rateLimitRaw = (payload.rate_limit ?? payload.rateLimit) as Record<string, unknown> | undefined;
  const concurrency = coerceNumber(rateLimitRaw?.concurrency) ?? 2;
  const delayMs = coerceNumber(rateLimitRaw?.delay_ms ?? rateLimitRaw?.delayMs) ?? 250;
  return {
    policy_id: typeof payload.policy_id === "string" && payload.policy_id.trim().length > 0 ? payload.policy_id.trim() : "global",
    enabled: coerceBoolean(payload.enabled),
    obey_robots: coerceBoolean(payload.obey_robots ?? payload.obeyRobots ?? true),
    include_patterns: coerceStringArray(payload.include_patterns ?? payload.includePatterns),
    exclude_patterns: coerceStringArray(payload.exclude_patterns ?? payload.excludePatterns),
    js_render: coerceBoolean(payload.js_render ?? payload.jsRender ?? false),
    rag: coerceBoolean(payload.rag ?? true),
    training: coerceBoolean(payload.training ?? true),
    ttl_days: coerceNumber(payload.ttl_days ?? payload.ttlDays) ?? 7,
    ttl_seconds: coerceNumber(payload.ttl_seconds ?? payload.ttlSeconds) ?? undefined,
    rate_limit: {
      concurrency: Math.max(1, Math.trunc(concurrency)),
      delay_ms: Math.max(0, Math.trunc(delayMs)),
    },
  };
}

export async function fetchShadowGlobalPolicy(): Promise<ShadowPolicy> {
  const response = await fetch(api("/api/shadow/policy"), { cache: "no-store" });
  const text = await response.text();
  if (!response.ok) {
    const payload = tryParseJson(text);
    throw new Error((payload?.error as string) || text || `Policy request failed (${response.status})`);
  }
  const payload = tryParseJson(text) ?? {};
  const policyRaw = (payload.policy ?? {}) as Record<string, unknown>;
  return normalizeShadowPolicy(policyRaw);
}

export async function updateShadowGlobalPolicy(patch: Partial<ShadowPolicy>): Promise<ShadowPolicy> {
  const response = await fetch(api("/api/shadow/policy"), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(patch),
  });
  const text = await response.text();
  const payload = tryParseJson(text) ?? {};
  if (!response.ok) {
    throw new Error((payload.error as string) || text || `Policy update failed (${response.status})`);
  }
  return normalizeShadowPolicy((payload.policy ?? {}) as Record<string, unknown>);
}

export async function fetchShadowDomainPolicy(domain: string): Promise<ShadowPolicyResponse> {
  const trimmed = domain.trim();
  if (!trimmed) {
    throw new Error("domain is required");
  }
  const response = await fetch(api(`/api/shadow/policy/${encodeURIComponent(trimmed)}`), {
    cache: "no-store",
  });
  const text = await response.text();
  const payload = tryParseJson(text) ?? {};
  if (!response.ok) {
    throw new Error((payload.error as string) || text || `Policy fetch failed (${response.status})`);
  }
  const policy = normalizeShadowPolicy((payload.policy ?? {}) as Record<string, unknown>);
  return {
    policy,
    inherited: coerceBoolean(payload.inherited),
  };
}

export async function updateShadowDomainPolicy(domain: string, patch: Partial<ShadowPolicy>): Promise<ShadowPolicyResponse> {
  const trimmed = domain.trim();
  if (!trimmed) {
    throw new Error("domain is required");
  }
  const response = await fetch(api(`/api/shadow/policy/${encodeURIComponent(trimmed)}`), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(patch),
  });
  const text = await response.text();
  const payload = tryParseJson(text) ?? {};
  if (!response.ok) {
    throw new Error((payload.error as string) || text || `Policy update failed (${response.status})`);
  }
  return {
    policy: normalizeShadowPolicy((payload.policy ?? {}) as Record<string, unknown>),
    inherited: coerceBoolean(payload.inherited),
  };
}

export async function listShadowDomainPolicies(): Promise<Record<string, ShadowPolicy>> {
  const response = await fetch(api("/api/shadow/policy/domains"), { cache: "no-store" });
  const text = await response.text();
  const payload = tryParseJson(text) ?? {};
  if (!response.ok) {
    throw new Error((payload.error as string) || text || `Policy list failed (${response.status})`);
  }
  const result: Record<string, ShadowPolicy> = {};
  const policies = payload.policies as Record<string, unknown> | undefined;
  if (policies) {
    for (const [key, value] of Object.entries(policies)) {
      if (value && typeof value === "object") {
        result[key] = normalizeShadowPolicy(value as Record<string, unknown>);
      }
    }
  }
  return result;
}

export async function requestShadowSnapshot(request: ShadowSnapshotRequest): Promise<ShadowSnapshotResponse> {
  const body: Record<string, unknown> = {
    url: request.url,
    tab_id: request.tabId,
    session_id: request.sessionId,
  };
  if (request.policyId) {
    body.policy_id = request.policyId;
  }
  if (typeof request.renderJs === "boolean") {
    body.render_js = request.renderJs;
  }
  if (Array.isArray(request.outlinks) && request.outlinks.length > 0) {
    body.outlinks = request.outlinks.map((item) => ({
      url: item.url,
      same_site: Boolean(item.same_site),
    }));
  }

  const response = await fetch(api("/api/shadow/snapshot"), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });

  const text = await response.text();
  const payload = tryParseJson(text) ?? {};
  if (!response.ok) {
    throw new Error((payload.error as string) || text || `Snapshot failed (${response.status})`);
  }
  const artifacts = Array.isArray(payload.artifacts) ? (payload.artifacts as Record<string, unknown>[]) : [];
  const normalizedArtifacts = artifacts.map((artifact) => ({
    kind: typeof artifact.kind === "string" ? artifact.kind : "artifact",
    path: typeof artifact.path === "string" ? artifact.path : null,
    bytes: coerceNumber(artifact.bytes) ?? 0,
    mime: typeof artifact.mime === "string" ? artifact.mime : null,
    download_url: typeof artifact.download_url === "string" ? artifact.download_url : null,
    local_path: typeof artifact.local_path === "string" ? artifact.local_path : null,
  }));

  return {
    ok: coerceBoolean(payload.ok ?? true),
    policy: normalizeShadowPolicy((payload.policy ?? {}) as Record<string, unknown>),
    document: {
      id: String((payload.document ?? {}).id ?? ""),
      url: String((payload.document ?? {}).url ?? request.url),
      canonical_url: String((payload.document ?? {}).canonical_url ?? request.url),
      domain: String((payload.document ?? {}).domain ?? ""),
      observed_at: String((payload.document ?? {}).observed_at ?? new Date().toISOString()),
    },
    artifacts: normalizedArtifacts,
    rag_indexed: coerceBoolean(payload.rag_indexed),
    pending_embedding: coerceBoolean(payload.pending_embedding),
    token_count: coerceNumber(payload.token_count) ?? undefined,
    bytes: coerceNumber(payload.bytes) ?? undefined,
    training_record:
      payload.training_record && typeof payload.training_record === "object"
        ? {
            path: String((payload.training_record as Record<string, unknown>).path ?? ""),
          }
        : null,
    rag_error: typeof payload.rag_error === "string" ? payload.rag_error : undefined,
  };
}

export async function updateShadowConfig(input: { enabled: boolean }): Promise<ShadowConfig> {
  const response = await fetch(api("/api/shadow"), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ enabled: Boolean(input.enabled) }),
  });

  const text = await response.text();
  const payload = tryParseJson(text) ?? {};

  if (!response.ok) {
    const message =
      (payload.error && typeof payload.error === "string" && payload.error.trim())
        ? payload.error.trim()
        : text || `Shadow config update failed (${response.status})`;
    throw new Error(message);
  }

  return normalizeShadowConfig(payload);
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
  clientTimezone?: string | null;
  serverTime?: string | null;
  serverTimezone?: string | null;
  serverUtc?: string | null;
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
      client_timezone: options.clientTimezone ?? undefined,
      server_time: options.serverTime ?? undefined,
      server_timezone: options.serverTimezone ?? undefined,
      server_time_utc: options.serverUtc ?? undefined,
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
  query?: string | Record<string, unknown>;
  seedIds?: string[];
  useLlm?: boolean;
  force?: boolean;
  model?: string | null;
  budget?: number;
  depth?: number;
}

export interface RefreshResponse {
  jobId: string | null;
  status: string | null;
  created: boolean;
  deduplicated: boolean;
  raw: Record<string, unknown>;
}

function coercePositiveInteger(value: unknown): number | undefined {
  if (typeof value !== "number" && typeof value !== "string") {
    return undefined;
  }
  const parsed = typeof value === "number" ? value : Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) {
    return undefined;
  }
  const normalized = Math.max(0, Math.floor(parsed));
  return normalized > 0 ? normalized : undefined;
}

export async function triggerRefresh(
  options: RefreshOptions = {},
): Promise<RefreshResponse> {
  const body: Record<string, unknown> = {};

  const seedIds = Array.isArray(options.seedIds)
    ? options.seedIds
        .map((id) => (typeof id === "string" ? id.trim() : String(id || "").trim()))
        .filter((id) => id.length > 0)
    : [];

  let queryPayload: unknown;
  if (typeof options.query === "string") {
    const trimmed = options.query.trim();
    if (trimmed.length > 0) {
      queryPayload = trimmed;
    }
  } else if (options.query && typeof options.query === "object") {
    queryPayload = options.query;
  }

  if (queryPayload === undefined && seedIds.length > 0) {
    queryPayload = { seed_ids: seedIds };
  }

  if (queryPayload !== undefined) {
    body.query = queryPayload;
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
  const budget = coercePositiveInteger(options.budget);
  if (typeof budget === "number") {
    body.budget = budget;
  }
  const depth = coercePositiveInteger(options.depth);
  if (typeof depth === "number") {
    body.depth = depth;
  }

  const response = await fetch(api("/api/refresh"), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });

  const text = await response.text();

  if (!response.ok) {
    const parsed = tryParseJson(text);
    const message =
      parsed && typeof parsed.error === "string" && parsed.error.trim().length > 0
        ? parsed.error.trim()
        : text || `Refresh request failed (${response.status})`;
    throw new Error(message);
  }

  let payload = tryParseJson(text) ?? {};
  if (response.status === 202) {
    payload = {
      status: "queued",
      seed_ids: seedIds.length > 0 ? seedIds : undefined,
      ...payload,
    };
  }
  const jobIdRaw = payload.job_id ?? (payload as { jobId?: unknown }).jobId;
  const jobId = typeof jobIdRaw === "string" && jobIdRaw.trim().length > 0 ? jobIdRaw.trim() : null;
  const statusValue = payload.status ?? (payload as { state?: unknown }).state;
  const status = typeof statusValue === "string" && statusValue.trim().length > 0 ? statusValue.trim() : null;
  const createdValue = payload.created;
  const created = typeof createdValue === "boolean" ? createdValue : Boolean(createdValue);
  const dedupValue = payload.deduplicated;
  const deduplicated = typeof dedupValue === "boolean" ? dedupValue : Boolean(dedupValue);

  return {
    jobId,
    status,
    created,
    deduplicated,
    raw: payload,
  };
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
  job_id?: string;
  state?: string;
  phase?: string;
  progress?: number;
  eta_seconds?: number;
  steps_total?: number;
  steps_completed?: number;
  retries?: number;
  url?: string;
  stats?: {
    pages_fetched?: number;
    normalized_docs?: number;
    docs_indexed?: number;
    skipped?: number;
    deduped?: number;
    embedded?: number;
  };
  started_at?: number;
  updated_at?: number;
  logs_tail?: string[];
  error?: string;
  message?: string;
  result?: unknown;
}

export async function fetchJobStatus(jobId: string): Promise<JobStatusPayload> {
  const response = await fetch(api(`/api/jobs/${jobId}/status`));
  if (!response.ok) {
    throw new Error(`Unable to fetch job status (${response.status})`);
  }
  return response.json();
}

export async function fetchJobProgress(jobId: string): Promise<JobStatusPayload> {
  const response = await fetch(api(`/api/jobs/${jobId}/progress`));
  if (!response.ok) {
    throw new Error(`Unable to fetch job progress (${response.status})`);
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
        handlers.onStatus(normalizeJobStatus(jobId, payload));
        const logs = payload.logs_tail ?? [];
        for (const line of logs) {
          if (!previousLogs.has(line)) {
            previousLogs.add(line);
            handlers.onLog?.(line);
          }
        }
        const state = typeof payload.state === "string" ? payload.state.toLowerCase() : "unknown";
        if (state === "done" || state === "error") {
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

function normalizeJobStatus(jobId: string, payload: JobStatusPayload): JobStatusSummary {
  const rawState = typeof payload.state === "string" ? payload.state.toLowerCase() : "unknown";
  const state: JobStatusSummary["state"] =
    rawState === "queued"
      ? "queued"
      : rawState === "running"
      ? "running"
      : rawState === "done"
      ? "done"
      : rawState === "error"
      ? "error"
      : "running";
  const statsPayload = payload.stats ?? {};
  const stats: JobStatusStats = {
    pagesFetched: Number(statsPayload.pages_fetched ?? 0) || 0,
    normalizedDocs: Number(statsPayload.normalized_docs ?? 0) || 0,
    docsIndexed: Number(statsPayload.docs_indexed ?? 0) || 0,
    skipped: Number(statsPayload.skipped ?? 0) || 0,
    deduped: Number(statsPayload.deduped ?? 0) || 0,
    embedded: Number(statsPayload.embedded ?? 0) || 0,
  };
  const stepsTotal = Number(payload.steps_total ?? 0) || 0;
  const stepsCompleted = Number(payload.steps_completed ?? 0) || 0;
  const progressFraction =
    stepsTotal > 0
      ? Math.max(0, Math.min(1, stepsCompleted / stepsTotal))
      : typeof payload.progress === "number" && Number.isFinite(payload.progress)
      ? payload.progress
      : undefined;
  const progress =
    progressFraction !== undefined
      ? Math.max(0, Math.min(100, Math.round(progressFraction * 100)))
      : state === "done" || state === "error"
      ? 100
      : state === "running"
      ? 65
      : state === "queued"
      ? 15
      : 0;
  const url = typeof payload.url === "string" && payload.url.trim().length > 0 ? payload.url.trim() : undefined;
  const updatedAtSeconds = typeof payload.updated_at === "number" ? payload.updated_at : undefined;
  const lastUpdated = updatedAtSeconds
    ? new Date(updatedAtSeconds * 1000).toISOString()
    : new Date().toISOString();
  return {
    jobId,
    state,
    phase: typeof payload.phase === "string" && payload.phase.trim() ? payload.phase : state,
    progress,
    etaSeconds: typeof payload.eta_seconds === "number" && Number.isFinite(payload.eta_seconds) ? Math.max(0, payload.eta_seconds) : undefined,
    stats,
    error: typeof payload.error === "string" ? payload.error : undefined,
    message: typeof payload.message === "string" ? payload.message : undefined,
    description: url ?? `Job ${jobId}`,
    lastUpdated,
    stepsTotal: stepsTotal || undefined,
    stepsCompleted: stepsCompleted || undefined,
    retries: Number(payload.retries ?? 0) || 0,
    url,
  };
}

export async function fetchPendingDocuments(): Promise<PendingDocument[]> {
  const response = await fetch(api("/api/docs/pending"));
  if (!response.ok) {
    throw new Error(`Unable to fetch pending documents (${response.status})`);
  }
  const payload = (await response.json()) as Record<string, unknown>;
  const items = Array.isArray((payload.items as unknown[]))
    ? (payload.items as Record<string, unknown>[])
    : Array.isArray((payload.pending as unknown[]))
    ? (payload.pending as Record<string, unknown>[])
    : [];
  const docs: PendingDocument[] = [];
  for (const item of items) {
    const docIdRaw = typeof item.doc_id === "string" ? item.doc_id : typeof item.docId === "string" ? item.docId : "";
    if (!docIdRaw) continue;
    docs.push({
      docId: docIdRaw,
      url: typeof item.url === "string" ? item.url : null,
      title: typeof item.title === "string" ? item.title : null,
      retryCount: Number(item.retry_count ?? item.retryCount ?? 0) || 0,
      lastError: typeof item.last_error === "string" ? item.last_error : null,
      updatedAt: coerceNumber(item.updated_at ?? item.updatedAt) ?? null,
    });
  }
  return docs;
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

  const availableSource = Array.isArray(modelsPayload.available)
    ? modelsPayload.available
    : [];
  const available = availableSource.length > 0
    ? availableSource
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
  seed: SeedRecord | null;
  duplicate: boolean;
  message?: string | null;
}

function normalizeSeedUrl(url: string): string {
  const trimmed = url.trim();
  if (!trimmed) return "";
  try {
    const parsed = new URL(trimmed);
    if (!parsed.protocol || (parsed.protocol !== "http:" && parsed.protocol !== "https:")) {
      return trimmed.toLowerCase();
    }
    const pathname = parsed.pathname ? parsed.pathname.replace(/\/+$/, "") : "";
    const search = parsed.search ?? "";
    const host = parsed.host.toLowerCase();
    const composed = `${parsed.protocol}//${host}${pathname}${search}`;
    return composed.replace(/\/+$/, "").toLowerCase();
  } catch {
    return trimmed.toLowerCase();
  }
}

function findSeedForUrl(
  registry: SeedRegistryResponse,
  targetUrl: string,
): SeedRecord | null {
  const normalizedTarget = normalizeSeedUrl(targetUrl);
  if (!normalizedTarget) {
    return null;
  }
  for (const seed of registry.seeds) {
    const url = typeof seed.url === "string" ? seed.url : null;
    if (url && normalizeSeedUrl(url) === normalizedTarget) {
      return seed;
    }
    if (Array.isArray(seed.entrypoints)) {
      for (const entry of seed.entrypoints) {
        if (typeof entry === "string" && normalizeSeedUrl(entry) === normalizedTarget) {
          return seed;
        }
      }
    }
  }
  return null;
}

export async function createDomainSeed(url: string, scope: CrawlScope = "domain"): Promise<SeedEnqueueResult> {
  const normalized = url.trim();
  if (!normalized) {
    throw new Error("URL is required");
  }

  const snapshot = await fetchSeeds();
  const revision = snapshot.revision;

  try {
    const registry = await saveSeed({
      action: "create",
      revision,
      seed: { url: normalized, scope },
    });
    const seed = findSeedForUrl(registry, normalized);
    return {
      registry,
      seed,
      duplicate: false,
    };
  } catch (error) {
    const err = error instanceof Error ? error : new Error(String(error));
    const status = (error as { status?: number }).status;
    if (status === 409) {
      let registry: SeedRegistryResponse | null = null;
      try {
        registry = await fetchSeeds();
      } catch {
        registry = snapshot;
      }
      const seed = registry ? findSeedForUrl(registry, normalized) : null;
      return {
        registry,
        seed,
        duplicate: true,
        message: err.message,
      };
    }
    throw err;
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
