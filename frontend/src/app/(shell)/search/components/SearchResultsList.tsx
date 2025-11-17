import type { SearchResult } from "@/app/(shell)/search/components/SearchResultItem";
import { SearchResultItem } from "@/app/(shell)/search/components/SearchResultItem";

export function SearchResultsList({ results }: { results: SearchResult[] }) {
  return (
    <ul className="space-y-3">
      {results.map((result) => (
        <SearchResultItem key={result.id} result={result} />
      ))}
    </ul>
  );
}
