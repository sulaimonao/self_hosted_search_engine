"use client";

import { Bell } from "lucide-react";
import { useId, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { NotificationCenter } from "@/components/notifications/NotificationCenter";
import { useAppStore } from "@/state/useAppStore";

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const notifications = useAppStore(useShallow((state) => state.notifications));
  const unreadCount = Object.values(notifications).reduce(
    (total, item) => total + (item.muted ? 0 : item.count),
    0,
  );
  const triggerDescriptionId = useId();
  const buttonLabel =
    unreadCount > 0
      ? `${unreadCount} unread notification${unreadCount === 1 ? "" : "s"}`
      : "Notifications";

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="icon"
          aria-label={buttonLabel}
          aria-describedby={triggerDescriptionId}
          className="relative"
        >
          <Bell size={16} aria-hidden="true" />
          <span id={triggerDescriptionId} className="sr-only">
            Opens the notification center
          </span>
          {unreadCount > 0 ? (
            <span
              className="absolute -right-1 -top-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold text-primary-foreground"
              aria-hidden="true"
            >
              {unreadCount > 99 ? "99+" : unreadCount}
            </span>
          ) : null}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="p-0">
        <NotificationCenter />
      </PopoverContent>
    </Popover>
  );
}
