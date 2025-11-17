import { apiClient } from "@/lib/backend/apiClient";
import type { BundleExportResponse, ThreadRecord } from "@/lib/backend/types";

export interface ResearchSession {
  threadId: string;
  topic?: string;
  createdAt: string;
}

export interface CreateResearchSessionInput {
  topic?: string;
  tabId?: string | null;
  tabTitle?: string | null;
}

const DEFAULT_COMPONENTS = ["llm_threads", "llm_messages", "tasks", "browser_history"];

export async function createResearchSession(input: CreateResearchSessionInput = {}): Promise<ResearchSession> {
  const normalizedTopic = input.topic?.trim() || undefined;
  const metadata = normalizedTopic ? { topic: normalizedTopic, session_type: "research" } : { session_type: "research" };
  const threadResponse = await apiClient.post<{ id: string; thread?: ThreadRecord }>("/api/threads", {
    origin: "browser",
    title: normalizedTopic ? `${normalizedTopic} research` : input.tabTitle,
    metadata,
  });

  const threadId = threadResponse.id;
  if (input.tabId) {
    await apiClient.post(`/api/browser/tabs/${input.tabId}/thread`, {
      thread_id: threadId,
      origin: "browser",
      title: input.tabTitle ?? normalizedTopic ?? "Research tab",
    });
  }

  let createdAt = threadResponse.thread?.created_at ?? new Date().toISOString();
  if (!threadResponse.thread) {
    try {
      const fetched = await apiClient.get<{ thread: ThreadRecord }>(`/api/threads/${threadId}`);
      createdAt = fetched.thread?.created_at ?? createdAt;
    } catch {
      // Ignore fetch failures and fall back to now
    }
  }

  return {
    threadId,
    topic: normalizedTopic,
    createdAt,
  };
}

export function inferResearchSessionFromThread(thread: ThreadRecord | null | undefined): ResearchSession | null {
  if (!thread) return null;
  const origin = thread.origin ?? "";
  if (origin.toLowerCase() !== "browser") return null;
  const metadata = (thread.metadata ?? {}) as Record<string, unknown>;
  const topic = typeof metadata.topic === "string" ? metadata.topic : undefined;
  const sessionType = typeof metadata.session_type === "string" ? metadata.session_type : undefined;
  if (sessionType && sessionType !== "research") {
    return null;
  }
  return {
    threadId: thread.id,
    topic,
    createdAt: thread.created_at ?? new Date().toISOString(),
  };
}

export async function exportResearchSessionBundle(thread: ThreadRecord): Promise<BundleExportResponse> {
  const params = new URLSearchParams();
  DEFAULT_COMPONENTS.forEach((component) => params.append("component", component));
  if (thread.created_at) {
    params.set("from", thread.created_at);
  }
  params.set("to", new Date().toISOString());
  const suffix = params.toString();
  return apiClient.get<BundleExportResponse>(`/api/export/bundle?${suffix}`);
}
