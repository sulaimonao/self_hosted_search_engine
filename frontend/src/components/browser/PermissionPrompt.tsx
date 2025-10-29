"use client";

import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { resolveBrowserAPI } from "@/lib/browser-ipc";
import { useBrowserRuntimeStore } from "@/state/useBrowserRuntime";

function describePermission(permission: string): string {
  switch (permission) {
    case "camera":
      return "use your camera";
    case "microphone":
      return "use your microphone";
    case "geolocation":
      return "access your location";
    case "notifications":
      return "show notifications";
    case "clipboard-read":
      return "read from your clipboard";
    default:
      return permission.replace(/-/g, " ");
  }
}

export function PermissionPrompt() {
  const prompt = useBrowserRuntimeStore((state) => state.permissionPrompt ?? null);
  const setPrompt = useBrowserRuntimeStore((state) => state.setPermissionPrompt);
  const api = useMemo(() => resolveBrowserAPI(), []);
  const [remember, setRemember] = useState(true);

  if (!prompt) {
    return null;
  }

  const handleDecision = (decision: "allow" | "deny") => {
    if (!api) {
      setPrompt(null);
      return;
    }
    api.respondToPermission({ id: prompt.id, decision, remember });
    setPrompt(null);
  };

  return (
    <div className="pointer-events-none fixed inset-0 z-50 flex items-end justify-center p-6">
      <Card className="pointer-events-auto w-full max-w-md shadow-lg">
        <CardHeader>
          <CardTitle className="text-base">{new URL(prompt.origin).host}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm">This site wants to {describePermission(prompt.permission)}.</p>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Checkbox
              id="remember-permission"
              checked={remember}
              onChange={(event) => setRemember(event.target.checked)}
            />
            <label htmlFor="remember-permission" className="cursor-pointer select-none">
              Remember this decision
            </label>
          </div>
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="outline" onClick={() => handleDecision("deny")}>
              Block
            </Button>
            <Button size="sm" onClick={() => handleDecision("allow")}>
              Allow
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
