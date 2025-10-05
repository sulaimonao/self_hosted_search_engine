"use client";

import { useState } from "react";
import useSWR from "swr";

import { api } from "@/app/shipit/lib/api";

import FacetRail from "./FacetRail";

type SearchResponse = {
  ok: boolean;
  data?: {
    total: number;
    page: number;
    size: number;
    facets: Record<string, [string, number][]>;
    hits: Array<{
      id: string;
      url: string;
      title: string;
      snippet: string;
      score: number;
      topics?: string[];
      source_type?: string;
      first_seen?: string;
      last_seen?: string;
      domain?: string;
    }>;
  };
};

export default function SearchPanel(): JSX.Element {
  const [query, setQuery] = useState<string>("");
  const searchPath = query
    ? `/api/search?shipit=1&q=${encodeURIComponent(query)}`
    : null;
  const { data, isLoading } = useSWR<SearchResponse>(searchPath, api);

  const hits = data?.data?.hits ?? [];

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
        <ul className="space-y-3">
          {hits.map((hit) => (
            <li key={hit.id} className="p-3 border rounded-2xl space-y-1">
              <a
                href={hit.url}
                className="font-medium"
                target="_blank"
                rel="noreferrer"
              >
                {hit.title || hit.url}
              </a>
              <div className="text-sm">{hit.snippet}</div>
              <div className="text-xs opacity-70">
                {hit.domain} · {(hit.topics ?? []).slice(0, 3).join(", ")}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
