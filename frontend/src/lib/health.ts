"use client";

import { useEffect } from "react";
import { useShallow } from "zustand/react/shallow";

import { useAppStore, type HealthSnapshot } from "@/state/useAppStore";

const HEALTH_ENDPOINT = process.env.NEXT_PUBLIC_LLM_HEALTH_URL ?? "/api/llm/health";
const MIN_POLL_INTERVAL_MS = 1_500;
let lastSnapshot: HealthSnapshot | null = null;
let lastFetchedAt = 0;
let inflight: Promise<HealthSnapshot> | null = null;

async function requestHealth(url: string): Promise<HealthSnapshot> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 4_000);
  try {
    const response = await fetch(url, { signal: controller.signal, cache: "no-store" });
    const checkedAt = Date.now();
    if (!response.ok) {
      return { status: "error", checkedAt };
    }
    const payload = await response.json().catch(() => null);
    const healthy = Boolean(payload?.healthy);
    return {
      status: healthy ? "ok" : "degraded",
      raw: payload ?? null,
      checkedAt,
    };
  } catch {
    return { status: "error", checkedAt: Date.now() };
  } finally {
    clearTimeout(timeout);
  }
}

async function pollHealth(): Promise<HealthSnapshot> {
  const now = Date.now();
  if (inflight) {
    return inflight;
  }
  if (lastSnapshot && now - lastFetchedAt < MIN_POLL_INTERVAL_MS) {
    return lastSnapshot;
  }

  inflight = requestHealth(HEALTH_ENDPOINT)
    .catch((): HealthSnapshot => ({ status: "error", checkedAt: Date.now() }))
    .then((snapshot) => {
      lastSnapshot = snapshot;
      lastFetchedAt = Date.now();
      inflight = null;
      return snapshot;
    });

  return inflight;
}

export function useHealth(intervalMs = 5_000): HealthSnapshot | null {
  const { health, setHealth } = useAppStore(
    useShallow((state) => ({
      health: state.health,
      setHealth: state.setHealth,
    })),
  );

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const scheduleNext = () => {
      const delay = Math.max(intervalMs, MIN_POLL_INTERVAL_MS);
      timer = window.setTimeout(async () => {
        try {
          const snapshot = await pollHealth();
          if (!cancelled) {
            setHealth(snapshot);
          }
        } finally {
          if (!cancelled) {
            scheduleNext();
          }
        }
      }, delay);
    };

    const prime = async () => {
      const snapshot = await pollHealth();
      if (!cancelled) {
        setHealth(snapshot);
        scheduleNext();
      }
    };

    void prime();

    return () => {
      cancelled = true;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [intervalMs, setHealth]);

  return health;
}
