"use client";

import { useEffect, useMemo, useState } from "react";
import { Shield } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { resolveBrowserAPI } from "@/lib/browser-ipc";
import { useBrowserRuntimeStore } from "@/state/useBrowserRuntime";

function originFromUrl(url?: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).origin;
  } catch {
    return null;
  }
}

type PermissionSetting = "allow" | "deny" | "ask";

export function SiteInfoPopover({ url }: { url?: string | null }) {
  const [open, setOpen] = useState(false);
  const api = useMemo(() => resolveBrowserAPI(), []);
  const origin = useMemo(() => originFromUrl(url), [url]);
  const permissions = useBrowserRuntimeStore((state) =>
    origin ? state.permissions[origin] ?? [] : [],
  );

  useEffect(() => {
    if (!open || !api || !origin) {
      return;
    }
    let cancelled = false;
    api
      .listPermissions(origin)
      .then((entries) => {
        if (cancelled || !origin) return;
        useBrowserRuntimeStore
          .getState()
          .updatePermissions({ origin, permissions: entries });
      })
      .catch((error) => console.warn("[browser] failed to load permissions", error));
    return () => {
      cancelled = true;
    };
  }, [api, open, origin]);

  const handlePermissionChange = async (permission: string, setting: PermissionSetting) => {
    if (!api || !origin) return;
    try {
      if (setting === "ask") {
        await api.clearPermission(origin, permission);
      } else {
        await api.setPermission(origin, permission, setting);
      }
      const refreshed = await api.listPermissions(origin);
      useBrowserRuntimeStore
        .getState()
        .updatePermissions({ origin, permissions: refreshed });
    } catch (error) {
      console.warn("[browser] failed to update permission", error);
    }
  };

  const handleClearSiteData = async () => {
    if (!api || !origin) return;
    try {
      await api.clearSiteData(origin);
    } catch (error) {
      console.warn("[browser] failed to clear site data", error);
    }
  };

  if (!origin) {
    return (
      <Button variant="ghost" size="icon" disabled className="text-muted-foreground">
        <Shield size={16} />
      </Button>
    );
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" title="Site information">
          <Shield size={16} />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 space-y-4">
        <div>
          <p className="text-sm font-medium">Site security</p>
          <p className="truncate text-xs text-muted-foreground">{origin}</p>
        </div>
        <div className="space-y-2">
          <p className="text-xs font-medium">Permissions</p>
          {permissions.length === 0 ? (
            <p className="text-xs text-muted-foreground">No saved decisions. Requests will ask.</p>
          ) : (
            <div className="space-y-2">
              {permissions.map((entry) => {
                const current = entry.setting ?? "ask";
                return (
                  <div key={entry.permission} className="flex items-center justify-between gap-2">
                    <span className="text-xs capitalize">{entry.permission.replace(/-/g, " ")}</span>
                    <Select
                      value={current}
                      onValueChange={(value) =>
                        handlePermissionChange(entry.permission, value as PermissionSetting)
                      }
                    >
                      <SelectTrigger className="h-8 w-[110px] text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="allow">Allow</SelectItem>
                        <SelectItem value="deny">Block</SelectItem>
                        <SelectItem value="ask">Ask</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                );
              })}
            </div>
          )}
        </div>
        <div className="flex items-center justify-between gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              if (!api || !origin) return;
              api
                .clearOriginPermissions(origin)
                .then(() => api.listPermissions(origin))
                .then((entries) =>
                  useBrowserRuntimeStore
                    .getState()
                    .updatePermissions({ origin, permissions: entries }),
                )
                .catch((error) => console.warn("[browser] failed to reset permissions", error));
            }}
          >
            Reset permissions
          </Button>
          <Button variant="secondary" size="sm" onClick={handleClearSiteData}>
            Clear site data
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
