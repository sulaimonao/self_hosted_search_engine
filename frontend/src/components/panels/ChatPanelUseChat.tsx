"use client";

import React, { useMemo, useState } from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { ChatMessageMarkdown } from "@/components/chat-message";
import { CopilotHeader } from "@/components/copilot-header";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Loader2, StopCircle } from "lucide-react";
import { safeLocalStorage } from "@/utils/isomorphicStorage";
import { storeChatMessage } from "@/lib/api";

const DEFAULT_THROTTLE = 50;

type ChatPanelUseChatProps = {
  inventory?: { chatModels?: string[] } | null;
  selectedModel?: string | null;
  threadId: string;
  onLinkClick?: (url: string, event: React.MouseEvent<HTMLAnchorElement>) => void;
};

export default function ChatPanelUseChat({ inventory, selectedModel, threadId, onLinkClick }: ChatPanelUseChatProps) {
  const storedThrottle = typeof window !== "undefined" ? safeLocalStorage.get("chat:throttleMs") : null;
  const throttleMs = storedThrottle ? Number.parseInt(storedThrottle, 10) || DEFAULT_THROTTLE : DEFAULT_THROTTLE;

  const transport = useMemo(() => new DefaultChatTransport({ api: "/api/chat" }), []);

  type IncomingMsg = { id?: string; role?: string; content?: string; text?: string };
  // useChat types vary; treat as unknown and narrow
  // useChat v5 expects you to manage your own input; keep a local input state
  const [input, setInput] = useState("");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const chatHook = useChat({ transport, experimental_throttle: throttleMs } as any) as unknown as {
    messages?: IncomingMsg[];
    sendMessage?: (arg: unknown, opts?: unknown) => Promise<unknown>;
    status?: string;
  };
  const { messages = [], sendMessage, status } = chatHook;

  const [isBusy, setIsBusy] = useState(false);

  const handleSend = async () => {
    const trimmed = (input ?? "").trim();
    if (!trimmed || isBusy) return;
    setIsBusy(true);
    try {
      // Persist user message locally for history parity
      await storeChatMessage(threadId, {
        id: `local-${Date.now()}`,
        role: "user",
        content: trimmed,
      }).catch(() => undefined);

    // v5: send text as `{ text }` and pass additional body via options
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    await (sendMessage as any)({ text: trimmed }, { body: { model: selectedModel ?? undefined } });
    } finally {
      setIsBusy(false);
      setInput("");
    }
  };

  const isStreaming = status === "streaming" || status === "loading";

  return (
    <div className="flex h-full w-full max-w-[34rem] flex-col gap-4 p-4 text-sm">
  <CopilotHeader chatModels={inventory?.chatModels ?? []} selectedModel={selectedModel ?? null} onModelChange={() => {}} />
      <div className="flex-1 overflow-hidden rounded-lg border bg-background">
        <ScrollArea className="h-full pr-3">
          <div className="space-y-4 p-3 pr-1">
            {messages.map((m: IncomingMsg, idx: number) => {
              const role = m.role ?? "assistant";
              const content = typeof m.content === "string" ? m.content : m.text ?? "";
              return (
                <div key={m.id ?? `${role}-${idx}`} className={role === "assistant" ? "bg-card rounded-lg border px-3 py-2" : "bg-muted rounded-lg border px-3 py-2"}>
                  <div className="text-xs text-muted-foreground uppercase tracking-wide">{role}</div>
                  <div className="mt-2">
                    <ChatMessageMarkdown text={content} onLinkClick={onLinkClick} />
                    {role === "assistant" && isStreaming ? (
                      <div className="flex items-center gap-2 text-xs text-muted-foreground mt-2">
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        <span>Generating…</span>
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        </ScrollArea>
      </div>

      <form
        className="space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          void handleSend();
        }}
      >
  <Textarea value={input ?? ""} onChange={(e) => setInput?.(e.target.value)} placeholder={inventory ? "Ask the copilot" : "Ask the copilot"} rows={4} />
        <div className="flex items-center justify-between gap-2">
          {isBusy ? (
            <Button type="button" variant="outline" onClick={() => {}}>
              <StopCircle className="mr-2 h-4 w-4" /> Cancel
            </Button>
          ) : (
            <span className="text-[11px] uppercase tracking-wide text-muted-foreground">⌘/Ctrl + Enter to send</span>
          )}
          <Button type="submit" disabled={isBusy || !input || !(inventory ? (inventory.chatModels ?? []).length > 0 : true)}>
            {isBusy ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Sending
              </>
            ) : (
              "Send"
            )}
          </Button>
        </div>
      </form>
    </div>
  );
}
