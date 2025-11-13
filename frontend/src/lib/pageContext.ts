import type { ChatContextResponse } from "@/lib/api";
import type { ChatPayloadMessage } from "@/lib/chatClient";

export type ContextPayload = {
  url: string | null;
  title: string | null;
  summary: unknown;
  selection: string | null;
  selection_word_count: number | null;
  metadata: Record<string, unknown>;
  history: unknown[];
  memories: unknown[];
};

export type ResolvedPageContext = {
  contextMessage: ChatPayloadMessage | null;
  contextPayload: ContextPayload | null;
  selectionText: string | null;
  selectionWordCount: number | null;
  pageUrl: string | null;
  pageTitle: string | null;
};

export type BuildPageContextOptions = {
  contextData?: ChatContextResponse | null;
  fallbackUrl?: string | null;
  fallbackTitle?: string | null;
  browserTitle?: string | null;
  selectionText?: string | null;
};

export function countWords(text: string | null | undefined): number | null {
  if (!text) {
    return null;
  }
  const tokens = text.trim().split(/\s+/).filter(Boolean);
  return tokens.length || null;
}

export function buildResolvedPageContext(options: BuildPageContextOptions): ResolvedPageContext {
  const { contextData, fallbackUrl, fallbackTitle, browserTitle, selectionText } = options;
  const combinedSelection = contextData?.selection?.text ?? selectionText ?? null;
  const selectionCount = contextData?.selection?.word_count ?? countWords(combinedSelection);
  const payloadUrl = contextData?.url ?? fallbackUrl ?? null;
  const metadataTitle = typeof contextData?.metadata?.title === "string" ? contextData.metadata?.title : undefined;
  const payloadTitle = fallbackTitle ?? metadataTitle ?? browserTitle ?? null;

  if (!payloadUrl && !payloadTitle && !combinedSelection) {
    return {
      contextMessage: null,
      contextPayload: null,
      selectionText: combinedSelection,
      selectionWordCount: selectionCount,
      pageUrl: null,
      pageTitle: null,
    } satisfies ResolvedPageContext;
  }

  const contextPayload: ContextPayload = {
    url: payloadUrl,
    title: payloadTitle,
    summary: contextData?.summary ?? null,
    selection: combinedSelection,
    selection_word_count: selectionCount,
    metadata: contextData?.metadata ?? {},
    history: contextData?.history ?? [],
    memories: contextData?.memories ?? [],
  };

  return {
    contextMessage: {
      role: "system",
      content: JSON.stringify({ context: contextPayload }, null, 2),
    },
    contextPayload,
    selectionText: combinedSelection,
    selectionWordCount: selectionCount,
    pageUrl: payloadUrl,
    pageTitle: payloadTitle,
  } satisfies ResolvedPageContext;
}
