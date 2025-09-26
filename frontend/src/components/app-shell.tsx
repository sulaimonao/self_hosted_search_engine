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
import { AgentLog } from "@/components/agent-log";
import { JobStatus } from "@/components/job-status";
import { CrawlManager } from "@/components/crawl-manager";
import { ActionEditor } from "@/components/action-editor";
import {
  fetchModelInventory,
  reindexUrl,
  startCrawlJob,
  streamChat,
  subscribeJob,
} from "@/lib/api";
import type {
  ActionKind,
  AgentLogEntry,
  ChatMessage,
  CrawlQueueItem,
  CrawlScope,
  JobStatusSummary,
  ModelStatus,
  OllamaStatus,
  ProposedAction,
  SelectionActionPayload,
} from "@/lib/types";

const INITIAL_URL = "https://news.ycombinator.com";

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
  const [defaultScope, setDefaultScope] = useState<CrawlScope>("page");
  const [omniboxValue, setOmniboxValue] = useState(INITIAL_URL);
  const [commandOpen, setCommandOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("chat");
  const [modelStatus, setModelStatus] = useState<ModelStatus[]>([]);
  const [chatModel, setChatModel] = useState<string | null>(null);
  const [embeddingModel, setEmbeddingModel] = useState<string | null>(null);
  const [ollamaStatus, setOllamaStatus] = useState<OllamaStatus | null>(null);
  const [editorAction, setEditorAction] = useState<ProposedAction | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);

  const omniboxRef = useRef<HTMLInputElement | null>(null);
  const streamingController = useRef<AbortController | null>(null);
  const jobSubscriptions = useRef(new Map<string, () => void>());
  const chatHistoryRef = useRef<ChatMessage[]>(chatMessages);

  const currentUrl = previewState.history[previewState.index];

  const navigateTo = useCallback(
    (inputValue: string) => {
      const value = inputValue.trim();
      if (!value) return;
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

      try {
        await streamChat(historySnapshot, content, {
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
      } catch (error) {
        const abort = controller.signal.aborted;
        if (!abort) {
          const message = error instanceof Error ? error.message : String(error ?? "Unknown error");
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
        }
      } finally {
        if (streamingController.current === controller) {
          streamingController.current = null;
        }
        setIsStreaming(false);
        updateAssistant((message) => ({ ...message, streaming: false }));
      }
    },
    [appendLog, appendMessage, chatModel, currentUrl]
  );

  const handleStopStreaming = useCallback(() => {
    if (streamingController.current) {
      streamingController.current.abort();
      streamingController.current = null;
    }
    setIsStreaming(false);
    appendLog({
      id: uid(),
      label: "Streaming stopped",
      detail: "User interrupted generation",
      status: "warning",
      timestamp: new Date().toISOString(),
    });
  }, [appendLog]);

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
        setActiveTab("chat");
        void handleSendChat(input);
      }
    },
    [handleNavigate, handleSendChat, handleStopStreaming, isStreaming, setActiveTab]
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

      try {
        if (action.kind === "crawl" || action.kind === "queue") {
          const url = String(action.payload.url ?? currentUrl);
          const scope = (action.payload.scope as CrawlScope) || defaultScope;
          const maxPages = Number(action.payload.maxPages ?? 25);
          const maxDepth = Number(action.payload.maxDepth ?? 2);
          const description = `Crawl ${new URL(url).hostname}`;

          const response = await startCrawlJob({ url, scope, maxPages, maxDepth });
          const jobId = (response as { job_id?: string; jobId?: string }).jobId ??
            (response as { job_id?: string }).job_id;
          const queuedItem: CrawlQueueItem = {
            id: uid(),
            url,
            scope,
            notes: action.description,
          };
          setCrawlQueue((queue) => [queuedItem, ...queue]);
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
          setCrawlQueue((queue) => [
            {
              id: uid(),
              url: seed,
              scope: "allowed-list",
              notes: action.description ?? "Seed captured",
            },
            ...queue,
          ]);
          appendLog({
            id: uid(),
            label: "Seed queued",
            detail: `Added ${seed} to crawl seeds`,
            status: "info",
            timestamp: new Date().toISOString(),
          });
        } else if (action.kind === "summarize") {
          appendLog({
            id: uid(),
            label: "Summary requested",
            detail: "Summary will be provided in chat",
            status: "info",
            timestamp: new Date().toISOString(),
          });
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
    [appendLog, currentUrl, defaultScope, registerJob, updateAction]
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

  const handleQueueAdd = useCallback(
    (url: string, scope: CrawlScope) => {
      const item: CrawlQueueItem = {
        id: uid(),
        url,
        scope,
      };
      setCrawlQueue((queue) => [item, ...queue]);
      appendLog({
        id: uid(),
        label: "Queued crawl",
        detail: `Added ${url} [${scope}] to queue`,
        status: "info",
        timestamp: new Date().toISOString(),
      });
    },
    [appendLog]
  );

  const handleQueueRemove = useCallback((id: string) => {
    setCrawlQueue((queue) => queue.filter((item) => item.id !== id));
  }, []);

  const handleQueueScopeUpdate = useCallback((id: string, scope: CrawlScope) => {
    setCrawlQueue((queue) =>
      queue.map((item) => (item.id === id ? { ...item, scope } : item))
    );
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
    const loadModels = async () => {
      try {
        const inventory = await fetchModelInventory();
        setModelStatus(inventory.models);
        setOllamaStatus(inventory.status);
        const primaryChat = inventory.models.find((model) => model.kind === "chat" && model.isPrimary);
        const anyChat = inventory.models.find((model) => model.kind === "chat");
        const embedding = inventory.models.find((model) => model.kind === "embedding");
        setChatModel(primaryChat?.model ?? anyChat?.model ?? null);
        setEmbeddingModel(embedding?.model ?? null);
      } catch (error) {
        console.warn("Unable to load model inventory", error);
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
        <section className="h-[45vh] flex-1 border-b lg:h-auto lg:flex-[1.4] lg:border-r">
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
        <aside className="flex flex-1 flex-col">
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
                        <Badge variant={model.available ? "default" : "destructive"}>
                          {model.available ? "Available" : "Unavailable"}
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
    </div>
  );
}
