import { useCallback, useEffect, useRef, useState } from "react";
import type { LlmHealth } from "@/lib/types";

interface BackendHealthOptions {
  /** How often to refresh the health check (ms). Defaults to 15s. */
  intervalMs?: number;
  /** If false, skip the initial check until refresh is called manually. */
  immediate?: boolean;
}

interface BackendHealthState {
  healthy: boolean;
  loading: boolean;
  error: string | null;
  warning: string | null;
  data: LlmHealth | null;
  reachable: boolean | null;
  lastChecked: number | null;
  refresh: () => Promise<void>;
}

const HEALTH_ENDPOINT = "/api/llm/health";
const OFFLINE_MESSAGE = "Backend offline (5050)";

export function useBackendHealth(options: BackendHealthOptions = {}): BackendHealthState {
  const { intervalMs = 15_000, immediate = true } = options;
  const [data, setData] = useState<LlmHealth | null>(null);
  const [healthy, setHealthy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [reachable, setReachable] = useState<boolean | null>(null);
  const [lastChecked, setLastChecked] = useState<number | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
      controllerRef.current?.abort();
    };
  }, []);

  const runCheck = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    if (mountedRef.current) {
      setLoading(true);
    }
    try {
      const response = await fetch(HEALTH_ENDPOINT, { signal: controller.signal });
      if (!response.ok) {
        throw new Error(`Health check failed (${response.status})`);
      }
      const payload = (await response.json()) as LlmHealth;
      if (!mountedRef.current || controller.signal.aborted) {
        return;
      }
      const reachableFlag =
        typeof payload.reachable === "boolean" ? payload.reachable : null;
      setData(payload);
      setHealthy(true);
      setReachable(reachableFlag);
      if (reachableFlag === false) {
        const host = payload.host ? ` (${payload.host})` : "";
        setWarning(
          `Local LLM unavailable${host}. Start Ollama or install a chat model to enable crawl and chat features.`,
        );
      } else {
        setWarning(null);
      }
      setError(null);
      setLastChecked(Date.now());
    } catch (err) {
      if (!mountedRef.current || controller.signal.aborted) {
        return;
      }
      console.warn("Backend health check failed", err);
      setData(null);
      setReachable(null);
      setHealthy(false);
      setError(OFFLINE_MESSAGE);
      setWarning(null);
      setLastChecked(Date.now());
    } finally {
      if (mountedRef.current && !controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (immediate) {
      void runCheck();
    } else {
      setLoading(false);
    }
  }, [runCheck, immediate]);

  useEffect(() => {
    if (!intervalMs || intervalMs <= 0) {
      return;
    }
    if (typeof window === "undefined") {
      return;
    }
    const id = window.setInterval(() => {
      void runCheck();
    }, intervalMs);
    return () => {
      window.clearInterval(id);
    };
  }, [runCheck, intervalMs]);

  const refresh = useCallback(async () => {
    await runCheck();
  }, [runCheck]);

  return {
    healthy,
    loading,
    error,
    data,
    warning,
    reachable,
    lastChecked,
    refresh,
  };
}
