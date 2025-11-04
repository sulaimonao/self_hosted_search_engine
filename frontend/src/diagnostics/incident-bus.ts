"use client";

import "@/shared/browser-diagnostics-script";

import {
  scanDomForBanner,
  installConsoleDetector,
  installNetworkDetector,
  IncidentSymptoms,
} from "./detectors";

type IncidentSeverity = "info" | "warn" | "error";

export type BrowserIncident = {
  id: string;
  url: string;
  ts: number;
  context: "browser";
  kind?: string;
  message?: string;
  severity?: IncidentSeverity;
  detail?: Record<string, unknown>;
  symptoms: IncidentSymptoms;
  domSnippet?: string;
};

type IncidentListener = (incidents: BrowserIncident[]) => void;

const INCIDENT_MESSAGE_SOURCE = "diagnostics::browser";
const INCIDENT_MESSAGE_TYPE = "diagnostics:incident";

const MAX_CONSOLE_ENTRIES = 50;
const MAX_NETWORK_ENTRIES = 50;
const MAX_INCIDENTS = 100;

function generateId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
}

function coerceSeverity(value: unknown, fallback: IncidentSeverity): IncidentSeverity {
  if (value === "info" || value === "warn" || value === "error") {
    return value;
  }
  return fallback;
}

function coerceTimestamp(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 1_000_000_000_000 ? value : value * 1000;
  }
  return Date.now();
}

export class IncidentBus {
  private consoleErrors: string[] = [];
  private networkErrors: { url: string; status?: number; error?: string }[] = [];
  private lastBannerText?: string;
  private incidents: BrowserIncident[] = [];
  private listeners = new Set<IncidentListener>();
  private started = false;
  private ingestedServerIds = new Set<string>();

  private readonly handleMessage = (event: MessageEvent) => {
    const data = event?.data as {
      source?: unknown;
      type?: unknown;
      payload?: {
        kind?: unknown;
        message?: unknown;
        severity?: unknown;
        detail?: unknown;
        ts?: unknown;
      };
    };
    if (!data || data.source !== INCIDENT_MESSAGE_SOURCE || data.type !== INCIDENT_MESSAGE_TYPE) {
      return;
    }
    const payload = data.payload ?? {};
    if (typeof payload.kind !== "string") {
      return;
    }
    const detail =
      payload.detail && typeof payload.detail === "object"
        ? (payload.detail as Record<string, unknown>)
        : undefined;
    this.record(payload.kind, {
      message: typeof payload.message === "string" ? payload.message : undefined,
      severity: coerceSeverity(payload.severity, "error"),
      detail,
      timestamp: coerceTimestamp(payload.ts),
    });
  };

  start(): void {
    if (this.started) {
      return;
    }
    this.started = true;
    installConsoleDetector((message) => {
      this.consoleErrors.push(message);
      if (this.consoleErrors.length > MAX_CONSOLE_ENTRIES) {
        this.consoleErrors.shift();
      }
    });
    installNetworkDetector((entry) => {
      this.networkErrors.push(entry);
      if (this.networkErrors.length > MAX_NETWORK_ENTRIES) {
        this.networkErrors.shift();
      }
      const severity: IncidentSeverity =
        typeof entry.status === "number" ? (entry.status >= 500 ? "error" : "warn") : entry.error ? "error" : "warn";
      const message = entry.error
        ? entry.error
        : entry.status
          ? `${entry.url} responded with ${entry.status}`
          : `${entry.url} request failed`;
      this.record("NETWORK_ERROR", {
        message,
        detail: entry,
        severity,
      });
    });
    if (typeof window !== "undefined") {
      window.addEventListener("message", this.handleMessage);
    }
  }

  subscribe(listener: IncidentListener): () => void {
    this.listeners.add(listener);
    listener(this.getIncidents());
    return () => {
      this.listeners.delete(listener);
    };
  }

  getIncidents(): BrowserIncident[] {
    return [...this.incidents];
  }

  record(
    kind: string,
    options?: {
      message?: string;
      severity?: IncidentSeverity;
      detail?: Record<string, unknown>;
      timestamp?: number;
    },
  ): BrowserIncident {
    const bannerText = scanDomForBanner();
    if (bannerText) {
      this.lastBannerText = bannerText;
    }
    const domEl =
      typeof document !== "undefined"
        ? (document.querySelector('[role="alert"], .toast, .error, .alert-error') as HTMLElement | null)
        : null;
    const incident: BrowserIncident = {
      id: generateId(),
      url: typeof location !== "undefined" ? location.href : "",
      ts: options?.timestamp ?? Date.now(),
      context: "browser",
      kind,
      message: options?.message,
      severity: options?.severity ?? "error",
      detail: options?.detail,
      symptoms: {
        bannerText: this.lastBannerText || bannerText,
        consoleErrors: [...this.consoleErrors],
        networkErrors: [...this.networkErrors],
      },
      domSnippet: domEl ? domEl.outerHTML.slice(0, 4000) : undefined,
    };
    this.incidents = [...this.incidents.slice(-MAX_INCIDENTS + 1), incident];
    this.emit();
    return incident;
  }

  ingest(entries: Array<Record<string, unknown>>): void {
    for (const entry of entries) {
      if (!entry || typeof entry !== "object") {
        continue;
      }
      const identifier =
        typeof entry["id"] === "string"
          ? entry["id"]
          : typeof entry["uuid"] === "string"
            ? (entry["uuid"] as string)
            : null;
      if (identifier && this.ingestedServerIds.has(identifier)) {
        continue;
      }
      if (identifier) {
        this.ingestedServerIds.add(identifier);
      }
      const kind =
        typeof entry["type"] === "string"
          ? (entry["type"] as string)
          : typeof entry["kind"] === "string"
            ? (entry["kind"] as string)
            : "SERVER_INCIDENT";
      const message =
        typeof entry["message"] === "string"
          ? (entry["message"] as string)
          : typeof entry["detail"] === "string"
            ? (entry["detail"] as string)
            : undefined;
      const severity = coerceSeverity(entry["severity"], "warn");
      const detail =
        entry["detail"] && typeof entry["detail"] === "object"
          ? (entry["detail"] as Record<string, unknown>)
          : undefined;
      const tsValue =
        typeof entry["ts"] === "number"
          ? coerceTimestamp(entry["ts"])
          : typeof entry["timestamp"] === "number"
            ? coerceTimestamp(entry["timestamp"])
            : undefined;
      this.record(kind, {
        message,
        severity,
        detail,
        timestamp: tsValue,
      });
    }
  }

  snapshot(): BrowserIncident {
    const bannerText = scanDomForBanner();
    this.lastBannerText = bannerText || this.lastBannerText;
    const domEl =
      typeof document !== "undefined"
        ? (document.querySelector('[role="alert"], .toast, .error, .alert-error') as HTMLElement | null)
        : null;
    return {
      id: generateId(),
      url: typeof location !== "undefined" ? location.href : "",
      ts: Date.now(),
      context: "browser",
      symptoms: {
        bannerText: this.lastBannerText || bannerText,
        consoleErrors: [...this.consoleErrors],
        networkErrors: [...this.networkErrors],
      },
      domSnippet: domEl ? domEl.outerHTML.slice(0, 4000) : undefined,
    };
  }

  private emit(): void {
    const snapshot = this.getIncidents();
    for (const listener of this.listeners) {
      try {
        listener(snapshot);
      } catch (error) {
        console.warn("[diagnostics] incident listener failed", error);
      }
    }
  }
}

export const incidentBus = new IncidentBus();
