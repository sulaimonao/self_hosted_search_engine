import { ChatResponsePayload, type ChatStreamEvent } from "@/lib/types";
import { fromChatResponse, parseAutopilotDirective, toChatRequest } from "@/lib/io/chat";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");

function resolveApi(path: string): string {
  if (!API_BASE) return path;
  return `${API_BASE}${path}`;
}

const JSON_HEADERS = {
  "Content-Type": "application/json",
} as const;

export type ChatPayloadMessage = {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  images?: string[];
};

export interface ChatSendRequest {
  messages: ChatPayloadMessage[];
  model?: string | null;
  stream?: boolean;
  url?: string | null;
  textContext?: string | null;
  imageContext?: string | null;
  clientTimezone?: string | null;
  serverTime?: string | null;
  serverTimezone?: string | null;
  serverUtc?: string | null;
  signal?: AbortSignal;
  onEvent?: (event: ChatStreamEvent) => void;
}

export interface ChatSendResult {
  payload: ChatResponsePayload;
  traceId: string | null;
  model: string | null;
}

export class ChatRequestError extends Error {
  status: number;
  traceId: string | null;
  code?: string;
  hint?: string;
  tried?: string[];

  constructor(
    message: string,
    options: {
      status: number;
      traceId: string | null;
      code?: string;
      hint?: string;
      tried?: string[];
    },
  ) {
    super(message);
    this.name = "ChatRequestError";
    this.status = options.status;
    this.traceId = options.traceId;
    this.code = options.code;
    this.hint = options.hint;
    this.tried = options.tried;
  }
}

interface ChatStreamConsumeOptions {
  onEvent?: (event: ChatStreamEvent) => void;
  fallbackTraceId: string | null;
  fallbackModel: string | null;
}

type ChatErrorEvent = Extract<ChatStreamEvent, { type: "error" }>;

function isChatErrorEvent(event: ChatStreamEvent): event is ChatErrorEvent {
  return event.type === "error";
}

async function consumeChatStream(
  response: Response,
  options: ChatStreamConsumeOptions,
): Promise<ChatSendResult> {
  const reader = response.body?.getReader();
  if (!reader) {
    throw new ChatRequestError("Streaming response is not supported in this environment", {
      status: response.status ?? 500,
      traceId: options.fallbackTraceId,
    });
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let metadata: ChatStreamEvent | null = null;
  let finalPayload: ChatResponsePayload | null = null;

  const getMetadataTraceId = (): string | null => {
    if (!metadata) {
      return null;
    }
    if (metadata.type === "metadata") {
      return metadata.trace_id ?? null;
    }
    if (isChatErrorEvent(metadata)) {
      return metadata.trace_id ?? null;
    }
    return null;
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      buffer += decoder.decode(new Uint8Array(), { stream: false });
    } else if (value) {
      buffer += decoder.decode(value, { stream: true });
    }

    let newlineIndex = buffer.indexOf("\n");
    while (newlineIndex !== -1) {
      const chunk = buffer.slice(0, newlineIndex).trim();
      buffer = buffer.slice(newlineIndex + 1);
      if (chunk) {
        try {
          const parsed = JSON.parse(chunk) as ChatStreamEvent;
          if (parsed.type === "metadata") {
            metadata = parsed;
            options.onEvent?.(parsed);
          } else if (parsed.type === "complete") {
            const sanitized = fromChatResponse(parsed.payload);
            finalPayload = sanitized;
            options.onEvent?.({ ...parsed, payload: sanitized });
          } else if (parsed.type === "delta") {
            const autopilot = parseAutopilotDirective((parsed as { autopilot?: unknown }).autopilot);
            options.onEvent?.({ ...parsed, autopilot });
          } else if (isChatErrorEvent(parsed)) {
            const trace = parsed.trace_id ?? getMetadataTraceId() ?? options.fallbackTraceId;
            throw new ChatRequestError(parsed.error || "chat stream error", {
              status: response.status ?? 500,
              traceId: trace,
              hint: parsed.hint ?? undefined,
            });
          } else {
            options.onEvent?.(parsed);
          }
        } catch (error) {
          console.warn("Skipping malformed stream chunk", error);
        }
      }
      newlineIndex = buffer.indexOf("\n");
    }

    if (done) {
      break;
    }
  }

  const trimmed = buffer.trim();
  if (trimmed) {
    try {
      const parsed = JSON.parse(trimmed) as ChatStreamEvent;
      if (parsed.type === "metadata") {
        metadata = parsed;
        options.onEvent?.(parsed);
      } else if (parsed.type === "complete") {
        const sanitized = fromChatResponse(parsed.payload);
        finalPayload = sanitized;
        options.onEvent?.({ ...parsed, payload: sanitized });
      } else if (parsed.type === "delta") {
        const autopilot = parseAutopilotDirective((parsed as { autopilot?: unknown }).autopilot);
        options.onEvent?.({ ...parsed, autopilot });
      } else if (isChatErrorEvent(parsed)) {
        const trace = parsed.trace_id ?? metadata?.trace_id ?? options.fallbackTraceId;
        throw new ChatRequestError(parsed.error || "chat stream error", {
          status: response.status ?? 500,
          traceId: trace,
          hint: parsed.hint ?? undefined,
        });
      } else {
        options.onEvent?.(parsed);
      }
    } catch (error) {
      console.warn("Ignoring trailing stream chunk", error);
    }
  }

  if (!finalPayload) {
    throw new ChatRequestError("Chat stream ended without completion", {
      status: response.status ?? 500,
      traceId: metadata?.type === "metadata" ? metadata.trace_id ?? null : options.fallbackTraceId,
    });
  }

  const metadataModel = metadata && metadata.type === "metadata" ? metadata.model : null;
  const metadataTraceId = metadata?.type === "metadata" ? metadata.trace_id ?? null : options.fallbackTraceId;

  return {
    payload: finalPayload,
    traceId: finalPayload.trace_id ?? metadataTraceId,
    model: finalPayload.model ?? metadataModel ?? options.fallbackModel,
  };
}

function isAbortError(error: unknown): boolean {
  if (!error) return false;
  if (typeof DOMException !== "undefined" && error instanceof DOMException) {
    return error.name === "AbortError";
  }
  return error instanceof Error && error.name === "AbortError";
}

export class ChatClient {
  async send(request: ChatSendRequest): Promise<ChatSendResult> {
    const streamPreferred = request.stream !== false;
    try {
      return await this.#sendOnce(request, streamPreferred);
    } catch (error) {
      if (!streamPreferred || isAbortError(error)) {
        throw error;
      }
      return this.#sendOnce(request, false);
    }
  }

  async #sendOnce(request: ChatSendRequest, stream: boolean): Promise<ChatSendResult> {
    if (!request.messages || request.messages.length === 0) {
      throw new ChatRequestError("messages must contain at least one entry", {
        status: 400,
        traceId: null,
      });
    }

    const headers: Record<string, string> = {
      ...JSON_HEADERS,
      Accept: stream ? "application/x-ndjson" : "application/json",
    };

    const payload = toChatRequest({
      model: request.model ?? null,
      stream,
      url: request.url ?? null,
      textContext: request.textContext ?? null,
      imageContext: request.imageContext ?? null,
      clientTimezone: request.clientTimezone ?? null,
      serverTime: request.serverTime ?? null,
      serverTimezone: request.serverTimezone ?? null,
      serverUtc: request.serverUtc ?? null,
      messages: request.messages,
    });

    const response = await fetch(resolveApi("/api/chat"), {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: request.signal,
    });

    const traceIdHeader = response.headers.get("X-Request-Id");
    const servedModel = response.headers.get("X-LLM-Model") ?? (request.model ?? null);
    const contentType = response.headers.get("Content-Type")?.toLowerCase() ?? "";

    if (stream && contentType.includes("application/x-ndjson") && response.body) {
      return consumeChatStream(response, {
        onEvent: request.onEvent,
        fallbackTraceId: traceIdHeader,
        fallbackModel: servedModel,
      });
    }

    if (!response.ok) {
      let fallbackText = "";
      try {
        fallbackText = await response.clone().text();
      } catch {
        fallbackText = "";
      }

      let payloadJson: Record<string, unknown> | null = null;
      if (fallbackText) {
        try {
          payloadJson = JSON.parse(fallbackText) as Record<string, unknown>;
        } catch {
          payloadJson = null;
        }
      }

      let message = fallbackText || `Chat request failed (${response.status})`;
      let code: string | undefined;
      let hint: string | undefined;
      let tried: string[] | undefined;
      if (payloadJson) {
        if (typeof payloadJson.error === "string" && payloadJson.error.trim()) {
          code = payloadJson.error.trim();
        }
        if (typeof payloadJson.hint === "string" && payloadJson.hint.trim()) {
          hint = payloadJson.hint.trim();
          message = hint;
        }
        if (Array.isArray(payloadJson.tried)) {
          tried = payloadJson.tried.filter((item): item is string => typeof item === "string");
        }
        const detailValue = payloadJson["detail"];
        const messageValue = payloadJson["message"];
        const detail = typeof detailValue === "string" ? detailValue : null;
        if (detail && detail.trim()) {
          message = detail.trim();
        } else if (!hint && typeof messageValue === "string" && messageValue.trim()) {
          message = messageValue.trim();
        } else if (!hint && typeof payloadJson.error === "string" && payloadJson.error.trim()) {
          message = payloadJson.error.trim();
        }
      }

      throw new ChatRequestError(message, {
        status: response.status,
        traceId: traceIdHeader,
        code,
        hint,
        tried,
      });
    }

    if (contentType.includes("application/json")) {
      const rawPayload = await response.json();
      const data = fromChatResponse(rawPayload);
      return {
        payload: data,
        traceId: data.trace_id ?? traceIdHeader,
        model: data.model ?? servedModel,
      } satisfies ChatSendResult;
    }

    // Fallback: treat body as NDJSON even if stream disabled.
    return consumeChatStream(response, {
      onEvent: request.onEvent,
      fallbackTraceId: traceIdHeader,
      fallbackModel: servedModel,
    });
  }
}

export const chatClient = new ChatClient();
