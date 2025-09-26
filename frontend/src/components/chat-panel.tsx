"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { Loader2, StopCircle, UploadCloud } from "lucide-react";

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
  onStopStreaming: () => void;
  isStreaming: boolean;
  onApproveAction: (action: ProposedAction) => void;
  onEditAction: (action: ProposedAction) => void;
  onDismissAction: (action: ProposedAction) => void;
  onUploadFile?: () => void;
}

export function ChatPanel({
  messages,
  input,
  onInputChange,
  onSend,
  onStopStreaming,
  isStreaming,
  onApproveAction,
  onEditAction,
  onDismissAction,
  onUploadFile,
}: ChatPanelProps) {
  const formRef = useRef<HTMLFormElement | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, isStreaming]);

  const handleSubmit = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!input.trim()) return;
      onSend(input.trim());
    },
    [input, onSend]
  );

  const groupedMessages = useMemo(() => {
    return messages.map((message) => {
      const lines = message.content.split(/\n+/);
      return {
        ...message,
        lines,
      };
    });
  }, [messages]);

  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-sm">Copilot chat</CardTitle>
          <div className="flex gap-2 text-xs text-muted-foreground">
            <span>Streaming {isStreaming ? "live" : "idle"}</span>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex-1 overflow-hidden">
        <ScrollArea className="h-full pr-4">
          <div className="space-y-4">
            {groupedMessages.length === 0 && (
              <div className="rounded border border-dashed p-6 text-center text-sm text-muted-foreground">
                Ask the agent what to do next or drop a URL into the crawl manager.
              </div>
            )}
            {groupedMessages.map((message) => (
              <div key={message.id} className="space-y-2">
                <div
                  className={cn(
                    "rounded-lg border px-3 py-2 text-sm",
                    message.role === "user" ? "bg-secondary/80" : "bg-card"
                  )}
                >
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span className="capitalize">{message.role}</span>
                    <time suppressHydrationWarning>
                      {new Date(message.createdAt).toLocaleTimeString()}
                    </time>
                  </div>
                  <Separator className="my-2" />
                  <div className="space-y-2">
                    {message.lines.map((line, index) => (
                      <p key={index} className="whitespace-pre-wrap leading-relaxed">
                        {line}
                      </p>
                    ))}
                  </div>
                </div>
                {message.proposedActions?.length ? (
                  <div className="space-y-2">
                    {message.proposedActions.map((action) => (
                      <ActionCard
                        key={action.id}
                        action={action}
                        onApprove={onApproveAction}
                        onEdit={onEditAction}
                        onDismiss={onDismissAction}
                      />
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
            {isStreaming && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" /> Generating response…
              </div>
            )}
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
          onKeyDown={(event) => {
            if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
              event.preventDefault();
              formRef.current?.requestSubmit();
            }
          }}
        />
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Button type="button" variant="ghost" size="sm" onClick={onUploadFile}>
              <UploadCloud className="h-4 w-4" /> Attach context
            </Button>
          </div>
          <div className="flex gap-2">
            {isStreaming && (
              <Button type="button" variant="outline" size="sm" onClick={onStopStreaming}>
                <StopCircle className="h-4 w-4" /> Stop
              </Button>
            )}
            <Button type="submit" size="sm">
              Send
            </Button>
          </div>
        </div>
      </form>
    </Card>
  );
}
