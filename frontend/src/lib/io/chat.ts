import type { AutopilotDirective, AutopilotToolDirective, ChatResponsePayload } from "@/lib/types";
import { fromDirective } from "@/lib/io/self_heal";
import type { DirectivePayload } from "@/lib/io/self_heal";
import type { Verb } from "@/autopilot/executor";

const CHAT_ROLES = new Set(["system", "user", "assistant", "tool"]);

type ChatMessageInput = {
  role?: unknown;
  content?: unknown;
  images?: unknown;
  metadata?: unknown;
};

type ChatRequestInput = {
  model?: string | null;
  stream?: boolean | null;
  context?: unknown;
  url?: string | null;
  textContext?: string | null;
  imageContext?: string | null;
  clientTimezone?: string | null;
  serverTime?: string | null;
  serverTimezone?: string | null;
  serverUtc?: string | null;
  requestId?: string | null;
  chatId?: string | null;
  messages?: unknown;
};

export type ChatRequestPayload = {
  model?: string;
  messages: Array<{
    role: "system" | "user" | "assistant" | "tool";
    content: string;
    images?: string[];
    metadata?: Record<string, unknown>;
  }>;
  stream?: boolean;
  context?: Record<string, unknown>;
  url?: string;
  text_context?: string;
  image_context?: string;
  client_timezone?: string;
  server_time?: string;
  server_timezone?: string;
  server_time_utc?: string;
  request_id?: string;
  chat_id?: string;
};

function normalizeString(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

function normalizeImages(value: unknown): string[] | undefined {
  if (Array.isArray(value)) {
    const items = value
      .map((entry) => (typeof entry === "string" ? entry.trim() : ""))
      .filter((entry) => entry.length > 0);
    return items.length > 0 ? items : undefined;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed ? [trimmed] : undefined;
  }
  return undefined;
}

function normalizeMetadata(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== "object") return undefined;
  const entries = Object.entries(value as Record<string, unknown>).filter(([key]) =>
    typeof key === "string" && key.trim().length > 0,
  );
  return entries.length > 0 ? Object.fromEntries(entries) : undefined;
}

function normalizeMessage(raw: unknown): ChatRequestPayload["messages"][number] | null {
  if (!raw || typeof raw !== "object") return null;
  const value = raw as ChatMessageInput;
  const role = normalizeString(value.role);
  if (!role) return null;
  const normalizedRole = CHAT_ROLES.has(role) ? role : "user";
  const content = normalizeString(value.content) ?? "";
  const images = normalizeImages(value.images);
  const metadata = normalizeMetadata(value.metadata);
  return {
    role: normalizedRole as ChatRequestPayload["messages"][number]["role"],
    content,
    images,
    metadata,
  };
}

export function toChatRequest(input: ChatRequestInput & { messages: unknown }): ChatRequestPayload {
  const normalizedMessages: ChatRequestPayload["messages"] = [];
  if (Array.isArray(input.messages)) {
    for (const entry of input.messages) {
      const message = normalizeMessage(entry);
      if (message) {
        normalizedMessages.push(message);
      }
    }
  }
  if (normalizedMessages.length === 0) {
    throw new Error("chat request requires at least one message");
  }

  const payload: ChatRequestPayload = {
    messages: normalizedMessages,
  };

  const model = normalizeString(input.model);
  if (model) payload.model = model;
  if (input.context && typeof input.context === "object" && !Array.isArray(input.context)) {
    payload.context = input.context as Record<string, unknown>;
  }
  if (typeof input.stream === "boolean") payload.stream = input.stream;
  const url = normalizeString(input.url);
  if (url) payload.url = url;
  const textContext = normalizeString(input.textContext);
  if (textContext) payload.text_context = textContext;
  const imageContext = normalizeString(input.imageContext);
  if (imageContext) payload.image_context = imageContext;
  const clientTz = normalizeString(input.clientTimezone);
  if (clientTz) payload.client_timezone = clientTz;
  const serverTime = normalizeString(input.serverTime);
  if (serverTime) payload.server_time = serverTime;
  const serverTimezone = normalizeString(input.serverTimezone);
  if (serverTimezone) payload.server_timezone = serverTimezone;
  const serverUtc = normalizeString(input.serverUtc);
  if (serverUtc) payload.server_time_utc = serverUtc;
  const requestId = normalizeString(input.requestId);
  if (requestId) payload.request_id = requestId;
  const chatId = normalizeString(input.chatId);
  if (chatId) payload.chat_id = chatId;

  return payload;
}

function parseTools(value: unknown): AutopilotToolDirective[] | null {
  if (!Array.isArray(value)) return null;
  const tools: AutopilotToolDirective[] = [];
  for (const entry of value) {
    if (!entry || typeof entry !== "object") continue;
    const record = entry as Record<string, unknown>;
    const label = normalizeString(record.label);
    const endpoint = normalizeString(record.endpoint);
    if (!label || !endpoint) continue;
    const tool: AutopilotToolDirective = { label, endpoint };
    const method = normalizeString(record.method)?.toUpperCase();
    if (method === "GET" || method === "POST") {
      tool.method = method;
    }
    if (record.payload && typeof record.payload === "object") {
      tool.payload = record.payload as Record<string, unknown>;
    }
    const description = normalizeString(record.description);
    if (description) {
      tool.description = description;
    }
    tools.push(tool);
  }
  return tools.length > 0 ? tools : null;
}

function parseDirectivePayload(value: unknown): DirectivePayload | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  try {
    return fromDirective(value);
  } catch {
    return null;
  }
}

function parseDirectiveSteps(value: unknown): Verb[] | null {
  if (!value) {
    return null;
  }
  const wrapper = typeof value === "object" && value !== null ? value : { steps: value };
  const directive = parseDirectivePayload(wrapper);
  if (!directive) {
    return null;
  }
  return directive.steps.length > 0 ? (directive.steps as Verb[]) : null;
}

export function parseAutopilotDirective(value: unknown): AutopilotDirective | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const rawMode = (normalizeString(record.mode) ?? "browser").toLowerCase();
  const allowedModes: AutopilotDirective["mode"][] = ["browser", "tools", "multi"];
  if (!allowedModes.includes(rawMode as AutopilotDirective["mode"])) {
    return null;
  }
  const directive: AutopilotDirective = { mode: rawMode as AutopilotDirective["mode"] };
  const query = normalizeString(record.query);
  if (query) directive.query = query;
  const reason = normalizeString(record.reason);
  if (reason) directive.reason = reason;
  const tools = parseTools(record.tools);
  if (tools) directive.tools = tools;
  const nestedDirective = parseDirectivePayload(record.directive);
  if (nestedDirective) {
    directive.directive = nestedDirective;
    if (nestedDirective.steps.length > 0) {
      directive.steps = nestedDirective.steps as Verb[];
    }
  }
  const topLevelSteps = parseDirectiveSteps(record.steps);
  if (topLevelSteps && topLevelSteps.length > 0) {
    directive.steps = topLevelSteps;
  }

  const hasMeaningfulSignal = Boolean(
    directive.query ||
      directive.reason ||
      (directive.tools && directive.tools.length > 0) ||
      (directive.steps && directive.steps.length > 0) ||
      directive.directive,
  );

  if (!hasMeaningfulSignal) {
    return null;
  }

  return directive;
}

export function fromChatResponse(raw: unknown): ChatResponsePayload {
  const data = (raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {}) ?? {};
  const reasoning = normalizeString(data.reasoning) ?? "";
  const answer = normalizeString(data.answer) ?? "";
  const message = normalizeString(data.message) ?? "";
  const citations = Array.isArray(data.citations)
    ? data.citations
        .map((entry) => (typeof entry === "string" ? entry.trim() : ""))
        .filter((entry) => entry.length > 0)
    : [];
  const model = normalizeString(data.model) ?? null;
  const traceId = normalizeString(data.trace_id ?? data.traceId) ?? null;
  const autopilot = parseAutopilotDirective(data.autopilot);
  return {
    reasoning,
    answer,
    message,
    citations,
    model,
    trace_id: traceId,
    autopilot,
  };
}
