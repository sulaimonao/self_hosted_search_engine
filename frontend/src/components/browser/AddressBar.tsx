"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAppStore } from "@/state/useAppStore";

function normalizeInput(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return "https://duckduckgo.com";
  }
  const urlPattern = /^(https?:\/\/)/i;
  if (urlPattern.test(trimmed)) {
    return trimmed;
  }
  try {
    const potential = new URL(`https://${trimmed}`);
    return potential.toString();
  } catch {
    return `https://duckduckgo.com/?q=${encodeURIComponent(trimmed)}`;
  }
}

export function AddressBar() {
  const activeTab = useAppStore((state) => state.activeTab?.());
  const updateTab = useAppStore((state) => state.updateTab);
  const [value, setValue] = useState(activeTab?.url ?? "");

  useEffect(() => {
    setValue(activeTab?.url ?? "");
  }, [activeTab?.id, activeTab?.url]);

  return (
    <form
      className="flex w-full items-center gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (!activeTab) return;
        const nextUrl = normalizeInput(value);
        updateTab(activeTab.id, { url: nextUrl, title: value.trim() || nextUrl });
      }}
    >
      <Input
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="Search or enter address"
        className="flex-1"
      />
      <Button type="submit" variant="secondary">
        Go
      </Button>
    </form>
  );
}
