import type { AgentLogEntry, CrawlScope, ShadowStatus } from "@/lib/types";
import type { ShadowQueueOptions } from "@/lib/api";
import type { ToastMessage } from "@/components/toast-container";

export type CitationIndexStatus = "idle" | "loading" | "success" | "error";

export interface CitationIndexRecord {
  status: CitationIndexStatus;
  error: string | null;
}

export interface CitationIndexingOptions {
  shadowModeEnabled: boolean;
  queueShadowIndex: (url: string, options?: ShadowQueueOptions) => Promise<ShadowStatus>;
  handleQueueAdd: (url: string, scope: CrawlScope, notes?: string) => Promise<unknown>;
  setStatus: (url: string, status: CitationIndexStatus, error?: string | null) => void;
  appendLog: (entry: AgentLogEntry) => void;
  pushToast: (
    message: string,
    options?: { variant?: ToastMessage["variant"]; traceId?: string | null },
  ) => void;
}

function createId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
}

function isHttpUrl(candidate: string | null | undefined): boolean {
  if (!candidate) {
    return false;
  }
  try {
    const parsed = new URL(candidate);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export function collectUniqueHttpCitations(citations: unknown): string[] {
  if (!Array.isArray(citations)) {
    return [];
  }

  const unique = new Set<string>();
  for (const entry of citations) {
    if (typeof entry !== "string") {
      continue;
    }
    const trimmed = entry.trim();
    if (!trimmed || !isHttpUrl(trimmed)) {
      continue;
    }
    try {
      const normalized = new URL(trimmed).toString();
      unique.add(normalized);
    } catch {
      // Ignore malformed URLs.
    }
  }

  return Array.from(unique);
}

export async function indexCitationUrls(
  urls: readonly string[],
  options: CitationIndexingOptions,
): Promise<void> {
  for (const url of urls) {
    options.setStatus(url, "loading");
    try {
      if (options.shadowModeEnabled) {
        await options.queueShadowIndex(url, { reason: "manual" });
      } else {
        await options.handleQueueAdd(url, "page", "Auto-indexed from chat citation");
      }
      options.setStatus(url, "success");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : String(error ?? "Failed to index citation");
      options.setStatus(url, "error", message);
      options.appendLog({
        id: createId(),
        label: "Citation indexing failed",
        detail: `${url}: ${message}`,
        status: "error",
        timestamp: new Date().toISOString(),
      });
      options.pushToast(message, { variant: "destructive" });
    }
  }
}
