"use client";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { useChatThread } from "@/lib/useChatThread";

export function ThreadSummaryBar() {
  const { messages } = useChatThread();
  const lastAssistant = [...messages].reverse().find((msg) => msg.role === "assistant");
  const lastUser = [...messages].reverse().find((msg) => msg.role === "user");

  return (
    <div className="mb-3 flex items-center gap-3 rounded-xl border bg-card/60 p-3">
      <Avatar className="size-10 bg-muted">
        <AvatarFallback>AI</AvatarFallback>
      </Avatar>
      <div className="text-sm">
        <p className="font-medium">{lastAssistant ? "Assistant" : "Waiting for input"}</p>
        <p className="text-xs text-muted-foreground">
          {lastAssistant?.content ?? lastUser?.content ?? "Send a message to kick things off."}
        </p>
      </div>
    </div>
  );
}
