const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");

export function api(path: string) {
  if (!API_BASE) return path;
  return `${API_BASE}${path}`;
}

import type {
  ChatMessage,
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
  ChatStreamEvent,
  ShadowConfig,
  ShadowStatus,
  ShadowStatusDoc,
  ShadowStatusError,
  DiscoveryPreview,
  DiscoveryItem,
  PendingDocument,
  ShadowPolicy,
  ShadowPolicyResponse,
  ShadowSnapshotResponse,
  SystemCheckResponse,
  CapabilitySnapshot,
  MetaHealthResponse,
} from "@/lib/types";

import { chatClient, type ChatPayloadMessage, type ChatSendRequest, type ChatSendResult } from "@/lib/chatClient";
import { isClient } from "@/lib/is-client";

export { ChatClient, ChatRequestError, chatClient, type ChatSendResult, type ChatSendRequest } from "@/lib/chatClient";

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
  const endpoints = ["/api/meta/time", "/api/meta/server_time"];
  let lastError: Error | null = null;

  for (const endpoint of endpoints) {
    try {
      const response = await fetch(api(endpoint));
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || `Unable to fetch server time (${response.status})`);
      }
      return (await response.json()) as MetaTimeResponse;
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
    }
  }

  throw lastError ?? new Error("Unable to fetch server time");
}

export async function getHealth(): Promise<MetaHealthResponse> {
  const response = await fetch(api("/api/meta/health"));
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Health check failed (${response.status})`);
  }
  return (await response.json()) as MetaHealthResponse;
}

export async function getCapabilities(): Promise<CapabilitySnapshot> {
  const response = await fetch(api("/api/meta/capabilities"), {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Capabilities fetch failed (${response.status})`);
  }
  return (await response.json()) as CapabilitySnapshot;
}

export async function runSystemCheck(): Promise<SystemCheckResponse> {
  const response = await fetch(api("/api/system_check"), {
    method: "POST",
    headers: JSON_HEADERS,
    body: "{}",
  });
  if (!response.ok) {
    throw new Error(`System check failed (${response.status})`);
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

const SHADOW_STATES = new Set(['queued', 'running', 'done', 'error']);

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
  fallback: { url?: string; jobId?: string } = {},
): ShadowStatus {
  const fallbackUrl = typeof fallback.url === 'string' ? fallback.url : '';
  const fallbackJobId = typeof fallback.jobId === 'string' ? fallback.jobId : '';
  const urlRaw =
    typeof payload.url === 'string' && payload.url.trim().length > 0
      ? payload.url.trim()
      : fallbackUrl;
  const jobIdRaw =
    typeof payload.jobId === 'string' && payload.jobId.trim().length > 0
      ? payload.jobId.trim()
      : typeof payload.job_id === 'string' && payload.job_id.trim().length > 0
      ? payload.job_id.trim()
      : fallbackJobId;
  if (!jobIdRaw) {
    throw new Error('shadow status missing jobId');
  }
  const phaseRaw = typeof payload.phase === 'string' ? payload.phase.trim() : '';
  const phase = phaseRaw || 'queued';
  const stateRaw = typeof payload.state === 'string' ? payload.state.trim().toLowerCase() : '';
  const state: ShadowStatus['state'] = (() => {
    if (SHADOW_STATES.has(stateRaw)) {
      return stateRaw as ShadowStatus['state'];
    }
    if (phase === 'queued') return 'queued';
    if (phase === 'done' || phase === 'indexed') return 'done';
    if (phase === 'error' || phase === 'failed') return 'error';
    return 'running';
  })();
  let message: string | null = null;
  const details = payload.details;
  if (typeof details === 'string' && details.trim().length > 0) {
    message = details.trim();
  } else if (details && typeof details === 'object') {
    const candidate = (details as Record<string, unknown>).message;
    if (typeof candidate === 'string' && candidate.trim().length > 0) {
      message = candidate.trim();
    }
  }
  if (!message) {
    const messageRaw =
      typeof payload.message === 'string'
        ? payload.message
        : typeof payload.status_message === 'string'
        ? payload.status_message
        : null;
    if (messageRaw && messageRaw.trim().length > 0) {
      message = messageRaw.trim();
    }
  }
  let progressFraction: number | null = null;
  const progressValue =
    typeof payload.progress === 'number'
      ? payload.progress
      : details && typeof details === 'object' && typeof (details as Record<string, unknown>).progress === 'number'
      ? ((details as Record<string, unknown>).progress as number)
      : null;
  if (typeof progressValue === 'number') {
    progressFraction = progressValue > 1 ? Math.min(1, progressValue / 100) : Math.max(0, progressValue);
  }
  const eta = coerceNumber(payload.eta ?? payload.eta_seconds ?? payload.etaSeconds);
  const updatedAt = coerceNumber(payload.updated_at ?? payload.updatedAt) ?? null;
  const docsSource = Array.isArray(payload.docs) ? (payload.docs as Record<string, unknown>[]) : [];
  const docs = docsSource
    .map((doc, index) => {
      const id = typeof doc.id === 'string' && doc.id.trim().length > 0 ? doc.id.trim() : `${jobIdRaw}-doc-${index}`;
      const title =
        typeof doc.title === 'string' && doc.title.trim().length > 0
          ? doc.title.trim()
          : typeof doc.name === 'string' && doc.name.trim().length > 0
          ? doc.name.trim()
          : typeof doc.url === 'string' && doc.url.trim().length > 0
          ? doc.url.trim()
          : 'Captured document';
      const tokens = coerceNumber(doc.tokens ?? doc.length ?? doc.size) ?? 0;
      return { id, title, tokens } as ShadowStatusDoc;
    })
    .filter(Boolean);
  const errorsSource = Array.isArray(payload.errors) ? (payload.errors as Record<string, unknown>[]) : [];
  const errors = errorsSource
    .map((item) => {
      const stage = typeof item.stage === 'string' && item.stage.trim().length > 0 ? item.stage.trim() : phase;
      const text = typeof item.message === 'string' && item.message.trim().length > 0 ? item.message.trim() : stage;
      return { stage, message: text } as ShadowStatusError;
    })
    .filter(Boolean);
  if (errors.length === 0) {
    const fallbackError =
      typeof payload.error === 'string'
        ? payload.error
        : typeof payload.error_message === 'string'
        ? payload.error_message
        : null;
    if (fallbackError && fallbackError.trim()) {
      errors.push({ stage: phase, message: fallbackError.trim() });
    }
  }
  const metricsRaw =
    payload.metrics && typeof payload.metrics === 'object'
      ? (payload.metrics as Record<string, unknown>)
      : undefined;
  const metrics = metricsRaw
    ? {
        fetch_ms: coerceNumber(metricsRaw.fetch_ms ?? metricsRaw.fetchMs) ?? undefined,
        extract_ms: coerceNumber(metricsRaw.extract_ms ?? metricsRaw.extractMs) ?? undefined,
        embed_ms: coerceNumber(metricsRaw.embed_ms ?? metricsRaw.embedMs) ?? undefined,
        index_ms: coerceNumber(metricsRaw.index_ms ?? metricsRaw.indexMs) ?? undefined,
      }
    : null;
  const title =
    typeof payload.title === 'string' && payload.title.trim().length > 0
      ? payload.title.trim()
      : docs.length > 0
      ? docs[0].title
      : urlRaw || null;
  const chunks = coerceNumber(payload.chunks) ?? (docs.length > 0 ? docs.length : null);
  const errorKind =
    typeof payload.errorKind === 'string' && payload.errorKind.trim().length > 0
      ? payload.errorKind.trim()
      : typeof payload.error_kind === 'string' && payload.error_kind.trim().length > 0
      ? payload.error_kind.trim()
      : null;
  const errorText =
    typeof payload.error === 'string' && payload.error.trim().length > 0
      ? payload.error.trim()
      : errors.length > 0
      ? errors[0].message
      : null;
  const pendingEmbedding = coerceBoolean(payload.pending_embedding ?? payload.pendingEmbedding ?? false);
  return {
    jobId: jobIdRaw,
    url: urlRaw || undefined,
    state,
    phase,
    message,
    etaSeconds: typeof eta === 'number' ? eta : null,
    docs,
    errors,
    metrics,
    updatedAt,
    progress: progressFraction,
    title,
    chunks,
    error: errorText,
    errorKind,
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

export interface ShadowQueueOptions {
  tabId?: number | null;
  reason?: string;
}

export async function queueShadowIndex(url: string, options: ShadowQueueOptions = {}): Promise<ShadowStatus> {
  const normalized = url.trim();
  if (!normalized) {
    throw new Error('URL is required');
  }
  const body: Record<string, unknown> = { url: normalized };
  if (typeof options.tabId === 'number') {
    body.tabId = options.tabId;
  }
  if (typeof options.reason === 'string' && options.reason.trim().length > 0) {
    body.reason = options.reason.trim();
  }

  const response = await fetch(api('/api/shadow/crawl'), {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Shadow crawl failed (${response.status})`);
  }

  const payload = (await response.json()) as Record<string, unknown>;
  const jobIdValue =
    typeof payload.jobId === 'string' && payload.jobId.trim().length > 0
      ? payload.jobId.trim()
      : typeof payload.job_id === 'string' && payload.job_id.trim().length > 0
      ? payload.job_id.trim()
      : undefined;
  return normalizeShadowStatus(
    { ...payload, jobId: jobIdValue ?? payload.jobId ?? payload.job_id, url: payload.url ?? normalized },
    { url: normalized, jobId: jobIdValue },
  );
}

export async function fetchShadowStatus(jobId: string): Promise<ShadowStatus> {
  const trimmed = jobId.trim();
  if (!trimmed) {
    throw new Error('jobId is required');
  }

  const params = new URLSearchParams({ jobId: trimmed });
  const response = await fetch(api(`/api/shadow/status?${params.toString()}`));
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Shadow status failed (${response.status})`);
  }

  const payload = (await response.json()) as Record<string, unknown>;
  return normalizeShadowStatus(payload, { jobId: trimmed });
}

export async function fetchShadowConfig(): Promise<ShadowConfig> {
  const response = await fetch(api("/api/shadow/shadow_config"), { cache: "no-store" });
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
  const documentPayload = (payload.document ?? {}) as Record<string, unknown>;
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
      id: String(documentPayload.id ?? ""),
      url: String(documentPayload.url ?? request.url),
      canonical_url: String(documentPayload.canonical_url ?? request.url),
      domain: String(documentPayload.domain ?? ""),
      observed_at: String(documentPayload.observed_at ?? new Date().toISOString()),
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
  const response = await fetch(api("/api/shadow/toggle"), {
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
  if (!isClient() || typeof EventSource === "undefined") {
    return null;
  }

  const endpoint = api("/api/discovery/stream_events");
  const fallbackEndpoint = api("/api/discovery/events");
  const buildSource = (url: string) => new EventSource(url);
  let source: EventSource | null = null;

  try {
    source = buildSource(endpoint);
  } catch {
    try {
      source = buildSource(fallbackEndpoint);
    } catch (error) {
      if (onError) onError(error);
      return null;
    }
  }

  if (!source) {
    return null;
  }
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
    source.onerror = (event) => {
      source?.close();
      if (source?.url !== fallbackEndpoint) {
        try {
          source = buildSource(fallbackEndpoint);
          source.onmessage = (evt) => {
            try {
              const payload = JSON.parse(evt.data) as DiscoveryPreview;
              if (payload && typeof payload.id === "string") {
                onEvent(payload);
              }
            } catch (error) {
              onError?.(error);
            }
          };
          source.onerror = (err) => onError(err);
          return;
        } catch (err) {
          onError(err);
        }
      } else {
        onError(event);
      }
    };
  }

  return {
    close: () => {
      source?.close();
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

  const body: Record<string, unknown> = { query: trimmed };
  const legacyParams = new URLSearchParams({ q: trimmed });
  if (typeof options.limit === "number" && Number.isFinite(options.limit)) {
    body.limit = options.limit;
    legacyParams.set("limit", String(options.limit));
  }
  if (typeof options.useLlm === "boolean") {
    body.use_llm = options.useLlm;
    body.llm = options.useLlm;
    legacyParams.set("llm", options.useLlm ? "1" : "0");
  }
  if (options.model) {
    body.model = options.model;
    legacyParams.set("model", options.model);
  }

  const abortSignal = options.signal;
  const attemptHybrid = async () => {
    try {
      const response = await fetch(api("/api/index/hybrid_search"), {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify(body),
        signal: abortSignal,
      });
      if (!response.ok) {
        if (![404, 405, 500, 501].includes(response.status)) {
          const detail = await response.text();
          throw new Error(detail || `Hybrid search failed (${response.status})`);
        }
        return { payload: null, reason: await response.text() } as const;
      }
      const payload = (await response.json()) as Record<string, unknown>;
      return { payload, reason: null } as const;
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw error;
      }
      return { payload: null, reason: error instanceof Error ? error.message : String(error) } as const;
    }
  };

  const hybridResult = await attemptHybrid();
  if (hybridResult.payload && !abortSignal?.aborted) {
    const fallbackFlag = Boolean(
      typeof hybridResult.payload["keyword_fallback"] === "boolean"
        ? hybridResult.payload["keyword_fallback"]
        : typeof hybridResult.payload["keywordFallback"] === "boolean"
        ? hybridResult.payload["keywordFallback"]
        : false,
    );
    return normalizeSearchPayload(hybridResult.payload, fallbackFlag);
  }

  if (abortSignal?.aborted) {
    throw new DOMException("The operation was aborted", "AbortError");
  }

  const fallbackEndpoints = ["/api/index/search", "/api/search"] as const;
  let lastError: Error | null = hybridResult.reason
    ? new Error(hybridResult.reason)
    : null;

  for (const endpoint of fallbackEndpoints) {
    try {
      const response = await fetch(api(endpoint), {
        method: endpoint === "/api/index/search" ? "POST" : "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify(body),
        signal: abortSignal,
      });
      if (!response.ok) {
        const detail = await response.text();
        lastError = new Error(detail || `Search request failed (${response.status})`);
        continue;
      }
      const payload = (await response.json()) as Record<string, unknown>;
      return normalizeSearchPayload(payload, true);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw error;
      }
      lastError = error instanceof Error ? error : new Error(String(error));
    }
  }

  try {
    const response = await fetch(api(`/api/search?${legacyParams.toString()}`), {
      signal: abortSignal,
    });
    if (response.ok) {
      const payload = (await response.json()) as Record<string, unknown>;
      return normalizeSearchPayload(payload, true);
    }
    const detail = await response.text();
    lastError = new Error(detail || `Search request failed (${response.status})`);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    lastError = error instanceof Error ? error : new Error(String(error));
  }

  throw lastError ?? new Error("Search request failed");
}

function normalizeSearchPayload(
  payload: Record<string, unknown>,
  keywordFallback: boolean = false,
): SearchIndexResponse {
  const candidateLists: unknown[][] = [];
  if (Array.isArray(payload.results)) candidateLists.push(payload.results);
  if (Array.isArray(payload.hits)) candidateLists.push(payload.hits);
  if (Array.isArray(payload.combined)) candidateLists.push(payload.combined);
  if (Array.isArray(payload.vector)) candidateLists.push(payload.vector);
  if (Array.isArray(payload.keyword)) candidateLists.push(payload.keyword);

  let rawResults: unknown[] = [];
  for (const list of candidateLists) {
    if (list.length > 0) {
      rawResults = list;
      break;
    }
  }

  const hits: SearchHit[] = [];
  rawResults.forEach((item, index) => {
    if (!item || typeof item !== "object") {
      return;
    }
    const entry = item as Record<string, unknown>;
    const url = typeof entry.url === "string" ? entry.url.trim() : "";
    const titleRaw = typeof entry.title === "string" ? entry.title.trim() : "";
    const snippet =
      typeof entry.snippet === "string"
        ? entry.snippet
        : typeof entry.chunk === "string"
        ? entry.chunk
        : typeof entry.summary === "string"
        ? entry.summary
        : "";
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

  const status = typeof payload.status === "string"
    ? payload.status
    : keywordFallback
    ? "warming"
    : "ok";
  const jobIdValue =
    typeof payload.job_id === "string"
      ? payload.job_id
      : typeof payload.jobId === "string"
      ? payload.jobId
      : undefined;
  const lastIndexTime = coerceNumber(payload.last_index_time ?? payload.lastIndexTime) ?? undefined;
  const confidence =
    coerceNumber(payload.confidence) ??
    coerceNumber(payload.vector_top_score) ??
    coerceNumber(payload.vectorTopScore) ??
    undefined;
  const seedCount = coerceNumber(payload.seed_count ?? payload.seedCount);
  const triggerReason =
    typeof payload.trigger_reason === "string"
      ? payload.trigger_reason
      : typeof payload.triggerReason === "string"
      ? payload.triggerReason
      : undefined;
  const explicitDetail = typeof payload.detail === "string" ? payload.detail : undefined;
  const detail =
    explicitDetail ??
    (keywordFallback ? "Hybrid search unavailable; showing keyword results." : undefined);
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

type SerializableMessage = Pick<ChatPayloadMessage, "role" | "content">;

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
  stream?: boolean;
  onStreamEvent?: (event: ChatStreamEvent) => void;
}

export async function sendChat(
  history: ChatMessage[],
  input: string,
  options: ChatSendOptions = {},
): Promise<ChatSendResult> {
  const serialized = serializeMessages(history, input);
  const request: ChatSendRequest = {
    messages: serialized,
    model: options.model ?? undefined,
    stream: options.stream,
    url: options.url ?? undefined,
    textContext: options.textContext ?? undefined,
    imageContext: options.imageContext ?? undefined,
    clientTimezone: options.clientTimezone ?? undefined,
    serverTime: options.serverTime ?? undefined,
    serverTimezone: options.serverTimezone ?? undefined,
    serverUtc: options.serverUtc ?? undefined,
    signal: options.signal,
    onEvent: options.onStreamEvent,
  };
  return chatClient.send(request);
}

export interface ChatContextResponse {
  url?: string | null;
  summary?: string | null;
  memories?: unknown[];
  messages?: unknown[];
  selection?: { text: string; word_count: number } | null;
  history?: unknown[];
  metadata?: Record<string, unknown> | null;
  query?: string | null;
}

export async function fetchChatContext(
  threadId: string,
  params: {
    url?: string | null;
    include?: string[];
    selection?: string | null;
    title?: string | null;
    locale?: string | null;
    time?: string | null;
  } = {},
): Promise<ChatContextResponse> {
  const normalizedThread = threadId.trim();
  if (!normalizedThread) {
    throw new Error("threadId is required to fetch chat context");
  }
  const search = new URLSearchParams();
  const includeTokens = params.include ?? [];
  if (includeTokens.length > 0) {
    search.set("include", includeTokens.join(","));
  }
  if (params.url) {
    search.set("url", params.url);
  }
  if (params.selection) {
    search.set("selection", params.selection);
  }
  if (params.title) {
    search.set("title", params.title);
  }
  if (params.locale) {
    search.set("locale", params.locale);
  }
  if (params.time) {
    search.set("time", params.time);
  }
  const endpoint = `/api/chat/${encodeURIComponent(normalizedThread)}/context?${search.toString()}`;
  const response = await fetch(api(endpoint));
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Failed to load chat context (${response.status})`);
  }
  const data = (await response.json()) as ChatContextResponse;
  return data;
}

export async function storeChatMessage(
  threadId: string,
  payload: { id?: string | null; role: string; content: string; tokens?: number | null },
): Promise<void> {
  const normalizedThread = threadId.trim();
  if (!normalizedThread) {
    throw new Error("threadId is required to store chat message");
  }
  const response = await fetch(api(`/api/chat/${encodeURIComponent(normalizedThread)}/message`), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({
      id: payload.id ?? undefined,
      role: payload.role,
      content: payload.content,
      tokens: payload.tokens ?? undefined,
    }),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Unable to persist chat message (${response.status})`);
  }
}

export async function runAutopilotTool(
  endpoint: string,
  options: { method?: string; payload?: Record<string, unknown>; chatId?: string | null; messageId?: string | null } = {},
): Promise<Record<string, unknown>> {
  const trimmed = endpoint.trim();
  if (!trimmed) {
    throw new Error("Tool endpoint is required");
  }
  const method = (options.method ?? "POST").toUpperCase();
  const headers: Record<string, string> = {};
  if (options.chatId) {
    headers["X-Chat-Id"] = options.chatId;
  }
  if (options.messageId) {
    headers["X-Message-Id"] = options.messageId;
  }
  let body: string | undefined;
  if (method !== "GET" && method !== "HEAD") {
    Object.assign(headers, JSON_HEADERS);
    body = JSON.stringify(options.payload ?? {});
  }
  const response = await fetch(api(trimmed), {
    method,
    headers,
    body,
  });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(text || `Tool request failed (${response.status})`);
  }
  try {
    return text ? (JSON.parse(text) as Record<string, unknown>) : {};
  } catch {
    return { ok: true, result: text };
  }
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

export interface AgentTurnResultItem {
  url?: string;
  title?: string;
  snippet?: string;
  score?: number | null;
}

export interface AgentTurnResponse {
  answer: string;
  citations: string[];
  coverage: number;
  actions: unknown[];
  results: AgentTurnResultItem[];
}

export async function runAgentTurn(query: string): Promise<AgentTurnResponse> {
  const trimmed = query.trim();
  if (!trimmed) {
    throw new Error("Query is required for agent turn");
  }
  const response = await fetch(api("/api/tools/agent/turn"), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ query: trimmed }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Agent turn failed (${response.status})`);
  }
  const payload = (await response.json()) as Record<string, unknown>;
  const answer = typeof payload.answer === "string" ? payload.answer : "";
  const citationsRaw = Array.isArray(payload.citations) ? payload.citations : [];
  const citations = citationsRaw
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter((item) => item.length > 0);
  const coverageValue = Number(payload.coverage ?? 0);
  const coverage = Number.isFinite(coverageValue) ? coverageValue : 0;
  const actions = Array.isArray(payload.actions) ? payload.actions : [];
  const resultsRaw = Array.isArray(payload.results) ? payload.results : [];
  const mappedResults: Array<AgentTurnResultItem | undefined> = resultsRaw.map((item) => {
      if (typeof item !== "object" || item === null) {
        return undefined;
      }
      const record = item as Record<string, unknown>;
      return {
        url: typeof record.url === "string" ? record.url : undefined,
        title: typeof record.title === "string" ? record.title : undefined,
        snippet: typeof record.snippet === "string" ? record.snippet : undefined,
        score: typeof record.score === "number" ? record.score : null,
      } satisfies AgentTurnResultItem;
    });

  const results: AgentTurnResultItem[] = mappedResults.filter(Boolean) as AgentTurnResultItem[];

  return { answer, citations, coverage, actions, results };
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
  const previousLogs = new Set<string>();
  let cancelled = false;
  let stopPolling: (() => void) | null = null;
  let source: EventSource | null = null;
  let fallbackStarted = false;

  const emitLogs = (logs: unknown) => {
    if (!logs) return;
    const lines: string[] = [];
    if (typeof logs === "string") {
      lines.push(logs);
    } else if (Array.isArray(logs)) {
      logs.forEach((entry) => {
        if (typeof entry === "string") {
          lines.push(entry);
        }
      });
    } else if (typeof logs === "object") {
      const record = logs as Record<string, unknown>;
      if (Array.isArray(record.logs)) {
        record.logs.forEach((entry) => {
          if (typeof entry === "string") {
            lines.push(entry);
          }
        });
      }
      if (Array.isArray(record.logs_tail)) {
        record.logs_tail.forEach((entry) => {
          if (typeof entry === "string") {
            lines.push(entry);
          }
        });
      }
      const message = record.message ?? record.log ?? record.line;
      if (typeof message === "string") {
        lines.push(message);
      }
    }

    for (const line of lines) {
      if (!previousLogs.has(line)) {
        previousLogs.add(line);
        handlers.onLog?.(line);
      }
    }
  };

  const emitStatus = (payload: JobStatusPayload | null) => {
    if (!payload) {
      return;
    }
    const status = normalizeJobStatus(jobId, payload);
    handlers.onStatus(status);
    if (status.state === "done" || status.state === "error") {
      cancelled = true;
      if (source) {
        source.close();
      }
      if (stopPolling) {
        stopPolling();
      }
    }
  };

  const parseStatusPayload = (data: unknown): JobStatusPayload | null => {
    if (!data || typeof data !== "object") {
      return null;
    }
    const record = data as Record<string, unknown>;
    if (record.status && typeof record.status === "object" && record.status !== null) {
      return record.status as JobStatusPayload;
    }
    if (record.data && typeof record.data === "object" && record.data !== null) {
      const nested = parseStatusPayload(record.data);
      if (nested) {
        return nested;
      }
    }
    if (
      typeof record.job_id === "string" ||
      typeof record.jobId === "string" ||
      typeof record.state === "string" ||
      typeof record.phase === "string" ||
      typeof record.progress === "number"
    ) {
      return record as JobStatusPayload;
    }
    return null;
  };

  const handleEventPayload = (payload: unknown) => {
    if (!payload) {
      return;
    }
    emitLogs(payload);
    const statusPayload = parseStatusPayload(payload);
    if (statusPayload) {
      emitStatus(statusPayload);
    }
  };

  const startPolling = () => {
    let active = true;
    const poll = async () => {
      while (active && !cancelled) {
        try {
          const payload = await fetchJobStatus(jobId);
          emitLogs(payload.logs_tail);
          emitStatus(payload);
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
  };

  const startSse = () => {
    if (typeof window === "undefined" || typeof EventSource === "undefined") {
      return null;
    }
    const url = api(`/api/progress/${encodeURIComponent(jobId)}/stream`);
    try {
      const evtSource = new EventSource(url);
      source = evtSource;

      const handleMessage = (event: MessageEvent<string>) => {
        if (!event.data) {
          return;
        }
        try {
          const data = JSON.parse(event.data) as unknown;
          handleEventPayload(data);
        } catch (error) {
          handlers.onError?.(error instanceof Error ? error : new Error(String(error)));
        }
      };

      evtSource.onmessage = handleMessage;
      evtSource.addEventListener("status", handleMessage);
      evtSource.addEventListener("progress", handleMessage);
      evtSource.addEventListener("log", (event) => {
        if (!event.data) return;
        try {
          const data = JSON.parse(event.data) as unknown;
          emitLogs(data);
        } catch {
          emitLogs(event.data);
        }
      });
      evtSource.onerror = (event) => {
        if (cancelled) {
          return;
        }
        evtSource.close();
        source = null;
        if (!fallbackStarted) {
          fallbackStarted = true;
          stopPolling = startPolling();
        }
        handlers.onError?.(event instanceof ErrorEvent ? event.error : new Error("progress stream disconnected"));
      };

      return () => {
        evtSource.close();
        source = null;
      };
    } catch (error) {
      handlers.onError?.(error instanceof Error ? error : new Error(String(error)));
      return null;
    }
  };

  const stopSse = startSse();
  if (!stopSse) {
    fallbackStarted = true;
    stopPolling = startPolling();
  }

  return () => {
    cancelled = true;
    stopSse?.();
    stopPolling?.();
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
  const healthPromise = fetch(api("/api/llm/health"));
  const modelEndpoints = ["/api/llm/llm_models", "/api/llm/models"] as const;
  let modelsResponse: Response | null = null;
  let lastModelError: Error | null = null;

  for (const endpoint of modelEndpoints) {
    try {
      const response = await fetch(api(endpoint));
      if (!response.ok) {
        const detail = await response.text();
        const message = detail || `Unable to retrieve model list (${response.status})`;
        lastModelError = new Error(message);
        continue;
      }
      modelsResponse = response;
      break;
    } catch (error) {
      lastModelError = error instanceof Error ? error : new Error(String(error));
    }
  }

  if (!modelsResponse) {
    throw lastModelError ?? new Error("Unable to retrieve model list");
  }

  const healthResponse = await healthPromise;
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
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`${errorMessage}: Unable to parse response (${detail})`);
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

export type AgentBrowserConfigPayload = {
  enabled?: boolean;
  AGENT_BROWSER_ENABLED?: boolean;
  AGENT_BROWSER_DEFAULT_TIMEOUT_S?: number;
  AGENT_BROWSER_NAV_TIMEOUT_MS?: number;
  AGENT_BROWSER_HEADLESS?: boolean;
  [key: string]: unknown;
};

const DEFAULT_AGENT_BROWSER_CONFIG: AgentBrowserConfigPayload = {
  enabled: false,
  AGENT_BROWSER_ENABLED: false,
  AGENT_BROWSER_DEFAULT_TIMEOUT_S: 15,
  AGENT_BROWSER_NAV_TIMEOUT_MS: 15000,
  AGENT_BROWSER_HEADLESS: true,
};

export async function fetchAgentBrowserConfig(): Promise<AgentBrowserConfigPayload> {
  try {
    const response = await fetch(api("/api/agent/config"), { cache: "no-store" });
    if (!response.ok) {
      if (response.status === 404) {
        return { ...DEFAULT_AGENT_BROWSER_CONFIG, _source: "fallback" };
      }
      const detail = await response.text();
      throw new Error(detail || `Failed to load agent browser config (${response.status})`);
    }
    return (await response.json()) as AgentBrowserConfigPayload;
  } catch (error) {
    console.warn("fetchAgentBrowserConfig failed; returning defaults", error);
    return { ...DEFAULT_AGENT_BROWSER_CONFIG, _source: "fallback_error" };
  }
}

export async function updateAgentBrowserConfig(
  payload: AgentBrowserConfigPayload
): Promise<AgentBrowserConfigPayload> {
  const response = await fetch(api("/api/agent/config"), {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Failed to update agent browser config (${response.status})`);
  }

  return (await response.json()) as AgentBrowserConfigPayload;
}

export type DesktopRuntimeInfo = {
  desktop_user_agent?: string;
  session_partition?: string;
  hardened?: boolean;
  documented_env_keys?: string[];
  [key: string]: unknown;
};

export async function fetchDesktopRuntime(): Promise<DesktopRuntimeInfo> {
  try {
    const response = await fetch(api("/api/admin/runtime"), { cache: "no-store" });
    if (!response.ok) {
      if (response.status !== 404) {
        const detail = await response.text();
        throw new Error(detail || `Failed to load desktop runtime (${response.status})`);
      }
      return {
        desktop_user_agent:
          process.env.NEXT_PUBLIC_DESKTOP_USER_AGENT ??
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        session_partition: "persist:main",
        hardened: true,
        documented_env_keys: [
          "DESKTOP_USER_AGENT",
          "AGENT_BROWSER_ENABLED",
          "AGENT_BROWSER_DEFAULT_TIMEOUT_S",
          "AGENT_BROWSER_NAV_TIMEOUT_MS",
          "AGENT_BROWSER_HEADLESS",
        ],
        _source: "fallback",
      };
    }
    return (await response.json()) as DesktopRuntimeInfo;
  } catch (error) {
    console.warn("fetchDesktopRuntime failed; returning defaults", error);
    return {
      desktop_user_agent:
        process.env.NEXT_PUBLIC_DESKTOP_USER_AGENT ??
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      session_partition: "persist:main",
      hardened: true,
      documented_env_keys: [
        "DESKTOP_USER_AGENT",
        "AGENT_BROWSER_ENABLED",
        "AGENT_BROWSER_DEFAULT_TIMEOUT_S",
        "AGENT_BROWSER_NAV_TIMEOUT_MS",
        "AGENT_BROWSER_HEADLESS",
      ],
      _source: "fallback_error",
    };
  }
}

export type OllamaHealthResponse = {
  ok: boolean;
  models?: string[];
  [key: string]: unknown;
};

export async function fetchModels(): Promise<OllamaHealthResponse> {
  const response = await fetch(api("/api/admin/ollama/health"), { cache: "no-store" });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Failed to load model health (${response.status})`);
  }
  return (await response.json()) as OllamaHealthResponse;
}

export async function installModels(payload: { models: string[] }): Promise<OllamaHealthResponse> {
  const response = await fetch(api("/api/admin/install_models"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Failed to install models (${response.status})`);
  }

  return (await response.json()) as OllamaHealthResponse;
}

export type DiagnosticsRunResponse = {
  ok: boolean;
  message?: string;
  summary?: Record<string, unknown>;
  [key: string]: unknown;
};

export async function runDiagnostics(): Promise<DiagnosticsRunResponse> {
  const response = await fetch(api("/api/diagnostics/run"), { method: "POST" });
  if (!response.ok) {
    if (response.status === 404) {
      return {
        ok: false,
        message: "Backend does not expose /api/diagnostics/run; run python3 tools/e2e_diag.py locally.",
      };
    }
    const detail = await response.text();
    throw new Error(detail || `Failed to run diagnostics (${response.status})`);
  }
  return (await response.json()) as DiagnosticsRunResponse;
}
