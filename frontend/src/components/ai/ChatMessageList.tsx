"use client";

import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { useChatThread } from "@/lib/useChatThread";

export function ChatMessageList() {
  const { messages, isLoading, error, reloadThread } = useChatThread();
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  if (isLoading) {
    return (
      <ScrollArea className="flex-1 rounded-xl border bg-background p-3">
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
        <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
          <div className="flex items-center justify-between gap-3">
            <p>{error}</p>
            <Button variant="outline" size="sm" onClick={reloadThread}>
              Retry
            </Button>
          </div>
        </div>
      )}
      {!messages.length ? (
        <div className="flex flex-1 flex-col items-center justify-center rounded-xl border bg-background p-6 text-center">
          <p className="text-sm font-medium text-foreground">Start a conversation</p>
          <p className="text-xs text-muted-foreground">Ask about your current tab or any captured data.</p>
          <ul className="mt-3 space-y-1 text-xs text-muted-foreground">
            <li>• Ask about this page</li>
            <li>• Search your knowledge base</li>
            <li>• Create a TODO list for this site</li>
          </ul>
        </div>
      ) : (
        <ScrollArea className="flex-1 rounded-xl border bg-background p-3">
          <div className="space-y-3 text-sm">
            {messages.map((message) => (
              <div key={message.id}>
                <p className="font-medium capitalize text-primary">{message.role}</p>
                <p className="whitespace-pre-wrap text-muted-foreground">{message.content}</p>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>
      )}
    </div>
  );
}
