const isDev = process.env.NODE_ENV !== "production";

let seq = 0;

export function devlog(entry: Record<string, unknown>) {
  if (!isDev) return;
  const payload = {
    ts: new Date().toISOString(),
    seq: ++seq,
    ...entry,
  };
  try {
    console.debug(JSON.stringify(payload));
  } catch (error) {
    console.debug("{\"evt\":\"devlog.fallback\",\"error\":\"serialization_failed\"}");
  }
}
