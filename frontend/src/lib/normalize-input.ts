export type NormalizedInput =
  | { kind: "external"; urlOrPath: string }
  | { kind: "internal"; urlOrPath: string };

const ABSOLUTE_URL_REGEX = /^https?:\/\//i;
const DOMAIN_LIKE_REGEX = /^(?:[\w-]+\.)+[a-z]{2,}(?::\d+)?(?:[/?#].*)?$/i;

export function normalizeInput(raw: string): NormalizedInput {
  const trimmed = raw.trim();
  if (!trimmed) {
    return { kind: "internal", urlOrPath: "/search?q=" };
  }

  if (ABSOLUTE_URL_REGEX.test(trimmed)) {
    return { kind: "external", urlOrPath: trimmed };
  }

  if (DOMAIN_LIKE_REGEX.test(trimmed)) {
    return { kind: "external", urlOrPath: `https://${trimmed}` };
  }

  return { kind: "internal", urlOrPath: `/search?q=${encodeURIComponent(trimmed)}` };
}
