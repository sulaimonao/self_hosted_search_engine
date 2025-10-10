"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export function ChatPanel() {
  const [input, setInput] = useState("");

  return (
    <div className="flex h-full w-[26rem] flex-col gap-3 p-4 text-sm">
      <h3 className="text-sm font-semibold">Copilot chat</h3>
      <div className="flex-1 overflow-y-auto rounded border p-3 text-xs text-muted-foreground">
        Conversation history coming soon.
      </div>
      <form
        className="space-y-2"
        onSubmit={(event) => {
          event.preventDefault();
          setInput("");
        }}
      >
        <Textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask the copilot"
        />
        <Button type="submit" className="w-full">
          Send
        </Button>
      </form>
    </div>
  );
}
