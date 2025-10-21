"use client";

import { Loader2, StopCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent } from "react";

import { CopilotHeader } from "@/components/copilot-header";
import { ChatMessageMarkdown } from "@/components/chat-message";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { useBrowserNavigation } from "@/hooks/useBrowserNavigation";
import {
  autopullModels,
  ChatRequestError,
  fetchModelInventory,
  fetchServerTime,
  sendChat,
  type MetaTimeResponse,
  type ModelInventory,
} from "@/lib/api";
import { resolveChatModelSelection } from "@/lib/chat-model";
import type { ChatMessage } from "@/lib/types";
import { cn } from "@/lib/utils";

const MODEL_STORAGE_KEY = "workspace:chat:model";
const AUTOPULL_FALLBACK_CANDIDATES = ["gemma3", "gpt-oss"];
const INVENTORY_REFRESH_DELAY_MS = 5_000;

type Banner = { intent: "info" | "error"; text: string };

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

const INITIAL_ASSISTANT_GREETING =
  "Welcome! Paste a URL or ask me to search. I only crawl when you approve each step.";

export function ChatPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>(() => [
    {
      id: createId(),
      role: "assistant",
      content: INITIAL_ASSISTANT_GREETING,
      createdAt: new Date().toISOString(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const [banner, setBanner] = useState<Banner | null>(null);
  const [statusBanner, setStatusBanner] = useState<Banner | null>(null);
  const [inventory, setInventory] = useState<ModelInventory | null>(null);
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const [inventoryError, setInventoryError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [installing, setInstalling] = useState(false);
  const [installMessage, setInstallMessage] = useState<string | null>(null);
  const [serverTime, setServerTime] = useState<MetaTimeResponse | null>(null);
  const [serverTimeError, setServerTimeError] = useState<string | null>(null);

  const messagesRef = useRef<ChatMessage[]>(messages);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const mountedRef = useRef(false);
  const storedModelRef = useRef<string | null>(null);
  const refreshTimeoutRef = useRef<number | null>(null);

  const navigate = useBrowserNavigation();

  const clientTimezone = useMemo(() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone;
    } catch {
      return undefined;
    }
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
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, isBusy]);

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

  useEffect(() => {
    const nextStatus: Banner | null = (() => {
      if (inventoryLoading) {
        return { intent: "info", text: "Checking available chat models…" } satisfies Banner;
      }
      if (inventoryError) {
        return { intent: "error", text: `Model inventory failed: ${inventoryError}` } satisfies Banner;
      }
      if (inventory && !inventory.reachable) {
        return {
          intent: "error",
          text: "Ollama host unreachable. Start Ollama and refresh the inventory.",
        } satisfies Banner;
      }
      if (inventory && inventory.chatModels.length === 0) {
        return {
          intent: "error",
          text: "No chat-capable models detected. Install a model to enable Copilot chat.",
        } satisfies Banner;
      }
      if (serverTimeError) {
        return { intent: "info", text: `Time sync unavailable: ${serverTimeError}` } satisfies Banner;
      }
      return null;
    })();
    setStatusBanner(nextStatus);
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

  const updateMessage = useCallback((id: string, updater: (message: ChatMessage) => ChatMessage) => {
    setMessages((prev) => prev.map((message) => (message.id === id ? updater(message) : message)));
  }, []);

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

    const controller = new AbortController();
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

    let streamedModel: string | null = null;
    let streamedTrace: string | null = null;

    try {
      const result = await sendChat(historySnapshot, trimmed, {
        signal: controller.signal,
        clientTimezone,
        model: selectedModel ?? undefined,
        serverTime: serverTime?.server_time ?? undefined,
        serverTimezone: serverTime?.server_timezone ?? undefined,
        serverUtc: serverTime?.server_time_utc ?? undefined,
        onStreamEvent: (event) => {
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
            }));
          }
        },
      });

      streamedModel = result.model ?? streamedModel;
      streamedTrace = result.traceId ?? streamedTrace;

      updateMessage(assistantId, (message) => ({
        ...message,
        streaming: false,
        content: result.payload.answer || result.payload.reasoning || message.content || "",
        answer: result.payload.answer || null,
        reasoning: result.payload.reasoning || null,
        citations: result.payload.citations ?? [],
        traceId: result.payload.trace_id ?? streamedTrace ?? message.traceId ?? null,
        model: result.payload.model ?? streamedModel ?? message.model ?? null,
        autopilot: result.payload.autopilot ?? null,
      }));
    } catch (error) {
      if (
        controller.signal.aborted ||
        (error instanceof DOMException && error.name === "AbortError")
      ) {
        updateMessage(assistantId, (message) => ({
          ...message,
          streaming: false,
          content: message.content || "(cancelled)",
        }));
        setBanner({ intent: "info", text: "Generation cancelled." });
      } else if (error instanceof ChatRequestError) {
        const messageText = error.hint ?? error.message;
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
    clientTimezone,
    input,
    inventory,
    isBusy,
    llmReachable,
    selectedModel,
    serverTime,
    updateMessage,
  ]);

  const handleSubmit = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      void handleSend();
    },
    [handleSend],
  );

  const handleCancel = useCallback(() => {
    if (!abortRef.current) {
      return;
    }
    abortRef.current.abort();
    setBanner({ intent: "info", text: "Cancelling request…" });
  }, []);

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
              const bodyText = message.answer ?? message.content ?? "";
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
                        {bodyText ? (
                          <ChatMessageMarkdown
                            text={bodyText}
                            onLinkClick={handleLinkNavigation}
                          />
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
                          </div>
                        ) : null}
                        {message.reasoning ? (
                          <details className="rounded-md border bg-muted/50 px-3 py-2 text-xs text-foreground/90">
                            <summary className="cursor-pointer font-medium text-foreground">
                              Show reasoning
                            </summary>
                            <div className="mt-2">
                              <ChatMessageMarkdown
                                text={message.reasoning}
                                onLinkClick={handleLinkNavigation}
                                className="text-xs"
                              />
                            </div>
                          </details>
                        ) : null}
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
