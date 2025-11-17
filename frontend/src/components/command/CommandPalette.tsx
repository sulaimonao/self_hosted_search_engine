"use client";

import { useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command";
import { useToast } from "@/components/ui/use-toast";
import { COMMAND_ACTIONS, NAV_ITEMS, ROUTES } from "@/lib/navigation";
import { useChatThread } from "@/lib/useChatThread";
import { apiClient } from "@/lib/backend/apiClient";

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (value: boolean) => void;
}) {
  const router = useRouter();
  const { toast } = useToast();
  const { startThread } = useChatThread();

  const runAction = useCallback(
    async (actionId: string) => {
      try {
        switch (actionId) {
          case "new-tab":
            await startThread({ origin: "browser" });
            router.push(ROUTES.browse);
            toast({ title: "Browser tab linked", description: "New AI thread ready." });
            break;
          case "new-chat":
            await startThread({ origin: "chat" });
            toast({ title: "New chat", description: "Ask the assistant anything." });
            break;
          case "export-bundle":
            router.push(ROUTES.data);
            toast({ title: "Open data", description: "Configure bundle export." });
            break;
          case "import-bundle":
            router.push(ROUTES.data);
            toast({ title: "Open data", description: "Upload bundle for import." });
            break;
          case "run-repo-checks":
            router.push(ROUTES.repo);
            break;
          case "clear-history":
            await apiClient.delete("/api/browser/history", {
              body: JSON.stringify({ clear_all: true }),
            });
            toast({ title: "History cleared" });
            break;
          default:
            toast({ title: "Action triggered", description: "Feature coming soon." });
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "Action failed";
        toast({ title: "Action failed", description: message, variant: "destructive" });
      }
    },
    [router, startThread, toast],
  );

  useEffect(() => {
    function handleKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpenChange(!open);
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onOpenChange, open]);

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="Jump to a section or run an action" />
      <CommandList>
        <CommandEmpty>No matching commands.</CommandEmpty>
        <CommandGroup heading="Navigate">
          {NAV_ITEMS.map((item) => (
            <CommandItem
              key={item.href}
              value={item.title}
              onSelect={() => {
                router.push(item.href);
                onOpenChange(false);
              }}
            >
              {item.title}
              <CommandShortcut>{item.href}</CommandShortcut>
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Quick actions">
          {COMMAND_ACTIONS.map((action) => (
            <CommandItem
              key={action.id}
              value={action.label}
              onSelect={async () => {
                await runAction(action.id);
                onOpenChange(false);
              }}
            >
              {action.label}
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
