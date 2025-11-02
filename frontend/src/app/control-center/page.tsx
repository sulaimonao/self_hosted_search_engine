"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { AlertTriangle, RefreshCcw } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { IndexHealthPanel } from "@/components/index-health/IndexHealthPanel";
import {
  fetchConfig,
  fetchConfigSchema,
  fetchDiagnosticsSnapshot,
  getHealth,
  requestModelInstall,
  triggerRepair,
  updateConfig,
} from "@/lib/configClient";
import type { ConfigFieldOption, ConfigSchema, RuntimeConfig, HealthSnapshot } from "@/lib/configClient";

function resolveFieldValue(config: RuntimeConfig | undefined, field: ConfigFieldOption) {
  const raw = config?.[field.key];
  if (field.type === "boolean") {
    if (typeof raw === "boolean") return raw;
    return Boolean(raw ?? field.default);
  }
  if (typeof raw === "string") {
    return raw;
  }
  if (typeof field.default === "string") {
    return field.default;
  }
  return String(raw ?? "");
}

export default function ControlCenterPage() {
  const { data: config, mutate: mutateConfig } = useSWR("runtime-config", fetchConfig);
  const { data: schema } = useSWR<ConfigSchema>("runtime-config-schema", fetchConfigSchema);
  const { data: health, mutate: mutateHealth } = useSWR<HealthSnapshot>("runtime-health", getHealth, {
    refreshInterval: 30000,
  });
  const { data: diagnostics, mutate: mutateDiagnostics } = useSWR(
    "runtime-diagnostics",
    fetchDiagnosticsSnapshot,
  );

  const [saving, setSaving] = useState<string | null>(null);
  const [installing, setInstalling] = useState(false);
  const [repairing, setRepairing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const sections = schema?.sections ?? [];
  const [activeTab, setActiveTab] = useState(() => sections[0]?.id ?? "models");

  const handleBooleanChange = async (field: ConfigFieldOption, value: boolean) => {
    setSaving(field.key);
    try {
      await mutateConfig(async (current) => {
        const next = { ...(current ?? {}), [field.key]: value };
        await updateConfig({ [field.key]: value });
        return next;
      }, { optimisticData: { ...(config ?? {}), [field.key]: value }, rollbackOnError: true, revalidate: false });
    } finally {
      setSaving(null);
    }
  };

  const handleSelectChange = async (field: ConfigFieldOption, value: string) => {
    setSaving(field.key);
    try {
      await mutateConfig(async (current) => {
        const next = { ...(current ?? {}), [field.key]: value };
        await updateConfig({ [field.key]: value });
        return next;
      }, { optimisticData: { ...(config ?? {}), [field.key]: value }, rollbackOnError: true, revalidate: false });
    } finally {
      setSaving(null);
    }
  };

  const handleInstallModels = async () => {
    setInstalling(true);
    setMessage(null);
    try {
      const result = await requestModelInstall(["gemma-3", "gpt-oss", "embeddinggemma"]);
      if (result.ok) {
        setMessage("Model install kicked off. Check the status ribbon for progress.");
        await mutateHealth();
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Install failed");
    } finally {
      setInstalling(false);
    }
  };

  const handleRepair = async () => {
    setRepairing(true);
    setMessage(null);
    try {
      const result = await triggerRepair();
      const ok = result?.ok;
      setMessage(ok ? "Repair actions launched." : String(result?.errors?.[0] ?? "Repair reported issues."));
      await mutateDiagnostics();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Repair failed");
    } finally {
      setRepairing(false);
    }
  };

  const renderField = (field: ConfigFieldOption) => {
    if (field.type === "boolean") {
      const value = resolveFieldValue(config, field) as boolean;
      return (
        <div className="flex items-center justify-between gap-4 rounded border p-3">
          <div>
            <p className="text-sm font-medium">{field.label}</p>
            {field.description ? (
              <p className="text-xs text-muted-foreground">{field.description}</p>
            ) : null}
          </div>
          <Switch
            checked={value}
            disabled={saving === field.key}
            onCheckedChange={(checked) => void handleBooleanChange(field, Boolean(checked))}
          />
        </div>
      );
    }
    if (field.type === "select" && field.options) {
      const value = String(resolveFieldValue(config, field));
      return (
        <div className="rounded border p-3 space-y-2">
          <div>
            <p className="text-sm font-medium">{field.label}</p>
            {field.description ? (
              <p className="text-xs text-muted-foreground">{field.description}</p>
            ) : null}
          </div>
          <Select
            value={value}
            onValueChange={(next) => void handleSelectChange(field, next)}
            disabled={saving === field.key}
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {field.options.map((option) => (
                <SelectItem key={option} value={option}>
                  {option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      );
    }
    return null;
  };

  const renderSection = (sectionId: string) => {
    const section = sections.find((entry) => entry.id === sectionId);
    if (!section) {
      return <p className="text-sm text-muted-foreground">No settings available.</p>;
    }
    return (
      <div className="space-y-4">
        {section.fields.map((field) => (
          <div key={field.key}>{renderField(field)}</div>
        ))}
        {section.id === "models" ? (
          <Card className="space-y-3 p-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold">Install Gemma & GPT-OSS</h3>
                <p className="text-xs text-muted-foreground">
                  Use the status ribbon to monitor progress while the models are downloaded.
                </p>
              </div>
              <Button onClick={() => void handleInstallModels()} disabled={installing}>
                {installing ? "Installing…" : "Install models"}
              </Button>
            </div>
            {message ? <p className="text-xs text-muted-foreground">{message}</p> : null}
          </Card>
        ) : null}
        {section.id === "index" ? (
          <Card className="p-4">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold">Index health</h3>
                <p className="text-xs text-muted-foreground">
                  Monitor document counts and rebuild the hybrid index when needed.
                </p>
              </div>
              <Button size="sm" variant="outline" onClick={() => void mutateHealth()}>
                <RefreshCcw className="mr-2 h-3.5 w-3.5" /> Refresh
              </Button>
            </div>
            <IndexHealthPanel />
          </Card>
        ) : null}
        {section.id === "developer" ? (
          <Card className="space-y-3 p-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold">Diagnostics</h3>
                <p className="text-xs text-muted-foreground">
                  Snapshot runtime links and trigger automatic repair routines.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="outline" onClick={() => void mutateDiagnostics()}>
                  Refresh snapshot
                </Button>
                <Button size="sm" onClick={() => void handleRepair()} disabled={repairing}>
                  {repairing ? "Repairing…" : "Repair"}
                </Button>
              </div>
            </div>
            <div className="space-y-2 rounded border p-3 text-xs text-muted-foreground">
              {diagnostics ? (
                <>
                  <p>Snapshot taken {diagnostics.captured_at ? new Date((diagnostics.captured_at as number) * 1000).toLocaleString() : "recently"}.</p>
                  <pre className="whitespace-pre-wrap break-words">{JSON.stringify(diagnostics.links, null, 2)}</pre>
                </>
              ) : (
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-amber-500" />
                  <span>No diagnostics captured yet.</span>
                </div>
              )}
            </div>
          </Card>
        ) : null}
      </div>
    );
  };

  const environment = useMemo(() => health?.environment ?? {}, [health?.environment]);

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-6 py-8">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold">Control Center</h1>
        <p className="text-sm text-muted-foreground">
          Configure runtime features, monitor model availability, and repair the local stack without editing files.
        </p>
        <div className="grid grid-cols-1 gap-3 text-xs text-muted-foreground sm:grid-cols-3">
          <div className="rounded border p-3">
            <Label className="text-[11px] uppercase text-muted-foreground">Python</Label>
            <p className="font-semibold text-foreground">{environment?.python ?? "checking"}</p>
          </div>
          <div className="rounded border p-3">
            <Label className="text-[11px] uppercase text-muted-foreground">Ollama CLI</Label>
            <p className="font-semibold text-foreground">{environment?.ollama ? "available" : "missing"}</p>
          </div>
          <div className="rounded border p-3">
            <Label className="text-[11px] uppercase text-muted-foreground">API port</Label>
            <p className="font-semibold text-foreground">{environment?.api_port_open ? "open" : "unreachable"}</p>
          </div>
        </div>
        {message ? <p className="text-xs text-muted-foreground">{message}</p> : null}
        <Separator className="mt-4" />
      </header>
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList>
          {sections.map((section) => (
            <TabsTrigger key={section.id} value={section.id}>
              {section.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {sections.map((section) => (
          <TabsContent key={section.id} value={section.id}>
            {renderSection(section.id)}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
