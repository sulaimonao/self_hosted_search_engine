"use client";

import { Badge } from "@/components/ui/badge";
import { useChatThread } from "@/lib/useChatThread";

export function AiPanelHeader() {
  const { currentThreadId, isLoading } = useChatThread();

  const status = currentThreadId ? "Thread active" : "No thread linked";

  return (
    <div className="mb-2 flex items-center justify-between">
      <div>
        <p className="text-xs uppercase text-muted-foreground">AI Copilot</p>
        <p className="font-semibold">
          {currentThreadId ? `Thread ${currentThreadId.slice(0, 8)}` : "Connect a thread"}
        </p>
      </div>
      <Badge variant={currentThreadId ? "secondary" : "outline"}>{isLoading ? "Loading" : status}</Badge>
    </div>
  );
}
