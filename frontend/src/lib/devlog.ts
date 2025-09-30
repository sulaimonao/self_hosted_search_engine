const isDev = process.env.NODE_ENV !== "production";

let seq = 0;

export function devlog(entry: Record<string, unknown>) {
  if (!isDev) return;
  const payload = {
    ts: new Date().toISOString(),
    seq: ++seq,
    ...entry,
  };

  let serialized: string | null = null;
  try {
    serialized = JSON.stringify(payload);
    console.debug(serialized);
  } catch (error) {
    console.debug("{\"evt\":\"devlog.fallback\",\"error\":\"serialization_failed\"}");
  }

  if (typeof window === "undefined") return;

  try {
    const body =
      serialized ??
      JSON.stringify(payload, (_key, value) => {
        if (value instanceof Error) {
          return { name: value.name, message: value.message };
        }
        return value;
      });
    void fetch("/api/dev/log", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body,
      keepalive: true,
      credentials: "same-origin",
    }).catch(() => undefined);
  } catch (error) {
    console.debug("{\"evt\":\"devlog.fallback\",\"error\":\"forward_failed\"}");
  }
}
