export type SearchMode = "auto" | "query";

const SCHEME_REGEX = /^https?:\/\//i;
const DOMAIN_LIKE_REGEX = /^[\w.-]+\.[a-z]{2,}(?:[:/?#].*)?$/i;
const SEARCH_HOSTNAMES = ["google.com", "www.google.com"];
const SEARCH_HOSTS = new Set(SEARCH_HOSTNAMES);

function toGoogleSearch(query: string) {
  const trimmed = query.trim();
  const base = new URL("https://www.google.com/search");
  if (trimmed) {
    base.searchParams.set("q", trimmed);
  }
  base.searchParams.set("igu", "1");
  return base.toString();
}

function ensureGoogleEmbeddable(candidate: string): string {
  try {
    const url = new URL(candidate);
    const host = url.hostname.toLowerCase();
    if (!SEARCH_HOSTS.has(host)) {
      return candidate;
    }
    if (host === "google.com") {
      url.hostname = "www.google.com";
    }
    if (!url.searchParams.has("igu")) {
      url.searchParams.set("igu", "1");
    }
    if (!url.pathname || url.pathname === "/") {
      url.pathname = "/webhp";
    }
    return url.toString();
  } catch {
    return candidate;
  }
}

export function isSearchHostUrl(candidate: string): boolean {
  try {
    const url = new URL(candidate);
    const host = url.hostname.toLowerCase();
    return SEARCH_HOSTS.has(host);
  } catch {
    return false;
  }
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
    return ensureGoogleEmbeddable(trimmed);
  }

  const mode = options.searchMode ?? "auto";
  const looksLikeDomain = DOMAIN_LIKE_REGEX.test(trimmed);

  if (mode === "query" && !SCHEME_REGEX.test(trimmed)) {
    return ensureGoogleEmbeddable(toGoogleSearch(trimmed));
  }

  if (looksLikeDomain) {
    return ensureGoogleEmbeddable(`https://${trimmed}`);
  }

  return ensureGoogleEmbeddable(toGoogleSearch(trimmed));
}
