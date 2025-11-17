"use client";

import { useEffect, useRef } from "react";

import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { useChatThread } from "@/lib/useChatThread";

export function ChatMessageList() {
  const { messages, isLoading, error } = useChatThread();
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

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center rounded-xl border bg-background p-4 text-sm text-destructive">
        {error}
      </div>
    );
  }

  if (!messages.length) {
    return (
      <div className="flex flex-1 items-center justify-center rounded-xl border bg-background p-6 text-sm text-muted-foreground">
        No messages yet. Ask the assistant anything about your current tab.
      </div>
    );
  }

  return (
    <ScrollArea className="flex-1 rounded-xl border bg-background p-3">
      <div className="space-y-3 text-sm">
        {messages.map((message) => (
          <div key={message.id}>
            <p className="font-medium text-primary capitalize">{message.role}</p>
            <p className="text-muted-foreground whitespace-pre-wrap">{message.content}</p>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  );
}
