"use client";

import type { CopilotEvent } from "@/lib/events";
import { parseEvent } from "@/lib/events";

type Closeable = { close: () => void };

const DISCOVERY_STREAM_ENDPOINT =
  process.env.NEXT_PUBLIC_DISCOVERY_STREAM_URL ?? "http://127.0.0.1:5050/api/discovery/stream_events";
const DISCOVERY_FALLBACK_ENDPOINT =
  process.env.NEXT_PUBLIC_DISCOVERY_EVENTS_URL ?? "http://127.0.0.1:5050/api/discovery/events";

export function connectEvents(onEvent: (event: CopilotEvent) => void): Closeable | undefined {
  if (typeof window === "undefined" || typeof EventSource === "undefined") {
    return undefined;
  }

  const endpoints = [DISCOVERY_STREAM_ENDPOINT, DISCOVERY_FALLBACK_ENDPOINT];
  let source: EventSource | null = null;
  let attempt = 0;
  let closed = false;
  let backoffMs = 1000;

  const attach = (stream: EventSource) => {
    stream.onmessage = (event) => {
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
    stream.onerror = () => {
      stream.close();
      if (closed) {
        return;
      }
      if (attempt < endpoints.length) {
        connectNext();
      } else {
        attempt = 0;
        // exponential backoff for reconnect attempts (1s,2s,4s,.. capped at 30s)
        setTimeout(() => {
          if (!closed) {
            backoffMs = Math.min(30000, backoffMs * 2);
            connectNext();
          }
        }, backoffMs);
      }
    };
  };

  const connectNext = () => {
    if (closed) {
      return;
    }
    if (attempt >= endpoints.length) {
      attempt = endpoints.length;
      return;
    }
    const url = endpoints[attempt++];
    try {
      const stream = new EventSource(url);
      source = stream;
      attach(stream);
    } catch {
      if (attempt < endpoints.length) {
        connectNext();
      } else {
        attempt = 0;
        setTimeout(() => {
          if (!closed) {
            backoffMs = Math.min(30000, backoffMs * 2);
            connectNext();
          }
        }, backoffMs);
      }
    }
  };

  connectNext();

  return {
    close: () => {
      closed = true;
      source?.close();
    },
  };
}
