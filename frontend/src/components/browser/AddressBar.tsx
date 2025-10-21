"use client";

import { useEffect, useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAppStore } from "@/state/useAppStore";
import { resolveBrowserAPI } from "@/lib/browser-ipc";
import { isSearchHostUrl, normalizeAddressInput } from "@/lib/url";
import { useBrowserRuntimeStore } from "@/state/useBrowserRuntime";

export function AddressBar() {
  const { activeTab, updateTab } = useAppStore(
    useShallow((state) => ({
      activeTab: state.activeTab?.(),
      updateTab: state.updateTab,
    })),
  );
  const [value, setValue] = useState(activeTab?.url ?? "");
  const browserAPI = useMemo(() => resolveBrowserAPI(), []);
  const searchMode = useBrowserRuntimeStore((state) => state.settings?.searchMode ?? "auto");
  const openSearchExternally = useBrowserRuntimeStore(
    (state) => state.settings?.openSearchExternally ?? false,
  );

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
        const shouldOpenExternally = openSearchExternally && isSearchHostUrl(nextUrl);
        if (browserAPI) {
          if (shouldOpenExternally && typeof browserAPI.openExternal === "function") {
            void browserAPI.openExternal(nextUrl);
            return;
          }
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
