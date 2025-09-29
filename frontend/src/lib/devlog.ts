const isDev = process.env.NODE_ENV === "development";

type LogPayload = Record<string, unknown> | undefined;

export function devlog(event: string, payload?: LogPayload) {
  if (!isDev) return;
  const parts: unknown[] = ["[UI]", event];
  if (payload && Object.keys(payload).length > 0) {
    parts.push(payload);
  }
  console.debug(...parts);
}
