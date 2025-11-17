"use client";

import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useChatThread } from "@/lib/useChatThread";

export function ChatInput() {
  const [value, setValue] = useState("");
  const [composerError, setComposerError] = useState<string | null>(null);
  const { sendMessage, isSending } = useChatThread();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) return;
    try {
      await sendMessage({ content: trimmed });
      setValue("");
      setComposerError(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to send";
      setComposerError(message);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mt-3 space-y-2">
      <div className="flex gap-2">
        <Input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="Ask the AI to summarize, search, or triage"
          disabled={isSending}
        />
        <Button type="submit" disabled={isSending}>
          {isSending ? "Sending" : "Send"}
        </Button>
      </div>
      {composerError && (
        <div className="rounded-md border border-state-danger/40 bg-state-danger/10 px-3 py-2 text-xs text-state-danger">
          <p>{composerError}</p>
          <button type="button" className="mt-1 underline" onClick={() => setComposerError(null)}>
            Dismiss
          </button>
        </div>
      )}
    </form>
  );
}
