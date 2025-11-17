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
import { useRepoList } from "@/lib/backend/hooks";
import { setAiPanelSessionOpen } from "@/lib/uiSession";

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
  const repoList = useRepoList();

  const runAction = useCallback(
    async (actionId: string) => {
      try {
        switch (actionId) {
          case "new-tab": {
            await startThread({ origin: "browser" });
            setAiPanelSessionOpen(true);
            router.push(ROUTES.browse);
            toast({ title: "New browser tab", description: "Linked to a fresh AI thread." });
            break;
          }
          case "new-chat": {
            await startThread({ origin: "chat" });
            setAiPanelSessionOpen(true);
            toast({ title: "New chat", description: "Ask the assistant anything." });
            break;
          }
          case "export-bundle": {
            router.push(`${ROUTES.data}?focus=export`);
            toast({ title: "Export bundle", description: "Focused the export form." });
            break;
          }
          case "import-bundle": {
            router.push(`${ROUTES.data}?focus=import`);
            toast({ title: "Import bundle", description: "Ready to paste a bundle path." });
            break;
          }
          case "run-repo-checks": {
            const repoId = repoList.data?.items?.[0]?.id ?? null;
            const href = repoId ? `${ROUTES.repo}?repo=${encodeURIComponent(repoId)}` : ROUTES.repo;
            router.push(href);
            toast({
              title: "Repo checks",
              description: repoId ? `Opening ${repoId}` : "Select a repo to continue.",
            });
            break;
          }
          case "clear-history": {
            const domain = window.prompt("Clear history for which domain? Leave blank to purge all.")?.trim();
            await apiClient.delete("/api/browser/history", {
              body: JSON.stringify(domain ? { domain, clear_all: false } : { clear_all: true }),
            });
            toast({
              title: "History cleared",
              description: domain ? `Removed visits for ${domain}` : "Cleared all captured history.",
            });
            break;
          }
          default:
            toast({ title: "Action triggered", description: "Feature coming soon." });
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "Action failed";
        toast({ title: "Action failed", description: message, variant: "destructive" });
      }
    },
    [repoList.data?.items, router, startThread, toast],
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
          {NAV_ITEMS.map((item, index) => (
            <CommandItem
              key={item.href}
              value={item.title}
              onSelect={() => {
                router.push(item.href);
                toast({ title: "Navigating", description: `Opening ${item.title}.` });
                onOpenChange(false);
              }}
            >
              {item.title}
              <CommandShortcut>{`⌘${index + 1}`}</CommandShortcut>
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
              {action.shortcut ? <CommandShortcut>{action.shortcut}</CommandShortcut> : null}
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
