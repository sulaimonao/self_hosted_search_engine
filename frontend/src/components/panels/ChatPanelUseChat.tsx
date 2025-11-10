"use client";

import React, { useMemo, useState, useEffect, useRef, useCallback } from "react";
import type { ModelInventory } from "@/lib/api";
import { ChatMessageMarkdown } from "@/components/chat-message";
import { CopilotHeader } from "@/components/copilot-header";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Loader2, StopCircle } from "lucide-react";
import { runAutopilotTool, storeChatMessage } from "@/lib/api";
import { chatClient, ChatRequestError, type ChatPayloadMessage } from "@/lib/chatClient";
import { AutopilotExecutor, type AutopilotRunResult, type Verb } from "@/autopilot/executor";
import ContextChips from "@/components/chat/ContextChips";
import { createDefaultChatContext, type AutopilotDirective, type AutopilotToolDirective, type ChatContext } from "@/lib/types";

type ChatViewMessage = {
  id: string;
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  reasoning?: string;
  citations?: string[];
  traceId?: string | null;
  autopilot?: AutopilotDirective | null;
};

const createId = () => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
};

function toPayloadMessages(history: ChatViewMessage[]): ChatPayloadMessage[] {
  return history
    .filter((entry) => entry.role === "user" || entry.role === "assistant" || entry.role === "system" || entry.role === "tool")
    .map((entry) => ({
      role: entry.role,
      content: entry.content ?? "",
    }));
}

type ToolExecutionState = {
  status: "idle" | "running" | "success" | "error";
  detail?: string;
};

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

type StepWithOptional = Verb & { selector?: string; text?: string; url?: string };

type ChatPanelUseChatProps = {
  inventory?: ModelInventory | null;
  selectedModel?: string | null;
  threadId: string;
  onLinkClick?: (url: string, event: React.MouseEvent<HTMLAnchorElement>) => void;
  onModelChange?: (model: string) => void;
};

export default function ChatPanelUseChat({ inventory, selectedModel, threadId, onLinkClick, onModelChange }: ChatPanelUseChatProps) {
  const [messages, setMessages] = useState<ChatViewMessage[]>([]);
  const messagesRef = useRef<ChatViewMessage[]>(messages);
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  const abortRef = useRef<AbortController | null>(null);
  const [input, setInput] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastAttempt, setLastAttempt] = useState<{ text: string; model?: string | undefined } | null>(null);
  const [toolExecutions, setToolExecutions] = useState<Record<string, ToolExecutionState>>({});
  const [planExecutions, setPlanExecutions] = useState<
    Record<string, { status: "idle" | "running" | "success" | "error"; detail?: string }>
  >({});
  const [pendingDirectives, setPendingDirectives] = useState<Record<string, Verb[]>>({});
  const [chatContext, setChatContext] = useState<ChatContext>(() => createDefaultChatContext());
  const contextRef = useRef<ChatContext>(chatContext);
  const [activeUrl, setActiveUrl] = useState<string | null>(null);
  const autopilotExecutor = useMemo(() => new AutopilotExecutor(), []);

  useEffect(() => {
    contextRef.current = chatContext;
  }, [chatContext]);

  const resolveActiveUrl = useCallback((): string | null => {
    if (typeof window === "undefined") {
      return null;
    }
    const href = window.location.href;
    try {
      const current = new URL(href);
      if (current.pathname.startsWith("/browser")) {
        const forwarded = current.searchParams.get("url");
        if (forwarded) {
          try {
            return new URL(forwarded).toString();
          } catch {
            return decodeURIComponent(forwarded);
          }
        }
      }
      const param = current.searchParams.get("url");
      if (param) {
        try {
          return new URL(param).toString();
        } catch {
          return decodeURIComponent(param);
        }
      }
      return current.href;
    } catch {
      const match = href.match(/url=([^&]+)/);
      if (match && match[1]) {
        try {
          return decodeURIComponent(match[1]);
        } catch {
          return match[1];
        }
      }
    }
    return href;
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const updateUrl = () => {
      setActiveUrl(resolveActiveUrl());
    };
    updateUrl();
    window.addEventListener("hashchange", updateUrl);
    window.addEventListener("popstate", updateUrl);
    window.addEventListener("focus", updateUrl);
    return () => {
      window.removeEventListener("hashchange", updateUrl);
      window.removeEventListener("popstate", updateUrl);
      window.removeEventListener("focus", updateUrl);
    };
  }, [resolveActiveUrl]);

  const normalizeContext = useCallback((next: ChatContext): ChatContext => {
    return {
      page: next.page ?? null,
      diagnostics: next.diagnostics ?? null,
      db: next.db ?? { enabled: false },
      tools: next.tools ?? { allowIndexing: false },
    };
  }, []);

  const handleContextChange = useCallback(
    (next: ChatContext) => {
      setChatContext(normalizeContext(next));
    },
    [normalizeContext],
  );

  const lastTraceId = useMemo(() => {
    const reversed = [...messages].reverse();
    for (const m of reversed) {
      if (m.traceId) return m.traceId;
    }
    return null;
  }, [messages]);

  useEffect(() => {
    setError(null);
  }, [selectedModel, inventory?.configured?.primary, inventory?.configured?.fallback]);

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
      validKeys.forEach((key) => {
        if (prev[key]) {
          next[key] = prev[key];
        } else {
          changed = true;
        }
      });
      for (const key of Object.keys(prev)) {
        if (!validKeys.has(key)) {
          changed = true;
        }
      }
      if (!changed && Object.keys(prev).length === Object.keys(next).length) {
        return prev;
      }
      return next;
    });
  }, [messages]);

  useEffect(() => {
    setPendingDirectives((prev) => {
      const validIds = new Set(messages.map((message) => message.id));
      const next: Record<string, Verb[]> = {};
      let changed = false;
      validIds.forEach((id) => {
        if (prev[id]) {
          next[id] = prev[id];
        }
      });
      for (const id of Object.keys(prev)) {
        if (!validIds.has(id)) {
          changed = true;
        }
      }
      if (!changed && Object.keys(prev).length === Object.keys(next).length) {
        return prev;
      }
      return changed ? next : prev;
    });
  }, [messages]);

  useEffect(() => {
    setPlanExecutions((prev) => {
      const validKeys = new Set(messages.map((message) => `${message.id}:directive`));
      const next: Record<string, { status: "idle" | "running" | "success" | "error"; detail?: string }> = {};
      let changed = false;
      for (const key of Object.keys(prev)) {
        if (validKeys.has(key)) {
          next[key] = prev[key];
        } else {
          changed = true;
        }
      }
      if (!changed && Object.keys(prev).length === Object.keys(next).length) {
        return prev;
      }
      return next;
    });
  }, [messages]);

  const resolveModel = () => selectedModel || inventory?.configured?.primary || inventory?.configured?.fallback || undefined;

  const updateAssistantMessage = (assistantId: string, partial: Partial<ChatViewMessage>) => {
    let autopilotSteps: Verb[] | null = null;
    messagesRef.current = messagesRef.current.map((entry) => {
      if (entry.id !== assistantId) {
        return entry;
      }
      const next = { ...entry, ...partial };
      autopilotSteps = extractAutopilotSteps(next.autopilot);
      return next;
    });
    setMessages(messagesRef.current);
    const steps = autopilotSteps ?? ([] as Verb[]);
    const hasSteps = steps.length > 0;
    setPendingDirectives((prev) => {
      if (!hasSteps) {
        if (!prev[assistantId]) {
          return prev;
        }
        const next = { ...prev };
        delete next[assistantId];
        return next;
      }
      const next = { ...prev, [assistantId]: steps };
      return next;
    });
    if (!hasSteps) {
      setPlanExecutions((prev) => {
        const key = `${assistantId}:directive`;
        if (!prev[key]) {
          return prev;
        }
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }
  };

  const sendChat = async ({ text, model, appendUser }: { text: string; model?: string | undefined; appendUser: boolean }) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    if (isBusy) return;

    setIsBusy(true);
    setIsStreaming(true);
    setError(null);
    setLastAttempt({ text: trimmed, model });

    const historyBefore = messagesRef.current;
    const userMessage = appendUser
      ? ({ id: createId(), role: "user" as const, content: trimmed } satisfies ChatViewMessage)
      : null;
    const assistantId = createId();
    const assistantMessage: ChatViewMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
    };

    const baseHistory = appendUser ? [...historyBefore, userMessage!] : [...historyBefore];
    const updatedHistory = [...baseHistory, assistantMessage];
    messagesRef.current = updatedHistory;
    setMessages(updatedHistory);

    if (userMessage) {
      void storeChatMessage(threadId, {
        id: `local-${Date.now()}`,
        role: "user",
        content: trimmed,
      }).catch(() => undefined);
    }

    const controller = new AbortController();
    abortRef.current = controller;

    const payloadMessages = toPayloadMessages(baseHistory);

    let streamedAnswer = "";
    let streamedReasoning = "";
    let streamedCitations: string[] = [];
    let streamedTraceId: string | null = null;
    let streamedAutopilot: AutopilotDirective | null | undefined;

    try {
      const result = await chatClient.send({
        messages: payloadMessages,
        model,
        stream: true,
        context: contextRef.current,
        signal: controller.signal,
        onEvent: (event) => {
          if (event.type === "metadata") {
            streamedTraceId = event.trace_id ?? streamedTraceId ?? null;
            if (streamedTraceId) {
              updateAssistantMessage(assistantId, { traceId: streamedTraceId });
            }
            return;
          }
          if (event.type === "delta") {
            if (typeof event.answer === "string" && event.answer) {
              streamedAnswer = event.answer;
            } else if (typeof event.delta === "string" && event.delta) {
              streamedAnswer += event.delta;
            }
            if (typeof event.reasoning === "string" && event.reasoning) {
              streamedReasoning = event.reasoning;
            }
            if (Array.isArray(event.citations) && event.citations.length > 0) {
              streamedCitations = event.citations;
            }
            updateAssistantMessage(assistantId, {
              content: streamedAnswer,
              reasoning: streamedReasoning || undefined,
              citations: streamedCitations.length > 0 ? streamedCitations : undefined,
            });
            return;
          }
          if (event.type === "complete") {
            streamedAnswer = event.payload.answer || streamedAnswer;
            streamedReasoning = event.payload.reasoning || streamedReasoning;
            streamedCitations = event.payload.citations ?? streamedCitations;
            streamedTraceId = event.payload.trace_id ?? streamedTraceId ?? null;
            streamedAutopilot = event.payload.autopilot ?? null;
            updateAssistantMessage(assistantId, {
              content: streamedAnswer,
              reasoning: streamedReasoning || undefined,
              citations: streamedCitations?.length ? streamedCitations : undefined,
              traceId: streamedTraceId,
              autopilot: streamedAutopilot ?? null,
            });
            return;
          }
          if (event.type === "error") {
            setError(event.error || "Chat stream error");
          }
        },
      });

      const finalAnswer = result.payload.answer || streamedAnswer;
      const finalReasoning = result.payload.reasoning || streamedReasoning;
      const finalCitations = result.payload.citations ?? streamedCitations;
      const finalTrace = result.traceId ?? streamedTraceId ?? null;
      const finalAutopilot = result.payload.autopilot ?? streamedAutopilot ?? null;

      updateAssistantMessage(assistantId, {
        content: finalAnswer,
        reasoning: finalReasoning || undefined,
        citations: finalCitations?.length ? finalCitations : undefined,
        traceId: finalTrace,
        autopilot: finalAutopilot,
      });

      setError(null);
      setLastAttempt(null);
    } catch (err) {
      const rollback = appendUser ? [...baseHistory] : [...historyBefore];
      messagesRef.current = rollback;
      setMessages(rollback);
      setPendingDirectives((prev) => {
        if (!prev[assistantId]) {
          return prev;
        }
        const next = { ...prev };
        delete next[assistantId];
        return next;
      });
      setPlanExecutions((prev) => {
        const key = `${assistantId}:directive`;
        if (!prev[key]) {
          return prev;
        }
        const next = { ...prev };
        delete next[key];
        return next;
      });
      setToolExecutions((prev) => {
        const targetKeys = Object.keys(prev).filter((key) => key.startsWith(`${assistantId}:`));
        if (targetKeys.length === 0) {
          return prev;
        }
        const next = { ...prev };
        for (const key of targetKeys) {
          delete next[key];
        }
        return next;
      });

      if (err && typeof err === "object" && (err as Error).name === "AbortError") {
        // User cancelled; keep lastAttempt for optional retry but avoid surfacing an error.
        return;
      }

      if (err instanceof ChatRequestError) {
        setError(err.hint ?? err.message ?? "Chat request failed");
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError(String(err));
      }
      console.error("Chat send failed", err);
    } finally {
      abortRef.current = null;
      setIsBusy(false);
      setIsStreaming(false);
      if (appendUser) {
        setInput("");
      }
    }
  };

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
        const detail = summarizeToolResult(result as Record<string, unknown> | null | undefined);
        setToolExecutions((prev) => ({
          ...prev,
          [key]: { status: "success", detail },
        }));
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error ?? "Tool request failed");
        setToolExecutions((prev) => ({
          ...prev,
          [key]: { status: "error", detail: message },
        }));
      }
    },
    [threadId],
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
        const result: AutopilotRunResult = await autopilotExecutor.run({ steps: directiveSteps });
        if (result.headlessErrors.length > 0) {
          const detail = result.headlessErrors.map((error) => error.message).join("; ") || "Headless execution failed.";
          setPlanExecutions((prev) => ({
            ...prev,
            [key]: { status: "error", detail },
          }));
          return;
        }
        const detail =
          result.headlessBatches > 0
            ? `Autopilot plan executed (${result.headlessBatches} headless batch${result.headlessBatches === 1 ? "" : "es"}).`
            : "Autopilot plan executed.";
        setPlanExecutions((prev) => ({
          ...prev,
          [key]: { status: "success", detail },
        }));
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error ?? "Autopilot run failed");
        setPlanExecutions((prev) => ({
          ...prev,
          [key]: { status: "error", detail: message },
        }));
      }
    },
    [autopilotExecutor, pendingDirectives],
  );

  const handleSend = async () => {
    if (isBusy) return;
    const trimmed = (input ?? "").trim();
    if (!trimmed) return;
    const model = resolveModel();
    await sendChat({ text: trimmed, model, appendUser: true });
  };

  const handleRetry = async () => {
    if (!lastAttempt || isBusy) return;
    await sendChat({ text: lastAttempt.text, model: lastAttempt.model, appendUser: false });
  };

  return (
    <div className="flex h-full w-full max-w-[34rem] flex-col gap-4 p-4 text-sm">
  <CopilotHeader
        chatModels={inventory?.chatModels ?? []}
        selectedModel={selectedModel ?? null}
        onModelChange={onModelChange ?? (() => {})}
      />
      {error ? (
        <div className="flex items-center justify-between rounded-md border border-destructive px-3 py-2 text-xs text-destructive">
          <div className="flex items-center gap-2">
            <div>Error: {error ?? "Failed to send message."}</div>
            {lastTraceId ? (
              <span className="opacity-80">(trace {lastTraceId})</span>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            {lastAttempt ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  void handleRetry();
                }}
              >
                Retry
              </Button>
            ) : null}
            <Button size="sm" variant="ghost" onClick={() => setError(null)}>
              Dismiss
            </Button>
          </div>
        </div>
      ) : null}
      <div className="flex-1 overflow-hidden rounded-lg border bg-background">
        <ScrollArea className="h-full pr-3">
          <div className="space-y-4 p-3 pr-1">
            {messages.map((m: ChatViewMessage, idx: number) => {
              const role = m.role ?? "assistant";
              const content = typeof m.content === "string" ? m.content : "";
              const isAssistant = role === "assistant";
              const autopilot = isAssistant ? m.autopilot ?? null : null;
              const directiveSteps = autopilot
                ? pendingDirectives[m.id] ?? extractAutopilotSteps(autopilot) ?? []
                : [];
              const planKey = `${m.id}:directive`;
              const planExecution = planExecutions[planKey];
              const planRunning = planExecution?.status === "running";
              const planSucceeded = planExecution?.status === "success";
              const planFailed = planExecution?.status === "error";
              const planDetail = planExecution?.detail;

              return (
                <div
                  key={m.id ?? `${role}-${idx}`}
                  className={isAssistant ? "bg-card rounded-lg border px-3 py-2" : "bg-muted rounded-lg border px-3 py-2"}
                >
                  <div className="text-xs text-muted-foreground uppercase tracking-wide">{role}</div>
                  <div className="mt-2 space-y-3">
                    <ChatMessageMarkdown text={content} onLinkClick={onLinkClick} />
                    {isAssistant && autopilot ? (
                      <div className="rounded-md border border-dashed border-primary/30 bg-primary/10 px-3 py-2 text-xs text-foreground">
                        <p className="font-semibold uppercase tracking-wide text-foreground/80">Autopilot suggestion</p>
                        <div className="mt-1 space-y-1">
                          {autopilot.mode ? (
                            <p className="text-[11px] text-muted-foreground">
                              Mode: <span className="font-mono text-foreground">{autopilot.mode}</span>
                            </p>
                          ) : null}
                          {autopilot.query ? (
                            <p className="break-all font-mono text-[13px] text-foreground">{autopilot.query}</p>
                          ) : null}
                          {autopilot.reason ? (
                            <p className="text-[13px] text-foreground/80">{autopilot.reason}</p>
                          ) : null}
                          {autopilot.directive?.reason ? (
                            <p className="text-[13px] text-foreground/70">Plan: {autopilot.directive.reason}</p>
                          ) : null}
                        </div>
                        {directiveSteps.length > 0 ? (
                          <div className="mt-3 space-y-2">
                            <p className="text-[11px] font-semibold uppercase tracking-wide text-primary/80">Directive steps</p>
                            <p className="text-[11px] text-muted-foreground">
                              This may open pages headlessly via the backend. You can revoke consent in Settings.
                            </p>
                            <ol className="list-decimal space-y-1 rounded-md border border-primary/20 bg-background/80 p-2 text-[11px]">
                              {directiveSteps.map((step, index) => (
                                <li key={`${m.id}:directive:${index}`} className="leading-relaxed">
                                  <span className="font-medium text-foreground">{step.type}</span>
                                  {step.headless ? <span className="ml-1 text-muted-foreground">(headless)</span> : null}
                                  {"selector" in step && (step as StepWithOptional).selector ? (
                                    <span className="ml-1 text-muted-foreground">{(step as StepWithOptional).selector}</span>
                                  ) : null}
                                  {"text" in step && (step as StepWithOptional).text ? (
                                    <span className="ml-1 text-muted-foreground">“{(step as StepWithOptional).text}”</span>
                                  ) : null}
                                  {"url" in step && (step as StepWithOptional).url ? (
                                    <span className="ml-1 truncate text-muted-foreground">{(step as StepWithOptional).url}</span>
                                  ) : null}
                                </li>
                              ))}
                            </ol>
                            <Button
                              type="button"
                              size="sm"
                              variant="secondary"
                              disabled={planRunning}
                              onClick={() => {
                                void handleRunAutopilotPlan(m.id, directiveSteps);
                              }}
                            >
                              {planRunning ? <Loader2 className="mr-2 h-3 w-3 animate-spin" /> : null}
                              {planRunning ? "Running" : "Run plan"}
                            </Button>
                            {planSucceeded && planDetail ? (
                              <p className="text-[11px] text-foreground/80">{planDetail}</p>
                            ) : null}
                            {planFailed && planDetail ? (
                              <p className="text-[11px] text-destructive">{planDetail}</p>
                            ) : null}
                          </div>
                        ) : null}
                        {Array.isArray(autopilot.tools) && autopilot.tools.length > 0 ? (
                          <div className="mt-3 space-y-2">
                            <p className="text-[11px] font-semibold uppercase tracking-wide text-primary/80">Available tools</p>
                            <div className="space-y-2">
                              {autopilot.tools.map((tool, toolIndex) => {
                                const toolKey = `${m.id}:${toolIndex}`;
                                const execution = toolExecutions[toolKey];
                                const running = execution?.status === "running";
                                const success = execution?.status === "success";
                                const failed = execution?.status === "error";
                                return (
                                  <div key={toolKey} className="rounded-md border border-primary/20 bg-background/80 p-2">
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                      <div className="min-w-0 flex-1">
                                        <p className="truncate text-xs font-semibold text-primary">{tool.label}</p>
                                        {tool.description ? (
                                          <p className="mt-1 text-[11px] text-muted-foreground">{tool.description}</p>
                                        ) : null}
                                      </div>
                                      <Button
                                        type="button"
                                        size="sm"
                                        variant="outline"
                                        disabled={running}
                                        onClick={() => {
                                          void handleRunAutopilotTool(m.id, toolIndex, tool);
                                        }}
                                      >
                                        {running ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
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
                    {isAssistant && isStreaming && idx === messages.length - 1 ? (
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        <span>Generating…</span>
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        </ScrollArea>
      </div>

      <div className="rounded-lg border bg-muted/30 p-3">
        <ContextChips activeUrl={activeUrl} value={chatContext} onChange={handleContextChange} />
      </div>

      <form
        className="space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          void handleSend();
        }}
      >
  <Textarea value={input ?? ""} onChange={(e) => setInput(e.target.value)} placeholder={inventory ? "Ask the copilot" : "Ask the copilot"} rows={4} />
        <div className="flex items-center justify-between gap-2">
          {isBusy ? (
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                abortRef.current?.abort();
              }}
            >
              <StopCircle className="mr-2 h-4 w-4" /> Cancel
            </Button>
          ) : (
            <span className="text-[11px] uppercase tracking-wide text-muted-foreground">⌘/Ctrl + Enter to send</span>
          )}
          <Button type="submit" disabled={isBusy || !input || !(inventory ? (inventory.chatModels ?? []).length > 0 : true)}>
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
