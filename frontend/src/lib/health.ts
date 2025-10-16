"use client";

import useSWR from "swr";

const HEALTH_ENDPOINT = process.env.NEXT_PUBLIC_LLM_HEALTH_URL ?? "/api/llm/health";

type HealthStatus = { status: "ok" | "degraded" | "error"; raw?: unknown };

const MIN_REFRESH_INTERVAL_MS = 500;
let lastSnapshot: HealthStatus | null = null;
let lastResolvedAt = 0;
let inflight: Promise<HealthStatus> | null = null;

async function requestHealth(url: string): Promise<HealthStatus> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 4000);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) {
      return { status: "error" };
    }
    const data = await response.json();
    return { status: data?.healthy ? "ok" : "degraded", raw: data };
  } catch {
    return { status: "error" };
  } finally {
    clearTimeout(timeout);
  }
}

async function throttledFetcher(url: string): Promise<HealthStatus> {
  const now = Date.now();
  if (inflight) {
    return inflight;
  }
  if (lastSnapshot && now - lastResolvedAt < MIN_REFRESH_INTERVAL_MS) {
    return lastSnapshot;
  }

  inflight = requestHealth(url)
    .catch(() => ({ status: "error" as const }))
    .then((snapshot) => {
      lastSnapshot = snapshot;
      lastResolvedAt = Date.now();
      inflight = null;
      return snapshot;
    });

  return inflight;
}

export function useHealth() {
  return useSWR(HEALTH_ENDPOINT, throttledFetcher, {
    refreshInterval: 10000,
    revalidateOnFocus: false,
  });
}
