"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { resolveBrowserAPI, type BrowserSettings } from "@/lib/browser-ipc";
import { useBrowserRuntimeStore } from "@/state/useBrowserRuntime";

const SPELLCHECK_OPTIONS = [
  { label: "English (US)", value: "en-US" },
  { label: "English (UK)", value: "en-GB" },
];

type SettingsSheetProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function SettingsSheet({ open, onOpenChange }: SettingsSheetProps) {
  const api = useMemo(() => resolveBrowserAPI(), []);
  const settings = useBrowserRuntimeStore((state) => state.settings);
  const setSettings = useBrowserRuntimeStore((state) => state.setSettings);
  const [proxyHost, setProxyHost] = useState("");
  const [proxyPort, setProxyPort] = useState("");

  useEffect(() => {
    if (open && settings) {
      setProxyHost(settings.proxy?.host ?? "");
      setProxyPort(settings.proxy?.port ?? "");
    }
  }, [open, settings]);

  const applyPatch = async (patch: Partial<BrowserSettings>) => {
    if (!api) {
      return;
    }
    try {
      const updated = await api.updateSettings(patch);
      if (updated) {
        setSettings(updated);
      }
    } catch (error) {
      console.warn("[browser] failed to update settings", error);
    }
  };

  const applyProxyPatch = async (patch: { mode?: "system" | "manual"; host?: string; port?: string }) => {
    await applyPatch({
      proxy: {
        mode: patch.mode ?? settings?.proxy?.mode ?? "system",
        host: patch.host ?? proxyHost,
        port: patch.port ?? proxyPort,
      },
    });
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[420px] space-y-6" side="right">
        <SheetHeader>
          <SheetTitle>Browser settings</SheetTitle>
        </SheetHeader>
        <div className="space-y-4">
          <section className="space-y-2">
            <h3 className="text-sm font-medium">Privacy</h3>
            <div className="flex items-center justify-between gap-4 rounded-md border p-3">
              <div>
                <p className="text-sm font-medium">Allow third-party cookies</p>
                <p className="text-xs text-muted-foreground">
                  Required for sites like Google to remember your session.
                </p>
              </div>
              <Switch
                checked={settings?.thirdPartyCookies ?? true}
                onCheckedChange={(checked) => applyPatch({ thirdPartyCookies: Boolean(checked) })}
              />
            </div>
          </section>
          <section className="space-y-2">
            <h3 className="text-sm font-medium">Search</h3>
            <div className="flex items-center justify-between gap-3 rounded-md border p-3">
              <div>
                <p className="text-sm font-medium">Address bar behavior</p>
                <p className="text-xs text-muted-foreground">Decide whether non-URLs are searched automatically.</p>
              </div>
              <Select
                value={settings?.searchMode ?? "auto"}
                onValueChange={(value) => applyPatch({ searchMode: value as "auto" | "query" })}
              >
                <SelectTrigger className="w-[140px] text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Auto-detect URL</SelectItem>
                  <SelectItem value="query">Always search</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between gap-4 rounded-md border p-3">
              <div>
                <p className="text-sm font-medium">Open searches externally</p>
                <p className="text-xs text-muted-foreground">
                  Launches matching search domains in your default system browser.
                </p>
              </div>
              <Switch
                checked={settings?.openSearchExternally ?? false}
                onCheckedChange={(checked) =>
                  applyPatch({ openSearchExternally: Boolean(checked) })
                }
              />
            </div>
          </section>
          <section className="space-y-2">
            <h3 className="text-sm font-medium">Spellcheck</h3>
            <Select
              value={settings?.spellcheckLanguage ?? "en-US"}
              onValueChange={(value) => applyPatch({ spellcheckLanguage: value })}
            >
              <SelectTrigger className="w-full text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SPELLCHECK_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </section>
          <section className="space-y-3">
            <h3 className="text-sm font-medium">Proxy</h3>
            <div className="rounded-md border p-3 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">Connection mode</p>
                <Select
                  value={settings?.proxy?.mode ?? "system"}
                  onValueChange={(value) => applyProxyPatch({ mode: value as "system" | "manual" })}
                >
                  <SelectTrigger className="w-[140px] text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="system">Use system proxy</SelectItem>
                    <SelectItem value="manual">Manual</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {settings?.proxy?.mode === "manual" ? (
                <div className="space-y-2">
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Proxy host</p>
                    <Input
                      value={proxyHost}
                      onChange={(event) => setProxyHost(event.target.value)}
                      onBlur={() => applyProxyPatch({ host: proxyHost })}
                      placeholder="proxy.example.com"
                    />
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Proxy port</p>
                    <Input
                      value={proxyPort}
                      onChange={(event) => setProxyPort(event.target.value)}
                      onBlur={() => applyProxyPatch({ port: proxyPort })}
                      placeholder="8080"
                    />
                  </div>
                </div>
              ) : null}
            </div>
          </section>
        </div>
        <div className="flex justify-end">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
