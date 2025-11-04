"use client";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { ChatPanel as ChatPanelContent } from "@/components/panels/ChatPanel";
import { useIsMounted } from "@/hooks/useIsMounted";

type ChatPanelProps = {
  open: boolean;
  onOpenChange: (value: boolean) => void;
};

export default function ChatPanel({ open, onOpenChange }: ChatPanelProps) {
  const mounted = useIsMounted();

  if (!mounted || !open) {
    return null;
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" size="xl" className="w-full max-w-[34rem] border-l bg-background p-0">
        <ChatPanelContent />
      </SheetContent>
    </Sheet>
  );
}
