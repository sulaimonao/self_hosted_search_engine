"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { OmniBox } from "@/components/omnibox";
import { WebPreview } from "@/components/web-preview";
import { ChatPanel } from "@/components/chat-panel";
import { SearchResultsPanel } from "@/components/search-results-panel";
import { AgentLog } from "@/components/agent-log";
import { JobStatus } from "@/components/job-status";
import { CrawlManager } from "@/components/crawl-manager";
import { ActionEditor } from "@/components/action-editor";
import { ToastContainer, ToastMessage } from "@/components/toast-container";
import {
  extractSelection,
  fetchModelInventory,
  fetchSeeds,
  searchIndex,
  reindexUrl,
  saveSeed,
  startCrawlJob,
  streamChat,
  subscribeJob,
  summarizeSelection,
  ChatRequestError,
  ChatStreamResult,
} from "@/lib/api";
import { resolveChatModelSelection } from "@/lib/chat-model";
import type {
  ActionKind,
  AgentLogEntry,
  ChatMessage,
  CrawlQueueItem,
  CrawlScope,
  SeedRegistryResponse,
  JobStatusSummary,
  ModelStatus,
  OllamaStatus,
  ProposedAction,
  SelectionActionPayload,
  SeedRecord,
  SearchHit,
} from "@/lib/types";
import { devlog } from "@/lib/devlog";

const INITIAL_URL = "https://news.ycombinator.com";
const MODEL_STORAGE_KEY = "chat:model";

function uid() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
}

function looksLikeUrl(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return false;
  if (/^https?:\/\//i.test(trimmed)) return true;
  return /^[\w.-]+\.[a-z]{2,}(\/.*)?$/i.test(trimmed);
}

const DEFAULT_AGENT_LOG: AgentLogEntry[] = [
  {
    id: uid(),
    label: "Ready",
    detail: "Agent idle. Waiting for instructions.",
    status: "info",
    timestamp: new Date().toISOString(),
  },
];

const DEFAULT_JOB_STATUS: JobStatusSummary[] = [];

const DEFAULT_CHAT_MESSAGES: ChatMessage[] = [
  {
    id: uid(),
    role: "assistant",
    content:
      "Welcome! Paste a URL or ask me to search. I will only crawl when you approve each step.",
    createdAt: new Date().toISOString(),
  },
];

type SearchPanelStatus = "idle" | "loading" | "ok" | "warming" | "focused_crawl_running" | "error";

interface SearchState {
  status: SearchPanelStatus;
  hits: SearchHit[];
  query: string;
  isLoading: boolean;
  error: string | null;
  detail: string | null;
  jobId: string | null;
  confidence: number | null;
  llmUsed: boolean;
  triggerReason: string | null;
  seedCount: number | null;
  action: string | null;
  code: string | null;
  candidates: Array<Record<string, unknown>>;
  lastIndexTime: number | null;
  lastFetchedAt: string | null;
}

function createInitialSearchState(): SearchState {
  return {
    status: "idle",
    hits: [],
    query: "",
    isLoading: false,
    error: null,
    detail: null,
    jobId: null,
    confidence: null,
    llmUsed: false,
    triggerReason: null,
    seedCount: null,
    action: null,
    code: null,
    candidates: [],
    lastIndexTime: null,
    lastFetchedAt: null,
  };
}

export function AppShell() {
  const [previewState, setPreviewState] = useState({
    history: [INITIAL_URL],
    index: 0,
  });
  const [reloadKey, setReloadKey] = useState(0);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(DEFAULT_CHAT_MESSAGES);
  const [chatInput, setChatInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [agentLog, setAgentLog] = useState<AgentLogEntry[]>(DEFAULT_AGENT_LOG);
  const [jobSummaries, setJobSummaries] = useState<JobStatusSummary[]>(DEFAULT_JOB_STATUS);
  const [crawlQueue, setCrawlQueue] = useState<CrawlQueueItem[]>([]);
  const [seedRevision, setSeedRevision] = useState<string | null>(null);
  const [isSeedsLoading, setIsSeedsLoading] = useState(false);
  const [seedError, setSeedError] = useState<string | null>(null);
  const [defaultScope, setDefaultScope] = useState<CrawlScope>("page");
  const [omniboxValue, setOmniboxValue] = useState(INITIAL_URL);
  const [commandOpen, setCommandOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("chat");
  const [modelStatus, setModelStatus] = useState<ModelStatus[]>([]);
  const [chatModel, setChatModel] = useState<string | null>(null);
  const [embeddingModel, setEmbeddingModel] = useState<string | null>(null);
  const [ollamaStatus, setOllamaStatus] = useState<OllamaStatus | null>(null);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [modelWarning, setModelWarning] = useState<string | null>(null);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [editorAction, setEditorAction] = useState<ProposedAction | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [searchState, setSearchState] = useState<SearchState>(() => createInitialSearchState());

  const omniboxRef = useRef<HTMLInputElement | null>(null);
  const streamingController = useRef<AbortController | null>(null);
  const jobSubscriptions = useRef(new Map<string, () => void>());
  const chatHistoryRef = useRef<ChatMessage[]>(chatMessages);
  const crawlQueueRef = useRef<CrawlQueueItem[]>(crawlQueue);
  const searchAbortRef = useRef<AbortController | null>(null);
  const lastSuccessfulModelRef = useRef<string | null>(null);

  const currentUrl = previewState.history[previewState.index];

  const pushToast = useCallback(
    (message: string, options?: { variant?: ToastMessage["variant"]; traceId?: string | null }) => {
      const id = uid();
      setToasts((items) => [
        ...items,
        { id, message, variant: options?.variant, traceId: options?.traceId ?? null },
      ]);
    },
    [],
  );

  const dismissToast = useCallback((id: string) => {
    setToasts((items) => items.filter((toast) => toast.id !== id));
  }, []);

  useEffect(() => {
    devlog("mount");
  }, []);

  const navigateTo = useCallback(
    (inputValue: string) => {
      const value = inputValue.trim();
      if (!value) return;
      devlog("navigate", { url: value });
      setIsPreviewLoading(true);
      setPreviewState((state) => {
        const nextHistory = state.history.slice(0, state.index + 1);
        nextHistory.push(value);
        return {
          history: nextHistory,
          index: nextHistory.length - 1,
        };
      });
    },
    []
  );

  const replaceUrl = useCallback((target: string) => {
    setIsPreviewLoading(true);
    setPreviewState((state) => {
      const nextHistory = [...state.history];
      nextHistory[state.index] = target;
      return {
        history: nextHistory,
        index: state.index,
      };
    });
  }, []);

  const handleNavigate = useCallback(
    (url: string, options?: { replace?: boolean }) => {
      if (options?.replace) {
        replaceUrl(url);
      } else {
        navigateTo(url);
      }
      setOmniboxValue(url);
    },
    [navigateTo, replaceUrl]
  );

  const handleBack = useCallback(() => {
    setPreviewState((state) => {
      if (state.index === 0) return state;
      return { ...state, index: state.index - 1 };
    });
  }, []);

  const handleForward = useCallback(() => {
    setPreviewState((state) => {
      if (state.index >= state.history.length - 1) return state;
      return { ...state, index: state.index + 1 };
    });
  }, []);

  const handleReload = useCallback(() => {
    setIsPreviewLoading(true);
    setReloadKey((key) => key + 1);
  }, []);

  const appendMessage = useCallback((message: ChatMessage) => {
    setChatMessages((prev) => [...prev, message]);
  }, []);

  const appendLog = useCallback((entry: AgentLogEntry) => {
    setAgentLog((prev) => [entry, ...prev].slice(0, 400));
  }, []);

  const updateLogEntry = useCallback((entryId: string, patch: Partial<AgentLogEntry>) => {
    setAgentLog((entries) =>
      entries.map((entry) => {
        if (entry.id !== entryId) return entry;
        const nextMeta = {
          ...(entry.meta ?? {}),
          ...(patch.meta ?? {}),
        };
        return {
          ...entry,
          ...patch,
          meta: Object.keys(nextMeta).length ? nextMeta : undefined,
        };
      })
    );
  }, []);

  const updateAction = useCallback((action: ProposedAction) => {
    setChatMessages((messages) =>
      messages.map((message) => {
        if (!message.proposedActions) return message;
        const updated = message.proposedActions.map((existing) =>
          existing.id === action.id ? { ...existing, ...action } : existing
        );
        return { ...message, proposedActions: updated };
      })
    );
  }, []);

  const updateMessageForAction = useCallback(
    (actionId: string, updater: (message: ChatMessage) => ChatMessage) => {
      setChatMessages((messages) =>
        messages.map((message) => {
          const hasAction = message.proposedActions?.some((existing) => existing.id === actionId);
          if (!hasAction) return message;
          return updater(message);
        })
      );
    },
    []
  );

  const mapSeedsToQueue = useCallback((seeds: SeedRecord[]): CrawlQueueItem[] => {
    const items = seeds
      .filter((seed) => typeof seed.url === "string" && seed.url.trim().length > 0)
      .map((seed) => ({
        id: seed.id,
        url: (seed.url as string).trim(),
        scope: seed.scope,
        notes: seed.notes ?? undefined,
        editable: seed.editable,
        directory: seed.directory,
        entrypoints: seed.entrypoints,
        createdAt: seed.created_at,
        updatedAt: seed.updated_at,
      }));
    return items.sort((a, b) => Number(b.editable) - Number(a.editable));
  }, []);

  const applySeedRegistry = useCallback(
    (payload: SeedRegistryResponse) => {
      setSeedRevision(payload.revision);
      setCrawlQueue(mapSeedsToQueue(payload.seeds));
    },
    [mapSeedsToQueue]
  );

  const refreshSeeds = useCallback(async () => {
    setIsSeedsLoading(true);
    try {
      const payload = await fetchSeeds();
      applySeedRegistry(payload);
      setSeedError(null);
      return payload.revision;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setSeedError(message);
      throw error instanceof Error ? error : new Error(message);
    } finally {
      setIsSeedsLoading(false);
    }
  }, [applySeedRegistry]);

  const ensureSeedRevision = useCallback(async () => {
    if (seedRevision) {
      return seedRevision;
    }
    const revision = await refreshSeeds();
    if (!revision) {
      throw new Error("Unable to resolve seed registry revision");
    }
    return revision;
  }, [refreshSeeds, seedRevision]);

  const handleSeedError = useCallback(
    async (error: unknown) => {
      const err = error instanceof Error ? error : new Error(String(error));
      const status = (error as { status?: number }).status;
      const revisionHint = (error as { revision?: string }).revision;
      if (status === 409 && revisionHint) {
        try {
          await refreshSeeds();
        } catch (refreshError) {
          console.warn("Failed to refresh seeds after conflict", refreshError);
        }
        const conflict = new Error("Seed registry updated. Please retry the action.");
        setSeedError(conflict.message);
        return conflict;
      }
      setSeedError(err.message);
      return err;
    },
    [refreshSeeds]
  );

  const handleQueueAdd = useCallback(
    async (url: string, scope: CrawlScope, notes?: string) => {
      try {
        const revision = await ensureSeedRevision();
        const payload = await saveSeed({
          action: "create",
          revision,
          seed: { url, scope, notes },
        });
        applySeedRegistry(payload);
        setSeedError(null);
        devlog("crawl.queue", { url, scope });
        appendLog({
          id: uid(),
          label: "Queued crawl",
          detail: `Saved ${url} [${scope}] to seed registry`,
          status: "info",
          timestamp: new Date().toISOString(),
        });
      } catch (error) {
        const normalized = await handleSeedError(error);
        appendLog({
          id: uid(),
          label: "Seed update failed",
          detail: normalized.message,
          status: "error",
          timestamp: new Date().toISOString(),
        });
        throw normalized;
      }
    },
    [appendLog, applySeedRegistry, ensureSeedRevision, handleSeedError]
  );

  const registerJob = useCallback(
    (jobId: string, description: string) => {
      setJobSummaries((jobs) => {
        if (jobs.some((job) => job.jobId === jobId)) {
          return jobs.map((job) =>
            job.jobId === jobId ? { ...job, description } : job
          );
        }
        return [
          {
            jobId,
            state: "queued",
            progress: 10,
            description,
            lastUpdated: new Date().toISOString(),
          },
          ...jobs,
        ];
      });

      const unsubscribe = subscribeJob(jobId, {
        onStatus: (status) => {
          setJobSummaries((jobs) =>
            jobs.map((job) =>
              job.jobId === status.jobId
                ? { ...job, ...status, description }
                : job
            )
          );
          if (status.state === "done" || status.state === "error") {
            appendLog({
              id: uid(),
              label: status.state === "done" ? "Job complete" : "Job error",
              detail: `${description} (${status.state})`,
              status: status.state === "done" ? "success" : "error",
              timestamp: new Date().toISOString(),
            });
            const cancel = jobSubscriptions.current.get(jobId);
            cancel?.();
            jobSubscriptions.current.delete(jobId);
          }
        },
        onLog: (line) => {
          const normalized = line.toLowerCase();
          appendLog({
            id: uid(),
            label: description,
            detail: line,
            status: normalized.includes("error") ? "error" : "info",
            timestamp: new Date().toISOString(),
          });
        },
        onError: (error) => {
          appendLog({
            id: uid(),
            label: "Job monitor",
            detail: error.message,
            status: "error",
            timestamp: new Date().toISOString(),
          });
        },
      });
      jobSubscriptions.current.set(jobId, unsubscribe);
    },
    [appendLog]
  );

  const handleSearch = useCallback(
    async (value: string) => {
      const query = value.trim();
      if (!query) {
        searchAbortRef.current?.abort();
        searchAbortRef.current = null;
        setSearchState(() => createInitialSearchState());
        return;
      }

      searchAbortRef.current?.abort();
      const controller = new AbortController();
      searchAbortRef.current = controller;
      const timestamp = new Date().toISOString();
      devlog("search", { query });

      setSearchState((state) => ({
        ...state,
        query,
        status: "loading",
        isLoading: true,
        error: null,
        detail: null,
      }));

      try {
        const result = await searchIndex(query, { signal: controller.signal });
        const normalizedStatus: SearchPanelStatus = result.error
          ? "error"
          : result.status === "focused_crawl_running"
          ? "focused_crawl_running"
          : result.status === "warming"
          ? "warming"
          : "ok";

        setSearchState({
          status: normalizedStatus,
          hits: result.hits,
          query,
          isLoading: false,
          error: result.error ?? null,
          detail: result.detail ?? null,
          jobId: result.jobId ?? null,
          confidence: typeof result.confidence === "number" ? result.confidence : null,
          llmUsed: result.llmUsed,
          triggerReason: result.triggerReason ?? null,
          seedCount: typeof result.seedCount === "number" ? result.seedCount : null,
          action: result.action ?? null,
          code: result.code ?? null,
          candidates: result.candidates ?? [],
          lastIndexTime: typeof result.lastIndexTime === "number" ? result.lastIndexTime : null,
          lastFetchedAt: timestamp,
        });

        if (result.jobId) {
          registerJob(result.jobId, `Focused crawl for "${query}"`);
        }
      } catch (error) {
        if (controller.signal.aborted || (error instanceof DOMException && error.name === "AbortError")) {
          return;
        }
        const message = error instanceof Error ? error.message : String(error ?? "Search failed");
        setSearchState({
          status: "error",
          hits: [],
          query,
          isLoading: false,
          error: message,
          detail: null,
          jobId: null,
          confidence: null,
          llmUsed: false,
          triggerReason: null,
          seedCount: null,
          action: null,
          code: null,
          candidates: [],
          lastIndexTime: null,
          lastFetchedAt: timestamp,
        });
      } finally {
        if (searchAbortRef.current === controller) {
          searchAbortRef.current = null;
        }
      }
    },
    [registerJob]
  );

  const refreshSearch = useCallback(() => {
    if (searchState.query) {
      void handleSearch(searchState.query);
    }
  }, [handleSearch, searchState.query]);

  const createActionFromSelection = useCallback(
    (kind: ActionKind, payload: SelectionActionPayload) => {
      const action: ProposedAction = {
        id: uid(),
        kind,
        title:
          kind === "extract"
            ? "Extract content"
            : kind === "summarize"
            ? "Summarize selection"
            : "Queue highlighted content",
        description: payload.selection.slice(0, 80) + (payload.selection.length > 80 ? "…" : ""),
        payload: { ...payload },
        status: "proposed",
        metadata: { preview: payload.selection, url: payload.url },
      };
      const message: ChatMessage = {
        id: uid(),
        role: "agent",
        content: "I captured a highlight from the page.",
        createdAt: new Date().toISOString(),
        proposedActions: [action],
      };
      appendMessage(message);
      appendLog({
        id: uid(),
        label: "Highlight captured",
        detail: `Captured ${payload.selection.length} characters for ${kind}.`,
        status: "info",
        timestamp: new Date().toISOString(),
      });
    },
    [appendLog, appendMessage]
  );

  const handleSendChat = useCallback(
    async (content: string) => {
      const historySnapshot = chatHistoryRef.current;
      const now = new Date().toISOString();
      const userMessage: ChatMessage = {
        id: uid(),
        role: "user",
        content,
        createdAt: now,
      };
      appendMessage(userMessage);
      appendLog({
        id: uid(),
        label: "User message",
        detail: content,
        status: "info",
        timestamp: now,
      });
      setChatInput("");

      streamingController.current?.abort();
      const controller = new AbortController();
      streamingController.current = controller;
      setIsStreaming(true);

      const assistantId = uid();
      const assistantMessage: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        createdAt: new Date().toISOString(),
        streaming: true,
        proposedActions: [],
      };
      appendMessage(assistantMessage);

      const updateAssistant = (updater: (message: ChatMessage) => ChatMessage) => {
        setChatMessages((messages) =>
          messages.map((message) =>
            message.id === assistantId ? updater(message) : message
          )
        );
      };

      devlog("chat.send", { model: chatModel ?? "auto" });

      try {
        const result: ChatStreamResult = await streamChat(historySnapshot, content, {
          model: chatModel,
          signal: controller.signal,
          onEvent: (chunk) => {
            if (chunk.type === "token" && chunk.content) {
              updateAssistant((message) => ({
                ...message,
                content: `${message.content ?? ""}${chunk.content}`,
              }));
            } else if (chunk.type === "action" && chunk.action) {
              const actionWithDefaults: ProposedAction = {
                ...chunk.action,
                status: chunk.action.status ?? "proposed",
              };
              updateAssistant((message) => ({
                ...message,
                proposedActions: [...(message.proposedActions ?? []), actionWithDefaults],
              }));
              appendLog({
                id: uid(),
                label: "Proposed action",
                detail: `${actionWithDefaults.kind}: ${actionWithDefaults.title}`,
                status: "info",
                timestamp: new Date().toISOString(),
              });
            } else if (chunk.type === "error" && chunk.content) {
              updateAssistant((message) => ({
                ...message,
                streaming: false,
                content: `${message.content}\n\nError: ${chunk.content}`.trim(),
              }));
              appendLog({
                id: uid(),
                label: "Chat error",
                detail: chunk.content,
                status: "error",
                timestamp: new Date().toISOString(),
              });
            } else if (chunk.type === "done") {
              updateAssistant((message) => ({
                ...message,
                streaming: false,
              }));
              appendLog({
                id: uid(),
                label: "Response complete",
                detail: `Finished streaming in ${currentUrl}`,
                status: "success",
                timestamp: new Date().toISOString(),
              });
            }
          },
        });
        devlog("chat.ok", { trace: result.traceId, model: result.model ?? chatModel ?? "unknown" });
        if (result.model && result.model !== chatModel) {
          setChatModel(result.model);
        }
        lastSuccessfulModelRef.current = result.model ?? chatModel;
      } catch (error) {
        const abort = controller.signal.aborted;
        if (!abort) {
          if (error instanceof ChatRequestError) {
            const message = error.hint ?? error.message;
            devlog("chat.fail", { trace: error.traceId, code: error.code });
            updateAssistant((assistant) => ({
              ...assistant,
              streaming: false,
              content: assistant.content ? `${assistant.content}\n\n${message}` : `Error: ${message}`,
            }));
            appendLog({
              id: uid(),
              label: "Chat failure",
              detail: error.traceId ? `${message} (trace ${error.traceId})` : message,
              status: "error",
              timestamp: new Date().toISOString(),
            });
            pushToast(message, { variant: "destructive", traceId: error.traceId });
            if (error.code === "model_not_found" && lastSuccessfulModelRef.current) {
              setChatModel(lastSuccessfulModelRef.current);
            }
          } else {
            const message = error instanceof Error ? error.message : String(error ?? "Unknown error");
            devlog("chat.fail", { trace: null, code: "unexpected" });
            updateAssistant((assistant) => ({
              ...assistant,
              streaming: false,
              content: assistant.content ? `${assistant.content}\n\n${message}` : `Error: ${message}`,
            }));
            appendLog({
              id: uid(),
              label: "Chat failure",
              detail: message,
              status: "error",
              timestamp: new Date().toISOString(),
            });
            pushToast(message, { variant: "destructive" });
          }
        }
      } finally {
        if (streamingController.current === controller) {
          streamingController.current = null;
        }
        setIsStreaming(false);
        updateAssistant((message) => ({ ...message, streaming: false }));
      }
    },
    [appendLog, appendMessage, chatModel, currentUrl, pushToast]
  );

  const handleStopStreaming = useCallback(() => {
    if (streamingController.current) {
      streamingController.current.abort();
      streamingController.current = null;
    }
    setIsStreaming(false);
    devlog("chat.stop");
    appendLog({
      id: uid(),
      label: "Streaming stopped",
      detail: "User interrupted generation",
      status: "warning",
      timestamp: new Date().toISOString(),
    });
  }, [appendLog]);

  const handleModelSelect = useCallback((value: string) => {
    setChatModel(value);
    devlog("modelChanged", { model: value });
  }, []);

  const handleAskAgent = useCallback(
    (question: string) => {
      const prompt = question.trim();
      if (!prompt) return;
      if (isStreaming) {
        handleStopStreaming();
      }
      setActiveTab("chat");
      void handleSendChat(prompt);
    },
    [handleSendChat, handleStopStreaming, isStreaming]
  );

  const handleOmniSubmit = useCallback(
    (value: string) => {
      const input = value.trim();
      if (!input) return;
      if (looksLikeUrl(input)) {
        handleNavigate(input);
      } else {
        if (isStreaming) {
          handleStopStreaming();
        }
        void handleSearch(input);
      }
    },
    [handleNavigate, handleSearch, handleStopStreaming, isStreaming]
  );

  const handleApproveAction = useCallback(
    async (action: ProposedAction) => {
      updateAction({ ...action, status: "approved" });
      appendLog({
        id: uid(),
        label: "Action approved",
        detail: `${action.kind} approved`,
        status: "success",
        timestamp: new Date().toISOString(),
      });
      devlog("action.approve", { kind: action.kind, id: action.id });

      try {
        if (action.kind === "crawl" || action.kind === "queue") {
          const url = String(action.payload.url ?? currentUrl);
          const scope = (action.payload.scope as CrawlScope) || defaultScope;
          const maxPages = Number(action.payload.maxPages ?? 25);
          const maxDepth = Number(action.payload.maxDepth ?? 2);
          const description = `Crawl ${new URL(url).hostname}`;
          devlog("crawl.start", { url, scope, maxPages, maxDepth });

          const response = await startCrawlJob({ url, scope, maxPages, maxDepth });
          const jobId = (response as { job_id?: string; jobId?: string }).jobId ??
            (response as { job_id?: string }).job_id;
          if (jobId) {
            registerJob(jobId, description);
          } else {
            appendLog({
              id: uid(),
              label: "Crawl queued",
              detail: `Queued ${url} without job id`,
              status: "warning",
              timestamp: new Date().toISOString(),
            });
          }
          await handleQueueAdd(url, scope, action.description);
        } else if (action.kind === "index") {
          const target = String(action.payload.url ?? currentUrl);
          await reindexUrl(target);
          appendLog({
            id: uid(),
            label: "Reindexing",
            detail: `Requested reindex for ${target}`,
            status: "info",
            timestamp: new Date().toISOString(),
          });
        } else if (action.kind === "add_seed") {
          const seed = String(action.payload.url ?? currentUrl);
          await handleQueueAdd(
            seed,
            (action.payload.scope as CrawlScope) || "allowed-list",
            action.description ?? "Seed captured"
          );
        } else if (action.kind === "summarize" || action.kind === "extract") {
          const payload = action.payload as SelectionActionPayload;
          const selection = typeof payload?.selection === "string" ? payload.selection.trim() : "";
          if (!selection) {
            throw new Error("Selection payload is empty");
          }
          const metadata: Record<string, unknown> = { ...(action.metadata ?? {}) };
          delete metadata.error;
          delete metadata.result;
          const progressLabel =
            action.kind === "summarize" ? "Summarizing selection…" : "Extracting selection…";
          metadata.progress = progressLabel;
          updateAction({
            ...action,
            status: "executing",
            metadata,
          });
          const logId = uid();
          appendLog({
            id: logId,
            label: action.kind === "summarize" ? "Summarizing highlight" : "Extracting highlight",
            detail: selection.slice(0, 120) + (selection.length > 120 ? "…" : ""),
            status: "info",
            timestamp: new Date().toISOString(),
            meta: { inProgress: true, actionId: action.id },
          });
          try {
            const result =
              action.kind === "summarize"
                ? await summarizeSelection(payload)
                : await extractSelection(payload);
            const formattedLabel = action.kind === "summarize" ? "Summary" : "Extraction";
            const truncated = result.text.slice(0, 160);
            const metadataDone: Record<string, unknown> = {
              ...(action.metadata ?? {}),
              result: result.text,
            };
            if (metadataDone.progress) {
              delete (metadataDone as { progress?: unknown }).progress;
            }
            if (metadataDone.error) {
              delete (metadataDone as { error?: unknown }).error;
            }
            updateAction({
              ...action,
              status: "done",
              metadata: metadataDone,
            });
            updateMessageForAction(action.id, (message) => {
              const baseContent = message.content?.trim() ?? "";
              const annotation = `${formattedLabel}:\n${result.text}`.trim();
              const alreadyIncluded = baseContent.includes(annotation);
              const combined = alreadyIncluded
                ? baseContent
                : [baseContent, annotation].filter(Boolean).join("\n\n");
              return {
                ...message,
                content: combined,
              };
            });
            updateLogEntry(logId, {
              status: "success",
              detail:
                truncated.length === result.text.length
                  ? `${formattedLabel} ready: ${truncated}`
                  : `${formattedLabel} ready: ${truncated}…`,
              meta: {
                inProgress: false,
                actionId: action.id,
                preview:
                  truncated.length === result.text.length ? truncated : `${truncated}…`,
              },
            });
          } catch (error) {
            const message = error instanceof Error ? error.message : String(error ?? "Unknown error");
            const failureMetadata: Record<string, unknown> = {
              ...(action.metadata ?? {}),
              error: message,
            };
            if (failureMetadata.progress) {
              delete (failureMetadata as { progress?: unknown }).progress;
            }
            if (failureMetadata.result) {
              delete (failureMetadata as { result?: unknown }).result;
            }
            updateAction({
              ...action,
              status: "error",
              metadata: failureMetadata,
            });
            updateMessageForAction(action.id, (existing) => {
              const baseContent = existing.content?.trim() ?? "";
              const failureLine = `${action.kind === "summarize" ? "Summary" : "Extraction"} failed: ${message}`;
              const combined = [baseContent, failureLine].filter(Boolean).join("\n\n");
              return {
                ...existing,
                content: combined,
              };
            });
            updateLogEntry(logId, {
              status: "error",
              detail: message,
              meta: { inProgress: false, actionId: action.id },
            });
          }
          return;
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error ?? "Unknown error");
        updateAction({ ...action, status: "error" });
        appendLog({
          id: uid(),
          label: "Action failed",
          detail: message,
          status: "error",
          timestamp: new Date().toISOString(),
        });
      }
    },
    [
      appendLog,
      currentUrl,
      defaultScope,
      handleQueueAdd,
      registerJob,
      summarizeSelection,
      extractSelection,
      updateAction,
      updateLogEntry,
      updateMessageForAction,
    ]
  );

  const handleDismissAction = useCallback(
    (action: ProposedAction) => {
      updateAction({ ...action, status: "dismissed" });
      appendLog({
        id: uid(),
        label: "Action dismissed",
        detail: `${action.kind} was dismissed`,
        status: "warning",
        timestamp: new Date().toISOString(),
      });
    },
    [appendLog, updateAction]
  );

  const handleEditAction = useCallback((action: ProposedAction) => {
    setEditorAction(action);
    setEditorOpen(true);
  }, []);

  const handleQueueRemove = useCallback(
    async (id: string) => {
      const target = crawlQueueRef.current.find((item) => item.id === id);
      try {
        const revision = await ensureSeedRevision();
        const payload = await saveSeed({ action: "delete", revision, seed: { id } });
        applySeedRegistry(payload);
        setSeedError(null);
        devlog("crawl.remove", { id, url: target?.url });
        appendLog({
          id: uid(),
          label: "Seed removed",
          detail: target ? `Removed ${target.url}` : `Removed ${id}`,
          status: "success",
          timestamp: new Date().toISOString(),
        });
      } catch (error) {
        const normalized = await handleSeedError(error);
        appendLog({
          id: uid(),
          label: "Seed removal failed",
          detail: normalized.message,
          status: "error",
          timestamp: new Date().toISOString(),
        });
        throw normalized;
      }
    },
    [appendLog, applySeedRegistry, ensureSeedRevision, handleSeedError]
  );

  const handleQueueScopeUpdate = useCallback(
    async (id: string, scope: CrawlScope) => {
      const target = crawlQueueRef.current.find((item) => item.id === id);
      try {
        const revision = await ensureSeedRevision();
        const payload = await saveSeed({
          action: "update",
          revision,
          seed: { id, scope },
        });
        applySeedRegistry(payload);
        setSeedError(null);
        devlog("crawl.scope", { id, scope, url: target?.url });
        appendLog({
          id: uid(),
          label: "Seed updated",
          detail: target ? `Scope for ${target.url} set to ${scope}` : `Updated ${id}`,
          status: "info",
          timestamp: new Date().toISOString(),
        });
      } catch (error) {
        const normalized = await handleSeedError(error);
        appendLog({
          id: uid(),
          label: "Seed update failed",
          detail: normalized.message,
          status: "error",
          timestamp: new Date().toISOString(),
        });
        throw normalized;
      }
    },
    [appendLog, applySeedRegistry, ensureSeedRevision, handleSeedError]
  );

  useEffect(() => {
    return () => {
      searchAbortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen((open) => !open);
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "l") {
        event.preventDefault();
        omniboxRef.current?.focus();
        omniboxRef.current?.select?.();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    setOmniboxValue(currentUrl);
    setIsPreviewLoading(false);
  }, [currentUrl]);

  useEffect(() => {
    chatHistoryRef.current = chatMessages;
  }, [chatMessages]);

  useEffect(() => {
    crawlQueueRef.current = crawlQueue;
  }, [crawlQueue]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (chatModel) {
      window.localStorage.setItem(MODEL_STORAGE_KEY, chatModel);
    } else {
      window.localStorage.removeItem(MODEL_STORAGE_KEY);
    }
  }, [chatModel]);

  useEffect(() => {
    const loadModels = async () => {
      try {
        const inventory = await fetchModelInventory();
        setModelStatus(inventory.models);
        setOllamaStatus(inventory.status);
        setAvailableModels(inventory.available);
        setEmbeddingModel(inventory.configured.embedder);
        setModelWarning(
          inventory.available.length === 0
            ? "No local models detected. Run: `ollama pull gpt-oss` (or your choice) then refresh."
            : null,
        );
        const stored =
          typeof window !== "undefined" ? window.localStorage.getItem(MODEL_STORAGE_KEY) : null;
        const nextModel = resolveChatModelSelection({
          available: inventory.available,
          configured: inventory.configured,
          stored: stored && stored.trim() ? stored.trim() : null,
          previous: lastSuccessfulModelRef.current,
        });
        setChatModel(nextModel);
        lastSuccessfulModelRef.current = nextModel;
        devlog("models.loaded", { available: inventory.available.length, model: nextModel });
      } catch (error) {
        console.warn("Unable to load model inventory", error);
        devlog("models.error", { message: error instanceof Error ? error.message : String(error) });
      }
    };
    loadModels();
  }, []);

  useEffect(() => {
    const subscriptions = jobSubscriptions.current;
    return () => {
      for (const cancel of subscriptions.values()) {
        cancel();
      }
      subscriptions.clear();
      streamingController.current?.abort();
    };
  }, []);

  const commands = useMemo(
    () => [
      {
        id: "open-settings",
        label: "Open settings",
        action: () => setSettingsOpen(true),
      },
      {
        id: "reload-preview",
        label: "Reload preview",
        action: handleReload,
      },
      {
        id: "focus-chat",
        label: "Focus chat input",
        action: () => {
          const textarea = document.querySelector<HTMLTextAreaElement>("textarea");
          textarea?.focus();
        },
      },
      {
        id: "toggle-agent-log",
        label: "Toggle agent log",
        action: () => setActiveTab((tab) => (tab === "chat" ? "agent" : "chat")),
      },
    ],
    [handleReload]
  );

  const chatModelOptions = useMemo(() => {
    if (!chatModel) {
      return availableModels;
    }
    if (availableModels.includes(chatModel)) {
      return availableModels;
    }
    return [chatModel, ...availableModels.filter((model) => model !== chatModel)];
  }, [availableModels, chatModel]);

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <OmniBox
        ref={omniboxRef}
        value={omniboxValue}
        onChange={setOmniboxValue}
        onSubmit={handleOmniSubmit}
        onOpenCommand={() => setCommandOpen(true)}
        onOpenSettings={() => setSettingsOpen(true)}
      />
      <div className="flex flex-1 flex-col lg:flex-row">
        <SearchResultsPanel
          className="order-1 h-[40vh] flex-1 border-b lg:h-auto lg:max-w-md lg:flex-[1.1] lg:border-r"
          query={searchState.query}
          hits={searchState.hits}
          status={searchState.status}
          isLoading={searchState.isLoading}
          error={searchState.error}
          detail={searchState.detail}
          onOpenHit={handleNavigate}
          onAskAgent={handleAskAgent}
          onRefresh={searchState.query ? refreshSearch : undefined}
          currentUrl={currentUrl}
          confidence={searchState.confidence}
          llmUsed={searchState.llmUsed}
          triggerReason={searchState.triggerReason}
          seedCount={searchState.seedCount}
          jobId={searchState.jobId}
          lastFetchedAt={searchState.lastFetchedAt}
          actionLabel={searchState.action}
          code={searchState.code}
          candidates={searchState.candidates}
        />
        <section className="order-2 h-[45vh] flex-1 border-b lg:order-2 lg:h-auto lg:flex-[1.4] lg:border-r">
          <WebPreview
            url={currentUrl}
            history={previewState.history}
            historyIndex={previewState.index}
            isLoading={isPreviewLoading}
            reloadKey={reloadKey}
            onNavigate={handleNavigate}
            onHistoryBack={handleBack}
            onHistoryForward={handleForward}
            onReload={handleReload}
            onOpenInNewTab={(url) => window.open(url, "_blank", "noopener")}
            onSelectionAction={createActionFromSelection}
          />
        </section>
        <aside className="order-3 flex flex-1 flex-col lg:order-3 lg:flex-[1.4]">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="flex h-full flex-col">
            <TabsList className="grid grid-cols-2 bg-muted/60">
              <TabsTrigger value="chat">Chat</TabsTrigger>
              <TabsTrigger value="agent">Agent ops</TabsTrigger>
            </TabsList>
            <TabsContent value="chat" className="flex-1 flex flex-col">
              <div className="flex flex-1 flex-col gap-3 p-3">
                <ChatPanel
                  messages={chatMessages}
                  input={chatInput}
                  onInputChange={setChatInput}
                  onSend={handleSendChat}
                  onStopStreaming={handleStopStreaming}
                  isStreaming={isStreaming}
                  onApproveAction={handleApproveAction}
                  onEditAction={handleEditAction}
                  onDismissAction={handleDismissAction}
                  modelOptions={chatModelOptions}
                  selectedModel={chatModel}
                  onModelChange={handleModelSelect}
                  noModelsWarning={modelWarning}
                />
              </div>
            </TabsContent>
            <TabsContent value="agent" className="flex-1">
              <div className="grid h-full grid-cols-1 gap-3 p-3 lg:grid-cols-2">
                <AgentLog entries={agentLog} isStreaming={isStreaming} />
                <div className="flex flex-col gap-3">
                  <JobStatus jobs={jobSummaries} />
                  <CrawlManager
                    queue={crawlQueue}
                    defaultScope={defaultScope}
                    onAddUrl={handleQueueAdd}
                    onRemove={handleQueueRemove}
                    onUpdateScope={handleQueueScopeUpdate}
                    onScopePresetChange={setDefaultScope}
                    onRefresh={refreshSeeds}
                    isLoading={isSeedsLoading}
                    errorMessage={seedError}
                  />
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </aside>
      </div>

      <CommandDialog open={commandOpen} onOpenChange={setCommandOpen}>
        <CommandInput placeholder="Start crawl, reload, settings…" />
        <CommandList>
          <CommandEmpty>No matches.</CommandEmpty>
          <CommandGroup heading="Workspace">
            {commands.map((command) => (
              <CommandItem
                key={command.id}
                onSelect={() => {
                  command.action();
                  setCommandOpen(false);
                }}
              >
                {command.label}
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </CommandDialog>

      <ActionEditor
        action={editorAction}
        open={editorOpen}
        onOpenChange={setEditorOpen}
        onSave={(updated) => {
          updateAction(updated);
          setEditorAction(updated);
          appendLog({
            id: uid(),
            label: "Action edited",
            detail: `${updated.kind} parameters updated`,
            status: "info",
            timestamp: new Date().toISOString(),
          });
        }}
      />

      <Sheet open={settingsOpen} onOpenChange={setSettingsOpen}>
        <SheetContent className="flex w-full flex-col gap-4 overflow-y-auto sm:max-w-xl">
          <SheetHeader>
            <SheetTitle>Workspace settings</SheetTitle>
          </SheetHeader>
          <Tabs defaultValue="models" className="w-full">
            <TabsList>
              <TabsTrigger value="models">Models</TabsTrigger>
              <TabsTrigger value="safety">Safety</TabsTrigger>
              <TabsTrigger value="about">About</TabsTrigger>
            </TabsList>
            <TabsContent value="models" className="space-y-3 py-3">
              {modelStatus.length === 0 ? (
                <div className="space-y-2 text-sm text-muted-foreground">
                  <Skeleton className="h-5 w-40" />
                  <Skeleton className="h-5 w-60" />
                  <Skeleton className="h-5 w-32" />
                  <p>
                    Model availability loads when the backend connection is established.
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="rounded border p-3 text-sm">
                    <p className="font-medium">Ollama</p>
                    <p className="text-xs text-muted-foreground">
                      Host: {ollamaStatus?.host ?? "unknown"} · Installed: {ollamaStatus?.installed ? "yes" : "no"} · Running: {ollamaStatus?.running ? "yes" : "no"}
                    </p>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-2">
                      <label className="text-sm font-medium">Chat model</label>
                      <Select
                        value={chatModel ?? undefined}
                        onValueChange={setChatModel}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Choose a chat model" />
                        </SelectTrigger>
                        <SelectContent>
                          {modelStatus
                            .filter((model) => model.kind === "chat")
                            .map((model) => (
                              <SelectItem key={model.model} value={model.model}>
                                {model.model}
                              </SelectItem>
                            ))}
                        </SelectContent>
                      </Select>
                      <p className="text-xs text-muted-foreground">
                        Preferred chat model. Fallback uses Gemma3 when available.
                      </p>
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-medium">Embedding model</label>
                      <Select
                        value={embeddingModel ?? undefined}
                        onValueChange={setEmbeddingModel}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Choose embedding model" />
                        </SelectTrigger>
                        <SelectContent>
                          {modelStatus
                            .filter((model) => model.kind === "embedding")
                            .map((model) => (
                              <SelectItem key={model.model} value={model.model}>
                                {model.model}
                              </SelectItem>
                            ))}
                        </SelectContent>
                      </Select>
                      <p className="text-xs text-muted-foreground">
                        Used for chunking and search embeddings.
                      </p>
                    </div>
                  </div>
                  <div className="grid gap-3">
                    {modelStatus.map((model) => (
                      <div
                        key={model.model}
                        className="flex items-center justify-between rounded border p-3"
                      >
                        <div>
                          <h4 className="text-sm font-medium">{model.model}</h4>
                          <p className="text-xs text-muted-foreground">
                            {model.kind}
                            {model.isPrimary ? " · primary" : ""}
                          </p>
                        </div>
                      <Badge variant={model.available !== false ? "default" : "destructive"}>
                        {model.available !== false ? "Available" : "Unavailable"}
                      </Badge>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </TabsContent>
            <TabsContent value="safety" className="space-y-3 py-3 text-sm text-muted-foreground">
              <p>
                Crawls require explicit approval. Large crawls prompt for scope confirmation and
                page budgets before running.
              </p>
            </TabsContent>
            <TabsContent value="about" className="space-y-3 py-3 text-sm text-muted-foreground">
              <p>Self-hosted search copilot UI revamp.</p>
            </TabsContent>
          </Tabs>
          <Button className="self-end" onClick={() => setSettingsOpen(false)}>
            Close
          </Button>
        </SheetContent>
      </Sheet>
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
