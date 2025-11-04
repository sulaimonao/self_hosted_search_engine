"use client";
import dynamic from "next/dynamic";
import { useChat } from "./ChatProvider";
import { ErrorBoundary } from "../layout/ErrorBoundary";
import { useIsMounted } from "@/hooks/useIsMounted";

const ChatPanel = dynamic(() => import("./chat-panel"), { ssr: false });

export default function ChatOverlay() {
  const { open, setOpen, ready } = useChat();
  const mounted = useIsMounted();

  if (!mounted || !ready) {
    return null;
  }

  return (
    <ErrorBoundary>
      <ChatPanel open={open} onOpenChange={setOpen} />
    </ErrorBoundary>
  );
}
