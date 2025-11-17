"use client";

import { useState } from "react";

import { SearchBar } from "@/app/(shell)/search/components/SearchBar";
import { SearchFilters } from "@/app/(shell)/search/components/SearchFilters";
import { SearchResultsList } from "@/app/(shell)/search/components/SearchResultsList";
import type { SearchResult } from "@/app/(shell)/search/components/SearchResultItem";

const mockResults: SearchResult[] = [
  { id: "r1", title: "Capture playbook", snippet: "Guide for configuring the capture agent.", source: "Docs" },
  { id: "r2", title: "HydraFlow timeline", snippet: "Conversation referencing the latest memory.", source: "Chat" },
  { id: "r3", title: "Job 3312", snippet: "Bundle export completed successfully.", source: "Jobs" },
];

export default function SearchPage() {
  const [results, setResults] = useState<SearchResult[]>(mockResults);

  function handleSearch(query: string) {
    if (!query) {
      setResults(mockResults);
      return;
    }
    setResults(
      mockResults.filter((item) => item.title.toLowerCase().includes(query.toLowerCase()))
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Search</h1>
        <p className="text-sm text-muted-foreground">One query across your entire workspace.</p>
      </div>
      <SearchBar onSearch={handleSearch} />
      <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
        <SearchResultsList results={results} />
        <SearchFilters />
      </div>
    </div>
  );
}
