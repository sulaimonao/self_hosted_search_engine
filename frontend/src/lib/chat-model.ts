import type { ConfiguredModels } from "@/lib/types";

interface ResolveOptions {
  available: string[];
  configured: ConfiguredModels;
  stored: string | null;
  previous: string | null;
}

export function resolveChatModelSelection({
  available,
  configured,
  stored,
  previous,
}: ResolveOptions): string | null {
  const uniqueAvailable = Array.from(new Set(available.filter(Boolean)));

  if (previous && uniqueAvailable.includes(previous)) {
    return previous;
  }

  if (stored && uniqueAvailable.includes(stored)) {
    return stored;
  }

  if (configured.primary && uniqueAvailable.includes(configured.primary)) {
    return configured.primary;
  }

  if (uniqueAvailable.length > 0) {
    return uniqueAvailable[0];
  }

  if (configured.primary) {
    return configured.primary;
  }

  return null;
}
