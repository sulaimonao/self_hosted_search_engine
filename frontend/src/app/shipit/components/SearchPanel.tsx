"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";

import type { HybridSearchResult } from "@/app/shipit/lib/api";
import { runHybridSearch } from "@/app/shipit/lib/api";
import { useApp } from "@/app/shipit/store/useApp";

import FacetRail from "./FacetRail";

function formatHostname(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

export default function SearchPanel(): JSX.Element {
  const [query, setQuery] = useState<string>("");
  const { features } = useApp();
  const backendAvailable = features.serverTime !== "unavailable";
  const trimmedQuery = query.trim();
  const searchKey = backendAvailable && trimmedQuery.length > 0 ? ["hybrid-search", trimmedQuery] : null;
  const { data, isValidating, error } = useSWR<HybridSearchResult>(
    searchKey,
    ([, value]) => runHybridSearch(value, { limit: 12 }),
    { keepPreviousData: true },
  );

  const hits = data?.hits ?? [];
  const facets = data?.facets;
  const keywordFallback = data?.keywordFallback ?? false;
  const disabled = !backendAvailable;
  const statusMessage = useMemo(() => {
    if (!backendAvailable) {
      return "Backend offline";
    }
    if (error) {
      return error instanceof Error ? error.message : "Search failed";
    }
    return null;
  }, [backendAvailable, error]);

  const isLoading = Boolean(searchKey && !data && !error) || isValidating;

  return (
    <div className="grid grid-cols-[16rem_1fr] gap-4">
      <FacetRail facets={facets} />
      <div>
        <div className="flex gap-2 mb-3">
          <input
            className="border rounded px-3 py-2 w-full"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search…"
            disabled={disabled}
          />
        </div>
        {statusMessage ? <div className="text-sm text-muted-foreground mb-2">{statusMessage}</div> : null}
        {isLoading && <div>Loading…</div>}
        {keywordFallback ? (
          <div className="mb-2 text-xs text-muted-foreground">
            Vector results were sparse; showing keyword matches.
          </div>
        ) : null}
        <ul className="space-y-3">
          {hits.map((hit) => (
            <li key={`${hit.source}-${hit.url}`} className="p-3 border rounded-2xl space-y-1">
              <a
                href={hit.url}
                className="font-medium"
                target="_blank"
                rel="noreferrer"
              >
                {hit.title || hit.url}
              </a>
              {hit.snippet ? <div className="text-sm">{hit.snippet}</div> : null}
              <div className="text-xs opacity-70 flex items-center gap-2">
                <span>{formatHostname(hit.url)}</span>
                <span>· {hit.source === "vector" ? "Vector" : "Keyword"}</span>
                {typeof hit.score === "number" ? <span>· {hit.score.toFixed(3)}</span> : null}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
