"use client";

import { useState } from "react";

type JsonValue = Record<string, unknown> | Array<unknown> | null;

function JsonBlock({ data }: { data: JsonValue }) {
  if (data === null) return null;
  return (
    <pre className="mt-3 text-sm bg-neutral-50 border p-3 overflow-auto rounded">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

export default function LocalHome() {
  const [q, setQ] = useState("");
  const [host, setHost] = useState("");
  const [profile, setProfile] = useState<JsonValue>(null);
  const [searchResult, setSearchResult] = useState<JsonValue>(null);
  const [searching, setSearching] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function search() {
    const query = q.trim();
    if (!query) {
      setSearchResult(null);
      return;
    }
    setSearching(true);
    setError(null);
    try {
      const response = await fetch(`/api/search?q=${encodeURIComponent(query)}&llm=off`);
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || `Search failed (${response.status})`);
      }
      const payload = await response.json();
      setSearchResult(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSearching(false);
    }
  }

  async function scan() {
    const target = host.trim();
    if (!target) {
      setProfile(null);
      return;
    }
    setScanning(true);
    setError(null);
    try {
      const scanResponse = await fetch(`/api/domains/scan?host=${encodeURIComponent(target)}`, {
        method: "POST",
      });
      if (!scanResponse.ok) {
        const detail = await scanResponse.text();
        throw new Error(detail || `Scan failed (${scanResponse.status})`);
      }
      const profileResponse = await fetch(`/api/domains/${encodeURIComponent(target)}`);
      if (!profileResponse.ok) {
        const detail = await profileResponse.text();
        throw new Error(detail || `Profile fetch failed (${profileResponse.status})`);
      }
      const payload = await profileResponse.json();
      setProfile(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setScanning(false);
    }
  }

  return (
    <main className="p-4 grid gap-6 md:grid-cols-2">
      <section>
        <h2 className="font-semibold mb-2">Local search</h2>
        <div className="flex gap-2">
          <input
            className="border p-2 flex-1 rounded"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder="Search local index..."
          />
          <button
            type="button"
            className="border px-3 rounded disabled:opacity-50"
            onClick={search}
            disabled={searching}
          >
            {searching ? "Searching..." : "Search"}
          </button>
        </div>
        <JsonBlock data={searchResult} />
      </section>
      <section>
        <h2 className="font-semibold mb-2">Domain profile</h2>
        <div className="flex gap-2">
          <input
            className="border p-2 flex-1 rounded"
            value={host}
            onChange={(event) => setHost(event.target.value)}
            placeholder="example.com"
          />
          <button
            type="button"
            className="border px-3 rounded disabled:opacity-50"
            onClick={scan}
            disabled={scanning}
          >
            {scanning ? "Scanning..." : "Scan"}
          </button>
        </div>
        <JsonBlock data={profile} />
      </section>
      {error && (
        <div className="md:col-span-2 text-sm text-red-600 border border-red-200 rounded p-3">
          {error}
        </div>
      )}
    </main>
  );
}
