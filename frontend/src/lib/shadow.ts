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


export type ShadowCrawlReason = 'did-navigate' | 'new-window' | 'manual';

let crawlTimer: ReturnType<typeof setTimeout> | null = null;
let lastCrawlKey = '';

export function requestShadowCrawl(
  tabId: number | null | undefined,
  url: string,
  reason: ShadowCrawlReason = 'manual',
) {
  const normalizedUrl = typeof url === 'string' ? url.trim() : '';
  if (!normalizedUrl) {
    return;
  }
  const normalizedReason = reason ?? 'manual';
  const key = `${tabId ?? 'main'}|${normalizedUrl}|${normalizedReason}`;
  if (key === lastCrawlKey) {
    return;
  }
  lastCrawlKey = key;
  if (crawlTimer) {
    clearTimeout(crawlTimer);
  }
  crawlTimer = setTimeout(() => {
    fetch('/api/shadow/crawl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tabId, url: normalizedUrl, reason: normalizedReason }),
    }).catch((error) => {
      console.warn('shadow crawl request failed', error);
    });
  }, 600);
}
