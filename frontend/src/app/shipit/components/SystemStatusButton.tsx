"use client";

import useSWR from "swr";

import { fetchLlmHealth } from "@/app/shipit/lib/api";
import { useApp } from "@/app/shipit/store/useApp";

export default function SystemStatusButton(): JSX.Element {
  const { features } = useApp();
  const { data } = useSWR("shipit:llm-health", () => fetchLlmHealth(), {
    refreshInterval: 15_000,
  });
  const reachable = data?.reachable ?? false;
  const statusLabel = reachable ? "LLM OK" : features.llm === "unavailable" ? "LLM Offline" : "LLM…";
  const modelCount = typeof data?.model_count === "number" ? data.model_count : 0;
  const host = data?.host ?? "local";
  return (
    <div
      className={`px-3 py-1 rounded-2xl border text-sm ${reachable ? "border-green-500 text-green-600" : "border-amber-500 text-amber-600"}`}
    >
      {statusLabel} • {modelCount} models • {host}
    </div>
  );
}
