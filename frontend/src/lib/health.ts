"use client";

import useSWR from "swr";

const HEALTH_ENDPOINT = process.env.NEXT_PUBLIC_LLM_HEALTH_URL ?? "/api/llm/health";

async function fetcher(url: string) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 4000);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) {
      return { status: "error" as const };
    }
    const data = await response.json();
    return { status: data?.healthy ? "ok" : "degraded", raw: data };
  } catch {
    return { status: "error" as const };
  } finally {
    clearTimeout(timeout);
  }
}

export function useHealth() {
  return useSWR(HEALTH_ENDPOINT, fetcher, {
    refreshInterval: 10000,
    revalidateOnFocus: false,
  });
}
