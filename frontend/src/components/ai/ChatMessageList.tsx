"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/use-toast";
import { apiClient } from "@/lib/backend/apiClient";
import { useChatThread } from "@/lib/useChatThread";
import { cn } from "@/lib/utils";
import { useQueryClient } from "@tanstack/react-query";

export function ChatMessageList() {
  const { messages, isLoading, error, reloadThread, currentThreadId } = useChatThread();
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [taskMessageId, setTaskMessageId] = useState<string | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const handleCreateTask = async (messageId: string, content: string) => {
    if (!currentThreadId) {
      toast({ title: "No session", description: "Link a thread to create tasks.", variant: "warning" });
      return;
    }
    setTaskMessageId(messageId);
    try {
      const normalized = content.trim();
      const [firstLine] = normalized.split("\n");
      const title = (firstLine || "Follow up").slice(0, 120);
      const description = normalized.length > 120 ? normalized : undefined;
      await apiClient.post("/api/tasks", {
        thread_id: currentThreadId,
        title,
        description,
        status: "open",
      });
      toast({ title: "Task created", description: "Find it under the Tasks tab." });
      await queryClient.invalidateQueries({ queryKey: ["tasks", currentThreadId] });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to create task";
      toast({ title: "Task not created", description: message, variant: "destructive" });
    } finally {
      setTaskMessageId(null);
    }
  };

  if (isLoading) {
    return (
      <ScrollArea className="flex-1 rounded-md border border-border-subtle bg-app-card-subtle p-3 shadow-subtle">
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-14 w-full" />
          ))}
        </div>
      </ScrollArea>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-3">
      {error && (
        <div className="rounded-md border border-state-danger/40 bg-state-danger/10 p-3 text-xs text-state-danger">
          <div className="flex items-center justify-between gap-3">
            <p>{error}</p>
            <Button variant="outline" size="sm" onClick={reloadThread}>
              Retry
            </Button>
          </div>
        </div>
      )}
      {!messages.length ? (
        <div className="flex flex-1 flex-col items-center justify-center rounded-md border border-border-subtle bg-app-card-subtle p-6 text-center">
          <p className="text-sm font-medium text-fg">Start a conversation</p>
          <p className="text-xs text-fg-muted">Ask about your current tab or any captured data.</p>
          <ul className="mt-3 space-y-1 text-xs text-fg-muted">
            <li>• Ask about this page</li>
            <li>• Search your knowledge base</li>
            <li>• Create a TODO list for this site</li>
          </ul>
        </div>
      ) : (
        <ScrollArea className="flex-1 rounded-md border border-border-subtle bg-app-card-subtle p-3 shadow-subtle">
          <div className="space-y-3 text-sm">
            {messages.map((message) => (
              <div
                key={message.id}
                className={cn(
                  "rounded-md border border-border-subtle px-3 py-2 shadow-subtle/0",
                  message.role === "user" ? "bg-app-card-subtle" : "bg-accent-soft"
                )}
              >
                <div className="mb-1 flex items-center justify-between text-[11px] uppercase tracking-wide text-fg-subtle">
                  <span>{message.role}</span>
                  {message.role !== "system" && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 px-2 text-[11px] font-semibold text-fg-muted hover:text-fg"
                      onClick={() => handleCreateTask(message.id, message.content)}
                      disabled={taskMessageId === message.id}
                    >
                      {taskMessageId === message.id ? "Saving…" : "Create task"}
                    </Button>
                  )}
                </div>
                <p className="whitespace-pre-wrap text-sm text-fg">{message.content}</p>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>
      )}
    </div>
  );
}
