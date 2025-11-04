"use client";

import { Loader2, StopCircle } from "lucide-react";
import { AutopilotExecutor, type AutopilotRunResult, type Verb } from "@/autopilot/executor";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent } from "react";
import { useShallow } from "zustand/react/shallow";

import { CopilotHeader } from "@/components/copilot-header";
import { ChatMessageMarkdown } from "@/components/chat-message";
import { AgentTracePanel } from "@/components/AgentTracePanel";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { UsePageContextToggle } from "@/components/UsePageContextToggle";
import { ReasoningToggle } from "@/components/ReasoningToggle";
import { useBrowserNavigation } from "@/hooks/useBrowserNavigation";
import { useLlmStream } from "@/hooks/useLlmStream";
import { incidentBus } from "@/diagnostics/incident-bus";
import {
  autopullModels,
  fetchModelInventory,
  fetchServerTime,
  fetchChatContext,
  runAutopilotTool,
  storeChatMessage,
  type MetaTimeResponse,
  type ModelInventory,
  type ChatContextResponse,
} from "@/lib/api";
import { resolveChatModelSelection } from "@/lib/chat-model";
import { chatClient, ChatRequestError, type ChatPayloadMessage } from "@/lib/chatClient";
import type { AutopilotDirective, AutopilotToolDirective, ChatMessage } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/state/useAppStore";
import { useUIStore } from "@/state/ui";
import { useSafeState } from "@/lib/react-safe";
import { useRenderLoopGuard } from "@/lib/useRenderLoopGuard";

const MODEL_STORAGE_KEY = "workspace:chat:model";
const AUTOPULL_FALLBACK_CANDIDATES = ["gemma3", "gpt-oss"];
const INVENTORY_REFRESH_DELAY_MS = 5_000;

type Banner = { intent: "info" | "error"; text: string };

type ToolExecutionState = {
  status: "idle" | "running" | "success" | "error";
  detail?: string;
};

function extractAutopilotSteps(value: AutopilotDirective | null | undefined): Verb[] | null {
  if (!value) {
    return null;
  }
  const directiveSteps = Array.isArray(value.directive?.steps) ? (value.directive?.steps as Verb[]) : [];
  const topLevelSteps = Array.isArray(value.steps) ? (value.steps as Verb[]) : [];
  const candidates = directiveSteps.length > 0 ? directiveSteps : topLevelSteps;
  if (!candidates || candidates.length === 0) {
    return null;
  }
  return candidates.filter((step): step is Verb => Boolean(step && step.type));
}

function createId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
}

function formatTimestamp(value: string) {
  const trimmed = value?.trim();
  if (!trimmed) return "";
  const date = new Date(trimmed);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  try {
    return date.toLocaleTimeString();
  } catch {
    return "";
  }
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

function formatCitationLabel(value: string) {
  if (!isHttpUrl(value)) {
    return value;
  }
  try {
    const url = new URL(value);
    return url.hostname.replace(/^www\./, "");
  } catch {
    return value;
  }
}

function truncateText(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }
  return value.slice(0, Math.max(0, maxLength - 1)).trimEnd() + "…";
}

function summarizeToolResult(result: Record<string, unknown> | null | undefined): string {
  if (!result) {
    return "OK";
  }
  try {
    const serialized = JSON.stringify(result, null, 2);
    return truncateText(serialized, 400) || "OK";
  } catch {
    return String(result);
  }
}

function captureWindowSelection(maxLength = 4000): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const selection = window.getSelection();
    const text = selection?.toString()?.trim();
    if (!text) {
      return null;
    }
    return truncateText(text, maxLength);
  } catch {
    return null;
  }
}

function countWords(text: string | null | undefined): number | null {
  if (!text) {
    return null;
  }
  const tokens = text.trim().split(/\s+/).filter(Boolean);
  return tokens.length || null;
}

const INITIAL_ASSISTANT_GREETING =
  "Welcome! Paste a URL or ask me to search. I only crawl when you approve each step.";

export function ChatPanel() {
  useRenderLoopGuard("ChatPanel");

  const [messages, setMessages] = useState<ChatMessage[]>(() => [
    {
      id: createId(),
      role: "assistant",
      content: INITIAL_ASSISTANT_GREETING,
      createdAt: new Date().toISOString(),
    },
  ]);
  const [threadId] = useState(() => createId());
  const [input, setInput] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const [banner, setBanner] = useState<Banner | null>(null);
  const [inventory, setInventory] = useState<ModelInventory | null>(null);
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const [inventoryError, setInventoryError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [installing, setInstalling] = useState(false);
  const [installMessage, setInstallMessage] = useState<string | null>(null);
  const [serverTime, setServerTime] = useState<MetaTimeResponse | null>(null);
  const [serverTimeError, setServerTimeError] = useState<string | null>(null);
  const [usePageContext, setUsePageContext] = useState(false);
  const [contextSummary, setContextSummary] = useSafeState<{
    url?: string | null;
    selectionWordCount?: number | null;
  } | null>(null);
  const [toolExecutions, setToolExecutions] = useState<Record<string, ToolExecutionState>>({});
  const [planExecutions, setPlanExecutions] = useState<
    Record<string, { status: "idle" | "running" | "success" | "error"; detail?: string }>
  >({});
  const [pendingDirectives, setPendingDirectives] = useState<Record<string, Verb[]>>({});
  const autopilotExecutor = useMemo(() => new AutopilotExecutor(), []);
  const {
    state: llmStream,
    start: startLlmStream,
    abort: abortLlmStream,
    supported: llmStreamSupported,
  } = useLlmStream();
  const activeStreamRef = useRef<{ requestId: string; messageId: string } | null>(null);
  const streamCompletionRef = useRef<string | null>(null);
  const streamSessionRef = useRef<string | null>(null);

  const messagesRef = useRef<ChatMessage[]>(messages);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const mountedRef = useRef(false);
  const storedModelRef = useRef<string | null>(null);
  const refreshTimeoutRef = useRef<number | null>(null);

  const navigate = useBrowserNavigation();
  const { activeTab } = useAppStore(
    useShallow((state) => ({
      activeTab: state.activeTab?.(),
    })),
  );
  const showReasoning = useUIStore((state) => state.showReasoning);

  const clientTimezone = useMemo(() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone;
    } catch {
      return undefined;
    }
  }, []);
  const clientLocale = useMemo(() => {
    if (typeof navigator === "undefined" || typeof navigator.language !== "string") {
      return undefined;
    }
    return navigator.language;
  }, []);

  const handleRefreshInventory = useCallback(async () => {
    setInventoryLoading(true);
    setInventoryError(null);
    try {
      const snapshot = await fetchModelInventory();
      if (!mountedRef.current) {
        return;
      }
      setInventory(snapshot);
    } catch (error) {
      if (!mountedRef.current) {
        return;
      }
      const message =
        error instanceof Error ? error.message : String(error ?? "Unable to load model inventory");
      setInventory(null);
      setInventoryError(message);
    } finally {
      if (mountedRef.current) {
        setInventoryLoading(false);
      }
    }
  }, []);

  const handleRefreshServerTime = useCallback(async () => {
    try {
      const snapshot = await fetchServerTime();
      if (!mountedRef.current) {
        return;
      }
      setServerTime(snapshot);
      setServerTimeError(null);
    } catch (error) {
      if (!mountedRef.current) {
        return;
      }
      const message =
        error instanceof Error ? error.message : String(error ?? "Unable to fetch server time");
      setServerTime(null);
      setServerTimeError(message);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    if (typeof window !== "undefined") {
      const stored = window.localStorage.getItem(MODEL_STORAGE_KEY);
      if (stored && stored.trim()) {
        storedModelRef.current = stored.trim();
        setSelectedModel(stored.trim());
      }
    }
    void handleRefreshInventory();
    void handleRefreshServerTime();

    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
      if (refreshTimeoutRef.current !== null && typeof window !== "undefined") {
        window.clearTimeout(refreshTimeoutRef.current);
      }
    };
  }, [handleRefreshInventory, handleRefreshServerTime]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    setToolExecutions((prev) => {
      const validKeys = new Set<string>();
      messages.forEach((message) => {
        message.autopilot?.tools?.forEach((_tool, index) => {
          validKeys.add(`${message.id}:${index}`);
        });
      });

      const next: Record<string, ToolExecutionState> = {};
      let changed = false;

      for (const key of validKeys) {
        if (prev[key]) {
          next[key] = prev[key];
        } else {
          changed = true;
        }
      }

      for (const key of Object.keys(prev)) {
        if (!validKeys.has(key)) {
          changed = true;
        }
      }

      if (!changed) {
        return prev;
      }
      return next;
    });
  }, [messages]);

  useEffect(() => {
    setPendingDirectives((prev) => {
      const validIds = new Set(messages.map((message) => message.id));
      let changed = false;
      const next: Record<string, Verb[]> = {};
      for (const id of Object.keys(prev)) {
        if (validIds.has(id)) {
          next[id] = prev[id];
        } else {
          changed = true;
        }
      }
      if (!changed) {
        return prev;
      }
      return next;
    });
  }, [messages]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, isBusy]);

  useEffect(() => {
    if (!usePageContext) {
      setContextSummary(null);
    }
  }, [usePageContext]);

  useEffect(() => {
    const resolved = resolveChatModelSelection({
      available: inventory?.chatModels ?? [],
      configured: inventory?.configured ?? { primary: null, fallback: null, embedder: null },
      stored: storedModelRef.current,
      previous: selectedModel,
    });
    if (resolved !== selectedModel) {
      setSelectedModel(resolved);
      storedModelRef.current = resolved;
    }
  }, [inventory, selectedModel]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    if (selectedModel) {
      window.localStorage.setItem(MODEL_STORAGE_KEY, selectedModel);
    } else {
      window.localStorage.removeItem(MODEL_STORAGE_KEY);
    }
  }, [selectedModel]);

  const statusBanner = useMemo((): Banner | null => {
    if (inventoryLoading) {
      return { intent: "info", text: "Checking available chat models…" };
    }
    if (inventoryError) {
      return { intent: "error", text: `Model inventory failed: ${inventoryError}` };
    }
    if (inventory && !inventory.reachable) {
      return {
        intent: "error",
        text: "Ollama host unreachable. Start Ollama and refresh the inventory.",
      };
    }
    if (inventory && inventory.chatModels.length === 0) {
      return {
        intent: "error",
        text: "No chat-capable models detected. Install a model to enable Copilot chat.",
      };
    }
    if (serverTimeError) {
      return { intent: "info", text: `Time sync unavailable: ${serverTimeError}` };
    }
    return null;
  }, [inventory, inventoryError, inventoryLoading, serverTimeError]);

  const headerStatusLabel = useMemo(() => {
    if (isBusy) {
      return "Responding…";
    }
    if (installing) {
      return "Installing model…";
    }
    if (inventoryLoading) {
      return "Checking models…";
    }
    if (inventoryError) {
      return "Model inventory failed";
    }
    if (inventory && !inventory.reachable) {
      return "Ollama offline";
    }
    if (inventory && inventory.chatModels.length === 0) {
      return "No chat models detected";
    }
    if (selectedModel) {
      return `Ready • ${selectedModel}`;
    }
    return "Idle";
  }, [installing, inventory, inventoryError, inventoryLoading, isBusy, selectedModel]);

  const timeSummary = useMemo(() => {
    if (!serverTime) {
      return null;
    }
    return {
      serverLocal: serverTime.server_time,
      serverUtc: serverTime.server_time_utc,
      serverZone: serverTime.server_timezone,
      clientZone: clientTimezone ?? "local",
    };
  }, [clientTimezone, serverTime]);

  const modelOptions = useMemo(() => {
    if (!inventory) {
      return [] as Array<{ value: string; label: string; description?: string; available?: boolean }>;
    }
    return inventory.models
      .filter((model) => model.kind === "chat")
      .map((model) => {
        const descriptionBits: string[] = [];
        if (model.isPrimary) {
          descriptionBits.push("Primary");
        } else if (model.role === "fallback") {
          descriptionBits.push("Fallback");
        }
        if (model.available === false) {
          descriptionBits.push("Not installed locally");
        }
        return {
          value: model.model,
          label: model.model,
          description: descriptionBits.length > 0 ? descriptionBits.join(" • ") : undefined,
          available: model.available !== false,
        };
      });
  }, [inventory]);

  const autopullCandidates = useMemo(() => {
    const unique = new Set<string>();
    if (inventory?.configured.primary) {
      unique.add(inventory.configured.primary);
    }
    if (inventory?.configured.fallback) {
      unique.add(inventory.configured.fallback);
    }
    (inventory?.chatModels ?? []).forEach((name) => unique.add(name));
    AUTOPULL_FALLBACK_CANDIDATES.forEach((candidate) => unique.add(candidate));
    return Array.from(unique).filter((candidate) => candidate && candidate.trim().length > 0);
  }, [inventory]);

  const llmReachable = inventory ? Boolean(inventory.reachable) : true;
  const chatModelsAvailable = inventory ? inventory.chatModels.length > 0 : true;

  const inputPlaceholder = useMemo(() => {
    if (installing) {
      return "Installing chat model…";
    }
    if (inventory && !llmReachable) {
      return "Start Ollama to chat";
    }
    if (inventory && inventory.chatModels.length === 0) {
      return "Install a chat model to begin";
    }
    return "Ask the copilot";
  }, [installing, inventory, llmReachable]);

  const handleContextToggle = useCallback((value: boolean) => {
    setUsePageContext(value);
    if (!value) {
      setContextSummary(null);
    }
  }, []);

  const updateMessage = useCallback((id: string, updater: (message: ChatMessage) => ChatMessage) => {
    let autopilotSteps: Verb[] | null | undefined;
    let matched = false;
    setMessages((prev) =>
      prev.map((message) => {
        if (message.id !== id) {
          return message;
        }
        matched = true;
        const next = updater(message);
        autopilotSteps = extractAutopilotSteps(next.autopilot);
        return next;
      }),
    );
    if (matched) {
      setPendingDirectives((prev) => {
        const next = { ...prev };
        if (autopilotSteps && autopilotSteps.length > 0) {
          next[id] = autopilotSteps;
        } else {
          delete next[id];
        }
        return next;
      });
    }
  }, []);

  const handleRunAutopilotTool = useCallback(
    async (messageId: string, index: number, tool: AutopilotToolDirective) => {
      const key = `${messageId}:${index}`;
      setToolExecutions((prev) => ({ ...prev, [key]: { status: "running" } }));
      try {
        const result = await runAutopilotTool(tool.endpoint, {
          method: tool.method,
          payload: tool.payload ?? undefined,
          chatId: threadId,
          messageId,
        });
        const summary = summarizeToolResult(result);
        setToolExecutions((prev) => ({
          ...prev,
          [key]: { status: "success", detail: summary },
        }));
        setBanner({ intent: "info", text: `${tool.label} executed.` });
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error ?? "Tool request failed");
        setToolExecutions((prev) => ({
          ...prev,
          [key]: { status: "error", detail: message },
        }));
        setBanner({ intent: "error", text: message });
      }
    },
    [setBanner, threadId],
  );

  const handleRunAutopilotPlan = useCallback(
    async (messageId: string, steps: Verb[]) => {
      const key = `${messageId}:directive`;
      const directiveSteps = pendingDirectives[messageId] ?? steps;
      if (!directiveSteps || directiveSteps.length === 0) {
        setPlanExecutions((prev) => ({
          ...prev,
          [key]: { status: "error", detail: "Directive has no executable steps." },
        }));
        return;
      }
      setPlanExecutions((prev) => ({ ...prev, [key]: { status: "running" } }));
      try {
        const result: AutopilotRunResult = await autopilotExecutor.run(
          { steps: directiveSteps },
          {
            onHeadlessError: (error) => {
              const message = error instanceof Error ? error.message : String(error ?? "headless_failed");
              setBanner({ intent: "error", text: message });
            },
          },
        );
        if (result.headlessErrors.length > 0) {
          const detail = result.headlessErrors.map((error) => error.message).join("; ") || "Headless execution failed.";
          setPlanExecutions((prev) => ({
            ...prev,
            [key]: { status: "error", detail },
          }));
        } else {
          setPlanExecutions((prev) => ({ ...prev, [key]: { status: "success" } }));
          const batchSummary =
            result.headlessBatches > 0
              ? ` (${result.headlessBatches} headless batch${result.headlessBatches === 1 ? "" : "es"})`
              : "";
          setBanner({ intent: "info", text: `Autopilot plan executed${batchSummary}.` });
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error ?? "Autopilot run failed");
        setPlanExecutions((prev) => ({
          ...prev,
          [key]: { status: "error", detail: message },
        }));
        setBanner({ intent: "error", text: message });
      }
    },
    [autopilotExecutor, pendingDirectives, setBanner],
  );

  const handleLinkNavigation = useCallback(
    (url: string, event?: MouseEvent<HTMLAnchorElement>) => {
      const newTab = Boolean(
        event?.metaKey || event?.ctrlKey || event?.shiftKey || (event && event.button === 1),
      );
      navigate(url, { newTab, closePanel: true });
    },
    [navigate],
  );

  const handleCitationClick = useCallback(
    (url: string, event: MouseEvent<HTMLButtonElement>) => {
      const newTab = Boolean(event.metaKey || event.ctrlKey || event.shiftKey || event.button === 1);
      if (isHttpUrl(url)) {
        navigate(url, { newTab, closePanel: true });
      }
    },
    [navigate],
  );

  const handleSend = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || isBusy) {
      if (!trimmed) {
        setInput("");
      }
      return;
    }

    if (inventory && !llmReachable) {
      setBanner({ intent: "error", text: "Cannot send message while Ollama is offline." });
      return;
    }

    if (inventory && inventory.chatModels.length === 0) {
      setBanner({ intent: "error", text: "Install a chat-capable model before chatting." });
      return;
    }

    if (llmStreamSupported && streamSessionRef.current) {
      return;
    }

    const controller = llmStreamSupported ? null : new AbortController();
    abortRef.current = controller;
    setIsBusy(true);
    setBanner(null);

    const historySnapshot = [...messagesRef.current];
    const createdAt = new Date().toISOString();

    const userMessage: ChatMessage = {
      id: createId(),
      role: "user",
      content: trimmed,
      createdAt,
    };
    const assistantId = createId();
    const assistantPlaceholder: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      createdAt,
      streaming: true,
      citations: [],
    };

    setMessages((prev) => [...prev, userMessage, assistantPlaceholder]);
    setInput("");

    void storeChatMessage(threadId, {
      id: userMessage.id,
      role: "user",
      content: trimmed,
    }).catch((error) => console.warn("[chat] failed to persist user message", error));

    let streamedModel: string | null = null;
    let streamedTrace: string | null = null;
    let contextMessage: ChatPayloadMessage | null = null;
    let contextData: ChatContextResponse | null = null;
    let selectionText: string | null = null;
    const browserUrl = typeof window !== "undefined" ? window.location.href : null;
    const browserTitle = typeof document !== "undefined" ? document.title : null;

    if (usePageContext) {
      const contextUrl = activeTab?.url ?? browserUrl ?? undefined;
      const contextTitle = activeTab?.title ?? browserTitle ?? undefined;
      try {
        selectionText = captureWindowSelection();
        if (contextUrl) {
          contextData = await fetchChatContext(threadId, {
            url: contextUrl,
            include: ["selection", "history", "metadata"],
            selection: selectionText,
            title: contextTitle,
            locale: clientLocale ?? undefined,
            time: new Date().toISOString(),
          });
        }
        const combinedSelection = contextData?.selection?.text ?? selectionText ?? null;
        const selectionCount = contextData?.selection?.word_count ?? countWords(combinedSelection);
        const payloadUrl = contextData?.url ?? contextUrl ?? null;
        const payloadTitle =
          contextTitle ?? (contextData?.metadata?.title as string | undefined) ?? browserTitle ?? null;
        if (payloadUrl || payloadTitle || combinedSelection) {
          const contextPayload = {
            url: payloadUrl,
            title: payloadTitle,
            summary: contextData?.summary ?? null,
            selection: combinedSelection,
            selection_word_count: selectionCount,
            metadata: contextData?.metadata ?? {},
            history: contextData?.history ?? [],
            memories: contextData?.memories ?? [],
          };
          contextMessage = {
            role: "system",
            content: JSON.stringify({ context: contextPayload }, null, 2),
          };
          void storeChatMessage(threadId, {
            role: "system",
            content: JSON.stringify({ type: "context", data: contextPayload }),
          }).catch((error) => console.warn("[chat] failed to persist context", error));
          setContextSummary({ url: payloadUrl, selectionWordCount: selectionCount });
        } else {
          setContextSummary({ url: payloadUrl, selectionWordCount: selectionCount });
        }
      } catch (error) {
        const messageText = error instanceof Error ? error.message : "Failed to resolve page context";
        setBanner({ intent: "error", text: messageText });
      }
    }

    const selectionContext = contextData?.selection?.text ?? selectionText ?? null;
    const textContextParts: string[] = [];
    if (usePageContext && browserTitle && browserTitle.trim()) {
      textContextParts.push(browserTitle.trim());
    }
    if (selectionContext && selectionContext.trim()) {
      textContextParts.push(selectionContext);
    }
    const requestUrl = usePageContext
      ? browserUrl ?? activeTab?.url ?? undefined
      : activeTab?.url ?? undefined;
    const textContextPayload = textContextParts.length > 0 ? textContextParts.join("\n\n") : undefined;

    const modelMessages: ChatPayloadMessage[] = [];
    if (contextMessage) {
      modelMessages.push(contextMessage);
    }
    for (const message of historySnapshot) {
      const role = message.role === "agent" ? "system" : message.role;
      if (role !== "system" && role !== "assistant" && role !== "user") {
        continue;
      }
      const baseContent =
        role === "assistant" ? message.answer ?? message.content ?? "" : message.content ?? "";
      if (!baseContent.trim()) {
        continue;
      }
      modelMessages.push({ role, content: baseContent });
    }
    modelMessages.push({ role: "user", content: trimmed });

    const requestId = createId();

    if (llmStreamSupported) {
      activeStreamRef.current = { requestId, messageId: assistantId };
      streamCompletionRef.current = null;
      streamSessionRef.current = requestId;
      const streamBody: Record<string, unknown> = {
        model: selectedModel ?? undefined,
        messages: modelMessages,
        stream: true,
        url: requestUrl,
        text_context: textContextPayload,
        client_timezone: clientTimezone ?? undefined,
        server_time: serverTime?.server_time ?? undefined,
        server_timezone: serverTime?.server_timezone ?? undefined,
        server_time_utc: serverTime?.server_time_utc ?? undefined,
        request_id: requestId,
        chat_id: requestId,
      };
      try {
        await startLlmStream({ requestId, body: streamBody });
      } catch (error) {
        let messageText = error instanceof Error ? error.message : String(error ?? "Stream failed");
        if (messageText === "stream_http_409") {
          messageText = "Another chat response is already streaming. Please wait for it to finish.";
          incidentBus.record("DUPLICATE_SSE", {
            message: "Blocked duplicate chat stream request.",
            severity: "warn",
            detail: { requestId, transport: "sse" },
          });
        } else {
          incidentBus.record("STREAM_ERROR", {
            message: messageText,
            severity: "warn",
            detail: { requestId, transport: "sse" },
          });
        }
        updateMessage(assistantId, (message) => ({
          ...message,
          streaming: false,
          content: message.content
            ? `${message.content}\n\n${messageText}`
            : `Error: ${messageText}`,
        }));
        setBanner({ intent: "error", text: messageText });
        setIsBusy(false);
        activeStreamRef.current = null;
        if (streamSessionRef.current === requestId) {
          streamSessionRef.current = null;
        }
      }
      return;
    }

    try {
      const activeController = controller ?? new AbortController();
      abortRef.current = activeController;
      const result = await chatClient.send({
        messages: modelMessages,
        model: selectedModel ?? undefined,
        url: requestUrl ?? null,
        textContext: textContextPayload ?? null,
        clientTimezone,
        serverTime: serverTime?.server_time ?? undefined,
        serverTimezone: serverTime?.server_timezone ?? undefined,
        serverUtc: serverTime?.server_time_utc ?? undefined,
        signal: activeController.signal,
        requestId,
        chatId: requestId,
        onEvent: (event) => {
          if (event.type === "metadata") {
            streamedModel = event.model ?? streamedModel;
            streamedTrace = event.trace_id ?? streamedTrace;
            updateMessage(assistantId, (message) => ({
              ...message,
              model: streamedModel ?? message.model ?? null,
              traceId: streamedTrace ?? message.traceId ?? null,
            }));
          } else if (event.type === "delta") {
            updateMessage(assistantId, (message) => ({
              ...message,
              streaming: true,
              content: event.answer ?? message.content ?? "",
              answer: event.answer ?? message.answer ?? "",
              reasoning: event.reasoning ?? message.reasoning ?? "",
              citations: event.citations ?? message.citations ?? [],
              autopilot: event.autopilot ?? message.autopilot ?? null,
            }));
          }
        },
      });

      streamedModel = result.model ?? streamedModel;
      streamedTrace = result.traceId ?? streamedTrace;

      updateMessage(assistantId, (message) => ({
        ...message,
        streaming: false,
        content:
          result.payload.message ||
          result.payload.answer ||
          result.payload.reasoning ||
          message.content ||
          "",
        answer: result.payload.answer || null,
        reasoning: result.payload.reasoning || null,
        citations: result.payload.citations ?? [],
        traceId: result.payload.trace_id ?? streamedTrace ?? message.traceId ?? null,
        model: result.payload.model ?? streamedModel ?? message.model ?? null,
        autopilot: result.payload.autopilot ?? null,
        message: result.payload.message || null,
      }));

      void storeChatMessage(threadId, {
        id: assistantId,
        role: "assistant",
        content: result.payload.message || result.payload.answer || result.payload.reasoning || "",
      }).catch((error) => console.warn("[chat] failed to persist assistant message", error));
    } catch (error) {
      if (
        controller?.signal.aborted ||
        (error instanceof DOMException && error.name === "AbortError")
      ) {
        updateMessage(assistantId, (message) => ({
          ...message,
          streaming: false,
          content: message.content || "(cancelled)",
        }));
        setBanner({ intent: "info", text: "Generation cancelled." });
      } else if (error instanceof ChatRequestError) {
        let messageText = error.hint ?? error.message;
        if (error.status === 409) {
          messageText = "Another chat response is already streaming. Please wait for it to finish.";
          incidentBus.record("DUPLICATE_SSE", {
            message: error.message || "Duplicate chat request rejected.",
            severity: "warn",
            detail: { requestId, transport: "http", traceId: error.traceId },
          });
        } else {
          incidentBus.record("CHAT_ERROR", {
            message: error.message,
            severity: "error",
            detail: {
              requestId,
              status: error.status,
              traceId: error.traceId,
              code: error.code,
            },
          });
        }
        updateMessage(assistantId, (message) => ({
          ...message,
          streaming: false,
          content: message.content
            ? `${message.content}\n\n${messageText}`
            : `Error: ${messageText}`,
          traceId: error.traceId ?? message.traceId ?? null,
        }));
        setBanner({ intent: "error", text: messageText });
      } else {
        const messageText =
          error instanceof Error ? error.message : String(error ?? "Unknown error");
        updateMessage(assistantId, (message) => ({
          ...message,
          streaming: false,
          content: message.content
            ? `${message.content}\n\n${messageText}`
            : `Error: ${messageText}`,
        }));
        setBanner({ intent: "error", text: messageText });
      }
      return;
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
      }
      setIsBusy(false);
    }
  }, [
    activeTab?.title,
    activeTab?.url,
    clientLocale,
    clientTimezone,
    input,
    inventory,
    isBusy,
    llmReachable,
    llmStreamSupported,
    selectedModel,
    serverTime,
    startLlmStream,
    threadId,
    updateMessage,
    usePageContext,
  ]);
  const handleSubmit = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      void handleSend();
    },
    [handleSend],
  );

  useEffect(() => {
    if (!llmStreamSupported) {
      return;
    }
    const active = activeStreamRef.current;
    if (!active) {
      return;
    }
    if (!llmStream.requestId || llmStream.requestId !== active.requestId) {
      return;
    }
    updateMessage(active.messageId, (message) => {
      const inProgressText = llmStream.text || message.content || "";
      const finalPayload = llmStream.final;
      let content = llmStream.done
        ? finalPayload?.answer || finalPayload?.reasoning || inProgressText
        : inProgressText;
      if (llmStream.done && llmStream.error) {
        content = content
          ? `${content}\n\n${llmStream.error}`
          : `Error: ${llmStream.error}`;
      }
      return {
        ...message,
        streaming: !llmStream.done,
        content,
        answer: llmStream.done
          ? finalPayload?.answer ?? (content || null)
          : message.answer ?? null,
        reasoning: llmStream.done
          ? finalPayload?.reasoning ?? message.reasoning ?? null
          : message.reasoning ?? null,
        citations: llmStream.done
          ? finalPayload?.citations ?? []
          : message.citations ?? [],
        traceId:
          llmStream.metadata?.traceId ??
          finalPayload?.trace_id ??
          message.traceId ??
          null,
        model:
          llmStream.metadata?.model ??
          finalPayload?.model ??
          message.model ??
          null,
        autopilot: llmStream.done ? finalPayload?.autopilot ?? null : message.autopilot ?? null,
      } satisfies ChatMessage;
    });
    if (llmStream.done) {
      if (streamCompletionRef.current === llmStream.requestId) {
        return;
      }
      streamCompletionRef.current = llmStream.requestId;
      setIsBusy(false);
      if (llmStream.error) {
        setBanner({ intent: "error", text: llmStream.error });
        incidentBus.record("STREAM_ERROR", {
          message: llmStream.error,
          severity: "warn",
          detail: {
            requestId: llmStream.requestId ?? active.requestId,
            transport: "sse",
          },
        });
      } else if (llmStream.final) {
        void storeChatMessage(threadId, {
          id: active.messageId,
          role: "assistant",
          content:
            llmStream.final.answer || llmStream.final.reasoning || llmStream.text || "",
        }).catch((error) => console.warn("[chat] failed to persist assistant message", error));
      }
      if (streamSessionRef.current === llmStream.requestId) {
        streamSessionRef.current = null;
      }
      activeStreamRef.current = null;
    }
  }, [llmStream, llmStreamSupported, setBanner, setIsBusy, threadId, updateMessage]);

  const handleCancel = useCallback(() => {
    if (llmStreamSupported) {
      const active = activeStreamRef.current;
      if (active) {
        abortLlmStream(active.requestId);
        if (streamSessionRef.current === active.requestId) {
          streamSessionRef.current = null;
        }
        setBanner({ intent: "info", text: "Cancelling request…" });
      }
      return;
    }
    if (!abortRef.current) {
      return;
    }
    abortRef.current.abort();
    setBanner({ intent: "info", text: "Cancelling request…" });
  }, [abortLlmStream, llmStreamSupported]);

  useEffect(() => {
    return () => {
      if (llmStreamSupported) {
        const active = activeStreamRef.current;
        if (active) {
          abortLlmStream(active.requestId);
          if (streamSessionRef.current === active.requestId) {
            streamSessionRef.current = null;
          }
        }
      }
    };
  }, [abortLlmStream, llmStreamSupported]);

  const handleModelChange = useCallback((model: string) => {
    const trimmed = model?.trim() ?? "";
    setSelectedModel(trimmed ? trimmed : null);
    storedModelRef.current = trimmed ? trimmed : null;
  }, []);

  const handleInstallModel = useCallback(async () => {
    if (installing) {
      return;
    }
    if (autopullCandidates.length === 0) {
      setBanner({ intent: "error", text: "No candidate models configured for installation." });
      return;
    }
    setInstalling(true);
    setInstallMessage("Requesting model installation via Ollama…");
    try {
      const response = await autopullModels(autopullCandidates);
      if (!mountedRef.current) {
        return;
      }
      if (response.started) {
        const message = response.model
          ? `Pulling ${response.model}. Monitor Ollama for progress.`
          : "Model download started via Ollama.";
        setBanner({ intent: "info", text: message });
        setInstallMessage(message);
        void handleRefreshInventory();
        if (typeof window !== "undefined") {
          refreshTimeoutRef.current = window.setTimeout(() => {
            void handleRefreshInventory();
          }, INVENTORY_REFRESH_DELAY_MS);
        }
      } else {
        const reason = response.reason ?? "Model install could not be started.";
        setBanner({ intent: "error", text: reason });
        setInstallMessage(reason);
      }
    } catch (error) {
      if (!mountedRef.current) {
        return;
      }
      const message = error instanceof Error ? error.message : String(error ?? "Model install failed");
      setBanner({ intent: "error", text: message });
      setInstallMessage(message);
    } finally {
      if (mountedRef.current) {
        setInstalling(false);
      }
    }
  }, [autopullCandidates, handleRefreshInventory, installing]);

  return (
    <div className="flex h-full w-full max-w-[34rem] flex-col gap-4 p-4 text-sm">
      <CopilotHeader
        chatModels={inventory?.chatModels ?? []}
        modelOptions={modelOptions}
        selectedModel={selectedModel}
        onModelChange={handleModelChange}
        installing={installing}
        onInstallModel={handleInstallModel}
        installMessage={installMessage ?? inventoryError}
        reachable={llmReachable}
        statusLabel={headerStatusLabel}
        timeSummary={timeSummary}
        controlsDisabled={isBusy || installing}
        contextControl={
          <div className="flex flex-col gap-2">
            <UsePageContextToggle
              enabled={usePageContext}
              disabled={isBusy || installing}
              onChange={handleContextToggle}
              summary={contextSummary}
            />
            <ReasoningToggle />
          </div>
        }
      />
      {statusBanner ? (
        <div
          className={cn(
            "rounded-md border px-3 py-2 text-xs",
            statusBanner.intent === "error"
              ? "border-destructive text-destructive"
              : "border-border text-muted-foreground",
          )}
        >
          {statusBanner.text}
        </div>
      ) : null}
      <div className="flex-1 overflow-hidden rounded-lg border bg-background">
        <ScrollArea className="h-full pr-3">
          <div className="space-y-4 p-3 pr-1">
            {messages.map((message) => {
              const isAssistant = message.role === "assistant";
              const recordMessage = message as unknown as Record<string, unknown>;
              const fallbackFields = [
                typeof message.message === "string" ? message.message : "",
                typeof message.answer === "string" ? message.answer : "",
                typeof message.content === "string" ? message.content : "",
              ];
              const extraFields = ["output", "text"].map((field) => {
                const value = recordMessage[field];
                return typeof value === "string" ? value : "";
              });
              const serialized =
                (() => {
                  try {
                    return JSON.stringify(recordMessage);
                  } catch {
                    return "";
                  }
                })() || "";
              const bodyText =
                [...fallbackFields, ...extraFields].find((value) => value && value.trim())?.trim() ||
                serialized ||
                "";
              const activeStream =
                llmStreamSupported &&
                llmStream.requestId &&
                activeStreamRef.current?.messageId === message.id &&
                llmStream.requestId === activeStreamRef.current?.requestId;
              const showPlaintext = isAssistant && activeStream && !llmStream.done;
              const plainText = showPlaintext ? llmStream.text : "";
              const frameCount = activeStream ? llmStream.frames : null;
              return (
                <div
                  key={message.id}
                  className={cn(
                    "rounded-lg border px-3 py-2 text-sm shadow-sm",
                    isAssistant ? "bg-card" : "bg-muted",
                  )}
                >
                  <div className="flex items-center justify-between text-[11px] uppercase tracking-wide text-muted-foreground">
                    <span>{message.role}</span>
                    <span>{formatTimestamp(message.createdAt)}</span>
                  </div>
                  <Separator className="my-2" />
                  <div className="space-y-3">
                    {isAssistant ? (
                      <>
                        {showPlaintext ? (
                          <div className="space-y-2">
                            <pre className="whitespace-pre-wrap text-sm font-mono leading-relaxed">
                              {plainText || ""}
                            </pre>
                            <div className="text-xs text-muted-foreground">
                              Frames received: {frameCount ?? 0}
                            </div>
                          </div>
                        ) : bodyText ? (
                          <ChatMessageMarkdown
                            text={bodyText}
                            onLinkClick={handleLinkNavigation}
                          />
                        ) : null}
                        {showReasoning && message.reasoning ? (
                          <details className="rounded-md border border-muted-foreground/40 bg-muted/20 p-2 text-xs">
                            <summary className="cursor-pointer font-semibold uppercase tracking-wide text-muted-foreground">
                              Reasoning
                            </summary>
                            <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-tight text-foreground/90">
                              {message.reasoning}
                            </pre>
                          </details>
                        ) : null}
                        {message.citations && message.citations.length > 0 ? (
                          <div className="space-y-2 text-xs text-muted-foreground">
                            <p className="font-medium text-foreground">Citations</p>
                            <ul className="space-y-1">
                              {message.citations.map((citation, index) => (
                                <li key={`${message.id}:citation:${index}`}>
                                  {isHttpUrl(citation) ? (
                                    <button
                                      type="button"
                                      className="font-medium text-primary underline underline-offset-2"
                                      onClick={(event) => handleCitationClick(citation, event)}
                                    >
                                      {formatCitationLabel(citation)}
                                    </button>
                                  ) : (
                                    <span>{citation}</span>
                                  )}
                                </li>
                              ))}
                            </ul>
                          </div>
                        ) : null}
                        {message.autopilot ? (
                          <div className="rounded-md border border-dashed border-primary/30 bg-primary/10 px-3 py-2 text-xs text-foreground">
                            <p className="font-semibold uppercase tracking-wide text-foreground/80">
                              Autopilot suggestion
                            </p>
                            <p className="mt-1 break-all font-mono text-[13px] text-foreground">
                              {message.autopilot.query}
                            </p>
                            {message.autopilot.reason ? (
                              <p className="mt-1 text-foreground/80">{message.autopilot.reason}</p>
                            ) : null}
                            {message.autopilot.directive?.reason ? (
                              <p className="mt-1 text-foreground/80">
                                Plan: {message.autopilot.directive.reason}
                              </p>
                            ) : null}
                            {(() => {
                              const directiveSteps =
                                pendingDirectives[message.id] ?? extractAutopilotSteps(message.autopilot) ?? [];
                              const planKey = `${message.id}:directive`;
                              const execution = planExecutions[planKey];
                              const running = execution?.status === "running";
                              const succeeded = execution?.status === "success";
                              const failed = execution?.status === "error";
                              if (!directiveSteps || directiveSteps.length === 0) {
                                return null;
                              }
                              return (
                                <div className="mt-3 space-y-2">
                                  <p className="text-[11px] font-semibold uppercase tracking-wide text-primary/80">
                                    Directive steps
                                  </p>
                                  <p className="text-[11px] text-muted-foreground">
                                    This may open pages headlessly via the backend. You can revoke consent in Settings.
                                  </p>
                                  <ol className="list-decimal space-y-1 rounded-md border border-primary/20 bg-background/80 p-2 text-[11px]">
                                    {directiveSteps.map((step, index) => (
                                      <li key={`${message.id}:directive:${index}`} className="leading-relaxed">
                                        <span className="font-medium text-foreground">{step.type}</span>
                                        {step.headless ? <span className="ml-1 text-muted-foreground">(headless)</span> : null}
                                        {step.selector ? <span className="ml-1 text-muted-foreground">{step.selector}</span> : null}
                                        {step.text ? <span className="ml-1 text-muted-foreground">“{step.text}”</span> : null}
                                        {step.url ? (
                                          <span className="ml-1 truncate text-muted-foreground">{step.url}</span>
                                        ) : null}
                                      </li>
                                    ))}
                                  </ol>
                                  <Button
                                    type="button"
                                    size="sm"
                                    variant="secondary"
                                    disabled={running}
                                    onClick={() => {
                                      void handleRunAutopilotPlan(message.id, directiveSteps);
                                    }}
                                  >
                                    {running ? <Loader2 className="mr-2 h-3 w-3 animate-spin" /> : null}
                                    {running ? "Running" : "Run plan"}
                                  </Button>
                                  {succeeded ? (
                                    <p className="text-[11px] text-foreground/80">Plan executed.</p>
                                  ) : null}
                                  {failed && execution?.detail ? (
                                    <p className="text-[11px] text-destructive">{execution.detail}</p>
                                  ) : null}
                                </div>
                              );
                            })()}
                            {message.autopilot.tools && message.autopilot.tools.length > 0 ? (
                              <div className="mt-2 space-y-2">
                                <p className="text-[11px] font-semibold uppercase tracking-wide text-primary/80">
                                  Available tools
                                </p>
                                <div className="space-y-2">
                                  {message.autopilot.tools.map((tool, toolIndex) => {
                                    const key = `${message.id}:${toolIndex}`;
                                    const execution = toolExecutions[key];
                                    const running = execution?.status === "running";
                                    const success = execution?.status === "success";
                                    const failed = execution?.status === "error";
                                    return (
                                      <div
                                        key={key}
                                        className="rounded-md border border-primary/20 bg-background/80 p-2"
                                      >
                                        <div className="flex flex-wrap items-center justify-between gap-2">
                                          <div className="min-w-0 flex-1">
                                            <p className="truncate text-xs font-semibold text-primary">
                                              {tool.label}
                                            </p>
                                            {tool.description ? (
                                              <p className="mt-1 text-[11px] text-muted-foreground">
                                                {tool.description}
                                              </p>
                                            ) : null}
                                          </div>
                                          <Button
                                            type="button"
                                            size="sm"
                                            variant="outline"
                                            disabled={running}
                                            onClick={() => {
                                              void handleRunAutopilotTool(message.id, toolIndex, tool);
                                            }}
                                          >
                                            {running ? (
                                              <Loader2 className="h-3 w-3 animate-spin" />
                                            ) : null}
                                            <span>{running ? "Running" : "Run"}</span>
                                          </Button>
                                        </div>
                                        {success && execution?.detail ? (
                                          <pre className="mt-2 max-h-40 overflow-auto rounded bg-muted px-2 py-1 text-[11px] leading-tight">
                                            {execution.detail}
                                          </pre>
                                        ) : null}
                                        {failed && execution?.detail ? (
                                          <p className="mt-2 text-[11px] text-destructive">{execution.detail}</p>
                                        ) : null}
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            ) : null}
                          </div>
                        ) : null}
                        <AgentTracePanel chatId={threadId} messageId={message.id} />
                        {message.model || message.traceId ? (
                          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                            {message.model ? `Model ${message.model}` : null}
                            {message.model && message.traceId ? " · " : null}
                            {message.traceId ? `Trace ${message.traceId}` : null}
                          </p>
                        ) : null}
                        {message.streaming ? (
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            <span>Generating…</span>
                          </div>
                        ) : null}
                      </>
                    ) : (
                      <ChatMessageMarkdown text={bodyText} />
                    )}
                  </div>
                </div>
              );
            })}
            <div ref={endRef} />
          </div>
        </ScrollArea>
      </div>
      {banner ? (
        <div
          className={cn(
            "rounded-md border px-3 py-2 text-xs",
            banner.intent === "error"
              ? "border-destructive text-destructive"
              : "border-border text-muted-foreground",
          )}
        >
          {banner.text}
        </div>
      ) : null}
      <form className="space-y-2" onSubmit={handleSubmit}>
        <Textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={inputPlaceholder}
          rows={4}
          disabled={installing}
          onKeyDown={(event) => {
            if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
              event.preventDefault();
              void handleSend();
            }
          }}
        />
        <div className="flex items-center justify-between gap-2">
          {isBusy ? (
            <Button type="button" variant="outline" onClick={handleCancel}>
              <StopCircle className="mr-2 h-4 w-4" /> Cancel
            </Button>
          ) : (
            <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
              ⌘/Ctrl + Enter to send
            </span>
          )}
          <Button
            type="submit"
            disabled={
              isBusy ||
              installing ||
              !input.trim() ||
              (inventory ? !chatModelsAvailable || !llmReachable : false)
            }
          >
            {isBusy ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Sending
              </>
            ) : (
              "Send"
            )}
          </Button>
        </div>
      </form>
    </div>
  );
}
