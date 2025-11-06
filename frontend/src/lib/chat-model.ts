import type { ConfiguredModels } from "@/lib/types";

interface ResolveOptions {
  available: string[];
  configured: ConfiguredModels;
  stored: string | null;
  previous?: string | null;
}

export function resolveChatModelSelection({
  available,
  configured,
  stored,
  previous,
}: ResolveOptions): string | null {
  const uniqueAvailable = Array.from(new Set(available.filter(Boolean)));

  // Helper: prefer exact match, otherwise try to resolve a family name
  // (e.g. "gpt-oss") to a concrete available model (e.g. "gpt-oss:120b").
  const resolveCandidate = (candidate: string | null | undefined): string | null => {
    if (!candidate) return null;
    if (uniqueAvailable.includes(candidate)) return candidate;
    // Try family -> concrete mapping: pick first available that starts with the family name + ':'
    const familyMatch = uniqueAvailable.find((a) => a.startsWith(`${candidate}:`));
    if (familyMatch) return familyMatch;
    // As a looser fallback, match when available entry contains the candidate as a prefix
    const looseMatch = uniqueAvailable.find((a) => a.toLowerCase().startsWith(candidate.toLowerCase()));
    if (looseMatch) return looseMatch;
    return null;
  };

  const resolvedPrevious = resolveCandidate(previous ?? null);
  if (resolvedPrevious) return resolvedPrevious;

  const resolvedStored = resolveCandidate(stored ?? null);
  if (resolvedStored) return resolvedStored;

  const resolvedConfiguredPrimary = resolveCandidate(configured.primary ?? null);
  if (resolvedConfiguredPrimary) return resolvedConfiguredPrimary;

  if (uniqueAvailable.length > 0) {
    return uniqueAvailable[0];
  }

  // Nothing concrete available — fall back to configured primary if present
  if (configured.primary) {
    return configured.primary;
  }

  return null;
}
