"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
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
import { Switch } from "@/components/ui/switch";
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
import { LocalDiscoveryPanel } from "@/components/local-discovery-panel";
import { CopilotHeader } from "@/components/copilot-header";
import { ContextPanel } from "@/components/context-panel";
import { ProgressPanel } from "@/components/ProgressPanel";
import { DocInspector } from "@/components/DocInspector";
import {
  extractSelection,
  fetchModelInventory,
  fetchSeeds,
  searchIndex,
  reindexUrl,
  saveSeed,
  startCrawlJob,
  sendChat,
  autopullModels,
  extractPage,
  subscribeJob,
  summarizeSelection,
  ChatRequestError,
  queueShadowIndex,
  fetchShadowStatus,
  ShadowQueueOptions,
  fetchShadowConfig,
  updateShadowConfig,
  subscribeDiscoveryEvents,
  fetchDiscoveryItem,
  fetchServerTime,
  confirmDiscoveryItem,
  upsertIndexDocument,
  createDomainSeed,
  triggerRefresh,
  fetchPendingDocuments,
} from "@/lib/api";
import type { MetaTimeResponse } from "@/lib/api";
import { resolveChatModelSelection } from "@/lib/chat-model";
import { recordVisit, requestShadowCrawl } from "@/lib/shadow";
import { desktop } from "@/lib/desktop";
import type {
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
  PageExtractResponse,
  DiscoveryPreview,
  ShadowConfig,
  ShadowStatus,
  PendingDocument,
} from "@/lib/types";
import { PendingEmbedsCard } from "@/components/pending-embeds-card";
import { ShadowProgress } from "@/components/shadow-progress";
import { NavProgressHud } from "@/components/nav-progress-hud";
import { devlog } from "@/lib/devlog";
import { useNavProgress } from "@/hooks/use-nav-progress";
import { normalizeInput } from "@/lib/normalize-input";
import { AGENT_ENABLED, IN_APP_BROWSER_ENABLED } from "@/lib/flags";

const INITIAL_URL = "https://news.ycombinator.com";
const MODEL_STORAGE_KEY = "chat:model";
const FEATURE_LOCAL_DISCOVERY = String(process.env.NEXT_PUBLIC_FEATURE_LOCAL_DISCOVERY ?? "");
const LOCAL_DISCOVERY_ENABLED = ["1", "true", "yes", "on"].includes(
  FEATURE_LOCAL_DISCOVERY.trim().toLowerCase(),
);

function uid() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
}

function modelSupportsVision(model: string | null | undefined) {
  if (!model) return false;
  const lowered = model.toLowerCase();
  return lowered.includes("vision") || lowered.includes("multimodal") || lowered.includes("vl");
}

function isHttpUrl(candidate: string | null | undefined) {
  if (!candidate) return false;
  try {
    const parsed = new URL(candidate);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function resolveLiveFallbackUrl(candidate: unknown): string | null {
  if (typeof candidate !== "string") {
    return null;
  }
  const trimmed = candidate.trim();
  if (!trimmed) {
    return null;
  }
  if (!isHttpUrl(trimmed)) {
    return null;
  }
  try {
    return new URL(trimmed).toString();
  } catch {
    return null;
  }
}

function isSelectionActionPayload(payload: unknown): payload is SelectionActionPayload {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const candidate = payload as Record<string, unknown>;
  const selection = (candidate as { selection?: unknown }).selection;
  const url = (candidate as { url?: unknown }).url;
  if (typeof selection !== "string" || typeof url !== "string") {
    return false;
  }
  const context = (candidate as { context?: unknown }).context;
  if (context !== undefined && typeof context !== "string") {
    return false;
  }
  const boundingRect = (candidate as { boundingRect?: unknown }).boundingRect;
  if (boundingRect === undefined || boundingRect === null) {
    return true;
  }
  if (typeof boundingRect !== "object") {
    return false;
  }
  const rect = boundingRect as Record<string, unknown>;
  return (
    typeof rect.x === "number" &&
    typeof rect.y === "number" &&
    typeof rect.width === "number" &&
    typeof rect.height === "number"
  );
}

export type CitationIndexStatus = "idle" | "loading" | "success" | "error";

export interface CitationIndexRecord {
  status: CitationIndexStatus;
  error: string | null;
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

interface CitationIndexingOptions {
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

export async function indexCitationUrls(
  urls: readonly string[],
  options: CitationIndexingOptions,
): Promise<void> {
  for (const url of urls) {
    options.setStatus(url, "loading");
    try {
      if (options.shadowModeEnabled) {
        await options.queueShadowIndex(url, { reason: 'manual' });
      } else {
        await options.handleQueueAdd(url, "page", "Auto-indexed from chat citation");
      }
      options.setStatus(url, "success");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : String(error ?? "Failed to index citation");
      options.setStatus(url, "error", message);
      options.appendLog({
        id: uid(),
        label: "Citation indexing failed",
        detail: `${url}: ${message}`,
        status: "error",
        timestamp: new Date().toISOString(),
      });
      options.pushToast(message, { variant: "destructive" });
    }
  }
}

type ChatLinkNavigationDecision =
  | { action: "navigate"; url: string }
  | { action: "external"; url: string }
  | { action: "ignore" };

export function resolveChatLinkNavigation(
  currentPreviewUrl: string | null | undefined,
  rawUrl: string,
): ChatLinkNavigationDecision {
  const candidate = typeof rawUrl === "string" ? rawUrl.trim() : "";
  if (!candidate) {
    return { action: "ignore" };
  }

  const hasPreviewBase = Boolean(currentPreviewUrl && isHttpUrl(currentPreviewUrl));
  const baseUrl = hasPreviewBase ? (currentPreviewUrl as string) : undefined;

  let parsed: URL;
  try {
    parsed = baseUrl ? new URL(candidate, baseUrl) : new URL(candidate);
  } catch {
    try {
      parsed = new URL(candidate);
    } catch {
      return { action: "ignore" };
    }
  }

  const normalized = parsed.toString();

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return { action: "external", url: normalized };
  }

  if (!hasPreviewBase) {
    return { action: "external", url: normalized };
  }

  let previewHost: string | null = null;
  try {
    previewHost = baseUrl ? new URL(baseUrl).host : null;
  } catch {
    previewHost = null;
  }

  if (previewHost && parsed.host === previewHost) {
    return { action: "navigate", url: normalized };
  }

  return { action: "external", url: normalized };
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
    createdAt: "",
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

interface CrawlMonitorState {
  running: boolean;
  statusText: string | null;
  jobId: string | null;
  targetUrl: string | null;
  scope: CrawlScope | null;
  error: string | null;
  lastUpdated: number | null;
}

interface AppShellProps {
  initialUrl?: string | null;
  initialContext?: PageExtractResponse | null;
}

export function AppShell({ initialUrl, initialContext }: AppShellProps = {}) {
  const router = useRouter();
  const liveFallbackUrl =
    (typeof process !== "undefined"
      ? process.env.NEXT_PUBLIC_LIVE_FALLBACK_URL?.trim()
      : "") || null;
  const browserHref = typeof window !== "undefined" ? window.location.href : null;
  const sanitizedInitialUrl = useMemo(() => {
    if (typeof initialUrl === "string") {
      const trimmed = initialUrl.trim();
      if (trimmed.length > 0) {
        return trimmed;
      }
    }
    return INITIAL_URL;
  }, [initialUrl]);

  const [previewState, setPreviewState] = useState(() => ({
    history: [sanitizedInitialUrl],
    index: 0,
  }));
  const [reloadKey, setReloadKey] = useState(0);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(DEFAULT_CHAT_MESSAGES);
  const [chatInput, setChatInput] = useState("");
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [agentLog, setAgentLog] = useState<AgentLogEntry[]>(DEFAULT_AGENT_LOG);
  const [jobSummaries, setJobSummaries] = useState<JobStatusSummary[]>(DEFAULT_JOB_STATUS);
  const [crawlQueue, setCrawlQueue] = useState<CrawlQueueItem[]>([]);
  const [seedRevision, setSeedRevision] = useState<string | null>(null);
  const [isSeedsLoading, setIsSeedsLoading] = useState(false);
  const [seedError, setSeedError] = useState<string | null>(null);
  const [defaultScope, setDefaultScope] = useState<CrawlScope>("page");
  const [omniboxValue, setOmniboxValue] = useState(sanitizedInitialUrl);
  const [commandOpen, setCommandOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("chat");
  const [modelStatus, setModelStatus] = useState<ModelStatus[]>([]);
  const [chatModel, setChatModel] = useState<string | null>(null);
  const [embeddingModel, setEmbeddingModel] = useState<string | null>(null);
  const [ollamaStatus, setOllamaStatus] = useState<OllamaStatus | null>(null);
  const [chatModels, setChatModels] = useState<string[]>([]);
  const [modelWarning, setModelWarning] = useState<string | null>(null);
  const [isAutopulling, setIsAutopulling] = useState(false);
  const [autopullMessage, setAutopullMessage] = useState<string | null>(null);
  const [pageContext, setPageContext] = useState<PageExtractResponse | null>(initialContext ?? null);
  const [docMetadata, setDocMetadata] = useState<Record<string, unknown> | null>(null);
  const [includeContext, setIncludeContext] = useState(Boolean(initialContext));
  const [isExtractingContext, setIsExtractingContext] = useState(false);
  const [manualContextTrigger, setManualContextTrigger] = useState(0);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [citationIndexState, setCitationIndexState] = useState<Record<string, CitationIndexRecord>>({});
  const [editorAction, setEditorAction] = useState<ProposedAction | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [searchState, setSearchState] = useState<SearchState>(() => createInitialSearchState());
  const [discoveryItems, setDiscoveryItems] = useState<DiscoveryPreview[]>([]);
  const [discoveryBusyIds, setDiscoveryBusyIds] = useState<Set<string>>(() => new Set());
  const [crawlMonitor, setCrawlMonitor] = useState<CrawlMonitorState>({
    running: false,
    statusText: null,
    jobId: null,
    targetUrl: null,
    scope: null,
    error: null,
    lastUpdated: null,
  });
  const clientTimezone = useMemo(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone ?? "UTC",
    [],
  );
  const [timeMeta, setTimeMeta] = useState<MetaTimeResponse | null>(null);
  const navEvent = useNavProgress((state) => state.current);
  const timeSummary = useMemo(() => {
    if (!timeMeta) return null;
    let serverLocal = timeMeta.server_time;
    let serverUtc = timeMeta.server_time_utc;
    try {
      serverLocal = new Date(timeMeta.server_time).toLocaleString();
    } catch {
      serverLocal = timeMeta.server_time;
    }
    try {
      serverUtc = new Date(timeMeta.server_time_utc).toLocaleString(undefined, { timeZone: "UTC" });
    } catch {
      serverUtc = timeMeta.server_time_utc;
    }
    return {
      serverLocal,
      serverUtc,
      serverZone: timeMeta.server_timezone,
      clientZone: clientTimezone,
    };
  }, [timeMeta, clientTimezone]);

  const omniboxRef = useRef<HTMLInputElement | null>(null);
  const chatAbortRef = useRef<AbortController | null>(null);
  const jobSubscriptions = useRef(new Map<string, () => void>());
  const chatHistoryRef = useRef<ChatMessage[]>(chatMessages);
  const crawlQueueRef = useRef<CrawlQueueItem[]>(crawlQueue);
  const searchAbortRef = useRef<AbortController | null>(null);
  const lastSuccessfulModelRef = useRef<string | null>(null);
  const autopullAttemptedRef = useRef(false);
  const shadowWatcherRef = useRef<{ cancel: () => void } | null>(null);
  const lastNavEventRef = useRef<{ url: string; tabId: number | null } | null>(null);
  const shadowNotifiedRef = useRef(new Set<string>());
  const discoveryErrorNotifiedRef = useRef(false);

  const agentEnabled = AGENT_ENABLED;
  const [fallbackUrl, setFallbackUrl] = useState<string | null>(() => liveFallbackUrl);
  const liveFallbackRef = useRef<string | null>(liveFallbackUrl);

  const buildWorkspaceHref = useCallback((url: string) => {
    const params = new URLSearchParams({ url });
    return `/workspace?${params.toString()}`;
  }, []);

  const pushWorkspaceRoute = useCallback(
    (url: string, replace = false) => {
      const href = buildWorkspaceHref(url);
      if (replace) {
        router.replace(href);
      } else {
        router.push(href);
      }
    },
    [buildWorkspaceHref, router],
  );

  const currentUrl = previewState.history[previewState.index];
  const normalizedCurrentUrl = resolveLiveFallbackUrl(currentUrl);
  const currentUrlIsHttp = isHttpUrl(currentUrl);
  const normalizedBrowserUrl = resolveLiveFallbackUrl(browserHref);
  const liveFallbackActive = Boolean(
    fallbackUrl &&
      ((normalizedCurrentUrl && fallbackUrl === normalizedCurrentUrl) ||
        (normalizedBrowserUrl && fallbackUrl === normalizedBrowserUrl)),
  );
  const envInAppBrowserEnabled =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_IN_APP_BROWSER_ENABLED === "true";
  const baseInAppBrowserEnabled = IN_APP_BROWSER_ENABLED;
  const inAppBrowserEnabled = (envInAppBrowserEnabled || baseInAppBrowserEnabled) && !liveFallbackActive;
  const livePreviewEnabled = inAppBrowserEnabled && !liveFallbackActive;
  const hasDocuments = true;
  const crawlButtonLabel = defaultScope === "page" ? "Crawl page" : "Crawl domain";
  const [shadowModeEnabled, setShadowModeEnabled] = useState<boolean>(false);
  const [shadowConfig, setShadowConfig] = useState<ShadowConfig | null>(null);
  const [shadowConfigLoading, setShadowConfigLoading] = useState(true);
  const [shadowConfigSaving, setShadowConfigSaving] = useState(false);
  const [shadowConfigError, setShadowConfigError] = useState<string | null>(null);
  const [pendingDocs, setPendingDocs] = useState<PendingDocument[]>([]);
  const [shadowJobId, setShadowJobId] = useState<string | null>(null);
  const shadowModeEnabledRef = useRef(shadowModeEnabled);
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

  useEffect(() => {
    liveFallbackRef.current = fallbackUrl;
  }, [fallbackUrl]);

  const openLiveUrl = useCallback(
    async (value: string) => {
      const trimmed = value.trim();
      if (
        !trimmed ||
        typeof window === "undefined" ||
        !window.omni?.openUrl ||
        !isHttpUrl(trimmed)
      ) {
        return;
      }
      const normalizedTarget = resolveLiveFallbackUrl(trimmed);
      if (!normalizedTarget) {
        return;
      }
      devlog({ evt: "ui.live.open", url: normalizedTarget });
      setFallbackUrl((existing) => (existing === normalizedTarget ? null : existing));
      if (liveFallbackRef.current === normalizedTarget) {
        liveFallbackRef.current = null;
      }
      try {
        await window.omni.openUrl(normalizedTarget);
      } catch (error) {
        const message =
          error instanceof Error ? error.message : String(error ?? "Live preview unavailable");
        devlog({ evt: "ui.live.open_error", url: normalizedTarget, message });
        setIsPreviewLoading(false);
        setFallbackUrl(normalizedTarget);
        liveFallbackRef.current = normalizedTarget;
        pushToast(message, { variant: "destructive" });
      }
    },
    [pushToast],
  );

  const fallbackContextRef = useRef<{
    extract: () => Promise<void> | void;
    toast: typeof pushToast;
    currentUrl: string | null | undefined;
  }>({
    extract: async () => {},
    toast: pushToast,
    currentUrl,
  });

  const setCitationIndexStatus = useCallback(
    (url: string, status: CitationIndexStatus, error?: string | null) => {
      setCitationIndexState((state) => ({
        ...state,
        [url]: { status, error: error ?? null },
      }));
    },
    [],
  );

  const dismissToast = useCallback((id: string) => {
    setToasts((items) => items.filter((toast) => toast.id !== id));
  }, []);

  useEffect(() => {
    devlog({ evt: "ui.mount" });
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const meta = await fetchServerTime();
        if (!cancelled) {
          setTimeMeta(meta);
        }
      } catch (error) {
        devlog({ evt: "ui.time.error", error: error instanceof Error ? error.message : String(error) });
      }
    };
    load();
    const interval = window.setInterval(load, 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setShadowConfigLoading(true);
      setShadowConfigError(null);
      try {
        const config = await fetchShadowConfig();
        if (cancelled) {
          return;
        }
        setShadowConfig(config);
        setShadowModeEnabled(Boolean(config.enabled));
      } catch (error) {
        if (cancelled) {
          return;
        }
        const message =
          error instanceof Error
            ? error.message
            : String(error ?? "Unable to load shadow mode status");
        setShadowConfigError(message);
        setShadowModeEnabled(false);
      } finally {
        if (!cancelled) {
          setShadowConfigLoading(false);
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    window.appBridge?.setShadowMode?.(shadowModeEnabled);
  }, [shadowModeEnabled]);

  useEffect(() => {
    setPreviewState((state) => {
      const current = state.history[state.index];
      if (current === sanitizedInitialUrl) {
        return state;
      }
      return {
        history: [sanitizedInitialUrl],
        index: 0,
      };
    });
    setOmniboxValue(sanitizedInitialUrl);
  }, [sanitizedInitialUrl]);

  useEffect(() => {
    if (typeof initialContext === "undefined") {
      return;
    }
    setPageContext(initialContext ?? null);
    setIncludeContext(Boolean(initialContext));
  }, [initialContext]);

  useEffect(() => {
    setChatMessages((messages) => {
      if (messages.length === 0) {
        return messages;
      }

      const [first, ...rest] = messages;
      const timestamp = typeof first.createdAt === "string" ? first.createdAt.trim() : "";
      if (timestamp && !Number.isNaN(new Date(timestamp).getTime())) {
        return messages;
      }

      return [{ ...first, createdAt: new Date().toISOString() }, ...rest];
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!currentUrl || !/^https?:/i.test(currentUrl)) {
      setDocMetadata(null);
      return;
    }
    const controller = new AbortController();
    const loadMetadata = async () => {
      try {
        const listResp = await fetch(
          `/api/docs?query=${encodeURIComponent(currentUrl)}`,
          { signal: controller.signal },
        );
        if (!listResp.ok) {
          if (!cancelled) {
            setDocMetadata(null);
          }
          return;
        }
        const payload = (await listResp.json()) as { items?: Array<Record<string, unknown>> };
        const items = Array.isArray(payload.items) ? payload.items : [];
        const match =
          items.find((item) => typeof item.url === "string" && item.url === currentUrl) ??
          items[0];
        if (!match) {
          if (!cancelled) {
            setDocMetadata(null);
          }
          return;
        }
        if (match && typeof match.id === "string" && match.id) {
          const detailResp = await fetch(`/api/docs/${match.id}`, { signal: controller.signal });
          if (detailResp.ok) {
            const detailPayload = await detailResp.json();
            if (!cancelled) {
              const detail = detailPayload?.item ?? match;
              setDocMetadata(detail as Record<string, unknown>);
            }
            return;
          }
        }
        if (!cancelled) {
          setDocMetadata(match as Record<string, unknown>);
        }
      } catch (error) {
        if (!cancelled) {
          setDocMetadata(null);
        }
      }
    };

    void loadMetadata();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [currentUrl]);

  const navigateTo = useCallback(
    (inputValue: string) => {
      const value = inputValue.trim();
      if (!value) return;
      devlog({ evt: "ui.navigate", url: value });
      setIsPreviewLoading(true);
      setPageContext(null);
      setIncludeContext(false);
      setPreviewState((state) => {
        const nextHistory = state.history.slice(0, state.index + 1);
        nextHistory.push(value);
        return {
          history: nextHistory,
          index: nextHistory.length - 1,
        };
      });
      pushWorkspaceRoute(value);
      if (inAppBrowserEnabled) {
        void openLiveUrl(value);
      }
    },
    [inAppBrowserEnabled, openLiveUrl, pushWorkspaceRoute]
  );

  const replaceUrl = useCallback(
    (target: string) => {
      const value = target.trim();
      if (!value) return;
      setIsPreviewLoading(true);
      setPageContext(null);
      setIncludeContext(false);
      setPreviewState((state) => {
        const nextHistory = [...state.history];
        nextHistory[state.index] = value;
        return {
          history: nextHistory,
          index: state.index,
        };
      });
      pushWorkspaceRoute(value, true);
      if (inAppBrowserEnabled) {
        void openLiveUrl(value);
      }
    },
    [inAppBrowserEnabled, openLiveUrl, pushWorkspaceRoute]
  );

  const handleNavigate = useCallback(
    (url: string, options?: { replace?: boolean }) => {
      const target = url.trim();
      if (!target) return;
      setOmniboxValue(target);
      if (options?.replace) {
        replaceUrl(target);
      } else {
        navigateTo(target);
      }
    },
    [navigateTo, replaceUrl]
  );

  const handleOpenInNewTab = useCallback((url: string) => {
    const target = url.trim();
    if (!target) return;
    devlog({ evt: "ui.preview.open_external", url: target });
    if (typeof window !== "undefined") {
      window.open(target, "_blank", "noopener,noreferrer");
    }
  }, []);

  const handleChatLink = useCallback(
    (url: string) => {
      const decision = resolveChatLinkNavigation(currentUrl, url);
      if (decision.action === "navigate") {
        handleNavigate(decision.url);
      } else if (decision.action === "external") {
        handleOpenInNewTab(decision.url);
      }
    },
    [currentUrl, handleNavigate, handleOpenInNewTab],
  );

  const handleBack = useCallback(() => {
    setPreviewState((state) => {
      if (state.index === 0) return state;
      const nextIndex = state.index - 1;
      const nextUrl = state.history[nextIndex];
      setIsPreviewLoading(true);
      setPageContext(null);
      setIncludeContext(false);
      setOmniboxValue(nextUrl);
      if (inAppBrowserEnabled && nextUrl) {
        pushWorkspaceRoute(nextUrl, true);
        void openLiveUrl(nextUrl);
      }
      return { ...state, index: nextIndex };
    });
  }, [inAppBrowserEnabled, openLiveUrl, pushWorkspaceRoute]);

  const handleForward = useCallback(() => {
    setPreviewState((state) => {
      if (state.index >= state.history.length - 1) return state;
      const nextIndex = state.index + 1;
      const nextUrl = state.history[nextIndex];
      setIsPreviewLoading(true);
      setPageContext(null);
      setIncludeContext(false);
      setOmniboxValue(nextUrl);
      if (inAppBrowserEnabled && nextUrl) {
        pushWorkspaceRoute(nextUrl, true);
        void openLiveUrl(nextUrl);
      }
      return { ...state, index: nextIndex };
    });
  }, [inAppBrowserEnabled, openLiveUrl, pushWorkspaceRoute]);

  const handleReload = useCallback(() => {
    setIsPreviewLoading(true);
    setReloadKey((key) => key + 1);
    if (currentUrl && inAppBrowserEnabled) {
      void openLiveUrl(currentUrl);
    }
  }, [currentUrl, inAppBrowserEnabled, openLiveUrl]);

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
        extras: seed.extras,
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


  const handleShadowToggle = useCallback(
    async (next: boolean) => {
      const previous = shadowModeEnabled;
      if (next === previous) {
        return;
      }
      setShadowModeEnabled(next);
      setShadowConfigSaving(true);
      setShadowConfigError(null);
      try {
        const config = await updateShadowConfig({ enabled: next });
        setShadowConfig(config);
        setShadowModeEnabled(Boolean(config.enabled));
        setShadowConfigError(null);
        devlog({ evt: "ui.shadow.mode", enabled: Boolean(config.enabled) });
        pushToast(config.enabled ? "Shadow mode enabled" : "Shadow mode disabled");
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : String(error ?? "Failed to update shadow mode");
        setShadowModeEnabled(previous);
        setShadowConfigError(message);
        pushToast(message, { variant: "destructive" });
        devlog({ evt: "ui.shadow.toggle_error", enabled: next, message });
      } finally {
        setShadowConfigSaving(false);
      }
    },
    [pushToast, shadowModeEnabled],
  );

  useEffect(() => {
    shadowModeEnabledRef.current = shadowModeEnabled;
  }, [shadowModeEnabled]);

  useEffect(() => {
    if (!desktop || typeof desktop.onShadowToggle !== "function") {
      return;
    }
    const off = desktop.onShadowToggle(() => {
      const next = !shadowModeEnabledRef.current;
      void handleShadowToggle(next);
    });
    return () => {
      if (typeof off === "function") {
        off();
      }
    };
  }, [handleShadowToggle]);

  const refreshModels = useCallback(async () => {
    try {
      const inventory = await fetchModelInventory();
      setModelStatus(inventory.models);
      setOllamaStatus(inventory.status);
      setChatModels(inventory.chatModels);
      setEmbeddingModel(inventory.configured.embedder);
      setModelWarning(
        inventory.chatModels.length === 0
          ? "No chat models detected. Click install to pull Gemma3 automatically."
          : null,
      );
      if (inventory.chatModels.length > 0) {
        setAutopullMessage(null);
      }
      const stored =
        typeof window !== "undefined" ? window.localStorage.getItem(MODEL_STORAGE_KEY) : null;
      const nextModel = resolveChatModelSelection({
        available: inventory.chatModels,
        configured: inventory.configured,
        stored: stored && stored.trim() ? stored.trim() : null,
        previous: lastSuccessfulModelRef.current,
      });
      setChatModel(nextModel);
      lastSuccessfulModelRef.current = nextModel;
      devlog({ evt: "ui.models.loaded", available: inventory.chatModels.length, model: nextModel });
      return inventory;
    } catch (error) {
      console.warn("Unable to load model inventory", error);
      devlog({ evt: "ui.models.error", message: error instanceof Error ? error.message : String(error) });
      throw error instanceof Error ? error : new Error(String(error));
    }
  }, []);

  const handleAutopull = useCallback(async () => {
    if (isAutopulling) return;
    setIsAutopulling(true);
    setAutopullMessage("Starting Gemma3 install…");
    devlog({ evt: "ui.models.autopull.start" });
    try {
      const result = await autopullModels(["gemma3", "gpt-oss"]);
      if (result.reason === "already_installed") {
        setAutopullMessage("Models already installed. Refreshing…");
        await refreshModels();
        devlog({ evt: "ui.models.autopull.skip", reason: result.reason });
        return;
      }
      setAutopullMessage("Downloading Gemma3… this may take a few minutes.");
      for (let attempt = 0; attempt < 12; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 5000));
        try {
          const inventory = await refreshModels();
          if (inventory && inventory.chatModels.length > 0) {
            setAutopullMessage("Gemma3 ready.");
            devlog({ evt: "ui.models.autopull.complete" });
            return;
          }
        } catch (refreshError) {
          console.warn("Autopull poll failed", refreshError);
        }
      }
      setAutopullMessage("Install still running. Check Ollama CLI for progress.");
      devlog({ evt: "ui.models.autopull.pending" });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error ?? "Autopull failed");
      setAutopullMessage(`Install failed: ${message}`);
      devlog({ evt: "ui.models.autopull.error", message });
      pushToast(message, { variant: "destructive" });
    } finally {
      setIsAutopulling(false);
    }
  }, [isAutopulling, refreshModels, pushToast]);

  useEffect(() => {
    if (chatModels.length > 0) {
      autopullAttemptedRef.current = false;
      return;
    }
    if (isAutopulling || autopullAttemptedRef.current) {
      return;
    }
    autopullAttemptedRef.current = true;
    setAutopullMessage((current) => current ?? "No chat models detected. Installing Gemma3…");
    devlog({ evt: "ui.models.autopull.auto" });
    void handleAutopull();
  }, [chatModels, handleAutopull, isAutopulling]);

  const handleExtractContext = useCallback(async () => {
    const targetUrl = currentUrl?.trim();
    if (!targetUrl) return;
    setIsExtractingContext(true);
    devlog({ evt: "ui.extract.start", url: targetUrl, vision: modelSupportsVision(chatModel) });
    try {
      const result = await extractPage(targetUrl, { vision: modelSupportsVision(chatModel) });
      setPageContext(result);
      setIncludeContext(true);
      devlog({ evt: "ui.extract.done", url: result.url, hasImg: Boolean(result.screenshot_b64) });
      pushToast("Captured page context");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error ?? "Extraction failed");
      devlog({ evt: "ui.extract.fail", url: targetUrl, message });
      pushToast(message, { variant: "destructive" });
    } finally {
      setIsExtractingContext(false);
    }
  }, [chatModel, currentUrl, pushToast]);

  const handleManualContext = useCallback(
    (text: string, title?: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      const manual: PageExtractResponse = {
        url: currentUrl,
        text: trimmed,
        title: title && title.trim() ? title.trim() : "Manual context",
      };
      setPageContext(manual);
      setIncludeContext(true);
      devlog({ evt: "ui.context.manual", chars: trimmed.length });
      pushToast("Manual context saved");
    },
    [currentUrl, pushToast]
  );

  const handleClearContext = useCallback(() => {
    setPageContext(null);
    setIncludeContext(false);
    devlog({ evt: "ui.context.clear" });
  }, []);

  useEffect(() => {
    fallbackContextRef.current = {
      extract: handleExtractContext,
      toast: pushToast,
      currentUrl,
    };
  }, [currentUrl, handleExtractContext, pushToast]);

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
        devlog({ evt: "ui.crawl.queue", url, scope });
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

  interface RegisterJobOptions {
    onStatus?: (status: JobStatusSummary) => void;
  }

  const registerJob = useCallback(
    (jobId: string, description: string, options: RegisterJobOptions = {}) => {
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
            phase: "queued",
            progress: 10,
            description,
            lastUpdated: new Date().toISOString(),
            stats: {
              pagesFetched: 0,
              normalizedDocs: 0,
              docsIndexed: 0,
              skipped: 0,
              deduped: 0,
              embedded: 0,
            },
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
          options.onStatus?.(status);
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

  const handleManualShadowCrawl = useCallback(async () => {
    const targetUrl = (currentUrl ?? '').trim();
    if (!isHttpUrl(targetUrl)) {
      pushToast('Open a valid http(s) page before crawling.', { variant: 'warning' });
      return;
    }
    try {
      const result = await queueShadowIndex(targetUrl, { reason: 'manual' });
      const jobId = result.jobId ?? null;
      if (jobId) {
        setShadowJobId(jobId);
        if (!jobSubscriptions.current.has(jobId)) {
          registerJob(jobId, `Shadow index ${targetUrl}`);
        }
      }
      pushToast('Shadow crawl queued');
    } catch (error) {
      const message =
        error instanceof Error ? error.message : String(error ?? 'Failed to queue shadow crawl');
      pushToast(message, { variant: 'destructive' });
      devlog({ evt: 'ui.shadow.manual_error', url: targetUrl, message });
    }
  }, [currentUrl, pushToast, queueShadowIndex, registerJob]);

  const handleCrawlDomain = useCallback(async () => {
    const targetUrl = (currentUrl ?? "").trim();
    if (!isHttpUrl(targetUrl)) {
      pushToast("Open a valid http(s) page before crawling.", { variant: "warning" });
      return;
    }

    const scope = defaultScope === "page" ? "page" : "domain";
    const scopeLabel = scope === "page" ? "page" : "domain";
    const domainLabel = (() => {
      try {
        return new URL(targetUrl).hostname;
      } catch {
        return targetUrl;
      }
    })();
    const crawlLabel = scope === "page" ? targetUrl : domainLabel;

    setCrawlMonitor({
      running: true,
      statusText: `Queueing ${scopeLabel} crawl for ${crawlLabel}…`,
      jobId: null,
      targetUrl,
      scope,
      error: null,
      lastUpdated: Date.now(),
    });

    appendLog({
      id: uid(),
      label: "Crawl requested",
      detail: `${scopeLabel === "page" ? "Page" : "Domain"} crawl for ${crawlLabel}`,
      status: "info",
      timestamp: new Date().toISOString(),
    });

    try {
      const seedResult = await createDomainSeed(targetUrl, scope);
      if (seedResult.registry) {
        applySeedRegistry(seedResult.registry);
      }

      const seedRecord = seedResult.seed;
      if (!seedRecord) {
        throw new Error("Unable to resolve seed id after creation");
      }

      if (seedResult.duplicate) {
        pushToast(`${scopeLabel === "page" ? "Page" : "Domain"} already queued. Forcing refresh…`);
      } else {
        pushToast(`Queued ${crawlLabel} for crawling`);
      }

      const refresh = await triggerRefresh({
        seedIds: [seedRecord.id],
        useLlm: false,
        force: true,
      });

      const jobDescription =
        scope === "page"
          ? `Focused crawl for page ${crawlLabel}`
          : `Focused crawl for ${crawlLabel}`;

      if (refresh.jobId) {
        const initialStatus = refresh.deduplicated
          ? `Crawl already in progress for ${crawlLabel}`
          : refresh.created
          ? `Crawl queued for ${crawlLabel}`
          : `Crawl request accepted for ${crawlLabel}`;

        setCrawlMonitor({
          running: true,
          statusText: initialStatus,
          jobId: refresh.jobId,
          targetUrl,
          scope,
          error: null,
          lastUpdated: Date.now(),
        });

        registerJob(refresh.jobId, jobDescription, {
          onStatus: (status) => {
            setCrawlMonitor({
              running: status.state === "queued" || status.state === "running",
              statusText:
                status.state === "queued"
                  ? `Crawl queued for ${crawlLabel}`
                  : status.state === "running"
                  ? status.description ?? `Crawl running for ${crawlLabel}`
                  : status.state === "done"
                  ? `Crawl complete for ${crawlLabel}`
                  : `Crawl failed for ${crawlLabel}`,
              jobId: refresh.jobId,
              targetUrl,
              scope,
              error: status.state === "error" ? status.error ?? "Crawl failed" : null,
              lastUpdated: Date.now(),
            });
          },
        });
      } else {
        setCrawlMonitor({
          running: false,
          statusText: refresh.deduplicated
            ? `Crawl already in progress for ${crawlLabel}`
            : `Crawl request submitted for ${crawlLabel}`,
          jobId: null,
          targetUrl,
          scope,
          error: null,
          lastUpdated: Date.now(),
        });
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error ?? "Crawl failed");
      setCrawlMonitor({
        running: false,
        statusText: `Crawl failed for ${crawlLabel}`,
        jobId: null,
        targetUrl,
        scope,
        error: message,
        lastUpdated: Date.now(),
      });
      pushToast(message, { variant: "destructive" });
      appendLog({
        id: uid(),
        label: "Crawl failed",
        detail: message,
        status: "error",
        timestamp: new Date().toISOString(),
      });
    }
  }, [
    applySeedRegistry,
    appendLog,
    createDomainSeed,
    currentUrl,
    defaultScope,
    pushToast,
    registerJob,
    triggerRefresh,
  ]);

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
      devlog({ evt: "ui.search", query });

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

  const handleSearchQueryChange = useCallback((value: string) => {
    setSearchState((state) => ({ ...state, query: value }));
  }, []);

  const handleLocalSearchSubmit = useCallback(
    (value: string) => {
      const trimmed = value.trim();
      if (!trimmed) {
        return;
      }
      void handleSearch(trimmed);
    },
    [handleSearch]
  );

  const refreshSearch = useCallback(() => {
    if (searchState.query) {
      void handleSearch(searchState.query);
    }
  }, [handleSearch, searchState.query]);

  const handleSendChat = useCallback(
    async (content: string) => {
      const trimmed = content.trim();
      if (!trimmed) return;

      const historySnapshot = chatHistoryRef.current;
      const now = new Date().toISOString();
      const userMessage: ChatMessage = {
        id: uid(),
        role: "user",
        content: trimmed,
        createdAt: now,
      };
      appendMessage(userMessage);
      appendLog({
        id: uid(),
        label: "User message",
        detail: trimmed,
        status: "info",
        timestamp: now,
      });
      setChatInput("");

      chatAbortRef.current?.abort();
      const controller = new AbortController();
      chatAbortRef.current = controller;
      setIsChatLoading(true);

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
          messages.map((message) => (message.id === assistantId ? updater(message) : message))
        );
      };

      const visionEnabled = modelSupportsVision(chatModel);
      const shouldAttachContext = includeContext && !!pageContext?.text;
      const contextUrl = shouldAttachContext ? pageContext?.url ?? currentUrl : currentUrl;
      const textContext = shouldAttachContext ? pageContext?.text ?? null : null;
      const imageContext = shouldAttachContext && visionEnabled ? pageContext?.screenshot_b64 ?? null : null;

      devlog({
        evt: "ui.chat.send",
        model: chatModel ?? "auto",
        hasText: Boolean(textContext),
        hasImg: Boolean(imageContext),
      });

      try {
        const result = await sendChat(historySnapshot, trimmed, {
          model: chatModel,
          signal: controller.signal,
          url: contextUrl || undefined,
          textContext: textContext ?? undefined,
          imageContext: imageContext ?? undefined,
          clientTimezone,
          serverTime: timeMeta?.server_time ?? null,
          serverTimezone: timeMeta?.server_timezone ?? null,
          serverUtc: timeMeta?.server_time_utc ?? null,
        });

        lastSuccessfulModelRef.current = result.model ?? chatModel;

        updateAssistant((message) => ({
          ...message,
          streaming: false,
          content: result.payload.answer || result.payload.reasoning || "",
          answer: result.payload.answer,
          reasoning: result.payload.reasoning,
          citations: result.payload.citations,
          traceId: result.traceId ?? result.payload.trace_id ?? null,
          model: result.model ?? chatModel ?? null,
        }));

        const citationUrls = collectUniqueHttpCitations(result.payload.citations);
        if (citationUrls.length > 0) {
          void indexCitationUrls(citationUrls, {
            shadowModeEnabled,
            queueShadowIndex,
            handleQueueAdd,
            setStatus: setCitationIndexStatus,
            appendLog,
            pushToast,
          });
        }

        devlog({
          evt: "ui.chat.ok",
          trace: result.traceId,
          model: result.model ?? chatModel ?? "unknown",
        });

        appendLog({
          id: uid(),
          label: "Response ready",
          detail: shouldAttachContext ? "Answer generated with page context." : "Answer generated.",
          status: "success",
          timestamp: new Date().toISOString(),
        });

        if (result.model && result.model !== chatModel) {
          setChatModel(result.model);
        }
      } catch (error) {
        if (controller.signal.aborted) {
          updateAssistant((message) => ({
            ...message,
            streaming: false,
            content: message.content || "(cancelled)",
          }));
          appendLog({
            id: uid(),
            label: "Chat cancelled",
            detail: "Request aborted by user",
            status: "warning",
            timestamp: new Date().toISOString(),
          });
        } else if (error instanceof ChatRequestError) {
          const message = error.hint ?? error.message;
          devlog({ evt: "ui.chat.fail", trace: error.traceId, code: error.code });
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
          devlog({ evt: "ui.chat.fail", trace: null, code: "unexpected" });
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
      } finally {
        if (chatAbortRef.current === controller) {
          chatAbortRef.current = null;
        }
        setIsChatLoading(false);
        updateAssistant((message) => ({ ...message, streaming: false }));
      }
    },
    [
      appendLog,
      appendMessage,
      chatModel,
      currentUrl,
      includeContext,
      pageContext,
      pushToast,
      clientTimezone,
      timeMeta,
      handleQueueAdd,
      queueShadowIndex,
      setCitationIndexStatus,
      shadowModeEnabled,
    ]
  );


  const handleCancelChat = useCallback(() => {
    if (chatAbortRef.current) {
      chatAbortRef.current.abort();
      chatAbortRef.current = null;
    }
    if (isChatLoading) {
      setIsChatLoading(false);
    }
    devlog({ evt: "ui.chat.cancel" });
    appendLog({
      id: uid(),
      label: "Chat cancelled",
      detail: "User interrupted generation",
      status: "warning",
      timestamp: new Date().toISOString(),
    });
  }, [appendLog, isChatLoading]);

  const handleModelSelect = useCallback((value: string) => {
    setChatModel(value);
    devlog({ evt: "ui.model.change", model: value });
  }, []);

  const handleAskAgent = useCallback(
    (question: string) => {
      const prompt = question.trim();
      if (!prompt) return;
      if (isChatLoading) {
        handleCancelChat();
      }
      setActiveTab("chat");
      void handleSendChat(prompt);
    },
    [handleSendChat, handleCancelChat, isChatLoading]
  );

  const handleOmniSubmit = useCallback(
    (value: string) => {
      const trimmed = value.trim();
      if (!trimmed) return;

      const normalized = normalizeInput(trimmed);
      if (normalized.kind === "external") {
        handleNavigate(normalized.urlOrPath);
        return;
      }

      if (!hasDocuments) {
        pushToast("Index empty. Crawl this domain first to enable local search.", {
          variant: "warning",
        });
        return;
      }

      if (isChatLoading) {
        handleCancelChat();
      }
      router.push(normalized.urlOrPath);
      void handleSearch(trimmed);
    },
    [handleNavigate, handleSearch, handleCancelChat, hasDocuments, isChatLoading, router, pushToast]
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
      devlog({ evt: "ui.action.approve", kind: action.kind, id: action.id });

      try {
        if (action.kind === "crawl" || action.kind === "queue") {
          const url = String(action.payload.url ?? currentUrl);
          const scope = (action.payload.scope as CrawlScope) || defaultScope;
          const maxPages = Number(action.payload.maxPages ?? 25);
          const maxDepth = Number(action.payload.maxDepth ?? 2);
          const description = `Crawl ${new URL(url).hostname}`;
          devlog({ evt: "ui.crawl.start", url, scope, maxPages, maxDepth });

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
          if (!isSelectionActionPayload(action.payload)) {
            throw new Error("Selection payload is missing required fields");
          }
          const payload = action.payload;
          const selection = payload.selection.trim();
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
            if (message.toLowerCase().includes("selection access blocked")) {
              setManualContextTrigger((value) => value + 1);
              pushToast("Site blocks automated selection. Paste the text manually.", { variant: "warning" });
            }
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
      pushToast,
      setManualContextTrigger,
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
        devlog({ evt: "ui.crawl.remove", id, url: target?.url });
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
        devlog({ evt: "ui.crawl.scope", id, scope, url: target?.url });
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

  const handleIncludeDiscovery = useCallback(
    async (id: string) => {
      setDiscoveryBusyIds((current) => {
        const next = new Set(current);
        next.add(id);
        return next;
      });
      try {
        const item = await fetchDiscoveryItem(id);
        await upsertIndexDocument(item.text, {
          title: item.name,
          meta: { path: item.path },
        });
        await confirmDiscoveryItem(id, "included");
        setDiscoveryItems((items) => items.filter((entry) => entry.id !== id));
        devlog({ evt: "ui.discovery.include", path: item.path, name: item.name });
        pushToast(`Indexed ${item.name}`);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error ?? "Failed to include file");
        pushToast(message, { variant: "destructive" });
        devlog({ evt: "ui.discovery.include_error", id, message });
      } finally {
        setDiscoveryBusyIds((current) => {
          const next = new Set(current);
          next.delete(id);
          return next;
        });
      }
    },
    [pushToast],
  );

  const handleDismissDiscovery = useCallback(
    async (id: string) => {
      setDiscoveryBusyIds((current) => {
        const next = new Set(current);
        next.add(id);
        return next;
      });
      try {
        await confirmDiscoveryItem(id, "dismissed");
        setDiscoveryItems((items) => items.filter((entry) => entry.id !== id));
        devlog({ evt: "ui.discovery.dismiss", id });
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error ?? "Failed to dismiss file");
        pushToast(message, { variant: "destructive" });
        devlog({ evt: "ui.discovery.dismiss_error", id, message });
      } finally {
        setDiscoveryBusyIds((current) => {
          const next = new Set(current);
          next.delete(id);
          return next;
        });
      }
    },
    [pushToast],
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
    if (!normalizedCurrentUrl) {
      setFallbackUrl((existing) => (existing === null ? existing : null));
      return;
    }
    setFallbackUrl((existing) => {
      if (!existing) {
        return existing;
      }
      if (existing !== normalizedCurrentUrl) {
        return null;
      }
      return normalizedCurrentUrl;
    });
  }, [normalizedCurrentUrl]);

  useEffect(() => {
    if (!normalizedCurrentUrl || !inAppBrowserEnabled) {
      return;
    }
    if (liveFallbackRef.current && liveFallbackRef.current === normalizedCurrentUrl) {
      return;
    }
    void openLiveUrl(normalizedCurrentUrl);
  }, [normalizedCurrentUrl, inAppBrowserEnabled, openLiveUrl]);

  useEffect(() => {
    if (typeof window === "undefined" || !window.omni?.onViewerFallback) {
      return;
    }
    const unsubscribe = window.omni.onViewerFallback(({ url }) => {
      const normalizedUrl = resolveLiveFallbackUrl(url);
      const fallbackUrl = normalizedUrl ?? null;
      const previous = liveFallbackRef.current;
      setIsPreviewLoading(false);
      setFallbackUrl(fallbackUrl);
      liveFallbackRef.current = fallbackUrl;
      const loggedUrl = fallbackUrl ?? (typeof url === "string" ? url.trim() : "");
      devlog({ evt: "ui.live.fallback", url: loggedUrl });
      const context = fallbackContextRef.current;
      if (context) {
        const contextUrlForComparison =
          resolveLiveFallbackUrl(context.currentUrl) ??
          (typeof context.currentUrl === "string" ? context.currentUrl.trim() || "" : "");
        const targetUrl = fallbackUrl ?? (contextUrlForComparison || null);
        if (targetUrl && contextUrlForComparison && contextUrlForComparison === targetUrl) {
          void context.extract();
        }
        if (previous !== fallbackUrl) {
          context.toast("Live preview blocked by site policies. Showing Reader instead.", {
            variant: "destructive",
          });
        }
      }
    });
    return () => {
      if (typeof unsubscribe === "function") {
        unsubscribe();
      }
    };
  }, []);

  useEffect(() => {
    if (!LOCAL_DISCOVERY_ENABLED) {
      return;
    }

    const subscription = subscribeDiscoveryEvents(
      (event) => {
        setDiscoveryItems((items) => {
          const index = items.findIndex((existing) => existing.id === event.id);
          if (index >= 0) {
            const next = [...items];
            next[index] = event;
            return next;
          }
          return [...items, event];
        });
        discoveryErrorNotifiedRef.current = false;
      },
      (error) => {
        if (discoveryErrorNotifiedRef.current) {
          return;
        }
        discoveryErrorNotifiedRef.current = true;
        const message =
          error instanceof Error
            ? error.message
            : error && typeof (error as { message?: unknown }).message === "string"
            ? String((error as { message?: unknown }).message)
            : "Local discovery stream unavailable";
        devlog({ evt: "ui.discovery.error", message });
        pushToast(message, { variant: "destructive" });
      },
    );

    return () => {
      subscription?.close();
    };
  }, [pushToast]);

  useEffect(() => {
    if (!shadowModeEnabled || shadowConfigSaving) {
      shadowWatcherRef.current?.cancel?.();
      shadowWatcherRef.current = null;
      setShadowJobId(null);
      return;
    }

    const targetUrl = (currentUrl ?? "").trim();
    if (!targetUrl) return;

    shadowWatcherRef.current?.cancel?.();
    shadowNotifiedRef.current.delete(targetUrl);
    shadowNotifiedRef.current.delete(`${targetUrl}:error`);

    let cancelled = false;
    shadowWatcherRef.current = {
      cancel: () => {
        cancelled = true;
      },
    };

    const run = async () => {
      try {
        await recordVisit({ url: targetUrl });
      } catch (error) {
        const message =
          error instanceof Error ? error.message : String(error ?? 'Failed to record visit');
        devlog({ evt: 'ui.shadow.visit_error', url: targetUrl, message });
      }

      const navContext = lastNavEventRef.current;
      const queueOptions: ShadowQueueOptions = {};
      if (navContext && navContext.url === targetUrl) {
        if (typeof navContext.tabId === 'number') {
          queueOptions.tabId = navContext.tabId;
        }
        queueOptions.reason = 'did-navigate';
      } else {
        queueOptions.reason = 'manual';
      }

      let jobId: string | null = null;

      try {
        const queued = await queueShadowIndex(targetUrl, queueOptions);
        jobId = queued.jobId ?? null;
        if (jobId) {
          setShadowJobId(jobId);
          if (!jobSubscriptions.current.has(jobId)) {
            registerJob(jobId, `Shadow index ${targetUrl}`);
          }
        }
      } catch (error) {
        const message =
          error instanceof Error ? error.message : String(error ?? 'Failed to queue shadow index job');
        devlog({ evt: 'ui.shadow.queue_error', url: targetUrl, message });
        return;
      }

      if (!jobId) {
        devlog({ evt: 'ui.shadow.queue_missing_job', url: targetUrl });
        return;
      }

      while (!cancelled) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        if (cancelled) return;

        const status = await fetchShadowStatus(jobId).catch((error) => {
          const message =
            error instanceof Error ? error.message : String(error ?? 'Failed to fetch shadow status');
          devlog({ evt: 'ui.shadow.status_error', url: targetUrl, jobId, message });
          return null;
        });

        if (!status) {
          return;
        }

        if (!cancelled) {
          if (!jobSubscriptions.current.has(jobId)) {
            registerJob(jobId, `Shadow index ${targetUrl}`);
          }
          setShadowJobId(jobId);
        }

        if (status.state === 'done') {
          if (!shadowNotifiedRef.current.has(targetUrl)) {
            const title = status.title && status.title.trim().length > 0 ? status.title.trim() : targetUrl;
            pushToast(`Indexed: ${title}`);
            shadowNotifiedRef.current.add(targetUrl);
            devlog({
              evt: 'ui.shadow.indexed',
              url: targetUrl,
              title,
              chunks: typeof status.chunks === 'number' ? status.chunks : null,
              docs: status.docs ?? [],
            });
          }
          if (jobId === shadowJobId) {
            setShadowJobId(null);
          }
          return;
        }

        if (status.state === 'error') {
          const key = `${targetUrl}:error`;
          if (!shadowNotifiedRef.current.has(key)) {
            shadowNotifiedRef.current.add(key);
            devlog({
              evt: 'ui.shadow.error',
              url: targetUrl,
              jobId,
              error: status.error ?? null,
              error_kind: status.errorKind ?? null,
            });
          }
          if (jobId === shadowJobId) {
            setShadowJobId(null);
          }
          return;
        }
      }
    };
    void run();

    return () => {
      cancelled = true;
      shadowWatcherRef.current = null;
    };
  }, [currentUrl, pushToast, shadowModeEnabled, shadowConfigSaving, registerJob, shadowJobId, queueShadowIndex]);

  useEffect(() => {
    chatHistoryRef.current = chatMessages;
  }, [chatMessages]);

  useEffect(() => {
    crawlQueueRef.current = crawlQueue;
  }, [crawlQueue]);

  useEffect(() => {
    if (!shadowModeEnabled) {
      setPendingDocs([]);
      return;
    }
    let cancelled = false;
    const tick = async () => {
      try {
        const docs = await fetchPendingDocuments();
        if (!cancelled) {
          setPendingDocs(docs);
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error ?? "Failed to fetch pending embeds");
        devlog({ evt: "ui.shadow.pending_error", message });
      }
    };
    void tick();
    const interval = window.setInterval(() => {
      void tick();
    }, 8000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [shadowModeEnabled]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (chatModel) {
      window.localStorage.setItem(MODEL_STORAGE_KEY, chatModel);
    } else {
      window.localStorage.removeItem(MODEL_STORAGE_KEY);
    }
  }, [chatModel]);

  useEffect(() => {
    if (!navEvent || navEvent.stage !== 'navigated' || !navEvent.url) {
      return;
    }
    lastNavEventRef.current = { url: navEvent.url, tabId: navEvent.tabId ?? null };
    if (shadowModeEnabled) {
      requestShadowCrawl(navEvent.tabId ?? null, navEvent.url, 'did-navigate');
    }
    if (desktop && typeof desktop.shadowCapture === 'function') {
      void (async () => {
        try {
          await desktop.shadowCapture({
            url: navEvent.url,
            tab_id: typeof navEvent.tabId === 'number' ? navEvent.tabId : undefined,
          });
        } catch (error) {
          console.warn('Desktop shadow capture failed', error);
        }
      })();
    }
  }, [navEvent, shadowModeEnabled]);

  useEffect(() => {
    void refreshModels();
  }, [refreshModels]);

  useEffect(() => {
    const subscriptions = jobSubscriptions.current;
    return () => {
      for (const cancel of subscriptions.values()) {
        cancel();
      }
      subscriptions.clear();
      chatAbortRef.current?.abort();
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
      return chatModels;
    }
    if (chatModels.includes(chatModel)) {
      return chatModels;
    }
    return [chatModel, ...chatModels.filter((model) => model !== chatModel)];
  }, [chatModels, chatModel]);

  const supportsVision = useMemo(() => modelSupportsVision(chatModel), [chatModel]);

  const shadowJobSummary = useMemo(
    () => (shadowJobId ? jobSummaries.find((job) => job.jobId === shadowJobId) ?? null : null),
    [jobSummaries, shadowJobId],
  );

  const shadowStatusText = useMemo(() => {
    if (shadowJobSummary) {
      const parts = [shadowJobSummary.phase];
      if (typeof shadowJobSummary.progress === "number") {
        parts.push(`${Math.max(0, Math.min(100, Math.round(shadowJobSummary.progress)))}%`);
      }
      if (shadowJobSummary.message) {
        parts.push(shadowJobSummary.message);
      }
      return parts.filter(Boolean).join(" · ");
    }
    if (shadowConfigError) {
      return shadowConfigError;
    }
    if (shadowConfigLoading) {
      return "Checking status…";
    }
    if (!shadowConfig) {
      return shadowModeEnabled ? "Idle" : "Disabled";
    }
    const details: string[] = [];
    if (typeof shadowConfig.running === "number" && shadowConfig.running > 0) {
      details.push(`${shadowConfig.running} running`);
    }
    if (typeof shadowConfig.queued === "number" && shadowConfig.queued > 0) {
      details.push(`${shadowConfig.queued} queued`);
    }
    if (shadowConfig.lastState && shadowConfig.lastUrl) {
      details.push(`${shadowConfig.lastState} ${shadowConfig.lastUrl}`);
    }
    if (details.length === 0) {
      return shadowModeEnabled ? "Idle" : "Disabled";
    }
    return details.join(" · ");
  }, [shadowConfig, shadowConfigError, shadowConfigLoading, shadowModeEnabled]);

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
      <NavProgressHud />
      <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-muted/40 px-3 py-2 text-xs">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="font-semibold text-foreground">Shadow mode</span>
          <Badge variant={shadowModeEnabled ? "default" : "outline"}>
            {shadowModeEnabled ? "Enabled" : "Disabled"}
          </Badge>
          {shadowConfigLoading || shadowConfigSaving ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" aria-hidden />
          ) : null}
          {shadowStatusText ? (
            <span
              className={`max-w-[16rem] truncate ${
                shadowConfigError ? "text-destructive" : "text-muted-foreground"
              }`}
              title={shadowStatusText}
            >
              {shadowStatusText}
            </span>
          ) : null}
          <Badge variant="outline">Pending {pendingDocs.length}</Badge>
        </div>
        <div className="flex items-center gap-2">
          {!shadowModeEnabled ? (
            <Button
              variant="outline"
              size="sm"
              onClick={handleManualShadowCrawl}
              disabled={shadowConfigLoading || shadowConfigSaving}
            >
              Crawl this page
            </Button>
          ) : null}
          <Switch
            checked={shadowModeEnabled}
            onCheckedChange={handleShadowToggle}
            disabled={shadowConfigLoading || shadowConfigSaving}
            aria-label="Toggle shadow mode"
          />
        </div>
      </div>
      {shadowJobSummary ? <ShadowProgress job={shadowJobSummary} /> : null}
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
          onAskAgent={agentEnabled ? handleAskAgent : undefined}
          onRefresh={searchState.query ? refreshSearch : undefined}
          onQueryChange={handleSearchQueryChange}
          onSubmitQuery={handleLocalSearchSubmit}
          inputDisabled={!hasDocuments}
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
          {livePreviewEnabled ? (
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
              onOpenInNewTab={handleOpenInNewTab}
              onCrawlDomain={handleCrawlDomain}
              crawlDisabled={!currentUrlIsHttp || crawlMonitor.running}
              crawlStatus={crawlMonitor}
              crawlLabel={crawlButtonLabel}
            />
          ) : inAppBrowserEnabled && liveFallbackActive ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 bg-muted/40 p-4 text-center text-sm text-muted-foreground">
              <p className="max-w-md">
                Live preview is unavailable for this site due to content security restrictions. Reader
                mode has been activated automatically.
              </p>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => {
                  if (currentUrl) {
                    void openLiveUrl(currentUrl);
                  }
                }}
              >
                Retry live preview
              </Button>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center bg-muted/40 p-4 text-center text-sm text-muted-foreground">
              In-app preview disabled. Set `NEXT_PUBLIC_IN_APP_BROWSER=true` to browse pages inside the workspace.
            </div>
          )}
        </section>
        <aside className="order-3 flex flex-1 flex-col lg:order-3 lg:flex-[1.4]">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="flex h-full flex-col">
            <TabsList className="grid grid-cols-2 bg-muted/60">
              <TabsTrigger value="chat">Chat</TabsTrigger>
              <TabsTrigger value="agent">Agent ops</TabsTrigger>
            </TabsList>
            <TabsContent value="chat" className="flex-1 flex flex-col">
              <div className="flex flex-1 flex-col gap-3 p-3">
                <ProgressPanel jobId={searchState.jobId} />
                <DocInspector doc={docMetadata} />
                <ContextPanel
                  url={currentUrl}
                  context={pageContext}
                  includeContext={includeContext}
                  onIncludeChange={setIncludeContext}
                  onExtract={handleExtractContext}
                  extracting={isExtractingContext}
                  supportsVision={supportsVision}
                  onManualSubmit={handleManualContext}
                  onClear={handleClearContext}
                  manualOpenTrigger={manualContextTrigger}
                />
                <ChatPanel
                  header={
                    <CopilotHeader
                      chatModels={chatModelOptions}
                      selectedModel={chatModel}
                      onModelChange={handleModelSelect}
                      installing={isAutopulling}
                      onInstallModel={handleAutopull}
                      installMessage={autopullMessage}
                      reachable={Boolean(ollamaStatus?.running)}
                      statusLabel={isChatLoading ? "Generating response" : undefined}
                      timeSummary={timeSummary}
                    />
                  }
                  messages={chatMessages}
                  input={chatInput}
                  onInputChange={setChatInput}
                  onSend={handleSendChat}
                  isBusy={isChatLoading}
                  onCancel={isChatLoading ? handleCancelChat : undefined}
                  onApproveAction={handleApproveAction}
                  onEditAction={handleEditAction}
                  onDismissAction={handleDismissAction}
                  disableInput={chatModels.length === 0 || isAutopulling}
                  onLinkClick={handleChatLink}
                />
              </div>
            </TabsContent>
            <TabsContent value="agent" className="flex-1">
              <div className="grid h-full grid-cols-1 gap-3 p-3 lg:grid-cols-2">
                <AgentLog entries={agentLog} isStreaming={isChatLoading} />
                <div className="flex flex-col gap-3">
                  <JobStatus jobs={jobSummaries} />
                  <PendingEmbedsCard docs={pendingDocs} />
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
                    currentUrl={currentUrl}
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
      {LOCAL_DISCOVERY_ENABLED ? (
        <LocalDiscoveryPanel
          items={discoveryItems}
          busyIds={discoveryBusyIds}
          onInclude={handleIncludeDiscovery}
          onDismiss={handleDismissDiscovery}
        />
      ) : null}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
