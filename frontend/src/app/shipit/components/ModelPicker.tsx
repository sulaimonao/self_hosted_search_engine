"use client";

import useSWR from "swr";

import { api } from "@/app/shipit/lib/api";

type HealthResponse = {
  ok: boolean;
  data?: {
    model_count: number;
    reachable: boolean;
  };
};

export default function ModelPicker(): JSX.Element {
  const { data } = useSWR<HealthResponse>("/api/llm/health", api);
  const count = data?.data?.model_count ?? 0;
  const reachable = data?.data?.reachable ?? false;
  return (
    <div className="text-sm px-3 py-1 rounded-2xl border">
      {count} models • {reachable ? "OK" : "Offline"}
    </div>
  );
}
