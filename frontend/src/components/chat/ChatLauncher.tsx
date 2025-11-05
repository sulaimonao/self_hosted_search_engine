"use client";
import { MessageSquare } from "lucide-react";
import { useChat } from "./ChatProvider";

export default function ChatLauncher() {
  const { toggle, ready } = useChat();

  return (
    <button
      type="button"
      aria-label="Open chat"
      onClick={ready ? toggle : undefined}
      disabled={!ready}
      className="fixed bottom-4 right-4 z-50 rounded-full bg-black/80 p-3 text-white shadow-lg transition-opacity hover:opacity-90 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
    >
      {/* Revert to the previous chat icon design using MessageSquare for a familiar look. */}
      <MessageSquare size={20} />
    </button>
  );
}
