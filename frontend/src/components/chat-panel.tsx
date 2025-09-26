<<<<<<< ours
<<<<<<< ours
import { AgentLog } from "./agent-log";

export function ChatPanel() {
  return (
    <div className="flex flex-col h-full bg-background">
      <div className="flex-1 p-4 overflow-y-auto">
        <p>Chat Panel</p>
      </div>
      <AgentLog />
    </div>
  );
}
=======
=======
>>>>>>> theirs
"use client";

import { useEffect, useMemo, useRef } from "react";
import { Bot, Loader2, SendHorizontal, User } from "lucide-react";
import { ActionCard } from "@/components/action-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { AgentAction, ChatMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ChatPanelProps {
  messages: ChatMessage[];
  actions: AgentAction[];
  input: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  disabled?: boolean;
  onActionApprove: (action: AgentAction, note?: string) => Promise<void> | void;
  onActionDismiss: (action: AgentAction) => Promise<void> | void;
  onActionEdit?: (action: AgentAction, updates: Partial<AgentAction>) => Promise<void> | void;
}

export function ChatPanel({
  messages,
  actions,
  input,
  onInputChange,
  onSend,
  disabled,
  onActionApprove,
  onActionDismiss,
  onActionEdit,
}: ChatPanelProps) {
  const listRef = useRef<HTMLDivElement>(null);
  const pendingActions = useMemo(() => actions.filter((action) => action.status === "proposed"), [actions]);

  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages.length, pendingActions.length]);

  return (
    <Card className="flex h-full flex-col border-muted-foreground/30">
      <CardHeader className="border-b border-border/60 pb-4">
        <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Co-pilot Chat
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4 p-0">
        <ScrollArea className="flex-1">
          <div ref={listRef} className="flex flex-col gap-4 px-6 py-4">
            {messages.map((message) => (
              <div
                key={message.id}
                className={cn(
                  "flex gap-3",
                  message.role === "user" ? "flex-row-reverse text-right" : "flex-row",
                )}
              >
                <div
                  className={cn(
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-full border",
                    message.role === "user" ? "border-primary/40 bg-primary/20" : "border-muted-foreground/40 bg-muted/20",
                  )}
                >
                  {message.role === "user" ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                </div>
                <div className="flex max-w-xl flex-col gap-2">
                  <div
                    className={cn(
                      "rounded-xl border px-4 py-2 text-sm leading-relaxed shadow-sm",
                      message.role === "user"
                        ? "border-primary/30 bg-primary/10"
                        : "border-border/60 bg-card/80",
                    )}
                  >
                    <p className="whitespace-pre-line text-foreground">{message.content}</p>
                  </div>
                  {message.pendingActions?.map((action) => (
                    <ActionCard
                      key={action.id}
                      action={action}
                      onApprove={onActionApprove}
                      onDismiss={onActionDismiss}
                      onEdit={onActionEdit}
                      compact
                    />
                  ))}
                </div>
              </div>
            ))}
            {pendingActions.length > 0 && (
              <div className="space-y-3">
                {pendingActions.map((action) => (
                  <ActionCard
                    key={action.id}
                    action={action}
                    onApprove={onActionApprove}
                    onDismiss={onActionDismiss}
                    onEdit={onActionEdit}
                  />
                ))}
              </div>
            )}
          </div>
        </ScrollArea>
        <div className="border-t border-border/60 bg-background p-4">
          <form
            className="flex items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              onSend();
            }}
          >
            <Input
              value={input}
              onChange={(event) => onInputChange(event.target.value)}
              placeholder="Ask the agent or propose a plan..."
              className="flex-1"
              disabled={disabled}
            />
            <Button type="submit" disabled={disabled || input.trim().length === 0}>
              {disabled ? <Loader2 className="h-4 w-4 animate-spin" /> : <SendHorizontal className="h-4 w-4" />}
            </Button>
          </form>
          <p className="mt-2 text-xs text-muted-foreground">
            Tip: Use natural language to request crawls or analysis. The agent will always ask for confirmation before acting.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
<<<<<<< ours
>>>>>>> theirs
=======
>>>>>>> theirs
