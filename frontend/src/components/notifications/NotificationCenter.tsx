"use client";

import { useMemo } from "react";

import { Button } from "@/components/ui/button";
import { useAppStore } from "@/state/useAppStore";

export function NotificationCenter() {
  const notifications = useAppStore((state) => state.notifications);
  const clearNotifications = useAppStore((state) => state.clearNotifications);
  const muteNotification = useAppStore((state) => state.muteNotification);

  const items = useMemo(() => {
    return Object.values(notifications)
      .filter((item) => !item.muted)
      .sort((a, b) => b.latest - a.latest);
  }, [notifications]);

  return (
    <div className="w-96 max-w-sm space-y-3 p-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Notifications</h3>
        <Button variant="ghost" size="sm" onClick={clearNotifications}>
          Clear all
        </Button>
      </div>
      <ul className="space-y-2 max-h-96 overflow-auto pr-1">
        {items.length === 0 ? (
          <li className="text-xs text-muted-foreground">No notifications</li>
        ) : null}
        {items.map((item) => (
          <li key={item.key} className="space-y-2 rounded-lg border p-2 text-xs">
            <div className="flex items-start justify-between gap-3">
              <div className="space-y-1">
                <p className="font-medium text-foreground">
                  {item.kind}
                  {item.site ? ` · ${item.site}` : ""}
                </p>
                <p className="text-muted-foreground">{item.lastMessage ?? "Updated"}</p>
              </div>
              <span className="text-[10px] text-muted-foreground">
                {new Date(item.latest).toLocaleTimeString()}
              </span>
            </div>
            <div className="flex items-center justify-between text-muted-foreground">
              <span>Count {item.count}</span>
              <Button size="sm" variant="ghost" onClick={() => muteNotification(item.key, true)}>
                Mute
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
