"use client";

import useSWR from "swr";

import { api } from "@/app/shipit/lib/api";

type HealthResponse = {
  ok: boolean;
  data?: {
    reachable: boolean;
  };
};

type ModelDiagResponse = {
  ok: boolean;
  data?: {
    in_use: "primary" | "fallback" | "none";
  };
};

export default function SystemStatusButton(): JSX.Element {
  const { data: llm } = useSWR<HealthResponse>(
    "/api/llm/health",
    api,
    { refreshInterval: 5_000 }
  );
  const { data: diag } = useSWR<ModelDiagResponse>(
    "/api/diag/models",
    api,
    { refreshInterval: 10_000 }
  );
  const reachable = llm?.data?.reachable ?? false;
  const inUse = diag?.data?.in_use ?? "none";
  return (
    <div className="px-3 py-1 rounded-2xl border text-sm">
      {reachable ? "LLM OK" : "LLM Down"} • {inUse}
    </div>
  );
}
