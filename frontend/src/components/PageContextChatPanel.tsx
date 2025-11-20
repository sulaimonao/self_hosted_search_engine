"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { storeChatMessage } from "@/lib/api";
import { apiClient } from "@/lib/backend/apiClient";

// Legacy diagnostic panel kept for manual page-context testing; not mounted in the current shell.
export function PageContextChatPanel() {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [usePageContext, setUsePageContext] = useState(true);

  useEffect(() => {
    let active = true;
    void apiClient
      .post<{ id: string }>("/api/threads", {
        title: "Page context diagnostic",
        origin: "diagnostic",
        metadata: { source: "home-panel" },
      })
      .then((payload) => {
        if (active) {
          setThreadId(payload.id);
        }
      })
      .catch((err) => {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to prepare chat thread");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const pageUrl = useMemo(() => {
    if (typeof window === "undefined") {
      return null;
    }
    return window.location.href;
  }, []);

  const handleSend = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || !threadId) {
      return;
    }
    setSending(true);
    setError(null);
    setStatus(null);
    try {
      const messageId =
        typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
          ? crypto.randomUUID()
          : Math.random().toString(36).slice(2);
      await storeChatMessage(threadId, {
        id: messageId,
        role: "user",
        content: trimmed,
        page_url: usePageContext ? pageUrl : undefined,
      });
      setInput("");
      setStatus(usePageContext && pageUrl ? `Sent with ${pageUrl}` : "Sent without page context");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message");
    } finally {
      setSending(false);
    }
  }, [input, pageUrl, threadId, usePageContext]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm">
        <Switch
          id="diagnostic-use-current-page"
          checked={usePageContext}
          disabled={!threadId || sending}
          onCheckedChange={setUsePageContext}
        />
        <label htmlFor="diagnostic-use-current-page" className="cursor-pointer select-none">
          Use current page
        </label>
      </div>
      <div>
        <Textarea
          aria-label="Chat message"
          data-testid="chat-composer"
          placeholder={threadId ? "Ask the copilot" : "Preparing chat session…"}
          disabled={!threadId || sending}
          rows={4}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void handleSend();
            }
          }}
        />
        <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
          <span>{usePageContext ? "Page URL will be included" : "Page context disabled"}</span>
          <Button type="button" size="sm" disabled={!threadId || sending || !input.trim()} onClick={() => void handleSend()}>
            {sending ? "Sending…" : "Send"}
          </Button>
        </div>
        {error ? <p className="mt-2 text-xs text-destructive">{error}</p> : null}
        {status ? <p className="mt-2 text-xs text-muted-foreground">{status}</p> : null}
      </div>
    </div>
  );
}
