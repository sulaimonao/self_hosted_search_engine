import type { Verb } from "@/autopilot/executor";
import type { BrowserIncident } from "@/diagnostics/incident-bus";

const VERB_ALIASES: Record<string, "navigate" | "reload" | "click" | "type" | "waitForStable"> = {
  navigate: "navigate",
  goto: "navigate",
  go: "navigate",
  open: "navigate",
  reload: "reload",
  refresh: "reload",
  click: "click",
  press: "click",
  tap: "click",
  type: "type",
  input: "type",
  enter: "type",
  wait: "waitForStable",
  waitforstable: "waitForStable",
  waitfor: "waitForStable",
  pause: "waitForStable",
};

const CONFIDENCE_LEVELS = new Set(["low", "medium", "high"]);

export type IncidentPayload = {
  id: string;
  url: string;
  symptoms: {
    bannerText?: string;
    consoleErrors?: string[];
    networkErrors?: { url?: string; status?: number; error?: string }[];
  };
  domSnippet?: string;
};

export type DirectiveStep = Verb & {
  verify?: Record<string, unknown>;
  onFailNext?: string;
  [key: string]: unknown;
};

export type DirectivePayload = {
  reason: string;
  steps: DirectiveStep[];
  plan_confidence?: "low" | "medium" | "high";
  needs_user_permission?: boolean;
  ask_user?: string[];
  fallback?: {
    enabled?: boolean;
    headless_hint?: string[];
    [key: string]: unknown;
  } | null;
};

function normalizeString(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

function normalizeBoolean(value: unknown): boolean | undefined {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") {
    const lowered = value.trim().toLowerCase();
    if (["1", "true", "yes", "on"].includes(lowered)) return true;
    if (["0", "false", "no", "off"].includes(lowered)) return false;
  }
  return undefined;
}

function normalizeNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return undefined;
}

function normalizeConsoleErrors(errors: unknown): string[] | undefined {
  if (!Array.isArray(errors)) return undefined;
  const list = errors
    .map((entry) => {
      if (typeof entry === "string") return entry.trim();
      if (!entry) return "";
      try {
        return JSON.stringify(entry);
      } catch {
        return String(entry ?? "");
      }
    })
    .filter((entry) => entry.length > 0)
    .slice(-5);
  return list.length > 0 ? list : undefined;
}

function normalizeNetworkErrors(errors: unknown): { url?: string; status?: number; error?: string }[] | undefined {
  if (!Array.isArray(errors)) return undefined;
  const list = errors
    .slice(-5)
    .map((entry) => {
      if (!entry || typeof entry !== "object") return null;
      const record = entry as Record<string, unknown>;
      const url = normalizeString(record.url);
      const status = normalizeNumber(record.status);
      const error = normalizeString(record.error);
      const payload: { url?: string; status?: number; error?: string } = {};
      if (url) payload.url = url;
      if (typeof status === "number" && Number.isFinite(status)) payload.status = status;
      if (error) payload.error = error;
      return Object.keys(payload).length > 0 ? payload : null;
    })
    .filter((item): item is { url?: string; status?: number; error?: string } => item !== null);
  return list.length > 0 ? list : undefined;
}

export function toIncident(snapshot: BrowserIncident | null | undefined): IncidentPayload {
  const id = normalizeString(snapshot?.id) ?? "";
  const url = normalizeString(snapshot?.url) ?? "";
  const banner = normalizeString(snapshot?.symptoms?.bannerText);
  const consoleErrors = normalizeConsoleErrors(snapshot?.symptoms?.consoleErrors);
  const networkErrors = normalizeNetworkErrors(snapshot?.symptoms?.networkErrors);
  const symptoms: IncidentPayload["symptoms"] = {};
  if (banner) symptoms.bannerText = banner;
  if (consoleErrors) symptoms.consoleErrors = consoleErrors;
  if (networkErrors) symptoms.networkErrors = networkErrors;
  const domSnippet = normalizeString(snapshot?.domSnippet)?.slice(0, 4096);
  return {
    id,
    url,
    symptoms,
    domSnippet,
  };
}

function normalizeStep(raw: unknown): DirectiveStep | null {
  if (!raw || typeof raw !== "object") return null;
  const record = raw as Record<string, unknown>;
  const token = normalizeString(record.type ?? record.verb ?? record.action) ?? "";
  const canonical = VERB_ALIASES[token.toLowerCase().replace(/\s+/g, "")];
  if (!canonical) return null;
  const headless = normalizeBoolean(record.headless) ?? false;
  const args = (record.args && typeof record.args === "object" ? (record.args as Record<string, unknown>) : {}) ?? {};
  const selector = normalizeString(record.selector ?? args.selector);
  const text = normalizeString(record.text ?? args.text);
  const url = normalizeString(record.url ?? args.url);
  const ms = normalizeNumber(record.ms ?? args.ms);
  const verify = record.verify && typeof record.verify === "object" ? (record.verify as Record<string, unknown>) : undefined;
  const onFailNext = normalizeString(record.on_fail_next ?? record.onFailNext ?? args.on_fail_next ?? args.onFailNext);

  if (canonical === "navigate") {
    if (!url) return null;
    const step: DirectiveStep = { type: "navigate", url };
    if (headless) step.headless = true;
    if (verify) step.verify = verify;
    if (onFailNext) step.onFailNext = onFailNext;
    return step;
  }

  if (canonical === "reload") {
    const step: DirectiveStep = { type: "reload" };
    if (headless) step.headless = true;
    if (verify) step.verify = verify;
    if (onFailNext) step.onFailNext = onFailNext;
    return step;
  }

  if (canonical === "click") {
    if (!selector && !text) return null;
    const step: DirectiveStep = { type: "click" };
    if (selector) step.selector = selector;
    if (text) step.text = text;
    if (headless) step.headless = true;
    if (verify) step.verify = verify;
    if (onFailNext) step.onFailNext = onFailNext;
    return step;
  }

  if (canonical === "type") {
    if (!selector || !text) return null;
    const step: DirectiveStep = { type: "type", selector, text };
    if (headless) step.headless = true;
    if (verify) step.verify = verify;
    if (onFailNext) step.onFailNext = onFailNext;
    return step;
  }

  // waitForStable
  const stableStep: DirectiveStep = { type: "waitForStable" };
  if (typeof ms === "number" && ms > 0) {
    stableStep.ms = Math.round(ms);
  }
  if (headless) stableStep.headless = true;
  if (verify) stableStep.verify = verify;
  if (onFailNext) stableStep.onFailNext = onFailNext;
  return stableStep;
}

export function fromDirective(raw: unknown): DirectivePayload {
  const data = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  const reason = normalizeString(data.reason) ?? "Planned fix";
  const stepsInput = Array.isArray(data.steps) ? data.steps : [];
  const steps = stepsInput.map((item) => normalizeStep(item)).filter((item): item is DirectiveStep => item !== null);
  if (steps.length === 0) {
    steps.push({ type: "reload" });
  }

  const planConfidence = normalizeString(data.plan_confidence ?? data.planConfidence);
  const needsPermission = normalizeBoolean(data.needs_user_permission ?? data.needsUserPermission);

  const askUserRaw = Array.isArray(data.ask_user ?? data.askUser) ? (data.ask_user ?? data.askUser) : [];
  const askUser = Array.isArray(askUserRaw)
    ? askUserRaw
        .map((entry) => (typeof entry === "string" ? entry.trim() : ""))
        .filter((entry) => entry.length > 0)
    : [];

  const fallbackRaw = data.fallback && typeof data.fallback === "object" ? (data.fallback as Record<string, unknown>) : null;
  let fallback: DirectivePayload["fallback"] = null;
  if (fallbackRaw) {
    const enabled = normalizeBoolean(fallbackRaw.enabled);
    const hints = Array.isArray(fallbackRaw.headless_hint)
      ? (fallbackRaw.headless_hint as unknown[])
          .map((entry) => (typeof entry === "string" ? entry.trim() : ""))
          .filter((entry) => entry.length > 0)
      : [];
    fallback = {};
    if (typeof enabled === "boolean") fallback.enabled = enabled;
    if (hints.length > 0) fallback.headless_hint = hints;
  }

  return {
    reason,
    steps,
    plan_confidence: planConfidence && CONFIDENCE_LEVELS.has(planConfidence) ? planConfidence : undefined,
    needs_user_permission: needsPermission,
    ask_user: askUser.length > 0 ? askUser : undefined,
    fallback,
  };
}
