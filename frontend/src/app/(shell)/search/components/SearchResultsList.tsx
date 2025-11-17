import type { SearchResult } from "@/app/(shell)/search/components/SearchResultItem";
import { SearchResultItem } from "@/app/(shell)/search/components/SearchResultItem";

export function SearchResultsList({ results }: { results: SearchResult[] }) {
  if (!results.length) {
    return (
      <p className="rounded-md border border-border-subtle bg-app-card-subtle p-6 text-sm text-fg-muted">
        No results yet. Try a different query.
      </p>
    );
  }

  return (
    <ul className="space-y-3">
      {results.map((result) => (
        <SearchResultItem key={result.id} result={result} />
      ))}
    </ul>
  );
}
