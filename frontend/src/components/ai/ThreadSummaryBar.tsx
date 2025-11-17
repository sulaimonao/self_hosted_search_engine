"use client";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { useChatThread } from "@/lib/useChatThread";

export function ThreadSummaryBar() {
  const { messages } = useChatThread();
  const lastAssistant = [...messages].reverse().find((msg) => msg.role === "assistant");
  const lastUser = [...messages].reverse().find((msg) => msg.role === "user");

  return (
    <div className="mb-3 flex items-center gap-3 rounded-md border border-border-subtle bg-app-card-subtle p-3 text-sm shadow-subtle">
      <Avatar className="size-10 border border-border-subtle bg-accent-soft/30 text-fg">
        <AvatarFallback>AI</AvatarFallback>
      </Avatar>
      <div className="text-sm">
        <p className="font-medium text-fg">{lastAssistant ? "Assistant" : "Waiting for input"}</p>
        <p className="text-xs text-fg-muted">
          {lastAssistant?.content ?? lastUser?.content ?? "Send a message to kick things off."}
        </p>
      </div>
    </div>
  );
}
