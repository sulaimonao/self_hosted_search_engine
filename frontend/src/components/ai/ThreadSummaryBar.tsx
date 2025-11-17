"use client";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { useResearchSessionActions } from "@/hooks/useResearchSessionActions";
import { inferResearchSessionFromThread } from "@/lib/researchSession";
import { useChatThread } from "@/lib/useChatThread";

interface ThreadSummaryBarProps {
  onRequestTabChange?: (tab: "chat" | "tasks" | "context") => void;
}

export function ThreadSummaryBar({ onRequestTabChange }: ThreadSummaryBarProps) {
  const { messages, currentThread } = useChatThread();
  const session = inferResearchSessionFromThread(currentThread);
  const { summarizePageToNotes, exportSession, isSummarizingPage, isExporting, linkedTab } = useResearchSessionActions();
  const lastAssistant = [...messages].reverse().find((msg) => msg.role === "assistant");
  const lastUser = [...messages].reverse().find((msg) => msg.role === "user");

  return (
    <div className="mb-3 space-y-3 rounded-md border border-border-subtle bg-app-card-subtle p-3 text-sm shadow-subtle">
      <div className="flex items-center gap-3">
        <Avatar className="size-10 border border-border-subtle bg-accent-soft/30 text-fg">
          <AvatarFallback>AI</AvatarFallback>
        </Avatar>
        <div className="text-sm">
          <p className="font-medium text-fg">{session?.topic ?? (lastAssistant ? "Assistant" : "Waiting for input")}</p>
          <p className="text-xs text-fg-muted">
            {lastAssistant?.content ?? lastUser?.content ?? "Send a message to kick things off."}
          </p>
          {linkedTab?.current_url && (
            <p className="text-[11px] text-fg-muted">Active tab: {linkedTab.current_title ?? linkedTab.current_url}</p>
          )}
        </div>
      </div>
      {session && (
        <div className="flex flex-wrap gap-2 text-xs">
          <Button
            variant="outline"
            size="sm"
            className="rounded-full border-border-subtle bg-app-subtle text-xs"
            onClick={() => summarizePageToNotes()}
            disabled={isSummarizingPage}
          >
            {isSummarizingPage ? "Summarizing…" : "Summarize current page"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="rounded-full border-border-subtle bg-app-subtle text-xs"
            onClick={() => onRequestTabChange?.("context")}
          >
            Search my notes
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="rounded-full border-border-subtle bg-app-subtle text-xs"
            onClick={() => exportSession()}
            disabled={isExporting}
          >
            {isExporting ? "Exporting…" : "Export session"}
          </Button>
        </div>
      )}
    </div>
  );
}
