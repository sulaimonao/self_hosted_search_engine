export type ChatLinkNavigationDecision =
  | { action: "navigate"; url: string }
  | { action: "external"; url: string }
  | { action: "ignore" };

function isHttpUrl(candidate: string | null | undefined): boolean {
  if (!candidate) {
    return false;
  }
  try {
    const parsed = new URL(candidate);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export function resolveChatLinkNavigation(
  currentPreviewUrl: string | null | undefined,
  rawUrl: string,
): ChatLinkNavigationDecision {
  const candidate = typeof rawUrl === "string" ? rawUrl.trim() : "";
  if (!candidate) {
    return { action: "ignore" };
  }

  const hasPreviewBase = Boolean(currentPreviewUrl && isHttpUrl(currentPreviewUrl));
  const baseUrl = hasPreviewBase ? (currentPreviewUrl as string) : undefined;

  let parsed: URL;
  try {
    parsed = baseUrl ? new URL(candidate, baseUrl) : new URL(candidate);
  } catch {
    try {
      parsed = new URL(candidate);
    } catch {
      return { action: "ignore" };
    }
  }

  const normalized = parsed.toString();

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return { action: "external", url: normalized };
  }

  if (!hasPreviewBase) {
    return { action: "external", url: normalized };
  }

  let previewHost: string | null = null;
  try {
    previewHost = baseUrl ? new URL(baseUrl).host : null;
  } catch {
    previewHost = null;
  }

  if (previewHost && parsed.host === previewHost) {
    return { action: "navigate", url: normalized };
  }

  return { action: "external", url: normalized };
}
