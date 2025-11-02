"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { Loader2, Wrench, PlugZap } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { fetchConfig, fetchHealth, requestModelInstall, updateConfig } from "@/lib/configClient";

const REQUIRED_MODELS = ["gemma-3", "gpt-oss", "embeddinggemma"];

function detectMissingModels(health: Awaited<ReturnType<typeof fetchHealth>> | null): string[] {
  if (!health) {
    return [];
  }
  const detail = health.components?.llm?.detail ?? {};
  const available = Array.isArray(detail?.available) ? (detail.available as string[]) : [];
  const chat = Array.isArray(detail?.chat) ? (detail.chat as string[]) : [];
  const candidates = new Set<string>();
  for (const entry of [...available, ...chat]) {
    if (typeof entry === "string" && entry) {
      candidates.add(entry.split(":")[0]);
    }
  }
  const missing: string[] = [];
  for (const name of REQUIRED_MODELS) {
    if (![...candidates].some((candidate) => candidate.startsWith(name))) {
      missing.push(name);
    }
  }
  return missing;
}

export function FirstRunWizard() {
  const { data: config, mutate: mutateConfig } = useSWR("runtime-config", fetchConfig);
  const { data: health, mutate: mutateHealth } = useSWR("runtime-health", fetchHealth);
  const [installing, setInstalling] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const completed = Boolean(config?.["setup.completed"]);
  const missingModels = useMemo(() => detectMissingModels(health ?? null), [health]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!completed) {
      setOpen(true);
    }
  }, [completed]);

  const handleInstall = async () => {
    setInstalling(true);
    setError(null);
    setMessage(null);
    try {
      const models = missingModels.length > 0 ? missingModels : REQUIRED_MODELS;
      const result = await requestModelInstall(models);
      if (result.ok) {
        setMessage("Model install started. This can take several minutes.");
        await mutateHealth();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start install");
    } finally {
      setInstalling(false);
    }
  };

  const handleFinish = async () => {
    await updateConfig({ "setup.completed": true });
    await mutateConfig();
    setOpen(false);
  };

  if (!open) {
    return null;
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Welcome to your self-hosted search engine</DialogTitle>
          <DialogDescription>
            We&apos;ve bundled the required dependencies. Use this wizard to finish configuring the runtime.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2 text-sm">
          <section className="rounded border p-3">
            <h3 className="text-sm font-semibold">Environment checks</h3>
            <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
              <li>Python: {health?.environment?.python ?? "detecting"}</li>
              <li>Ollama CLI: {health?.environment?.ollama ? "available" : "missing"}</li>
              <li>API port: {health?.environment?.api_port_open ? "listening" : "unreachable"}</li>
            </ul>
          </section>
          <section className="rounded border p-3 space-y-2">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold">Models</h3>
                <p className="text-xs text-muted-foreground">
                  Gemma-3 and GPT-OSS provide chat; embeddinggemma powers semantic search.
                </p>
              </div>
              <Button size="sm" onClick={() => void mutateHealth()} variant="outline">
                Refresh
              </Button>
            </div>
            {missingModels.length === 0 ? (
              <div className="flex items-center gap-2 text-xs text-emerald-600">
                <PlugZap className="h-4 w-4" /> All required models detected.
              </div>
            ) : (
              <div className="space-y-2 text-xs">
                <p className="text-muted-foreground">
                  Missing models: {missingModels.join(", ")}.
                </p>
                <Button onClick={() => void handleInstall()} disabled={installing}>
                  {installing ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Installing…
                    </>
                  ) : (
                    <>
                      <Wrench className="mr-2 h-4 w-4" /> Install models
                    </>
                  )}
                </Button>
              </div>
            )}
            {message ? <p className="text-xs text-muted-foreground">{message}</p> : null}
            {error ? <p className="text-xs text-destructive">{error}</p> : null}
          </section>
          <section className="rounded border p-3">
            <h3 className="text-sm font-semibold">Next steps</h3>
            <p className="text-xs text-muted-foreground">
              Visit the Control Center at any time to tweak features, privacy controls, and diagnostics.
            </p>
          </section>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => setOpen(false)}>
            Skip for now
          </Button>
          <Button onClick={() => void handleFinish()}>
            Finish setup
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default FirstRunWizard;
