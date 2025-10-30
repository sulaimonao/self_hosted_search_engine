"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import ModelPicker from "./ModelPicker";
import SystemStatusButton from "./SystemStatusButton";
import { useApp } from "@/app/shipit/store/useApp";
import { fetchShadowGlobalPolicy, updateShadowGlobalPolicy } from "@/lib/api";
import { Switch } from "@/components/ui/switch";

export default function HeaderBar(): JSX.Element {
  const { mode, shadow, setMode, setShadow, autopilot, setAutopilot, features } = useApp();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchShadowGlobalPolicy()
      .then((policy) => setShadow(Boolean(policy.enabled)))
      .catch((error) => console.warn("Unable to load shadow policy", error));
  }, [setShadow]);

  const handleToggle = async (next: boolean) => {
    setShadow(next);
    setBusy(true);
    try {
      await updateShadowGlobalPolicy({ enabled: next });
    } catch (error) {
      console.warn("Failed to update global shadow policy", error);
      setShadow(!next);
    } finally {
      setBusy(false);
    }
  };

  const autopilotDisabled = features.llm === "unavailable";

  return (
    <div className="w-full flex items-center justify-between p-4 border-b">
      <div className="flex items-center gap-3">
        <button
          className={`px-3 py-1 rounded-2xl ${mode === "search" ? "border" : ""}`}
          onClick={() => setMode("search")}
          type="button"
        >
          Search
        </button>
        <button
          className={`px-3 py-1 rounded-2xl ${mode === "browser" ? "border" : ""}`}
          onClick={() => setMode("browser")}
          type="button"
        >
          Browser
        </button>
        {mode === "browser" && (
          <label className="ml-3 inline-flex items-center gap-2 text-sm">
            <Switch checked={shadow} disabled={busy} onCheckedChange={handleToggle} />
            <span>Shadow global default</span>
          </label>
        )}
      </div>
      <div className="flex items-center gap-3">
        <label className="flex items-center gap-2 text-sm">
          <Switch checked={autopilot} onCheckedChange={setAutopilot} disabled={autopilotDisabled} />
          <span>Autopilot</span>
        </label>
        <ModelPicker />
        <SystemStatusButton />
        <Link href="/shipit/diagnostics" className="px-3 py-1 rounded-2xl border text-sm">
          Diagnostics
        </Link>
        <Link
          href="/shipit/diagnostics/self-heal"
          className="px-3 py-1 text-sm text-primary underline-offset-2 hover:underline"
        >
          Self-Heal
        </Link>
      </div>
    </div>
  );
}
