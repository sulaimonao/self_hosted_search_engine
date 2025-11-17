"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { AlertTriangle, RefreshCcw } from "lucide-react";
import { useShallow } from "zustand/react/shallow";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import ClientOnly from "@/components/layout/ClientOnly";
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
  fetchAgentBrowserConfig,
  fetchDesktopRuntime,
  fetchModels,
  installModels as installOllamaModels,
  runDiagnostics as runDiagnosticsJob,
  updateAgentBrowserConfig,
} from "@/lib/api";
import type {
  AgentBrowserConfigPayload,
  DesktopRuntimeInfo,
  OllamaHealthResponse,
} from "@/lib/api";
import {
  fetchConfig,
  fetchConfigSchema,
  getDiagnosticsSnapshot,
  getHealth,
  requestModelInstall,
  triggerRepair,
  updateConfig,
} from "@/lib/configClient";
import type { ConfigFieldOption, ConfigSchema, RuntimeConfig, HealthSnapshot } from "@/lib/configClient";
import { useSafeNavigate } from "@/lib/useSafeNavigate";
import RoadmapPanel from "@/components/roadmap/RoadmapPanel";
import { useRenderLoopGuardState } from "@/lib/renderLoopContext";
import { useRenderLoopDiagnostics } from "@/state/useRenderLoopDiagnostics";
import { safeLocalStorage } from "@/utils/isomorphicStorage";

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

const RUNTIME_TAB_ID = "runtime-desktop";
const ROADMAP_TAB_ID = "roadmap";

const AGENT_BROWSER_DEFAULTS: AgentBrowserConfigPayload = {
  enabled: true,
  AGENT_BROWSER_ENABLED: true,
  AGENT_BROWSER_DEFAULT_TIMEOUT_S: 15,
  AGENT_BROWSER_NAV_TIMEOUT_MS: 15000,
  AGENT_BROWSER_HEADLESS: false,
};

const MANDATORY_MODEL_FAMILIES = ["gpt-oss", "gemma3", "embeddinggemma"] as const;

function coerceBoolean(value: unknown, fallback: boolean): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const normalised = value.trim().toLowerCase();
    if (["true", "1", "yes", "on"].includes(normalised)) return true;
    if (["false", "0", "no", "off"].includes(normalised)) return false;
  }
  return fallback;
}

function coerceNumber(value: unknown, fallback: number): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number.parseFloat(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

export default function ControlCenterPage() {
  const { data: config, mutate: mutateConfig } = useSWR("runtime-config", fetchConfig);
  const { data: schema } = useSWR<ConfigSchema>("runtime-config-schema", fetchConfigSchema);
  const { data: health, mutate: mutateHealth } = useSWR<HealthSnapshot>("runtime-health", getHealth, {
    refreshInterval: 30000,
  });
  const { data: diagnostics, mutate: mutateDiagnostics } = useSWR(
    "runtime-diagnostics",
    getDiagnosticsSnapshot,
  );
  const { data: agentConfig, mutate: mutateAgentConfig } = useSWR<AgentBrowserConfigPayload>(
    "agent-browser-config",
    fetchAgentBrowserConfig,
  );
  const { data: desktopRuntime } = useSWR<DesktopRuntimeInfo>("desktop-runtime", fetchDesktopRuntime);
  const { data: ollamaHealth, mutate: mutateModels } = useSWR<OllamaHealthResponse>(
    "ollama-model-health",
    fetchModels,
  );

  const navigate = useSafeNavigate();
  const hasNavigatedRef = useRef(false);
  const [saving, setSaving] = useState<string | null>(null);
  const [installing, setInstalling] = useState(false);
  const [repairing, setRepairing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [savingAgent, setSavingAgent] = useState(false);
  const [agentMessage, setAgentMessage] = useState<string | null>(null);
  const [installingModel, setInstallingModel] = useState<string | null>(null);
  const [modelsMessage, setModelsMessage] = useState<string | null>(null);
  const [runtimeDiagnosticsMessage, setRuntimeDiagnosticsMessage] = useState<string | null>(null);
  const { events: renderLoopEvents, clear: clearRenderLoopEvents } = useRenderLoopDiagnostics(
    useShallow((state) => ({
      events: state.events,
      clear: state.clear,
    })),
  );
  const { enabled: renderLoopGuardEnabled } = useRenderLoopGuardState();
  const handleBackToBrowser = useCallback(() => {
    if (hasNavigatedRef.current) {
      return;
    }
    hasNavigatedRef.current = true;
    navigate.push("/browser");
  }, [navigate]);

  const schemaSections = useMemo(
    () => (Array.isArray(schema?.sections) ? schema.sections : []),
    [schema],
  );
  const sections = useMemo(() => {
    if (process.env.NODE_ENV === "production") {
      return schemaSections.filter((section) => section.id !== "developer");
    }
    return schemaSections;
  }, [schemaSections]);
  const [activeTab, setActiveTab] = useState(() => sections[0]?.id ?? RUNTIME_TAB_ID);

  // replace existing effect that depended on `activeTab` and `sections` with a guarded auto-set
  const lastAutoTabRef = useRef<string | null>(null);
  // Driven by `sections` only; setting `activeTab` here would create a loop if included.
  /* eslint-disable react-hooks/exhaustive-deps */
  useEffect(() => {
    // determine desired tab based on sections alone
    let target = activeTab;
    if (sections.length === 0) {
      target = RUNTIME_TAB_ID;
    } else if (!sections.some((section) => section.id === activeTab)) {
      target = sections[0]?.id ?? RUNTIME_TAB_ID;
    }

    if (target !== activeTab && target !== lastAutoTabRef.current) {
      lastAutoTabRef.current = target;
      setActiveTab(target);
    }
    // intentionally only depend on `sections` so that changes to sections drive this effect
  }, [sections]);
  /* eslint-enable react-hooks/exhaustive-deps */

  const agentState = agentConfig ?? AGENT_BROWSER_DEFAULTS;
  const agentSource =
    typeof agentState["_source"] === "string" ? (agentState["_source"] as string) : null;
  const agentConfigUnavailable = Boolean(agentSource && agentSource.startsWith("fallback"));
  const agentEnabled = useMemo(
    () =>
      coerceBoolean(
        agentState.AGENT_BROWSER_ENABLED ?? agentState.enabled,
        coerceBoolean(AGENT_BROWSER_DEFAULTS.AGENT_BROWSER_ENABLED, false),
      ),
    [agentState.AGENT_BROWSER_ENABLED, agentState.enabled],
  );

  const agentHeadless = useMemo(
    () =>
      coerceBoolean(
        agentState.AGENT_BROWSER_HEADLESS,
        coerceBoolean(AGENT_BROWSER_DEFAULTS.AGENT_BROWSER_HEADLESS, true),
      ),
    [agentState.AGENT_BROWSER_HEADLESS],
  );
  const agentDefaultTimeoutValue =
    agentState.AGENT_BROWSER_DEFAULT_TIMEOUT_S ??
    agentState.default_timeout_s ??
    AGENT_BROWSER_DEFAULTS.AGENT_BROWSER_DEFAULT_TIMEOUT_S ??
    "";
  const agentNavigationTimeoutValue =
    agentState.AGENT_BROWSER_NAV_TIMEOUT_MS ??
    agentState.nav_timeout_ms ??
    AGENT_BROWSER_DEFAULTS.AGENT_BROWSER_NAV_TIMEOUT_MS ??
    "";

  const desktopRuntimeSource =
    typeof desktopRuntime?.["_source"] === "string" ? (desktopRuntime["_source"] as string) : null;
  const desktopRuntimeUnavailable = Boolean(desktopRuntimeSource && desktopRuntimeSource.startsWith("fallback"));
  const desktopHardened = coerceBoolean(desktopRuntime?.hardened, true);

  const documentedEnvKeys = useMemo(() => {
    if (Array.isArray(desktopRuntime?.documented_env_keys)) {
      return desktopRuntime.documented_env_keys
        .map((item) => (typeof item === "string" ? item : String(item)))
        .filter((item, index, list) => item && index === list.indexOf(item));
    }
    return [
      "DESKTOP_USER_AGENT",
      "AGENT_BROWSER_ENABLED",
      "AGENT_BROWSER_DEFAULT_TIMEOUT_S",
      "AGENT_BROWSER_NAV_TIMEOUT_MS",
      "AGENT_BROWSER_HEADLESS",
    ];
  }, [desktopRuntime?.documented_env_keys]);

  const installedModelFamilies = useMemo(() => {
    if (!Array.isArray(ollamaHealth?.models)) {
      return new Set<string>();
    }
    return new Set(
      (ollamaHealth.models as unknown[])
        .filter((entry): entry is string => typeof entry === "string")
        .map((entry) => entry.split(":")[0].toLowerCase()),
    );
  }, [ollamaHealth?.models]);

  const diagnosticsCapturedLabel = useMemo(() => {
    const captured = diagnostics?.captured_at;
    if (typeof captured === "number") {
      return new Date(captured * 1000).toLocaleString();
    }
    const generated = diagnostics?.generated_at;
    if (typeof generated === "string") {
      return generated;
    }
    return "unknown";
  }, [diagnostics?.captured_at, diagnostics?.generated_at]);

  const diagnosticsCounts = useMemo(() => {
    const summary =
      diagnostics && typeof diagnostics === "object"
        ? (diagnostics as Record<string, unknown>).summary
        : null;
    if (summary && typeof summary === "object") {
      const counts = (summary as Record<string, unknown>).counts;
      if (counts && typeof counts === "object") {
        return counts as Record<string, unknown>;
      }
    }
    return null;
  }, [diagnostics]);
  const diagHigh = coerceNumber(diagnosticsCounts?.high, 0);
  const diagMedium = coerceNumber(diagnosticsCounts?.medium, 0);
  const diagLow = coerceNumber(diagnosticsCounts?.low, 0);

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

  const handleAgentSave = async () => {
    setSavingAgent(true);
    setAgentMessage(null);
    if (agentConfigUnavailable) {
      setAgentMessage("Runtime config endpoint unavailable; edit .env to persist changes.");
      setSavingAgent(false);
      return;
    }
    const payload: AgentBrowserConfigPayload = {
      ...agentState,
      enabled: agentEnabled,
      AGENT_BROWSER_ENABLED: agentEnabled,
      AGENT_BROWSER_DEFAULT_TIMEOUT_S: coerceNumber(
        agentState.AGENT_BROWSER_DEFAULT_TIMEOUT_S ?? agentState.default_timeout_s,
        coerceNumber(AGENT_BROWSER_DEFAULTS.AGENT_BROWSER_DEFAULT_TIMEOUT_S, 15),
      ),
      AGENT_BROWSER_NAV_TIMEOUT_MS: coerceNumber(
        agentState.AGENT_BROWSER_NAV_TIMEOUT_MS ?? agentState.nav_timeout_ms,
        coerceNumber(AGENT_BROWSER_DEFAULTS.AGENT_BROWSER_NAV_TIMEOUT_MS, 15000),
      ),
      AGENT_BROWSER_HEADLESS: agentHeadless,
    };
    delete (payload as Record<string, unknown>)["_source"];
    try {
      const result = await updateAgentBrowserConfig(payload);
      await mutateAgentConfig(result, false);
      setAgentMessage("Agent browser settings saved.");
    } catch (error) {
      setAgentMessage(error instanceof Error ? error.message : "Failed to save agent browser settings.");
    } finally {
      setSavingAgent(false);
    }
  };

  const handleInstallOllamaModel = async (model: string) => {
    setInstallingModel(model);
    setModelsMessage(null);
    try {
      await installOllamaModels({ models: [model] });
      setModelsMessage(`Install triggered for ${model}.`);
      await mutateModels();
      await mutateHealth();
    } catch (error) {
      setModelsMessage(error instanceof Error ? error.message : `Failed to install ${model}.`);
    } finally {
      setInstallingModel(null);
    }
  };

  const handleRunDiagnostics = async () => {
    setRuntimeDiagnosticsMessage(null);
    try {
      const result = await runDiagnosticsJob();
      if (result?.ok) {
        setRuntimeDiagnosticsMessage("Diagnostics run started.");
        await mutateDiagnostics();
      } else {
        setRuntimeDiagnosticsMessage(
          result?.message ?? "Diagnostics endpoint unavailable. Run python3 tools/e2e_diag.py locally.",
        );
      }
    } catch (error) {
      setRuntimeDiagnosticsMessage(
        error instanceof Error ? error.message : "Failed to trigger diagnostics run.",
      );
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
                <Card>
                  <div className="p-4">
                    <h3 className="text-sm font-semibold">Chat</h3>
                    <p className="text-xs text-muted-foreground">Renderer and streaming throttle settings for the chat UI.</p>
                    <div className="mt-3 space-y-2">
                      <div>
                        <Label>Renderer</Label>
                        <div className="mt-2 flex items-center gap-4">
                          <label className="flex items-center gap-2">
                            <input
                              type="radio"
                              name="chat-renderer"
                              defaultChecked
                              onChange={() => {
                                // prefer server config when available
                                if (typeof updateConfig === "function") {
                                  void updateConfig({ "chat.renderer": "useChat" }).then(() => mutateConfig?.());
                                } else {
                                  safeLocalStorage.set("chat:renderer", "useChat");
                                }
                              }}
                            />
                            <span className="text-[13px]">useChat (recommended)</span>
                          </label>
                          <label className="flex items-center gap-2">
                            <input
                              type="radio"
                              name="chat-renderer"
                              onChange={() => {
                                if (typeof updateConfig === "function") {
                                  void updateConfig({ "chat.renderer": "manual" }).then(() => mutateConfig?.());
                                } else {
                                  safeLocalStorage.set("chat:renderer", "manual");
                                }
                              }}
                            />
                            <span className="text-[13px]">Manual (buffered)</span>
                          </label>
                        </div>
                      </div>
                      <div>
                        <Label>Streaming throttle (ms)</Label>
                        <div className="mt-2">
                          <Input
                            type="number"
                            defaultValue={String((config && config["chat.throttleMs"]) ?? "50")}
                            onBlur={(e) => {
                              const v = Number.parseInt(e.currentTarget.value || "50", 10) || 50;
                              if (typeof updateConfig === "function") {
                                void updateConfig({ "chat.throttleMs": v }).then(() => mutateConfig?.());
                              } else {
                                safeLocalStorage.set("chat:throttleMs", String(v));
                              }
                            }}
                          />
                          <p className="text-xs text-muted-foreground mt-1">Lower values update more frequently; recommended ≥ 50ms.</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </Card>
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
          <>
            <Card className="space-y-3 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold">Render loop guard</h3>
                  <p className="text-xs text-muted-foreground">
                    Detects components committing repeatedly in development mode.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={renderLoopGuardEnabled ? "secondary" : "outline"}>
                    {renderLoopGuardEnabled ? "Enabled" : "Disabled"}
                  </Badge>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => clearRenderLoopEvents()}
                    disabled={renderLoopEvents.length === 0}
                  >
                    Clear
                  </Button>
                </div>
              </div>
              <div className="space-y-2 text-xs">
                {renderLoopEvents.length === 0 ? (
                  <p className="text-muted-foreground">No render loops detected this session.</p>
                ) : (
                  <ul className="space-y-2">
                    {renderLoopEvents
                      .slice()
                      .reverse()
                      .map((event) => (
                        <li key={`${event.key}:${event.timestamp}`} className="rounded border p-2">
                          <div className="flex items-center justify-between">
                            <span className="font-medium">{event.key}</span>
                            <span className="text-muted-foreground">
                              {new Date(event.timestamp).toLocaleTimeString()}
                            </span>
                          </div>
                          <p className="text-muted-foreground">
                            {event.count} renders within {event.windowMs}ms window
                          </p>
                        </li>
                      ))}
                  </ul>
                )}
              </div>
            </Card>
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
              <div className="space-y-2 rounded border border-border-subtle p-3 text-xs text-muted-foreground">
                {diagnostics ? (
                  <>
                    <p>Snapshot taken {diagnostics.captured_at ? new Date((diagnostics.captured_at as number) * 1000).toLocaleString() : "recently"}.</p>
                    <pre className="whitespace-pre-wrap break-words">{JSON.stringify(diagnostics.links, null, 2)}</pre>
                  </>
                ) : (
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-state-warning" />
                    <span>No diagnostics captured yet.</span>
                  </div>
                )}
              </div>
            </Card>
          </>
        ) : null}
      </div>
    );
  };

  const environment = useMemo(() => health?.environment ?? {}, [health?.environment]);

  return (
    <ClientOnly fallback={<div className="px-6 py-8 text-sm text-muted-foreground">Loading Control Center…</div>}>
      <div className="mx-auto max-w-5xl space-y-6 px-6 py-8">
        <header className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-1">
              <h1 className="text-2xl font-bold">Control Center</h1>
              <p className="text-sm text-muted-foreground">
                Configure runtime features, monitor model availability, and repair the local stack without editing files.
              </p>
            </div>
            <Button variant="outline" onClick={handleBackToBrowser}>
              Back to Browser
            </Button>
          </div>
          <div className="grid grid-cols-1 gap-3 text-xs text-muted-foreground sm:grid-cols-3">
            <div className="rounded border p-3">
              <Label className="text-[11px] uppercase text-muted-foreground">Python</Label>
              <p className="font-semibold text-foreground">
                {typeof environment?.python === "string"
                  ? environment.python
                  : String(environment?.python ?? "checking")}
              </p>
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
            <TabsTrigger value={RUNTIME_TAB_ID}>Runtime & Desktop</TabsTrigger>
            <TabsTrigger value={ROADMAP_TAB_ID}>Roadmap</TabsTrigger>
          </TabsList>
          {sections.map((section) => (
            <TabsContent key={section.id} value={section.id}>
              {renderSection(section.id)}
            </TabsContent>
          ))}
          <TabsContent value={RUNTIME_TAB_ID}>
            <div className="grid gap-4 md:grid-cols-2">
              <Card className="space-y-3 p-4">
                <div>
                  <h3 className="text-sm font-semibold">Desktop / Electron</h3>
                  <p className="text-xs text-muted-foreground">
                    Shows the state of the hardened Electron shell.
                  </p>
                </div>
                {desktopRuntimeUnavailable ? (
                  <p className="text-xs italic text-muted-foreground">
                    Runtime endpoint unavailable; displaying fallback values from the local build.
                  </p>
                ) : null}
                <div className="space-y-1 text-xs">
                  <div>
                    <span className="font-medium">User-Agent:</span>{" "}
                    {typeof desktopRuntime?.desktop_user_agent === "string"
                      ? desktopRuntime.desktop_user_agent
                      : "unknown"}
                  </div>
                  <div>
                    <span className="font-medium">Session partition:</span>{" "}
                    {typeof desktopRuntime?.session_partition === "string"
                      ? desktopRuntime.session_partition
                      : "persist:main"}
                  </div>
                  <div>
                    <span className="font-medium">Hardened:</span> {desktopHardened ? "yes" : "no"}
                  </div>
                </div>
                <div>
                  <p className="text-[11px] uppercase text-muted-foreground">Documented env keys</p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {documentedEnvKeys.map((key) => (
                      <span
                        key={key}
                        className="rounded border px-1.5 py-0.5 text-[11px] text-muted-foreground"
                      >
                        {key}
                      </span>
                    ))}
                  </div>
                </div>
              </Card>

              <Card className="space-y-4 p-4">
                <div>
                  <h3 className="text-sm font-semibold">Agent browser</h3>
                  <p className="text-xs text-muted-foreground">
                    Enable the Playwright-powered browser and adjust its safety limits.
                  </p>
                </div>
                {agentConfigUnavailable ? (
                  <p className="text-xs italic text-muted-foreground">
                    Config endpoint missing; update .env or backend to persist changes.
                  </p>
                ) : null}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="agent-browser-enabled" className="text-xs font-medium">
                      Enabled
                    </Label>
                    <Switch
                      id="agent-browser-enabled"
                      checked={agentEnabled}
                      onCheckedChange={(next) =>
                        void mutateAgentConfig(
                          (previous?: AgentBrowserConfigPayload) => ({
                            ...(previous ?? AGENT_BROWSER_DEFAULTS),
                            enabled: next,
                            AGENT_BROWSER_ENABLED: next,
                          }),
                          false,
                        )
                      }
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <Label htmlFor="agent-browser-headless" className="text-xs font-medium">
                      Headless mode
                    </Label>
                    <Switch
                      id="agent-browser-headless"
                      checked={agentHeadless}
                      onCheckedChange={(next) =>
                        void mutateAgentConfig(
                          (previous?: AgentBrowserConfigPayload) => ({
                            ...(previous ?? AGENT_BROWSER_DEFAULTS),
                            AGENT_BROWSER_HEADLESS: next,
                          }),
                          false,
                        )
                      }
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="agent-browser-default-timeout" className="text-xs">
                      Default timeout (seconds)
                    </Label>
                    <Input
                      id="agent-browser-default-timeout"
                      type="number"
                      min={1}
                      value={agentDefaultTimeoutValue === "" ? "" : String(agentDefaultTimeoutValue)}
                      onChange={(event) => {
                        const nextValue = event.target.value;
                        void mutateAgentConfig(
                          (previous?: AgentBrowserConfigPayload) => {
                            const nextConfig = { ...(previous ?? AGENT_BROWSER_DEFAULTS) };
                            if (!nextValue) {
                              nextConfig.AGENT_BROWSER_DEFAULT_TIMEOUT_S = undefined;
                            } else {
                              const numeric = Number.parseFloat(nextValue);
                              nextConfig.AGENT_BROWSER_DEFAULT_TIMEOUT_S = Number.isFinite(numeric)
                                ? numeric
                                : coerceNumber(
                                    nextConfig.AGENT_BROWSER_DEFAULT_TIMEOUT_S,
                                    coerceNumber(AGENT_BROWSER_DEFAULTS.AGENT_BROWSER_DEFAULT_TIMEOUT_S, 15),
                                  );
                            }
                            return nextConfig;
                          },
                          false,
                        );
                      }}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="agent-browser-nav-timeout" className="text-xs">
                      Navigation timeout (milliseconds)
                    </Label>
                    <Input
                      id="agent-browser-nav-timeout"
                      type="number"
                      min={1000}
                      step={500}
                      value={
                        agentNavigationTimeoutValue === "" ? "" : String(agentNavigationTimeoutValue)
                      }
                      onChange={(event) => {
                        const nextValue = event.target.value;
                        void mutateAgentConfig(
                          (previous?: AgentBrowserConfigPayload) => {
                            const nextConfig = { ...(previous ?? AGENT_BROWSER_DEFAULTS) };
                            if (!nextValue) {
                              nextConfig.AGENT_BROWSER_NAV_TIMEOUT_MS = undefined;
                            } else {
                              const numeric = Number.parseInt(nextValue, 10);
                              nextConfig.AGENT_BROWSER_NAV_TIMEOUT_MS = Number.isFinite(numeric)
                                ? numeric
                                : coerceNumber(
                                    nextConfig.AGENT_BROWSER_NAV_TIMEOUT_MS,
                                    coerceNumber(AGENT_BROWSER_DEFAULTS.AGENT_BROWSER_NAV_TIMEOUT_MS, 15000),
                                  );
                            }
                            return nextConfig;
                          },
                          false,
                        );
                      }}
                    />
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button size="sm" onClick={() => void handleAgentSave()} disabled={savingAgent}>
                    {savingAgent ? "Saving…" : "Save agent settings"}
                  </Button>
                  {agentMessage ? (
                    <span className="text-xs text-muted-foreground">{agentMessage}</span>
                  ) : null}
                </div>
              </Card>

              <Card className="space-y-4 p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-semibold">Models</h3>
                    <p className="text-xs text-muted-foreground">
                      Install or verify the required Ollama models.
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void mutateModels()}
                    disabled={installingModel !== null}
                  >
                    <RefreshCcw className="mr-2 h-3.5 w-3.5" />
                    Refresh
                  </Button>
                </div>
                <div className="space-y-2 text-xs">
                  {MANDATORY_MODEL_FAMILIES.map((name) => {
                    const installed = installedModelFamilies.has(name.toLowerCase());
                    const inFlight = installingModel === name;
                    return (
                      <div key={name} className="flex items-center justify-between rounded border border-border-subtle p-2">
                        <span className="font-medium">{name}</span>
                        {installed ? (
                          <span className="text-[10px] font-semibold uppercase text-state-success">
                            installed
                          </span>
                        ) : (
                          <Button
                            size="sm"
                            onClick={() => void handleInstallOllamaModel(name)}
                            disabled={inFlight}
                          >
                            {inFlight ? "Installing…" : "Install"}
                          </Button>
                        )}
                      </div>
                    );
                  })}
                </div>
                {modelsMessage ? (
                  <p className="text-xs text-muted-foreground">{modelsMessage}</p>
                ) : null}
                {ollamaHealth?.ok === false ? (
                  <p className="text-xs text-destructive">
                    Ollama reported an error – check the backend logs.
                  </p>
                ) : null}
              </Card>

              <Card className="space-y-4 p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-semibold">Diagnostics</h3>
                    <p className="text-xs text-muted-foreground">
                      Trigger backend diagnostics and review the latest snapshot.
                    </p>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => void mutateDiagnostics()}>
                    <RefreshCcw className="mr-2 h-3.5 w-3.5" />
                    Refresh
                  </Button>
                </div>
                <Button size="sm" onClick={() => void handleRunDiagnostics()}>
                  Run diagnostics
                </Button>
                {runtimeDiagnosticsMessage ? (
                  <p className="text-xs text-muted-foreground">{runtimeDiagnosticsMessage}</p>
                ) : null}
                <div className="space-y-1 text-xs">
                  <div>
                    <span className="font-medium">Last snapshot:</span> {diagnosticsCapturedLabel}
                  </div>
                  <div>
                    <span className="font-medium">LLM:</span>{" "}
                    {((diagnostics?.health as Record<string, unknown> | undefined)?.components as
                      Record<string, { status?: string }> | undefined)?.llm?.status ?? "unknown"}
                  </div>
                  <div>
                    <span className="font-medium">Index:</span>{" "}
                    {((diagnostics?.health as Record<string, unknown> | undefined)?.components as
                      Record<string, { status?: string }> | undefined)?.index?.status ?? "unknown"}
                  </div>
                </div>
                <div className="text-xs">
                  <span className="font-medium">Counts:</span>{" "}
                  High {diagHigh} · Medium {diagMedium} · Low {diagLow}
                </div>
              </Card>
            </div>
          </TabsContent>
          <TabsContent value={ROADMAP_TAB_ID}>
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Live roadmap of features and stability tasks. Items mapped to diagnostics auto-update; manual items can be edited inline.
              </p>
              <RoadmapPanel />
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </ClientOnly>
  );
}
