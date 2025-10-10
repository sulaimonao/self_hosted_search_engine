"use client";

import type { CopilotEvent } from "@/lib/events";
import { parseEvent } from "@/lib/events";

type Closeable = { close: () => void };

const EVENT_ENDPOINT = process.env.NEXT_PUBLIC_EVENTS_URL ?? "ws://127.0.0.1:5050/api/events";
const SSE_ENDPOINT = process.env.NEXT_PUBLIC_EVENTS_SSE_URL ?? "http://127.0.0.1:5050/api/events/sse";

function isWebSocketSupported() {
  return typeof window !== "undefined" && "WebSocket" in window;
}

export function connectEvents(onEvent: (event: CopilotEvent) => void): Closeable | undefined {
  if (typeof window === "undefined") {
    return undefined;
  }

  if (isWebSocketSupported()) {
    const socket = new WebSocket(EVENT_ENDPOINT);
    socket.onmessage = (message) => {
      try {
        const parsed = parseEvent(JSON.parse(message.data));
        if (parsed) {
          onEvent(parsed);
        }
      } catch {
        // ignore malformed payloads
      }
    };
    socket.onclose = () => {
      setTimeout(() => connectEvents(onEvent), 1000);
    };
    socket.onerror = () => {
      socket.close();
    };
    return socket;
  }

  if (typeof EventSource !== "undefined") {
    const source = new EventSource(SSE_ENDPOINT);
    source.onmessage = (event) => {
      try {
        const payload = event.data ? JSON.parse(event.data) : null;
        const parsed = parseEvent(payload);
        if (parsed) {
          onEvent(parsed);
        }
      } catch {
        // swallow malformed data
      }
    };
    source.onerror = () => {
      source.close();
      setTimeout(() => connectEvents(onEvent), 1000);
    };
    return { close: () => source.close() };
  }

  return undefined;
}
