const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");

function api(path: string) {
  if (!API_BASE) return path;
  return `${API_BASE}${path}`;
}

import type {
  ChatMessage,
  ChatStreamChunk,
  CrawlScope,
  SeedRegistryResponse,
  JobStatusSummary,
  ModelStatus,
  OllamaStatus,
  SelectionActionPayload,
  SearchHit,
  SearchIndexResponse,
} from "@/lib/types";

const JSON_HEADERS = {
  "Content-Type": "application/json",
  Accept: "application/json",
};

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

export async function searchIndex(
  query: string,
  options: SearchIndexOptions = {}
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

  const response = await fetch(api(`/api/search?${params.toString()}`), {
    signal: options.signal,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Search request failed (${response.status})`);
  }

  const payload = (await response.json()) as Record<string, unknown>;
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

export async function streamChat(
  history: ChatMessage[],
  input: string,
  options: {
    model?: string | null;
    signal?: AbortSignal;
    onEvent: (chunk: ChatStreamChunk) => void;
  }
): Promise<void> {
  const { signal, onEvent, model } = options;
  const response = await fetch(api("/api/chat"), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({
      messages: serializeMessages(history, input),
      model: model ?? undefined,
      stream: true,
    }),
    signal,
  });

  if (!response.ok || !response.body) {
    const reason = await response.text();
    throw new Error(reason || `Chat request failed (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const segments = buffer.split("\n\n");
    buffer = segments.pop() ?? "";
    for (const segment of segments) {
      const line = segment.trim();
      if (!line.startsWith("data:")) continue;
      const payload = line.slice(5).trim();
      if (!payload || payload === "[DONE]") continue;
      try {
        const parsed = JSON.parse(payload) as ChatStreamChunk;
        onEvent(parsed);
      } catch (error) {
        console.warn("Failed to parse chat chunk", error, payload);
      }
    }
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
}

export async function fetchModelInventory(): Promise<ModelInventory> {
  const [statusResponse, modelsResponse] = await Promise.all([
    fetch(api("/api/llm/status")),
    fetch(api("/api/llm/models")),
  ]);

  if (!statusResponse.ok) {
    throw new Error("Unable to reach Ollama status endpoint");
  }
  if (!modelsResponse.ok) {
    throw new Error("Unable to retrieve model list");
  }

  const status = (await statusResponse.json()) as OllamaStatus;
  type RawModel = {
    name?: unknown;
    role?: unknown;
    kind?: unknown;
    installed?: unknown;
    available?: unknown;
  };

  const rawModels = ((await modelsResponse.json()) as { models?: RawModel[] }).models ?? [];

  const knownModels: ModelStatus[] = [];
  const seenModels = new Set<string>();

  for (const entry of rawModels) {
    if (!entry || typeof entry !== "object") continue;
    const record = entry as RawModel;
    const name = typeof record.name === "string" ? record.name.trim() : "";
    if (!name || seenModels.has(name)) continue;
    seenModels.add(name);

    const normalizedRole = typeof record.role === "string" ? record.role.trim().toLowerCase() : undefined;
    let role: ModelStatus["role"];
    switch (normalizedRole) {
      case "primary":
      case "fallback":
      case "embedding":
      case "extra":
        role = normalizedRole;
        break;
      default:
        role = undefined;
    }

    const normalizedKind = typeof record.kind === "string" ? record.kind.trim().toLowerCase() : undefined;
    const isEmbedding =
      normalizedKind === "embedding" || role === "embedding" || /embed|embedding/i.test(name);

    const installed =
      record.installed === undefined ? status.running : coerceBoolean(record.installed);
    const available =
      record.available === undefined ? status.running : coerceBoolean(record.available);

    knownModels.push({
      model: name,
      installed,
      available,
      kind: isEmbedding ? "embedding" : "chat",
      isPrimary: role === "primary" || name.toLowerCase() === "gpt-oss",
      role,
    });
  }

  if (!knownModels.some((model) => model.kind === "embedding")) {
    knownModels.push({
      model: "embeddinggemma",
      installed: false,
      available: status.running,
      kind: "embedding",
      role: "embedding",
    });
  }

  return {
    status,
    models: knownModels,
  };
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
