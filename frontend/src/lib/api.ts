import type { Dispatch, SetStateAction } from "react";

export type ChatRole = "user" | "assistant" | "system" | "action";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: string;
  streaming?: boolean;
  pendingActions?: AgentAction[];
}

export type AgentActionType = "crawl" | "index" | "seed" | "search";

export interface AgentAction {
  id: string;
  type: AgentActionType;
  title: string;
  summary: string;
  payload: Record<string, unknown>;
  status: "proposed" | "approved" | "dismissed" | "running" | "done" | "error";
  error?: string;
}

export interface CrawlScope {
  maxPages: number;
  maxDepth: number;
  domains: string[];
}

export interface JobEvent {
  id: string;
  type: string;
  message: string;
  ts: string;
  meta?: Record<string, unknown>;
  jobId?: string;
}

export interface JobSummary {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  progress: number;
  totals?: {
    queued: number;
    running: number;
    done: number;
    errors: number;
  };
  lastEvent?: JobEvent;
}

export interface LlmStatusResponse {
  available: string[];
  chat?: string;
  embedding?: string;
  fallbackChat?: string;
  fallbackEmbedding?: string;
}

export interface StreamCallbacks {
  onToken: (token: string) => void;
  onAction?: (action: AgentAction) => void;
  onDone?: () => void;
  onError?: (error: Error) => void;
}

export async function* streamChat(
  input: { message: string; context?: Record<string, unknown> },
  signal?: AbortSignal,
): AsyncGenerator<{ token?: string; action?: AgentAction; done?: boolean }, void, unknown> {
  const response = await fetch("/api/chat", {
    method: "POST",
    body: JSON.stringify(input),
    headers: {
      "Content-Type": "application/json",
    },
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`Chat request failed: ${response.status} ${response.statusText}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      if (buffer.trim().length > 0) {
        for (const chunk of parseStreamChunk(buffer)) {
          yield chunk;
        }
      }
      yield { done: true };
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split(/\n\n/);
    buffer = lines.pop() ?? "";

    for (const raw of lines) {
      for (const chunk of parseStreamChunk(raw)) {
        yield chunk;
      }
    }
  }
}

function parseStreamChunk(raw: string) {
  const chunks: { token?: string; action?: AgentAction }[] = [];
  const lines = raw
    .split(/\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  for (const line of lines) {
    if (line.startsWith("data:")) {
      const payload = line.slice(5).trim();
      if (payload === "[DONE]") {
        chunks.push({ token: undefined });
        continue;
      }
      try {
        const data = JSON.parse(payload);
        if (typeof data.token === "string") {
          chunks.push({ token: data.token });
        }
        if (data.action) {
          chunks.push({ action: data.action as AgentAction });
        }
      } catch (error) {
        chunks.push({ token: payload });
      }
    } else if (!line.startsWith(":")) {
      chunks.push({ token: line });
    }
  }
  return chunks;
}

export async function queueCrawl(payload: {
  url: string;
  scope: CrawlScope;
  note?: string;
}) {
  const response = await fetch("/api/crawl", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Failed to queue crawl: ${await response.text()}`);
  }

  return response.json();
}

export async function searchIndex(query: string) {
  const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
  if (!response.ok) {
    throw new Error(`Search failed: ${response.status}`);
  }
  return response.json();
}

export function streamJob(jobId: string, onEvent: (event: JobEvent) => void, signal?: AbortSignal) {
  const source = new EventSource(`/api/jobs/${jobId}/stream`);
  const close = () => source.close();

  source.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data) as JobEvent;
      onEvent({ ...data, jobId });
    } catch (error) {
      console.error("Failed to parse job event", error);
    }
  };

  source.onerror = () => {
    if (!signal?.aborted) {
      console.warn("Job stream error; closing source");
    }
    source.close();
  };

  if (signal) {
    signal.addEventListener("abort", () => source.close(), { once: true });
  }

  return { close };
}

export async function fetchLlmStatus(): Promise<LlmStatusResponse> {
  const response = await fetch("/api/llm/status");
  if (!response.ok) {
    throw new Error(`Unable to load model status: ${response.status}`);
  }
  return response.json();
}

export async function listJobs(): Promise<JobSummary[]> {
  const response = await fetch("/api/jobs");
  if (!response.ok) {
    throw new Error(`Unable to load jobs: ${response.status}`);
  }
  return response.json();
}

export async function acknowledgeAction(actionId: string, status: AgentAction["status"], message?: string) {
  await fetch(`/api/actions/${actionId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, message }),
  });
}

export function optimisticActionUpdate(
  actionId: string,
  setActions: Dispatch<SetStateAction<AgentAction[]>>,
  status: AgentAction["status"],
) {
  setActions((prev) => prev.map((action) => (action.id === actionId ? { ...action, status } : action)));
}
