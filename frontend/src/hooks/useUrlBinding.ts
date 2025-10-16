"use client";

import { useEffect, useRef } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useShallow } from "zustand/react/shallow";

import { useAppStore } from "@/state/useAppStore";

const BROWSER_PATH = "/browser";

/**
 * Keeps the `/browser?url=` query param and the store's desired URL in sync without feedback loops.
 */
export function useUrlBinding(): void {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const syncingRef = useRef(false);

  const { desiredUrl, setDesiredUrl } = useAppStore(
    useShallow((state) => ({
      desiredUrl: state.browser.desiredUrl ?? null,
      setDesiredUrl: state.setBrowserDesiredUrl,
    })),
  );

  const urlParam = searchParams?.get("url") ?? "";

  // router -> store
  useEffect(() => {
    if (pathname !== BROWSER_PATH) {
      return;
    }
    if (syncingRef.current) {
      return;
    }
    const normalized = urlParam || null;
    if ((desiredUrl ?? null) === normalized) {
      return;
    }
    setDesiredUrl(normalized);
  }, [desiredUrl, pathname, setDesiredUrl, urlParam]);

  // store -> router
  useEffect(() => {
    if (pathname !== BROWSER_PATH) {
      return;
    }
    if (typeof window === "undefined") {
      return;
    }
    const normalizedDesired = desiredUrl ?? "";
    if (urlParam === normalizedDesired) {
      return;
    }
    syncingRef.current = true;
    const href = normalizedDesired ? `${BROWSER_PATH}?url=${encodeURIComponent(normalizedDesired)}` : BROWSER_PATH;
    router.replace(href, { scroll: false });
    const id = window.setTimeout(() => {
      syncingRef.current = false;
    }, 100);
    return () => {
      window.clearTimeout(id);
    };
  }, [desiredUrl, pathname, router, urlParam]);
}
