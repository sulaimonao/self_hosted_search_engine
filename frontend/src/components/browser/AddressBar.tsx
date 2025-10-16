"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAppStore } from "@/state/useAppStore";
import { resolveBrowserAPI } from "@/lib/browser-ipc";
import { normalizeAddressInput } from "@/lib/url";
import { useBrowserRuntimeStore } from "@/state/useBrowserRuntime";

export function AddressBar() {
  const activeTab = useAppStore((state) => state.activeTab?.());
  const updateTab = useAppStore((state) => state.updateTab);
  const [value, setValue] = useState(activeTab?.url ?? "");
  const browserAPI = useMemo(() => resolveBrowserAPI(), []);
  const searchMode = useBrowserRuntimeStore((state) => state.settings?.searchMode ?? "auto");

  useEffect(() => {
    setValue(activeTab?.url ?? "");
  }, [activeTab?.id, activeTab?.url]);

  return (
    <form
      className="flex w-full items-center gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (!activeTab) return;
        const nextUrl = normalizeAddressInput(value, { searchMode });
        if (browserAPI) {
          browserAPI.navigate(nextUrl, { tabId: activeTab.id, transition: "typed" });
        } else {
          updateTab(activeTab.id, { url: nextUrl, title: value.trim() || nextUrl });
        }
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
