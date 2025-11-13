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
  const [chat, setChat] = useState("");
  const [chatSending, setChatSending] = useState(false);
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
      <section className="md:col-span-2">
        <h2 className="font-semibold mb-2">Quick chat</h2>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const text = chat.trim();
            if (!text) return;
            setChatSending(true);
            setError(null);
            try {
              const threadId = (typeof crypto !== "undefined" && 'randomUUID' in crypto) ? crypto.randomUUID() : `local-${Date.now()}`;
              const backend = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");
              const endpoint = `${backend}/api/chat/${encodeURIComponent(threadId)}/message`;
              const body = {
                role: "user",
                content: text,
                page_url: typeof window !== 'undefined' ? window.location.href : undefined,
              };
              const resp = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
              });
              if (!resp.ok) {
                const detail = await resp.text();
                throw new Error(detail || `Chat send failed (${resp.status})`);
              }
              setChat("");
            } catch (err) {
              setError(err instanceof Error ? err.message : String(err));
            } finally {
              setChatSending(false);
            }
          }}
          className="flex gap-2"
        >
          <input
            className="border p-2 flex-1 rounded"
            value={chat}
            onChange={(event) => setChat(event.target.value)}
            placeholder="Ask the copilot…"
          />
          <button
            type="submit"
            className="border px-3 rounded disabled:opacity-50"
            disabled={chatSending || !chat.trim()}
          >
            {chatSending ? "Sending…" : "Send"}
          </button>
        </form>
      </section>
      <section>
        <h2 className="font-semibold mb-2">Local search</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            search();
          }}
          className="flex gap-2"
        >
          <input
            className="border p-2 flex-1 rounded"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder="Search local index..."
          />
          <button
            type="submit"
            className="border px-3 rounded disabled:opacity-50"
            onClick={search}
            disabled={searching}
          >
            {searching ? "Searching..." : "Search"}
          </button>
        </form>
        <JsonBlock data={searchResult} />
      </section>
      <section>
        <h2 className="font-semibold mb-2">Domain profile</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            scan();
          }}
          className="flex gap-2"
        >
          <input
            className="border p-2 flex-1 rounded"
            value={host}
            onChange={(event) => setHost(event.target.value)}
            placeholder="example.com"
          />
          <button
            type="submit"
            className="border px-3 rounded disabled:opacity-50"
            onClick={scan}
            disabled={scanning}
          >
            {scanning ? "Scanning..." : "Scan"}
          </button>
        </form>
        <JsonBlock data={profile} />
      </section>
      {error && (
        <div
          className="md:col-span-2 text-sm text-red-600 border border-red-200 rounded p-3"
          role="alert"
          aria-live="assertive"
        >
          {error}
        </div>
      )}
    </main>
  );
}
