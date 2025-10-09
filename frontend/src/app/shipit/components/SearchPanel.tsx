// @ts-nocheck
"use client";

import { useState } from "react";
import useSWR from "swr";

import { api } from "@/app/shipit/lib/api";

import FacetRail from "./FacetRail";

type HybridSearchHit = {
  url: string;
  title: string;
  snippet?: string;
  score?: number;
  source: "vector" | "keyword";
};

type HybridSearchResponse = {
  query: string;
  combined: HybridSearchHit[];
  vector_top_score: number;
  keyword_fallback: boolean;
};

function formatHostname(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

export default function SearchPanel(): JSX.Element {
  const [query, setQuery] = useState<string>("");
  const searchPath = query ? `/api/index/search?q=${encodeURIComponent(query)}&k=12` : null;
  const { data, isLoading } = useSWR<HybridSearchResponse>(searchPath, api);

  const hits = data?.combined ?? [];

  return (
    <div className="grid grid-cols-[16rem_1fr] gap-4">
      <FacetRail facets={data?.data?.facets} />
      <div>
        <div className="flex gap-2 mb-3">
          <input
            className="border rounded px-3 py-2 w-full"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search…"
          />
        </div>
        {isLoading && <div>Loading…</div>}
        {data?.keyword_fallback ? (
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
