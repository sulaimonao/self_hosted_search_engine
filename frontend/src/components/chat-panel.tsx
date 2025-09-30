"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronDown, ChevronUp, Loader2, StopCircle } from "lucide-react";

import { ActionCard } from "@/components/action-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { ChatMessage, ProposedAction } from "@/lib/types";

interface ChatPanelProps {
  messages: ChatMessage[];
  input: string;
  onInputChange: (value: string) => void;
  onSend: (message: string) => void;
  isBusy: boolean;
  onCancel?: () => void;
  onApproveAction: (action: ProposedAction) => void;
  onEditAction: (action: ProposedAction) => void;
  onDismissAction: (action: ProposedAction) => void;
  header?: ReactNode;
  disableInput?: boolean;
}

function formatTimestamp(value: string) {
  try {
    return new Date(value).toLocaleTimeString();
  } catch {
    return value;
  }
}

export function ChatPanel({
  messages,
  input,
  onInputChange,
  onSend,
  isBusy,
  onCancel,
  onApproveAction,
  onEditAction,
  onDismissAction,
  header,
  disableInput = false,
}: ChatPanelProps) {
  const formRef = useRef<HTMLFormElement | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const [expandedReasoning, setExpandedReasoning] = useState<Record<string, boolean>>({});

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, isBusy]);

  const handleSubmit = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!input.trim()) return;
      onSend(input.trim());
    },
    [input, onSend],
  );

  const toggleReasoning = useCallback((id: string) => {
    setExpandedReasoning((prev) => ({ ...prev, [id]: !prev[id] }));
  }, []);

  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="space-y-2 pb-3">
        {header ? (
          header
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle className="text-sm">Copilot chat</CardTitle>
              <p className="text-xs text-muted-foreground">{isBusy ? "Thinking" : "Idle"}</p>
            </div>
          </div>
        )}
      </CardHeader>
      <CardContent className="flex-1 overflow-hidden">
        <ScrollArea className="h-full pr-4">
          <div className="space-y-4">
            {messages.length === 0 ? (
              <div className="rounded border border-dashed p-6 text-center text-sm text-muted-foreground">
                Ask the agent what to do next or enable context from the preview panel.
              </div>
            ) : null}
            {messages.map((message) => {
              const isAssistant = message.role === "assistant";
              const reasoningId = `${message.id}:reasoning`;
              const reasoningOpen = Boolean(expandedReasoning[reasoningId]);
              const reasoningText = (message.reasoning ?? "").trim();
              const answerText = (message.answer ?? message.content ?? "").trim();

              return (
                <div key={message.id} className="space-y-2">
                  <div
                    className={cn(
                      "rounded-lg border px-3 py-2 text-sm",
                      isAssistant ? "bg-card" : "bg-secondary/80",
                    )}
                  >
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span className="capitalize">{message.role}</span>
                      <span>{formatTimestamp(message.createdAt)}</span>
                    </div>
                    <Separator className="my-2" />
                    <div className="space-y-3">
                      {isAssistant ? (
                        <div className="space-y-3">
                          <div className="leading-relaxed whitespace-pre-wrap">{answerText || message.content}</div>
                          {reasoningText ? (
                            <div className="rounded-md border bg-muted/40 px-3 py-2 text-xs">
                              <button
                                type="button"
                                className="flex w-full items-center justify-between text-left font-medium text-foreground"
                                onClick={() => toggleReasoning(reasoningId)}
                              >
                                <span>Show reasoning (dev)</span>
                                {reasoningOpen ? (
                                  <ChevronUp className="h-3.5 w-3.5" />
                                ) : (
                                  <ChevronDown className="h-3.5 w-3.5" />
                                )}
                              </button>
                              {reasoningOpen ? (
                                <p className="mt-2 whitespace-pre-wrap text-foreground/90">
                                  {reasoningText}
                                </p>
                              ) : null}
                            </div>
                          ) : null}
                          {message.citations && message.citations.length > 0 ? (
                            <div className="space-y-1 text-xs text-muted-foreground">
                              <p className="font-medium text-foreground">Citations</p>
                              <ul className="list-disc space-y-1 pl-4">
                                {message.citations.map((citation, index) => {
                                  const label = citation.startsWith("http") ? new URL(citation).host : citation;
                                  return (
                                    <li key={`${message.id}:citation:${index}`}>
                                      {citation.startsWith("http") ? (
                                        <a
                                          href={citation}
                                          target="_blank"
                                          rel="noreferrer"
                                          className="text-foreground/80 hover:underline"
                                        >
                                          {label}
                                        </a>
                                      ) : (
                                        <span className="text-foreground/80">{citation}</span>
                                      )}
                                    </li>
                                  );
                                })}
                              </ul>
                            </div>
                          ) : null}
                        </div>
                      ) : (
                        <div className="leading-relaxed whitespace-pre-wrap">{message.content}</div>
                      )}
                    </div>
                  </div>
                  {message.proposedActions?.length ? (
                    <div className="space-y-3">
                      {message.proposedActions.map((action) => {
                        const progress =
                          typeof action.metadata?.progress === "string"
                            ? action.metadata.progress
                            : null;
                        const result =
                          typeof action.metadata?.result === "string"
                            ? action.metadata.result
                            : null;
                        const errorMessage =
                          typeof action.metadata?.error === "string" ? action.metadata.error : null;
                        return (
                          <div key={action.id} className="space-y-2">
                            <ActionCard
                              action={action}
                              onApprove={onApproveAction}
                              onEdit={onEditAction}
                              onDismiss={onDismissAction}
                            />
                            {progress && action.status === "executing" ? (
                              <div className="flex items-center gap-2 rounded-md border border-dashed border-primary/40 bg-primary/10 px-3 py-2 text-xs text-primary">
                                <Loader2 className="h-3 w-3 animate-spin" />
                                <span>{progress}</span>
                              </div>
                            ) : null}
                            {result && action.status === "done" ? (
                              <div className="rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                                <p className="font-medium text-foreground/80">Result</p>
                                <p className="mt-1 whitespace-pre-wrap leading-relaxed text-foreground/80">
                                  {result}
                                </p>
                              </div>
                            ) : null}
                            {errorMessage && action.status === "error" ? (
                              <div className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                                <span className="whitespace-pre-wrap leading-relaxed">{errorMessage}</span>
                              </div>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  ) : null}
                </div>
              );
            })}
            {isBusy ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" /> Generating response…
              </div>
            ) : null}
          </div>
          <div ref={endRef} />
        </ScrollArea>
      </CardContent>
      <Separator />
      <form ref={formRef} onSubmit={handleSubmit} className="space-y-3 p-4">
        <Textarea
          value={input}
          onChange={(event) => onInputChange(event.target.value)}
          rows={3}
          placeholder="Ask a question or give the agent instructions…"
          disabled={disableInput}
          onKeyDown={(event) => {
            if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
              event.preventDefault();
              formRef.current?.requestSubmit();
            }
          }}
        />
        <div className="flex items-center justify-between gap-2">
          <div className="text-xs text-muted-foreground" />
          <div className="flex gap-2">
            {isBusy && onCancel ? (
              <Button type="button" variant="outline" size="sm" onClick={onCancel}>
                <StopCircle className="h-4 w-4" />
                Cancel
              </Button>
            ) : null}
            <Button type="submit" size="sm" disabled={isBusy || disableInput}>
              {isBusy ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : null}
              Send
            </Button>
          </div>
        </div>
      </form>
    </Card>
  );
}
