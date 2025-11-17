"use client";

import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";

export function ChatInput() {
  const [value, setValue] = useState("");
  const { toast } = useToast();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) return;
    toast({ title: "Message queued", description: trimmed });
    setValue("");
  }

  return (
    <form onSubmit={handleSubmit} className="mt-3 flex gap-2">
      <Input
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="Ask the AI to summarize, search, or triage"
      />
      <Button type="submit">Send</Button>
    </form>
  );
}
