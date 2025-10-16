export type SearchMode = "auto" | "query";

const SCHEME_REGEX = /^https?:\/\//i;
const DOMAIN_LIKE_REGEX = /^[\w.-]+\.[a-z]{2,}(?:[:/?#].*)?$/i;

function toGoogleSearch(query: string) {
  return `https://www.google.com/search?q=${encodeURIComponent(query.trim())}`;
}

export function normalizeAddressInput(
  value: string,
  options: { searchMode?: SearchMode } = {},
): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return toGoogleSearch("");
  }

  if (SCHEME_REGEX.test(trimmed)) {
    return trimmed;
  }

  const mode = options.searchMode ?? "auto";
  const looksLikeDomain = DOMAIN_LIKE_REGEX.test(trimmed);

  if (mode === "query" && !SCHEME_REGEX.test(trimmed)) {
    return toGoogleSearch(trimmed);
  }

  if (looksLikeDomain) {
    return `https://${trimmed}`;
  }

  return toGoogleSearch(trimmed);
}
