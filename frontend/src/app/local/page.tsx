"use client";

import { useState } from "react";

type JsonValue = Record<string, unknown> | Array<unknown> | null;

function JsonBlock({ data }: { data: JsonValue }) {
  if (data === null) return null;
  return (
    <pre className="mt-3 max-h-64 overflow-auto rounded-md border border-border-subtle bg-app-card p-3 font-mono text-sm text-fg">
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
            className="flex-1 rounded-xs border border-border-subtle bg-app-input p-2 text-sm text-fg placeholder:text-fg-subtle focus-visible:border-transparent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            value={chat}
            onChange={(event) => setChat(event.target.value)}
            placeholder="Ask the copilot…"
          />
          <button
            type="submit"
            className="rounded-md border border-transparent bg-accent px-3 py-2 text-sm font-medium text-fg-on-accent transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
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
            className="flex-1 rounded-xs border border-border-subtle bg-app-input p-2 text-sm text-fg placeholder:text-fg-subtle focus-visible:border-transparent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder="Search local index..."
          />
          <button
            type="submit"
            className="rounded-md border border-border-subtle bg-app-card-subtle px-3 py-2 text-sm font-medium text-fg transition hover:bg-app-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
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
            className="flex-1 rounded-xs border border-border-subtle bg-app-input p-2 text-sm text-fg placeholder:text-fg-subtle focus-visible:border-transparent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            value={host}
            onChange={(event) => setHost(event.target.value)}
            placeholder="example.com"
          />
          <button
            type="submit"
            className="rounded-md border border-border-subtle bg-app-card-subtle px-3 py-2 text-sm font-medium text-fg transition hover:bg-app-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
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
          className="md:col-span-2 rounded-md border border-border-strong bg-app-card-subtle p-3 text-sm text-state-danger"
          role="alert"
          aria-live="assertive"
        >
          {error}
        </div>
      )}
    </main>
  );
}
