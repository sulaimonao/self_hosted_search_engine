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
import { COMMAND_ACTIONS, NAV_ITEMS } from "@/lib/navigation";

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (value: boolean) => void;
}) {
  const router = useRouter();
  const { toast } = useToast();

  const runAction = useCallback(
    (actionId: string) => {
      const description = COMMAND_ACTIONS.find((action) => action.id === actionId)?.label;
      toast({
        title: description ?? "Action triggered",
        description: "This is a placeholder action in the new shell.",
      });
    },
    [toast]
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
              onSelect={() => {
                runAction(action.id);
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
