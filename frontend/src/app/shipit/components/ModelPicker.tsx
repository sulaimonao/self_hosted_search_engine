"use client";

import { useEffect, useMemo } from "react";
import { safeLocalStorage } from "@/utils/isomorphicStorage";
import useSWR from "swr";

import { fetchLlmHealth, fetchLlmModels } from "@/app/shipit/lib/api";
import { useApp } from "@/app/shipit/store/useApp";

const MODEL_STORAGE_KEY = "shipit:model";

export default function ModelPicker(): JSX.Element {
  const {
    selectedModel,
    availableModels,
    setSelectedModel,
    setAvailableModels,
    setFeature,
  } = useApp();
  const {
    data: health,
    error: healthError,
  } = useSWR("shipit:llm-health", () => fetchLlmHealth());
  const { data: models, error: modelsError } = useSWR("shipit:llm-models", () => fetchLlmModels());

  useEffect(() => {
    const stored = safeLocalStorage.get(MODEL_STORAGE_KEY);
    if (stored && stored.trim()) {
      setSelectedModel(stored.trim());
    }
  }, [setSelectedModel]);

  useEffect(() => {
    if (!models) {
      return;
    }
    const chatModels = Array.isArray(models.chat_models) ? models.chat_models : [];
    setAvailableModels(chatModels);
    if (chatModels.length > 0) {
      if (!selectedModel || !chatModels.includes(selectedModel)) {
        const configured = models.configured?.primary;
        const fallback = configured && chatModels.includes(configured) ? configured : chatModels[0];
        setSelectedModel(fallback);
      }
    }
  }, [models, selectedModel, setAvailableModels, setSelectedModel]);

  useEffect(() => {
    if (health) {
      setFeature("llm", health.reachable ? "available" : "unavailable");
      return;
    }
    if (healthError || modelsError) {
      setFeature("llm", "unavailable");
    }
  }, [health, healthError, modelsError, setFeature]);

  useEffect(() => {
    if (selectedModel) {
      safeLocalStorage.set(MODEL_STORAGE_KEY, selectedModel);
    } else {
      safeLocalStorage.remove(MODEL_STORAGE_KEY);
    }
  }, [selectedModel]);

  const count = useMemo(() => availableModels.length, [availableModels]);
  const reachable = Boolean(health?.reachable);
  const statusLabel = reachable ? "LLM OK" : "LLM Offline";

  return (
    <div className="flex items-center gap-3 text-sm">
      <label className="flex items-center gap-2">
        <span className="text-xs uppercase tracking-wide text-muted-foreground">Model</span>
        <select
          className="rounded-2xl border px-3 py-1 text-sm"
          value={selectedModel ?? ""}
          onChange={(event) => setSelectedModel(event.target.value || null)}
        >
          <option value="" disabled>
            {availableModels.length === 0 ? "Loading…" : "Select model"}
          </option>
          {availableModels.map((model) => (
            <option key={model} value={model}>
              {model}
            </option>
          ))}
        </select>
      </label>
      <div
        className={`rounded-2xl border px-3 py-1 ${reachable ? "border-green-500 text-green-600" : "border-red-500 text-red-600"}`}
      >
        {statusLabel} • {count}
      </div>
    </div>
  );
}
