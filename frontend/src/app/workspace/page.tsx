"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";

function sanitizeUrl(raw: string | null): string | null {
  if (!raw) {
    return null;
  }
  const trimmed = raw.trim();
  if (!trimmed) {
    return null;
  }
  const domainLike = /^(?:[\w-]+\.)+[a-z]{2,}(?::\d+)?(?:[/?#].*)?$/i;
  if (domainLike.test(trimmed)) {
    return `https://${trimmed}`;
  }
  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      return parsed.toString();
    }
  } catch {
    return null;
  }
  return null;
}

export default function WorkspacePage() {
  const [initialUrl, setInitialUrl] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setInitialUrl(sanitizeUrl(params.get("url")));
  }, []);

  return <AppShell initialUrl={initialUrl ?? undefined} initialContext={null} />;
}
