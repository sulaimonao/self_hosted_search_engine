"use client";

import React, { useMemo, useState, useEffect, useRef } from "react";
import type { ModelInventory } from "@/lib/api";
import { ChatMessageMarkdown } from "@/components/chat-message";
import { CopilotHeader } from "@/components/copilot-header";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Loader2, StopCircle } from "lucide-react";
import { storeChatMessage } from "@/lib/api";
import { chatClient, ChatRequestError, type ChatPayloadMessage } from "@/lib/chatClient";
import type { AutopilotDirective } from "@/lib/types";

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

  const resolveModel = () => selectedModel || inventory?.configured?.primary || inventory?.configured?.fallback || undefined;

  const updateAssistantMessage = (assistantId: string, partial: Partial<ChatViewMessage>) => {
    messagesRef.current = messagesRef.current.map((entry) =>
      entry.id === assistantId ? { ...entry, ...partial } : entry
    );
    setMessages(messagesRef.current);
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
              return (
                <div
                  key={m.id ?? `${role}-${idx}`}
                  className={role === "assistant" ? "bg-card rounded-lg border px-3 py-2" : "bg-muted rounded-lg border px-3 py-2"}
                >
                  <div className="text-xs text-muted-foreground uppercase tracking-wide">{role}</div>
                  <div className="mt-2">
                    <ChatMessageMarkdown text={content} onLinkClick={onLinkClick} />
                    {role === "assistant" && isStreaming && idx === messages.length - 1 ? (
                      <div className="flex items-center gap-2 text-xs text-muted-foreground mt-2">
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

      <form
        className="space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          void handleSend();
        }}
      >
  <Textarea value={input ?? ""} onChange={(e) => setInput?.(e.target.value)} placeholder={inventory ? "Ask the copilot" : "Ask the copilot"} rows={4} />
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
