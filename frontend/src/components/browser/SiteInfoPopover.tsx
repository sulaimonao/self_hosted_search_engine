"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Shield } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import type { BrowserPermissionState } from "@/lib/browser-ipc";
import { useBrowserRuntimeStore } from "@/state/useBrowserRuntime";

type PermissionEntry = BrowserPermissionState["permissions"][number];
const EMPTY_PERMISSIONS: readonly PermissionEntry[] = Object.freeze([]);

function originFromUrl(url?: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).origin;
  } catch {
    return null;
  }
}

type PermissionSetting = "allow" | "deny" | "ask";

function describePermissionSetting(setting: PermissionSetting): string {
  switch (setting) {
    case "allow":
      return "Allowed";
    case "deny":
      return "Blocked";
    default:
      return "Ask every time";
  }
}

type BadgeVariant = "default" | "secondary" | "destructive" | "outline";

function permissionBadgeVariant(setting: PermissionSetting): BadgeVariant {
  switch (setting) {
    case "allow":
      return "default";
    case "deny":
      return "destructive";
    default:
      return "secondary";
  }
}

function formatPermissionLabel(permission: string): string {
  return permission.replace(/-/g, " ");
}

function getPermissionDescriptor(permission: string): PermissionDescriptor | null {
  const normalized = permission.toLowerCase();
  switch (normalized) {
    case "camera":
    case "microphone":
    case "geolocation":
    case "notifications":
    case "midi":
    case "clipboard-read":
    case "clipboard-write":
      return { name: normalized as PermissionName };
    default:
      return null;
  }
}

async function revokeNavigatorPermission(permission: string): Promise<void> {
  if (typeof navigator === "undefined" || !("permissions" in navigator)) {
    return;
  }
  const descriptor = getPermissionDescriptor(permission);
  if (!descriptor) {
    return;
  }
  const permissionsApi = navigator.permissions;
  if (!permissionsApi || typeof permissionsApi.revoke !== "function") {
    return;
  }
  try {
    await permissionsApi.revoke(descriptor);
  } catch (error) {
    console.warn("[browser] failed to revoke navigator permission", { permission, error });
  }
}

export function SiteInfoPopover({ url }: { url?: string | null }) {
  const [open, setOpen] = useState(false);
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);
  const [clearingSiteData, setClearingSiteData] = useState(false);
  const [resettingPermission, setResettingPermission] = useState<string | null>(null);
  const api = useMemo(() => resolveBrowserAPI(), []);
  const origin = useMemo(() => originFromUrl(url), [url]);
  const permissions = useBrowserRuntimeStore(
    useCallback(
      (state) => (origin ? state.permissions[origin] ?? EMPTY_PERMISSIONS : EMPTY_PERMISSIONS),
      [origin],
    ),
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
        await handlePermissionReset(permission);
        return;
      }
      await api.setPermission(origin, permission, setting);
      const refreshed = await api.listPermissions(origin);
      useBrowserRuntimeStore
        .getState()
        .updatePermissions({ origin, permissions: refreshed });
    } catch (error) {
      console.warn("[browser] failed to update permission", error);
    }
  };

  const handlePermissionReset = async (permission: string) => {
    if (!api || !origin) return;
    setResettingPermission(permission);
    try {
      await revokeNavigatorPermission(permission);
      await api.clearPermission(origin, permission);
      const refreshed = await api.listPermissions(origin);
      useBrowserRuntimeStore
        .getState()
        .updatePermissions({ origin, permissions: refreshed });
    } catch (error) {
      console.warn("[browser] failed to reset permission", error);
    } finally {
      setResettingPermission((current) => (current === permission ? null : current));
    }
  };

  const handleClearSiteData = async () => {
    if (!api || !origin) return;
    setClearingSiteData(true);
    try {
      const result = await api.clearSiteData(origin);
      if (!result?.ok) {
        throw new Error(result?.error || "Unknown error");
      }
      setOpen(false);
      setConfirmClearOpen(false);
    } catch (error) {
      console.warn("[browser] failed to clear site data", error);
    } finally {
      setClearingSiteData(false);
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
    <>
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
              <p className="text-xs text-muted-foreground">
                No saved decisions. Requests will ask.
              </p>
            ) : (
              <div className="space-y-2">
                {permissions.map((entry) => {
                  const current = (entry.setting as PermissionSetting | undefined) ?? "ask";
                  const isResetting = resettingPermission === entry.permission;
                  return (
                    <div key={entry.permission} className="space-y-1 rounded-md border p-2 text-xs">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate capitalize">
                          {formatPermissionLabel(entry.permission)}
                        </span>
                        <Badge variant={permissionBadgeVariant(current)}>
                          {describePermissionSetting(current)}
                        </Badge>
                      </div>
                      <div className="flex items-center justify-between gap-2 text-[11px] lowercase">
                        <Select
                          value={current}
                          onValueChange={(value) =>
                            handlePermissionChange(entry.permission, value as PermissionSetting)
                          }
                        >
                          <SelectTrigger className="h-8 w-[110px] text-xs normal-case">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="allow">Allow</SelectItem>
                            <SelectItem value="deny">Block</SelectItem>
                            <SelectItem value="ask">Ask</SelectItem>
                          </SelectContent>
                        </Select>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 px-2 text-xs normal-case"
                          disabled={isResetting}
                          onClick={() => handlePermissionReset(entry.permission)}
                        >
                          {isResetting ? "Resetting..." : "Reset"}
                        </Button>
                      </div>
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
            <Button variant="secondary" size="sm" onClick={() => setConfirmClearOpen(true)}>
              Clear site data
            </Button>
          </div>
        </PopoverContent>
      </Popover>
      <Dialog
        open={confirmClearOpen}
        onOpenChange={(next) => {
          if (clearingSiteData && !next) {
            return;
          }
          setConfirmClearOpen(next);
        }}
      >
        <DialogContent showCloseButton={!clearingSiteData}>
          <DialogHeader>
            <DialogTitle>Clear data for this site?</DialogTitle>
            <DialogDescription>
              This will remove stored information for <span className="font-medium">{origin}</span>.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 text-sm text-muted-foreground">
            <p>Items that will be deleted:</p>
            <ul className="list-disc pl-5">
              <li>Cookies and authentication tokens</li>
              <li>Local/session storage, IndexedDB, cache, and service worker data</li>
              <li>History entries saved for this domain</li>
            </ul>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              disabled={clearingSiteData}
              onClick={() => setConfirmClearOpen(false)}
            >
              Cancel
            </Button>
            <Button variant="destructive" disabled={clearingSiteData} onClick={handleClearSiteData}>
              {clearingSiteData ? "Clearing…" : "Clear site data"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
