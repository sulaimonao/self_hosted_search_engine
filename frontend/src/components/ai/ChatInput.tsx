"use client";

import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";
import { useChatThread } from "@/lib/useChatThread";

export function ChatInput() {
  const [value, setValue] = useState("");
  const { toast } = useToast();
  const { sendMessage, isSending } = useChatThread();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) return;
    try {
      await sendMessage({ content: trimmed });
      setValue("");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to send";
      toast({ title: "Chat error", description: message, variant: "destructive" });
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mt-3 flex gap-2">
      <Input
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="Ask the AI to summarize, search, or triage"
        disabled={isSending}
      />
      <Button type="submit" disabled={isSending}>
        {isSending ? "Sending" : "Send"}
      </Button>
    </form>
  );
}
