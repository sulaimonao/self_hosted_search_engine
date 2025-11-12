"use client";

import { fromChatResponse } from "@/lib/io/chat";
import type { ChatStreamEvent } from "@/lib/types";

type StreamEnvelope = {
  event?: string;
  data?: unknown;
};

function coerceString(value: unknown): string | null {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed || null;
  }
  return null;
}

function coerceStringArray(value: unknown): string[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const entries = value
    .map((entry) => (typeof entry === "string" ? entry.trim() : ""))
    .filter((entry) => entry.length > 0);
  return entries.length > 0 ? entries : null;
}

export function normalizeChatStreamChunk(payload: unknown): ChatStreamEvent | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const candidate = payload as StreamEnvelope & ChatStreamEvent;
  if (typeof (candidate as ChatStreamEvent).type === "string") {
    return candidate as ChatStreamEvent;
  }

  const eventName = typeof candidate.event === "string" ? candidate.event : null;
  if (!eventName) {
    return null;
  }
  const data = candidate.data;
  if (!data || typeof data !== "object") {
    return null;
  }
  const record = data as Record<string, unknown>;

  switch (eventName) {
    case "chat.metadata": {
      const attemptRaw = record["attempt"];
      const numericAttempt =
        typeof attemptRaw === "number"
          ? attemptRaw
          : Number.parseInt(String(attemptRaw ?? ""), 10);
      const attempt = Number.isFinite(numericAttempt) ? Number(numericAttempt) : 1;
      return {
        type: "metadata",
        attempt: attempt > 0 ? attempt : 1,
        model: coerceString(record["model"]),
        trace_id: coerceString(record["trace_id"]),
      };
    }
    case "chat.delta": {
      const content = coerceString(record["content"]) ?? "";
      const reasoning = coerceString(record["reasoning"]) ?? undefined;
      const citations = coerceStringArray(record["citations"]) ?? undefined;
      return {
        type: "delta",
        delta: content,
        reasoning,
        citations,
      };
    }
    case "chat.done": {
      try {
        const normalized = fromChatResponse(record);
        return { type: "complete", payload: normalized };
      } catch (error) {
        console.warn("[chat] failed to normalize chat.done payload", error);
        return null;
      }
    }
    case "chat.error": {
      const errorText = coerceString(record["error"]) ?? "stream_error";
      const hint = coerceString(record["hint"]) ?? undefined;
      const trace = coerceString(record["trace_id"]) ?? null;
      return {
        type: "error",
        error: errorText,
        hint,
        trace_id: trace,
      };
    }
    default:
      return null;
  }
}
