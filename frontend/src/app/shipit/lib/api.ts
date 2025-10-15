const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");

function resolve(path: string): string {
  if (!API_BASE) return path;
  return `${API_BASE}${path}`;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(resolve(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `${response.status}`);
  }
  if (response.status === 204) {
    return {} as T;
  }
  return (await response.json()) as T;
}

export interface LlmHealthResponse {
  reachable: boolean;
  model_count: number;
  duration_ms?: number;
  host?: string;
  error?: string;
}

export interface LlmModelsResponse {
  chat_models: string[];
  configured?: {
    primary: string | null;
    fallback: string | null;
  };
  embedder?: string | null;
  ollama_host?: string | null;
  reachable?: boolean;
  available?: string[] | null;
  error?: string | null;
}

export type FacetEntry = [string, number];
export type FacetRecord = Record<string, FacetEntry[]>;

export interface HybridSearchHit {
  url: string;
  title: string;
  snippet?: string;
  score?: number;
  source: "vector" | "keyword";
}

export interface HybridSearchResult {
  hits: HybridSearchHit[];
  keywordFallback: boolean;
  facets?: FacetRecord;
  raw: Record<string, unknown>;
}

function normalizeHybridHits(payload: Record<string, unknown>, defaultSource: "vector" | "keyword") {
  const combined = Array.isArray(payload.combined)
    ? payload.combined
    : Array.isArray(payload.results)
    ? payload.results
    : Array.isArray(payload.hits)
    ? payload.hits
    : [];

  const hits: HybridSearchHit[] = [];
  combined.forEach((entry) => {
    if (!entry || typeof entry !== "object") return;
    const record = entry as Record<string, unknown>;
    const url = typeof record.url === "string" ? record.url.trim() : "";
    if (!url) return;
    const titleRaw = typeof record.title === "string" ? record.title.trim() : "";
    const snippet = typeof record.snippet === "string" ? record.snippet : undefined;
    const scoreValue =
      typeof record.score === "number"
        ? record.score
        : typeof record.vector_score === "number"
        ? record.vector_score
        : typeof record.blended_score === "number"
        ? record.blended_score
        : undefined;
    const sourceRaw = typeof record.source === "string" ? record.source.toLowerCase() : defaultSource;
    const source: "vector" | "keyword" = sourceRaw === "keyword" ? "keyword" : "vector";
    hits.push({
      url,
      title: titleRaw || url,
      snippet,
      score: typeof scoreValue === "number" ? scoreValue : undefined,
      source,
    });
  });
  return hits;
}

function normalizeFacets(payload: Record<string, unknown>): FacetRecord | undefined {
  const direct = payload.facets;
  if (direct && typeof direct === "object") {
    return direct as FacetRecord;
  }
  const nested = payload.data;
  if (nested && typeof nested === "object" && (nested as Record<string, unknown>).facets) {
    return (nested as Record<string, unknown>).facets as FacetRecord;
  }
  return undefined;
}

export async function fetchLlmHealth(signal?: AbortSignal): Promise<LlmHealthResponse> {
  const response = await fetch(resolve("/api/llm/health"), { signal });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Health check failed (${response.status})`);
  }
  return (await response.json()) as LlmHealthResponse;
}

export async function fetchLlmModels(signal?: AbortSignal): Promise<LlmModelsResponse> {
  const response = await fetch(resolve("/api/llm/llm_models"), { signal });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Model inventory failed (${response.status})`);
  }
  return (await response.json()) as LlmModelsResponse;
}

interface HybridSearchOptions {
  limit?: number;
  signal?: AbortSignal;
}

export async function runHybridSearch(query: string, options: HybridSearchOptions = {}): Promise<HybridSearchResult> {
  const trimmed = query.trim();
  if (!trimmed) {
    throw new Error("Query is required");
  }

  const body: Record<string, unknown> = { query: trimmed };
  if (typeof options.limit === "number" && Number.isFinite(options.limit)) {
    body.limit = options.limit;
  }

  const attemptHybrid = async () => {
    const response = await fetch(resolve("/api/index/hybrid_search"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(body),
      signal: options.signal,
    });
    if (!response.ok) {
      if (![404, 405, 500, 501].includes(response.status)) {
        const detail = await response.text();
        throw new Error(detail || `Hybrid search failed (${response.status})`);
      }
      return null;
    }
    const payload = (await response.json()) as Record<string, unknown>;
    const keywordFallback = Boolean(payload.keyword_fallback ?? payload.keywordFallback);
    const hits = normalizeHybridHits(payload, keywordFallback ? "keyword" : "vector");
    return {
      hits,
      keywordFallback,
      facets: normalizeFacets(payload),
      raw: payload,
    } satisfies HybridSearchResult;
  };

  try {
    const hybridResult = await attemptHybrid();
    if (hybridResult) {
      return hybridResult;
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
  }

  const fallbackResponse = await fetch(resolve("/api/index/search"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(body),
    signal: options.signal,
  });
  if (!fallbackResponse.ok) {
    const detail = await fallbackResponse.text();
    throw new Error(detail || `Search fallback failed (${fallbackResponse.status})`);
  }
  const fallbackPayload = (await fallbackResponse.json()) as Record<string, unknown>;
  return {
    hits: normalizeHybridHits(fallbackPayload, "keyword"),
    keywordFallback: true,
    facets: normalizeFacets(fallbackPayload),
    raw: fallbackPayload,
  } satisfies HybridSearchResult;
}

export interface DiagnosticsResponse {
  ok: boolean;
  data?: Record<string, unknown>;
  error?: string;
}

export async function triggerDiagnostics(payload: Record<string, unknown> = {}): Promise<DiagnosticsResponse> {
  const response = await fetch(resolve("/api/diagnostics"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Diagnostics failed (${response.status})`);
  }
  return (await response.json()) as DiagnosticsResponse;
}

export function openProgressStream(jobId: string): EventSource {
  const trimmed = jobId.trim();
  if (!trimmed) {
    throw new Error("jobId required");
  }
  const url = resolve(`/api/progress/${encodeURIComponent(trimmed)}/stream`);
  return new EventSource(url);
}
