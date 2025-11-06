const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "";

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

export type ModelRef = {
  name: string;
};

export type SeedSources = {
  news: string[];
  music: string[];
  tech: string[];
  art: string[];
  other: string[];
};

export type AppConfig = {
  models_primary: ModelRef;
  models_fallback: ModelRef;
  models_embedder: ModelRef;
  features_shadow_mode: boolean;
  features_agent_mode: boolean;
  features_local_discovery: boolean;
  features_browsing_fallbacks: boolean;
  features_index_auto_rebuild: boolean;
  features_auth_clearance_detectors: boolean;
  chat_use_page_context_default: boolean;
  browser_persist: boolean;
  browser_allow_cookies: boolean;
  sources_seed: SeedSources;
  setup_completed: boolean;
  dev_render_loop_guard: boolean;
};

type FieldDefinition = {
  legacyKey: string;
  property: keyof AppConfig;
  type: "boolean" | "select";
  label: string;
  description?: string;
  section: "models" | "features" | "browser" | "chat" | "setup" | "developer";
  options?: string[];
  defaultBoolean?: boolean;
  defaultOption?: string;
};

const FIELD_DEFINITIONS = [
  {
    legacyKey: "models.chat.primary",
    property: "models_primary",
    type: "select",
    label: "Primary chat model",
    description: "Default chat model offered to the assistant UI.",
    section: "models",
    options: ["gemma-3", "gpt-oss"],
    defaultOption: "gemma-3",
  },
  {
    legacyKey: "models.chat.fallback",
    property: "models_fallback",
    type: "select",
    label: "Fallback chat model",
    description: "Used when the primary model is unavailable or busy.",
    section: "models",
    options: ["gemma-3", "gpt-oss"],
    defaultOption: "gpt-oss",
  },
  {
    legacyKey: "models.embedding.primary",
    property: "models_embedder",
    type: "select",
    label: "Embedding model",
    description: "Vector store embedding model used for hybrid search.",
    section: "models",
    options: ["embeddinggemma"],
    defaultOption: "embeddinggemma",
  },
  {
    legacyKey: "features.shadow_mode",
    property: "features_shadow_mode",
    type: "boolean",
    label: "Shadow mode",
    description: "Mirror your browsing session for offline replay.",
    section: "features",
    defaultBoolean: true,
  },
  {
    legacyKey: "features.agent_mode",
    property: "features_agent_mode",
    type: "boolean",
    label: "Agent mode",
    description: "Allow the assistant to stage multi-step browsing plans.",
    section: "features",
    defaultBoolean: true,
  },
  {
    legacyKey: "features.local_discovery",
    property: "features_local_discovery",
    type: "boolean",
    label: "Local discovery",
    description: "Stream link previews and domain annotations in real time.",
    section: "features",
    defaultBoolean: true,
  },
  {
    legacyKey: "features.browsing_fallbacks",
    property: "features_browsing_fallbacks",
    type: "boolean",
    label: "Browser fallbacks",
    description: "Open the desktop browser when the embedded engine fails.",
    section: "features",
    defaultBoolean: true,
  },
  {
    legacyKey: "features.index_auto_rebuild",
    property: "features_index_auto_rebuild",
    type: "boolean",
    label: "Auto rebuild index",
    description: "Automatically rebuild keyword + vector indexes when corruption is detected.",
    section: "features",
    defaultBoolean: true,
  },
  {
    legacyKey: "features.auth_clearance_detectors",
    property: "features_auth_clearance_detectors",
    type: "boolean",
    label: "Auth clearance detectors",
    description: "Detect authentication gates and prompt for manual review.",
    section: "features",
    defaultBoolean: false,
  },
  {
    legacyKey: "chat.use_page_context_default",
    property: "chat_use_page_context_default",
    type: "boolean",
    label: "Use page context by default",
    description: "Provide the active tab context to the assistant when chats begin.",
    section: "chat",
    defaultBoolean: true,
  },
  {
    legacyKey: "browser.persist",
    property: "browser_persist",
    type: "boolean",
    label: "Persist browsing state",
    description: "Persist browsing sessions across restarts.",
    section: "browser",
    defaultBoolean: true,
  },
  {
    legacyKey: "browser.allow_cookies",
    property: "browser_allow_cookies",
    type: "boolean",
    label: "Allow cookies",
    description: "Retain cookies for authenticated browsing sessions.",
    section: "browser",
    defaultBoolean: true,
  },
  {
    legacyKey: "setup.completed",
    property: "setup_completed",
    type: "boolean",
    label: "Setup completed",
    description: "Tracks whether the first-run wizard has been acknowledged.",
    section: "setup",
    defaultBoolean: false,
  },
  {
    legacyKey: "dev.render_loop_guard",
    property: "dev_render_loop_guard",
    type: "boolean",
    label: "Render loop guard (dev)",
    description: "Enable render loop detection and logging in development builds.",
    section: "developer",
    defaultBoolean: true,
  },
] as const;

// derived types are available above; use runtime typing below as FieldDefinition[]

const SECTION_LABELS: Record<FieldDefinition["section"], string> = {
  models: "Models",
  features: "Features",
  browser: "Browser",
  chat: "Chat",
  setup: "Setup",
  developer: "Developer",
};

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

export async function getConfig(): Promise<AppConfig> {
  const response = await fetch(apiPath("/api/config"), { credentials: "include" });
  return parseJson<AppConfig>(response);
}

export async function putConfig(patch: Partial<AppConfig>): Promise<void> {
  const response = await fetch(apiPath("/api/config"), {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch ?? {}),
  });
  await parseJson<{ ok: boolean }>(response);
}

export async function getConfigSchema(): Promise<Record<string, unknown>> {
  const response = await fetch(apiPath("/api/config/schema"), { credentials: "include" });
  return parseJson<Record<string, unknown>>(response);
}

function toRuntimeConfig(config: AppConfig): RuntimeConfig {
  const payload: RuntimeConfig = {};
  for (const field of FIELD_DEFINITIONS) {
    const value = config[field.property];
    if (field.type === "select" && typeof value === "object" && value !== null) {
      payload[field.legacyKey] = (value as ModelRef).name;
    } else {
      payload[field.legacyKey] = value as unknown;
    }
  }
  return payload;
}

function normaliseBoolean(input: unknown, fallback: boolean): boolean {
  if (typeof input === "boolean") {
    return input;
  }
  if (typeof input === "string") {
    const lowered = input.trim().toLowerCase();
    if (["true", "1", "yes", "on"].includes(lowered)) return true;
    if (["false", "0", "no", "off"].includes(lowered)) return false;
  }
  return fallback;
}

export function buildPatch(patch: Record<string, unknown>, current?: AppConfig): Partial<AppConfig> {
  const partial: Partial<AppConfig> = {};
  type SelectKey = "models_primary" | "models_fallback" | "models_embedder";
  type BoolKey =
    | "features_shadow_mode"
    | "features_agent_mode"
    | "features_local_discovery"
    | "features_browsing_fallbacks"
    | "features_index_auto_rebuild"
    | "features_auth_clearance_detectors"
    | "chat_use_page_context_default"
    | "browser_persist"
    | "browser_allow_cookies"
    | "setup_completed"
    | "dev_render_loop_guard";

  function assignPartial(key: SelectKey, value: { name: string }): void;
  function assignPartial(key: BoolKey, value: boolean): void;
  function assignPartial<K extends keyof AppConfig>(key: K, value: AppConfig[K]) {
    partial[key] = value;
  }
  const SELECT_PROPERTIES: Array<keyof AppConfig> = [
    "models_primary",
    "models_fallback",
    "models_embedder",
  ];
  const BOOL_PROPERTIES: Array<keyof AppConfig> = [
    "features_shadow_mode",
    "features_agent_mode",
    "features_local_discovery",
    "features_browsing_fallbacks",
    "features_index_auto_rebuild",
    "features_auth_clearance_detectors",
    "chat_use_page_context_default",
    "browser_persist",
    "browser_allow_cookies",
    "setup_completed",
    "dev_render_loop_guard",
  ];
  for (const [key, value] of Object.entries(patch ?? {})) {
    const definition = FIELD_DEFINITIONS.find((f) => f.legacyKey === key);
    if (!definition) continue;

    if (definition.type === "select") {
      // apply only when patch explicitly provides a non-empty string
      const selected = typeof value === "string" && value ? value : undefined;
      if (!selected) continue;
      // assign a ModelRef shape with a narrow cast based on known properties
      if (SELECT_PROPERTIES.includes(definition.property)) {
        assignPartial(definition.property as "models_primary", { name: selected });
      }
      continue;
    }

    if (definition.type === "boolean") {
      const currentValue = current?.[definition.property];
      const fallback = typeof currentValue === "boolean" ? currentValue : Boolean(definition.defaultBoolean ?? false);
      const normalized = normaliseBoolean(value, fallback);
      if (BOOL_PROPERTIES.includes(definition.property)) {
        assignPartial(definition.property as BoolKey, Boolean(normalized));
      }
      continue;
    }
  }
  return partial;
}

export async function fetchConfig(): Promise<RuntimeConfig> {
  const config = await getConfig();
  return toRuntimeConfig(config);
}

export async function updateConfig(patch: Record<string, unknown>): Promise<RuntimeConfig> {
  const current = await getConfig();
  const partial = buildPatch(patch, current);
  if (Object.keys(partial).length > 0) {
    await putConfig(partial);
  }
  const next = await getConfig();
  return toRuntimeConfig(next);
}

export async function fetchConfigSchema(): Promise<ConfigSchema> {
  try {
    await getConfigSchema();
  } catch (error) {
    console.warn("Failed to load config JSON schema", error);
  }
  const sections = Object.entries(SECTION_LABELS).map(([sectionId, label]) => ({
    id: sectionId,
    label,
  fields: (FIELD_DEFINITIONS as unknown as FieldDefinition[])
      .filter((field) => field.section === sectionId)
      .map((field) => {
        if (field.type === "select") {
        return {
          key: field.legacyKey,
          type: field.type,
          label: field.label,
          description: field.description,
          default: field.defaultOption ?? (field.options && field.options[0]) ?? null,
          options: field.options ? Array.from(field.options) : null,
        };
      }
      // boolean field
      return {
        key: field.legacyKey,
        type: field.type,
        label: field.label,
        description: field.description,
        default: normaliseBoolean(undefined, field.defaultBoolean ?? false),
        options: null,
      };
    }),
  }));
  return { version: 1, sections };
}

export type HealthSnapshot = {
  status: string;
  timestamp: string;
  environment?: Record<string, unknown>;
  components: Record<string, { status: string; detail: Record<string, unknown> }>;
};

export async function getHealth(): Promise<HealthSnapshot> {
  const response = await fetch(apiPath("/api/health"), { credentials: "include" });
  return parseJson<HealthSnapshot>(response);
}

export const fetchHealth = getHealth;

export async function getCapabilities(): Promise<Record<string, unknown>> {
  const response = await fetch(apiPath("/api/capabilities"), { credentials: "include" });
  return parseJson<Record<string, unknown>>(response);
}

export async function requestModelInstall(models: string[]): Promise<{ ok: boolean; results?: unknown }> {
  const response = await fetch(apiPath("/api/admin/install_models"), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ models }),
  });
  return parseJson<{ ok: boolean; results?: unknown; error?: string }>(response);
}

export async function getDiagnosticsSnapshot(): Promise<Record<string, unknown>> {
  const response = await fetch(apiPath("/api/dev/diag/snapshot"), { credentials: "include" });
  return parseJson<Record<string, unknown>>(response);
}

export async function triggerRepair(): Promise<Record<string, unknown>> {
  const response = await fetch(apiPath("/api/dev/diag/repair"), {
    method: "POST",
    credentials: "include",
  });
  return parseJson<Record<string, unknown>>(response);
}
