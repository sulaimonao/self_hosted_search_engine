"use client";

import "@/autopilot/executor";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { RefObject } from "react";
import { AlertTriangle, Check, Clipboard, ClipboardCheck, Loader2, X } from "lucide-react";

import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import type { BrowserAPI, BrowserDiagnosticsReport } from "@/lib/browser-ipc";
import type { Verb } from "@/autopilot/executor";
import { IncidentBus, type BrowserIncident } from "@/diagnostics/incident-bus";
import { fromDirective, toIncident, type DirectivePayload } from "@/lib/io/self_heal";
import { api } from "@/lib/api";

import { BROWSER_DIAGNOSTICS_SCRIPT } from "@shared/browser-diagnostics-script";

type CheckStatus = "pass" | "warn" | "fail";

type DiagnosticsCheck = {
  key: string;
  label: string;
  detail: string;
  status: CheckStatus;
};

type PayloadSnapshot = {
  id: string;
  stage: string;
  preview: string;
  ts: number;
  payload: unknown;
};

type RuleSignature = {
  banner_regex?: string;
  network_any?: { url_regex?: string; status?: number }[];
  console_any?: string[];
  dom_regex?: string;
  [key: string]: unknown;
};

type SelfHealRule = {
  id: string;
  enabled?: boolean;
  signature?: RuleSignature;
  directive?: { reason?: string; steps?: DirectiveStep[] };
};

type EpisodeSymptoms = {
  bannerText?: string;
  networkErrors?: { url?: string; status?: number }[];
  [key: string]: unknown;
};

type SelfHealEpisode = {
  id: string;
  ts?: number;
  url?: string;
  symptoms?: EpisodeSymptoms;
  outcome?: string;
  mode: string;
};

type SelfHealMetrics = {
  planner_calls_total: number;
  planner_fallback_count: number;
  rule_hits_count: number;
  headless_runs_count: number;
};

type RulepackResponse = {
  rules?: SelfHealRule[];
  yaml?: string;
  metrics?: SelfHealMetrics | null;
};

type EpisodesResponse = {
  episodes?: SelfHealEpisode[];
};

type PromoteResponse = {
  rule_id: string;
  yaml_diff?: string;
  yaml?: string;
  rules?: SelfHealRule[];
  metrics?: SelfHealMetrics | null;
};

const PLANNER_REQUEST_TIMEOUT_MS = 25_000;

const isAbortError = (error: unknown): boolean => {
  if (!error || typeof error !== "object") {
    return false;
  }
  if ("name" in error && typeof (error as { name?: unknown }).name === "string") {
    return (error as { name: string }).name === "AbortError";
  }
  return false;
};

function describeRule(rule: SelfHealRule): string {
  const parts: string[] = [];
  if (rule.signature?.banner_regex) {
    parts.push(`banner~/${rule.signature.banner_regex}/`);
  }
  if (rule.signature?.network_any && rule.signature.network_any.length > 0) {
    const first = rule.signature.network_any[0];
    const status = typeof first.status !== "undefined" ? ` ${first.status}` : "";
    parts.push(`network~/${first.url_regex ?? "*"}/${status}`.trim());
  }
  if (rule.signature?.dom_regex) {
    parts.push(`dom~/${rule.signature.dom_regex}/`);
  }
  if (parts.length === 0) {
    parts.push("(match all incidents)");
  }
  if (rule.directive?.reason) {
    parts.push(`→ ${rule.directive.reason}`);
  }
  return parts.join(" · ");
}

function normalizeMetrics(metrics?: Record<string, number> | null): SelfHealMetrics | null {
  if (!metrics) {
    return null;
  }
  return {
    planner_calls_total: metrics.planner_calls_total ?? 0,
    planner_fallback_count: metrics.planner_fallback_count ?? 0,
    rule_hits_count: metrics.rule_hits_count ?? 0,
    headless_runs_count: metrics.headless_runs_count ?? 0,
  };
}

function formatPayload(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value ?? "null");
  }
}

function resolveStatusBadge(status: CheckStatus) {
  switch (status) {
    case "pass":
      return { label: "Pass", variant: "secondary" as const, Icon: Check };
    case "warn":
      return { label: "Warn", variant: "outline" as const, Icon: AlertTriangle };
    default:
      return { label: "Fail", variant: "destructive" as const, Icon: X };
  }
}

interface DiagnosticsDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  browserAPI?: BrowserAPI;
  webviewRef: RefObject<ElectronWebviewElement | null>;
  supportsWebview?: boolean;
}

export function DiagnosticsDrawer({
  open,
  onOpenChange,
  browserAPI,
  webviewRef,
  supportsWebview = false,
}: DiagnosticsDrawerProps) {
  const [report, setReport] = useState<BrowserDiagnosticsReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState("snapshot");
  const [logEntries, setLogEntries] = useState<string[]>([]);
  const [payloadEvents, setPayloadEvents] = useState<PayloadSnapshot[]>([]);
  const [plannerBusy, setPlannerBusy] = useState(false);
  const [headlessBusy, setHeadlessBusy] = useState(false);
  const [incidentSnapshot, setIncidentSnapshot] = useState<BrowserIncident | null>(null);
  const [lastDirective, setLastDirective] = useState<DirectivePayload | null>(null);
  const [selfHealSubTab, setSelfHealSubTab] = useState("actions");
  const [rulepackRules, setRulepackRules] = useState<SelfHealRule[]>([]);
  const [rulepackYaml, setRulepackYaml] = useState("");
  const [rulepackMetrics, setRulepackMetrics] = useState<SelfHealMetrics | null>(null);
  const [rulesLoading, setRulesLoading] = useState(false);
  const [rulesError, setRulesError] = useState<string | null>(null);
  const [episodes, setEpisodes] = useState<SelfHealEpisode[]>([]);
  const [episodesLoading, setEpisodesLoading] = useState(false);
  const [promoteDiff, setPromoteDiff] = useState<string | null>(null);
  const [lastRuleHit, setLastRuleHit] = useState<string | null>(null);

  const incidentBusRef = useRef<IncidentBus | null>(null);
  if (!incidentBusRef.current) {
    incidentBusRef.current = new IncidentBus();
  }

  const autoPlanKeyRef = useRef<string | null>(null);
  const episodesRequestRef = useRef<Promise<void> | null>(null);

  useEffect(() => {
    incidentBusRef.current?.start();
  }, []);

  const appendLog = useCallback((entry: string) => {
    setLogEntries((prev) => {
      const timestamp = new Date().toLocaleTimeString();
      const next = [...prev, `[${timestamp}] ${entry}`];
      return next.slice(-400);
    });
  }, []);

  useEffect(() => {
    if (!open) {
      return;
    }
    const source = new EventSource("/api/progress/__diagnostics__/stream");
    source.onmessage = (event) => {
      let formatted = event.data;
      try {
        const data = JSON.parse(event.data) as {
          stage?: string;
          message?: string;
          metrics?: Record<string, number>;
          kind?: string;
          preview?: string;
          payload?: unknown;
        };
        if (data.stage || data.message) {
          formatted = `${data.stage ?? "event"}: ${data.message ?? ""}`.trim();
        }
        if (data.stage === "planner.rulepack" && typeof data.message === "string") {
          const match = data.message.split("rule_hit:")[1];
          if (match) {
            setLastRuleHit(match);
          }
        }
        if (data.stage === "self_heal.metrics" && data.metrics) {
          setRulepackMetrics((prev) =>
            normalizeMetrics({ ...(prev ?? ({} as Record<string, number>)), ...data.metrics }),
          );
        }
        if (data.kind === "payload") {
          const snapshot: PayloadSnapshot = {
            id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            stage: data.stage ?? "event",
            preview: typeof data.preview === "string" ? data.preview : formatted,
            ts: Date.now(),
            payload: data.payload,
          };
          setPayloadEvents((prev) => [snapshot, ...prev].slice(0, 20));
        }
      } catch {
        // fall back to raw text
      }
      appendLog(`[sse] ${formatted}`);
    };
    source.onerror = () => {
      appendLog("[sse] stream disconnected.");
      source.close();
    };
    return () => {
      source.close();
    };
  }, [appendLog, open]);

  const fetchDirective = useCallback(
    async (
      apply: boolean,
      options?: {
        label?: string;
        suppressBusy?: boolean;
        incident?: BrowserIncident | null;
        logPlan?: boolean;
      },
    ): Promise<DirectivePayload | null> => {
      const label = options?.label ?? (apply ? "apply" : "plan");
      const incident = options?.incident ?? incidentBusRef.current?.snapshot();
      if (!incident) {
        appendLog(`[self-heal] ${label}: unable to capture incident snapshot.`);
        return null;
      }
      setIncidentSnapshot(incident);
      if (!options?.suppressBusy) {
        setPlannerBusy(true);
      }
      appendLog(`[self-heal] ${label}: requesting directive (apply=${apply}).`);
      const incidentPayload = toIncident(incident);
      const controller = new AbortController();
      const timeoutHandle: ReturnType<typeof setTimeout> = setTimeout(() => {
        controller.abort();
      }, PLANNER_REQUEST_TIMEOUT_MS);
      try {
        const response = await fetch(`/api/diagnostics/self_heal?apply=${apply ? "true" : "false"}`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(incidentPayload),
          signal: controller.signal,
        });
        const text = await response.text();
        let payload: unknown = {};
        if (text) {
          try {
            payload = JSON.parse(text);
          } catch (err) {
            payload = { raw: text };
            appendLog(`[self-heal] ${label}: failed to parse planner JSON: ${String(err)}`);
          }
        }
        if (!response.ok) {
          appendLog(`[self-heal] ${label}: planner error (${response.status}).`);
          appendLog(`[self-heal] ${label}: payload -> ${JSON.stringify(payload, null, 2)}`);
          return null;
        }
        if (options?.logPlan !== false) {
          appendLog(`[self-heal] ${label}: response ->\n${JSON.stringify(payload, null, 2)}`);
        }
        let directive: DirectivePayload | null = null;
        if (payload && typeof payload === "object" && "directive" in payload) {
          const candidate = (payload as { directive?: unknown }).directive;
          directive = fromDirective(candidate);
        }
        if (payload && typeof payload === "object" && "meta" in payload) {
          const meta = (payload as { meta?: { rule_id?: string; episode_id?: string; source?: string } }).meta;
          if (meta?.rule_id) {
            setLastRuleHit(meta.rule_id);
            appendLog(`[self-heal] ${label}: deterministic directive from rule ${meta.rule_id}.`);
          }
        }
        if (!directive) {
          appendLog(`[self-heal] ${label}: planner returned no directive.`);
          return null;
        }
        setLastDirective(directive);
        const headlessCount = (directive.steps ?? []).filter((step) => step && step.headless).length;
        if (headlessCount > 0) {
          appendLog(
            `[self-heal] ${label}: directive includes ${headlessCount} headless step${headlessCount === 1 ? "" : "s"}.`,
          );
        }
        return directive;
      } catch (err) {
        if (isAbortError(err)) {
          appendLog(
            `[self-heal] ${label}: planner request timed out after ${PLANNER_REQUEST_TIMEOUT_MS / 1000}s.`,
          );
        } else {
          appendLog(`[self-heal] ${label}: request failed: ${String(err)}`);
        }
        return null;
      } finally {
        clearTimeout(timeoutHandle);
        if (!options?.suppressBusy) {
          setPlannerBusy(false);
        }
      }
    },
    [appendLog],
  );

  const handlePlan = useCallback(async () => {
    await fetchDirective(false, { label: "manual plan" });
  }, [fetchDirective]);

  const handleFixInTab = useCallback(async () => {
    const directive = await fetchDirective(true, { label: "in-tab fix" });
    if (!directive) {
      return;
    }
    const steps = Array.isArray(directive.steps) ? directive.steps : [];
    const inTabSteps = steps.filter((step) => step && !step.headless) as Verb[];
    if (inTabSteps.length === 0) {
      appendLog("[self-heal] in-tab fix: no in-tab steps to execute.");
      return;
    }
    const executor = typeof window !== "undefined" ? window.autopilotExecutor : undefined;
    if (!executor) {
      appendLog("[self-heal] in-tab fix: autopilot executor unavailable in this environment.");
      return;
    }
    try {
      await executor.run({ steps: inTabSteps });
      appendLog(`[self-heal] in-tab fix: executed ${inTabSteps.length} step${inTabSteps.length === 1 ? "" : "s"}.`);
    } catch (err) {
      appendLog(`[self-heal] in-tab fix: execution error: ${String(err)}`);
    }
  }, [appendLog, fetchDirective]);

  const handleFixHeadless = useCallback(async () => {
    let directive = lastDirective;
    if (!directive) {
      appendLog("[self-heal] headless fix: no cached directive; requesting a fresh plan.");
      directive = await fetchDirective(true, { label: "headless fix (fresh plan)" });
    }
    if (!directive) {
      appendLog("[self-heal] headless fix: unable to proceed without a directive.");
      return;
    }
    const headlessSteps = (directive.steps ?? []).filter((step) => step && step.headless);
    if (headlessSteps.length === 0) {
      appendLog("[self-heal] headless fix: directive contains no headless steps.");
      return;
    }
    if (typeof window !== "undefined") {
      const proceed = window.confirm(
        "Headless fix will run server-side scripted steps. Do you want to continue?",
      );
      if (!proceed) {
        appendLog("[self-heal] headless fix: execution cancelled by user.");
        return;
      }
    }
    setHeadlessBusy(true);
    const controller = new AbortController();
    const timeoutHandle: ReturnType<typeof setTimeout> = setTimeout(() => {
      controller.abort();
    }, PLANNER_REQUEST_TIMEOUT_MS);
    try {
      const response = await fetch(api("/api/diagnostics/self_heal/execute_headless"), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ consent: true, directive }),
        signal: controller.signal,
      });
      const text = await response.text();
      let payload: unknown = {};
      if (text) {
        try {
          payload = JSON.parse(text);
        } catch (err) {
          payload = { raw: text };
          appendLog(`[self-heal] headless fix: failed to parse response JSON: ${String(err)}`);
        }
      }
      if (!response.ok) {
        appendLog(`[self-heal] headless fix: executor error (${response.status}).`);
        appendLog(`[self-heal] headless fix: payload -> ${JSON.stringify(payload, null, 2)}`);
        return;
      }
      appendLog(`[self-heal] headless fix: result ->\n${JSON.stringify(payload, null, 2)}`);
    } catch (err) {
      if (isAbortError(err)) {
        appendLog(
          `[self-heal] headless fix: request timed out after ${PLANNER_REQUEST_TIMEOUT_MS / 1000}s.`,
        );
      } else {
        appendLog(`[self-heal] headless fix: request failed: ${String(err)}`);
      }
    } finally {
      clearTimeout(timeoutHandle);
      setHeadlessBusy(false);
    }
  }, [appendLog, fetchDirective, lastDirective]);

  const runChecks = useCallback(async () => {
    setError(null);
    setRunning(true);
    autoPlanKeyRef.current = null;
    try {
      let payload: BrowserDiagnosticsReport | null = null;
      if (browserAPI?.runDiagnostics) {
        const response = await browserAPI.runDiagnostics();
        if (!response?.ok) {
          throw new Error(response?.error || "diagnostics_failed");
        }
        payload = response.data ?? null;
      } else {
        const webview = webviewRef.current;
        if (!webview?.executeJavaScript) {
          throw new Error(supportsWebview ? "webview_unavailable" : "diagnostics_unavailable");
        }
        payload = await webview.executeJavaScript<BrowserDiagnosticsReport>(BROWSER_DIAGNOSTICS_SCRIPT, true);
      }
      setReport(payload ?? null);
      if (!payload) {
        setError("Diagnostics completed but returned no data.");
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
    } finally {
      setRunning(false);
    }
  }, [browserAPI, supportsWebview, webviewRef]);

  useEffect(() => {
    if (!report) {
      autoPlanKeyRef.current = null;
      return;
    }
    const key = String(report.timestamp ?? "");
    if (!key || autoPlanKeyRef.current === key) {
      return;
    }
    const incident = incidentBusRef.current?.snapshot();
    if (!incident) {
      return;
    }
    const hasSignals = Boolean(
      incident.symptoms.bannerText ||
        (incident.symptoms.consoleErrors && incident.symptoms.consoleErrors.length > 0) ||
        (incident.symptoms.networkErrors && incident.symptoms.networkErrors.length > 0),
    );
    if (!hasSignals) {
      return;
    }
    autoPlanKeyRef.current = key;
    appendLog("[self-heal] diagnostics run detected issues; requesting automatic plan.");
    void fetchDirective(false, {
      label: "auto-plan (diagnostics)",
      suppressBusy: true,
      incident,
    });
  }, [appendLog, fetchDirective, report]);

  const loadEpisodes = useCallback(async () => {
    if (episodesRequestRef.current) {
      return episodesRequestRef.current;
    }
    const request = (async () => {
      setEpisodesLoading(true);
      setRulesError(null);
      try {
        const response = await fetch("/api/diagnostics/rules/episodes?limit=120");
        if (!response.ok) {
          throw new Error(`failed to load episodes (${response.status})`);
        }
        const data = (await response.json()) as EpisodesResponse;
        setEpisodes(Array.isArray(data.episodes) ? data.episodes : []);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setRulesError(message);
      } finally {
        setEpisodesLoading(false);
        episodesRequestRef.current = null;
      }
    })();
    episodesRequestRef.current = request;
    return request;
  }, []);

  useEffect(() => {
    if (activeTab !== "self-heal") {
      setSelfHealSubTab("actions");
    }
  }, [activeTab]);

  const loadRulepack = useCallback(
    async (options?: { withEpisodes?: boolean }) => {
      setRulesLoading(true);
      setRulesError(null);
      try {
        const response = await fetch("/api/diagnostics/rules");
        if (!response.ok) {
          throw new Error(`failed to load rules (${response.status})`);
        }
        const data = (await response.json()) as RulepackResponse;
        setRulepackRules(Array.isArray(data.rules) ? data.rules : []);
        setRulepackYaml(typeof data.yaml === "string" ? data.yaml : "");
        setRulepackMetrics(normalizeMetrics(data.metrics ?? null));
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setRulesError(message);
      } finally {
        setRulesLoading(false);
      }
      if (options?.withEpisodes) {
        await loadEpisodes();
      }
    },
    [loadEpisodes],
  );

  useEffect(() => {
    if (activeTab !== "self-heal" || selfHealSubTab !== "rules") {
      return;
    }
    void loadRulepack({ withEpisodes: episodes.length === 0 });
  }, [activeTab, episodes.length, loadRulepack, selfHealSubTab]);

  const toggleRule = useCallback(
    async (ruleId: string, enabled: boolean) => {
      if (!ruleId) {
        return;
      }
      setRulesError(null);
      try {
        const response = await fetch("/api/diagnostics/rules/update", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ rule_id: ruleId, enabled }),
        });
        if (!response.ok) {
          throw new Error(`failed to update rule (${response.status})`);
        }
        const payload = (await response.json()) as RulepackResponse;
        setRulepackRules(Array.isArray(payload.rules) ? payload.rules : []);
        setRulepackYaml(typeof payload.yaml === "string" ? payload.yaml : "");
        setRulepackMetrics(normalizeMetrics(payload.metrics ?? null));
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setRulesError(message);
      }
    },
    [],
  );

  const reorderRule = useCallback(
    async (ruleId: string, direction: "up" | "down") => {
      const currentIndex = rulepackRules.findIndex((rule) => rule.id === ruleId);
      if (currentIndex === -1) {
        return;
      }
      if (!ruleId) {
        return;
      }
      const nextIndex = direction === "up" ? currentIndex - 1 : currentIndex + 1;
      if (nextIndex < 0 || nextIndex >= rulepackRules.length) {
        return;
      }
      const order = [...rulepackRules];
      const [moved] = order.splice(currentIndex, 1);
      order.splice(nextIndex, 0, moved);
      setRulesError(null);
      try {
        const response = await fetch("/api/diagnostics/rules/update", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ order: order.map((rule) => rule.id) }),
        });
        if (!response.ok) {
          throw new Error(`failed to reorder rules (${response.status})`);
        }
        const payload = (await response.json()) as RulepackResponse;
        setRulepackRules(Array.isArray(payload.rules) ? payload.rules : []);
        setRulepackYaml(typeof payload.yaml === "string" ? payload.yaml : "");
        setRulepackMetrics(normalizeMetrics(payload.metrics ?? null));
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setRulesError(message);
      }
    },
    [rulepackRules],
  );

  const promoteEpisode = useCallback(
    async (episodeId: string) => {
      setRulesError(null);
      setPromoteDiff(null);
      try {
        const response = await fetch("/api/diagnostics/rules/promote", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ episode_id: episodeId }),
        });
        const text = await response.text();
        let payload: PromoteResponse | { error?: string } = {};
        if (text) {
          try {
            payload = JSON.parse(text) as PromoteResponse | { error?: string };
          } catch (err) {
            throw new Error(`invalid promote response: ${String(err)}`);
          }
        }
        if (!response.ok) {
          throw new Error((payload as { error?: string }).error ?? `failed to promote (${response.status})`);
        }
        const promote = payload as PromoteResponse;
        setRulepackRules(Array.isArray(promote.rules) ? promote.rules : []);
        setRulepackYaml(typeof promote.yaml === "string" ? promote.yaml : "");
        setRulepackMetrics(normalizeMetrics(promote.metrics ?? null));
        if (typeof promote.yaml_diff === "string" && promote.yaml_diff.trim()) {
          setPromoteDiff(promote.yaml_diff);
        } else {
          setPromoteDiff(`Rule ${promote.rule_id} added (no diff).`);
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setRulesError(message);
      }
    },
    [],
  );

  const checks: DiagnosticsCheck[] = useMemo(() => {
    if (!report) {
      return [];
    }
    const uaStatus: CheckStatus = report.userAgent ? "pass" : "fail";
    const uaChStatus: CheckStatus = report.uaCh ? "pass" : report.uaChError ? "warn" : "warn";
    const webdriverStatus: CheckStatus = report.webdriver === false || typeof report.webdriver === "undefined" ? "pass" : "fail";
    const webglStatus: CheckStatus = report.webgl.vendor && report.webgl.renderer ? "pass" : report.webgl.error ? "warn" : "warn";
    const cookieStatus: CheckStatus = report.cookies.count !== null ? "pass" : report.cookies.error ? "warn" : "warn";
    let swStatus: CheckStatus = "warn";
    if (report.serviceWorker.status === "registered") {
      swStatus = "pass";
    } else if (!report.serviceWorker.supported || report.serviceWorker.status === "unsupported") {
      swStatus = "warn";
    } else if (report.serviceWorker.error) {
      swStatus = "fail";
    }

    return [
      {
        key: "ua",
        label: "User agent",
        detail: report.userAgent ? report.userAgent : "Unavailable",
        status: uaStatus,
      },
      {
        key: "ua-ch",
        label: "UA-CH",
        detail: report.uaCh ? JSON.stringify(report.uaCh) : report.uaChError || "Not provided",
        status: uaChStatus,
      },
      {
        key: "webdriver",
        label: "navigator.webdriver",
        detail: `${report.webdriver}`,
        status: webdriverStatus,
      },
      {
        key: "webgl",
        label: "WebGL vendor/renderer",
        detail:
          report.webgl.vendor && report.webgl.renderer
            ? `${report.webgl.vendor} / ${report.webgl.renderer}`
            : report.webgl.error || "Unavailable",
        status: webglStatus,
      },
      {
        key: "cookies",
        label: "Cookie count",
        detail:
          report.cookies.count !== null
            ? `${report.cookies.count} cookie${report.cookies.count === 1 ? "" : "s"}`
            : report.cookies.error || "Unavailable",
        status: cookieStatus,
      },
      {
        key: "service-worker",
        label: "Service worker",
        detail: report.serviceWorker.error
          ? report.serviceWorker.error
          : `${report.serviceWorker.status} (${report.serviceWorker.registrations} registrations)`,
        status: swStatus,
      },
    ];
  }, [report]);

  const handleCopy = useCallback(async () => {
    if (!report) {
      return;
    }
    try {
      if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") {
        throw new Error("Clipboard API unavailable");
      }
      await navigator.clipboard.writeText(JSON.stringify(report, null, 2));
      setError(null);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
    }
  }, [report]);

  const planDisabled = plannerBusy || running;
  const headlessDisabled = plannerBusy || headlessBusy;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" size="lg" className="w-full max-w-xl">
        <SheetHeader>
          <SheetTitle>Diagnostics</SheetTitle>
          <SheetDescription>
            Validate the embedded Chromium environment before logging into sensitive sites.
          </SheetDescription>
        </SheetHeader>
        <Tabs value={activeTab} onValueChange={setActiveTab} className="mt-4 flex flex-1 flex-col gap-4">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="snapshot">Snapshot</TabsTrigger>
          <TabsTrigger value="self-heal">Self-Heal</TabsTrigger>
        </TabsList>
        <TabsContent value="snapshot" className="flex flex-1 flex-col gap-4">
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={runChecks} disabled={running} size="sm">
                {running ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                {running ? "Running checks…" : "Run checks"}
              </Button>
              <Button onClick={handleCopy} variant="outline" size="sm" disabled={!report}>
                {copied ? <ClipboardCheck className="mr-2 h-4 w-4" /> : <Clipboard className="mr-2 h-4 w-4" />}
                {copied ? "Copied" : "Copy report"}
              </Button>
            </div>
            {!browserAPI && !supportsWebview ? (
              <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
                Diagnostics require the desktop app or a compatible Electron webview environment.
              </p>
            ) : null}
            {error ? (
              <p className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{error}</p>
            ) : null}
            {report ? (
              <ScrollArea className="flex-1 pr-4">
                <div className="space-y-3">
                  <div className="grid gap-2 text-xs text-muted-foreground">
                    <div>
                      <span className="font-medium text-foreground">Last run:</span> {new Date(report.timestamp).toLocaleString()}
                    </div>
                    <div>
                      <span className="font-medium text-foreground">Locale:</span> {report.navigatorLanguage ?? "unknown"}
                    </div>
                    <div>
                      <span className="font-medium text-foreground">Navigator languages:</span> {report.navigatorLanguages.join(", ") || "unknown"}
                    </div>
                  </div>
                  <Separator />
                  {checks.map((check) => {
                    const badge = resolveStatusBadge(check.status);
                    const Icon = badge.Icon;
                    return (
                      <div key={check.key} className="flex items-start justify-between gap-3 rounded-md border p-3">
                        <div>
                          <p className="text-sm font-medium">{check.label}</p>
                          <p className="mt-1 break-words text-xs text-muted-foreground whitespace-pre-wrap">{check.detail}</p>
                        </div>
                        <Badge variant={badge.variant} className="flex items-center gap-1 text-xs">
                          <Icon className="h-3 w-3" />
                          {badge.label}
                        </Badge>
                      </div>
                    );
                  })}
                  <Separator />
                  <div>
                    <p className="mb-2 text-sm font-medium">Raw payload</p>
                    <pre className="max-h-64 overflow-auto rounded-md bg-muted p-3 text-xs">
                      {JSON.stringify(report, null, 2)}
                    </pre>
                  </div>
                </div>
              </ScrollArea>
            ) : (
              <div className="flex flex-1 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
                Run diagnostics to generate a report.
              </div>
            )}
          </TabsContent>
        <TabsContent value="self-heal" className="flex flex-1 flex-col gap-4">
          <Tabs value={selfHealSubTab} onValueChange={setSelfHealSubTab} className="flex flex-1 flex-col gap-4">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="actions">Actions</TabsTrigger>
              <TabsTrigger value="rules">Rules</TabsTrigger>
            </TabsList>
            <TabsContent value="actions" className="flex flex-1 flex-col gap-4">
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">
                  Capture the current incident snapshot and stream planner updates through the diagnostics log.
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <Button size="sm" onClick={handlePlan} disabled={planDisabled}>
                    {plannerBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                    Plan
                  </Button>
                  <Button size="sm" variant="secondary" onClick={handleFixInTab} disabled={planDisabled}>
                    {plannerBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                    Fix in-tab
                  </Button>
                  <Button size="sm" variant="destructive" onClick={handleFixHeadless} disabled={headlessDisabled}>
                    {headlessBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                    Fix headless
                  </Button>
                </div>
              </div>
              {incidentSnapshot ? (
                <div className="space-y-2 rounded-md border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-sm font-semibold">Incident snapshot</h3>
                    <span className="text-xs text-muted-foreground">{new Date(incidentSnapshot.ts).toLocaleTimeString()}</span>
                  </div>
                  <div className="grid gap-1 text-xs text-muted-foreground">
                    <div>
                      <span className="font-medium text-foreground">URL:</span> {incidentSnapshot.url}
                    </div>
                    <div>
                      <span className="font-medium text-foreground">Banner:</span> {incidentSnapshot.symptoms.bannerText || "None"}
                    </div>
                    <div>
                      <span className="font-medium text-foreground">Console errors:</span> {incidentSnapshot.symptoms.consoleErrors.length}
                    </div>
                    <div>
                      <span className="font-medium text-foreground">Network errors:</span> {incidentSnapshot.symptoms.networkErrors.length}
                    </div>
                  </div>
                  {incidentSnapshot.domSnippet ? (
                    <div>
                      <p className="mt-2 text-xs font-medium">DOM snippet</p>
                      <pre className="max-h-32 overflow-auto rounded-md bg-muted p-2 text-[11px]">
                        {incidentSnapshot.domSnippet}
                      </pre>
                    </div>
                  ) : null}
                </div>
              ) : (
                <p className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
                  The next plan request will capture banner, console, and network signals from this tab.
                </p>
              )}
              <div className="flex flex-1 flex-col gap-2">
                <h3 className="text-sm font-semibold">Self-Heal log</h3>
                <ScrollArea className="h-48 w-full rounded-md border">
                  <pre className="whitespace-pre-wrap break-words p-3 text-xs">
                    {logEntries.length > 0 ? logEntries.join("\n") : "Waiting for planner output…"}
                  </pre>
                </ScrollArea>
              </div>
              <div className="flex flex-1 flex-col gap-2">
                <h3 className="text-sm font-semibold">Payload snapshots</h3>
                <ScrollArea className="h-48 w-full rounded-md border">
                  {payloadEvents.length > 0 ? (
                    <div className="space-y-3 p-3 text-xs">
                      {payloadEvents.map((event) => (
                        <div key={event.id} className="space-y-1">
                          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                            <span className="font-medium text-foreground">{event.stage}</span>
                            <span>{new Date(event.ts).toLocaleTimeString()}</span>
                          </div>
                          <pre className="whitespace-pre-wrap break-words rounded-md bg-muted p-2 text-[11px]">
                            {formatPayload(event.payload)}
                          </pre>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="flex h-full items-center justify-center p-3 text-xs text-muted-foreground">
                      Payload snapshots will appear once planner activity occurs.
                    </div>
                  )}
                </ScrollArea>
              </div>
            </TabsContent>
            <TabsContent value="rules" className="flex flex-1 flex-col gap-4">
              <div className="flex flex-col gap-4 md:flex-row">
                <div className="flex-1 space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-semibold">Rulepack</h3>
                      <p className="text-xs text-muted-foreground">
                        Rules run before the planner. Enable with care; order determines precedence.
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button size="xs" variant="outline" onClick={() => loadRulepack()} disabled={rulesLoading}>
                        {rulesLoading ? <Loader2 className="mr-2 h-3 w-3 animate-spin" /> : null}
                        Refresh
                      </Button>
                    </div>
                  </div>
                  {lastRuleHit ? (
                    <p className="text-xs text-muted-foreground">Last rule hit: {lastRuleHit}</p>
                  ) : null}
                  {rulepackMetrics ? (
                    <div className="grid grid-cols-2 gap-2 rounded-md border p-3 text-xs text-muted-foreground">
                      <div>
                        <span className="font-medium text-foreground">Planner calls:</span> {rulepackMetrics.planner_calls_total}
                      </div>
                      <div>
                        <span className="font-medium text-foreground">Fallbacks:</span> {rulepackMetrics.planner_fallback_count}
                      </div>
                      <div>
                        <span className="font-medium text-foreground">Rule hits:</span> {rulepackMetrics.rule_hits_count}
                      </div>
                      <div>
                        <span className="font-medium text-foreground">Headless runs:</span> {rulepackMetrics.headless_runs_count}
                      </div>
                    </div>
                  ) : null}
                  {rulesError ? (
                    <p className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
                      {rulesError}
                    </p>
                  ) : null}
                  <div className="space-y-2">
                    {rulepackRules.length === 0 ? (
                      <p className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
                        No rules defined. Promote an episode to create the first rule.
                      </p>
                    ) : (
                      rulepackRules.map((rule, index) => {
                        const summary = describeRule(rule);
                        const isFirst = index === 0;
                        const isLast = index === rulepackRules.length - 1;
                        return (
                          <div key={rule.id ?? index} className="rounded-md border p-3 text-xs text-muted-foreground">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <div>
                                <p className="text-sm font-semibold text-foreground">{rule.id || `rule_${index + 1}`}</p>
                                <p className="mt-1 break-words">{summary}</p>
                              </div>
                              <div className="flex items-center gap-2">
                                <Switch
                                  checked={Boolean(rule.enabled)}
                                  onCheckedChange={(checked) => toggleRule(rule.id, checked)}
                                  id={`switch-${rule.id}`}
                                />
                                <Button
                                  size="xs"
                                  variant="ghost"
                                  disabled={isFirst}
                                  onClick={() => reorderRule(rule.id, "up")}
                                >
                                  Up
                                </Button>
                                <Button
                                  size="xs"
                                  variant="ghost"
                                  disabled={isLast}
                                  onClick={() => reorderRule(rule.id, "down")}
                                >
                                  Down
                                </Button>
                              </div>
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
                <div className="flex-1 space-y-3">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-sm font-semibold">Episodes</h3>
                    <Button size="xs" variant="outline" onClick={loadEpisodes} disabled={episodesLoading}>
                      {episodesLoading ? <Loader2 className="mr-2 h-3 w-3 animate-spin" /> : null}
                      Refresh
                    </Button>
                  </div>
                  <ScrollArea className="h-64 w-full rounded-md border">
                    <div className="divide-y">
                      {episodes.length === 0 ? (
                        <p className="p-3 text-xs text-muted-foreground">No recent episodes recorded.</p>
                      ) : (
                        episodes.map((episode) => (
                          <div key={episode.id} className="space-y-1 p-3 text-xs text-muted-foreground">
                            <div className="flex items-center justify-between gap-2">
                              <p className="font-medium text-foreground">{episode.url || "(unknown url)"}</p>
                              <span>{new Date((episode.ts ?? 0) * 1000).toLocaleTimeString()}</span>
                            </div>
                            <p className="break-words">Outcome: {episode.outcome ?? "unknown"}</p>
                            <p className="break-words">Mode: {episode.mode}</p>
                            {episode.symptoms?.bannerText ? (
                              <p className="break-words">Banner: {episode.symptoms.bannerText}</p>
                            ) : null}
                            {episode.symptoms?.networkErrors?.length ? (
                              <p className="break-words">
                                Network: {episode.symptoms.networkErrors[0].url} ({episode.symptoms.networkErrors[0].status})
                              </p>
                            ) : null}
                            <div className="flex justify-end">
                              <Button size="xs" onClick={() => promoteEpisode(episode.id)}>
                                Promote to rule
                              </Button>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </ScrollArea>
                </div>
              </div>
              <div className="space-y-2">
                <h3 className="text-sm font-semibold">rulepack.yml</h3>
                <Textarea readOnly value={rulepackYaml} className="min-h-[180px] text-xs" />
                {promoteDiff ? (
                  <div>
                    <p className="text-xs font-medium">Last promote diff</p>
                    <pre className="max-h-40 overflow-auto rounded-md bg-muted p-2 text-[11px] whitespace-pre-wrap">
                      {promoteDiff}
                    </pre>
                  </div>
                ) : null}
              </div>
            </TabsContent>
          </Tabs>
        </TabsContent>
        </Tabs>
        <SheetFooter className="pt-0">
          <p className="text-xs text-muted-foreground">
            Tip: Run the checks after signing into a site to confirm cookies and service workers persist across restarts.
          </p>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
