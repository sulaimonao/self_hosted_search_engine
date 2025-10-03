import { AppShell } from "@/components/app-shell";
import { extractPage } from "@/lib/api";
import type { PageExtractResponse } from "@/lib/types";

interface WorkspacePageProps {
  searchParams?: Record<string, string | string[] | undefined>;
}

function sanitizeUrl(raw: string | null | undefined): string | null {
  if (typeof raw !== "string") {
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

async function fetchInitialContext(url: string | null): Promise<PageExtractResponse | null> {
  if (!url) {
    return null;
  }
  try {
    return await extractPage(url, { vision: false });
  } catch {
    return null;
  }
}

export default async function WorkspacePage({ searchParams }: WorkspacePageProps) {
  const rawUrl = Array.isArray(searchParams?.url) ? searchParams?.url[0] : searchParams?.url;
  const initialUrl = sanitizeUrl(rawUrl);
  const initialContext = await fetchInitialContext(initialUrl);

  return <AppShell initialUrl={initialUrl ?? undefined} initialContext={initialContext} />;
}
