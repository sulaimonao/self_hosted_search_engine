"use client";

export type ConfigFieldOption = {
  key: string;
  type: "boolean" | "select";
  label: string;
  description?: string;
  default: unknown;
  options?: string[] | null;
};

export type ConfigSection = {
  id: string;
  label: string;
  fields: ConfigFieldOption[];
};

export type ConfigSchema = {
  version: number;
  sections: ConfigSection[];
};

export type RuntimeConfig = Record<string, unknown>;

export type HealthSnapshot = {
  status: string;
  timestamp: string;
  environment?: Record<string, unknown>;
  components: Record<string, { status: string; detail: Record<string, unknown> }>;
};

export type CapabilitySnapshot = Record<string, unknown>;

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "";

function apiPath(path: string): string {
  if (!path.startsWith("/")) {
    return `${API_BASE}/${path}`;
  }
  return `${API_BASE}${path}`;
}

async function parseJson<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok) {
    const message = typeof data?.error === "string" ? data.error : `Request failed (${response.status})`;
    throw new Error(message);
  }
  return data as T;
}

export async function fetchConfig(): Promise<RuntimeConfig> {
  const response = await fetch(apiPath("/api/config"), {
    credentials: "include",
  });
  const payload = await parseJson<{ config: RuntimeConfig }>(response);
  return payload.config ?? {};
}

export async function updateConfig(patch: Record<string, unknown>): Promise<RuntimeConfig> {
  const response = await fetch(apiPath("/api/config"), {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch ?? {}),
  });
  const payload = await parseJson<{ config: RuntimeConfig }>(response);
  return payload.config ?? {};
}

export async function fetchConfigSchema(): Promise<ConfigSchema> {
  const response = await fetch(apiPath("/api/config/schema"), {
    credentials: "include",
  });
  return parseJson<ConfigSchema>(response);
}

export async function fetchHealth(): Promise<HealthSnapshot> {
  const response = await fetch(apiPath("/api/health"), {
    credentials: "include",
  });
  return parseJson<HealthSnapshot>(response);
}

export async function fetchCapabilities(): Promise<CapabilitySnapshot> {
  const response = await fetch(apiPath("/api/capabilities"), {
    credentials: "include",
  });
  return parseJson<CapabilitySnapshot>(response);
}

export async function requestModelInstall(
  models: string[],
): Promise<{ ok: boolean; results?: unknown }> {
  const response = await fetch(apiPath("/api/admin/install_models"), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ models }),
  });
  try {
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(typeof payload?.error === "string" ? payload.error : "Install failed");
    }
    return { ok: true, results: payload?.results };
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }
    throw new Error("Install failed");
  }
}

export async function fetchDiagnosticsSnapshot(): Promise<Record<string, unknown>> {
  const response = await fetch(apiPath("/api/dev/diag/snapshot"), {
    credentials: "include",
  });
  return parseJson<Record<string, unknown>>(response);
}

export async function triggerRepair(): Promise<Record<string, unknown>> {
  const response = await fetch(apiPath("/api/dev/diag/repair"), {
    method: "POST",
    credentials: "include",
  });
  return parseJson<Record<string, unknown>>(response);
}
