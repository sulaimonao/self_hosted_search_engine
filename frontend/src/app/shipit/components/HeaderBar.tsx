"use client";

import ModelPicker from "./ModelPicker";
import SystemStatusButton from "./SystemStatusButton";
import { useApp } from "@/app/shipit/store/useApp";

export default function HeaderBar(): JSX.Element {
  const { mode, shadow, setMode, toggleShadow } = useApp();
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
            <input type="checkbox" checked={shadow} onChange={toggleShadow} />
            <span>Shadow crawl</span>
          </label>
        )}
      </div>
      <div className="flex items-center gap-3">
        <ModelPicker />
        <SystemStatusButton />
      </div>
    </div>
  );
}
