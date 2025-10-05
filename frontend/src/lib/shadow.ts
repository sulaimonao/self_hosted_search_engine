export interface RecordVisitOptions {
  url: string;
  referer?: string;
  durationMs?: number;
  enqueue?: boolean;
}

export async function recordVisit({ url, referer, durationMs, enqueue }: RecordVisitOptions) {
  if (typeof url !== "string" || !url.trim()) {
    throw new Error("url required");
  }
  const payload: Record<string, unknown> = { url };
  if (referer) {
    payload.referer = referer;
  }
  if (typeof durationMs === "number" && Number.isFinite(durationMs)) {
    payload.dur_ms = Math.max(0, Math.round(durationMs));
  }
  if (enqueue) {
    payload.enqueue = true;
  }
  const response = await fetch("/api/visits", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || "failed to record visit");
  }
  return response.json();
}
