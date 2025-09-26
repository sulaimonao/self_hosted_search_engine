const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");

function api(path: string) {
  if (!API_BASE) return path;
  return `${API_BASE}${path}`;
}

import type {
  ChatMessage,
  ChatStreamChunk,
  CrawlScope,
  JobStatusSummary,
  ModelStatus,
  OllamaStatus,
  SelectionActionPayload,
} from "@/lib/types";

const JSON_HEADERS = {
  "Content-Type": "application/json",
  Accept: "application/json",
};

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
  const rawModels = ((await modelsResponse.json()) as { models?: Array<{ name: string }> }).models ?? [];

  const knownModels: ModelStatus[] = [];
  for (const entry of rawModels) {
    const name = entry?.name?.trim();
    if (!name) continue;
    const isEmbedding = /embed|embedding/i.test(name);
    knownModels.push({
      model: name,
      installed: true,
      available: status.running,
      kind: isEmbedding ? "embedding" : "chat",
      isPrimary: name.toLowerCase() === "gpt-oss",
    });
  }

  if (!knownModels.some((model) => /embeddinggemma/i.test(model.model))) {
    knownModels.push({
      model: "embeddinggemma",
      installed: false,
      available: status.running,
      kind: "embedding",
    });
  }

  return {
    status,
    models: knownModels,
  };
}

export async function summarizeSelection(payload: SelectionActionPayload): Promise<string> {
  const body = {
    query: payload.selection,
    model: "gpt-oss",
  };
  const response = await fetch(api("/api/research"), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error("Failed to summarize selection");
  }
  const result = await response.json();
  return JSON.stringify(result);
}
