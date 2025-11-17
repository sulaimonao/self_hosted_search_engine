import { useEffect, useState } from "react";

// API base URL resolution
const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");

function resolveApi(path: string): string {
  if (!API_BASE) return path;
  return `${API_BASE}${path}`;
}

interface OllamaModel {
  name: string;
}

interface OllamaHealthResponse {
  ok: boolean;
  tags?: {
    models?: OllamaModel[];
  };
  error?: string;
}

/**
 * Hook to check Ollama health and available models
 * 
 * @example
 * ```tsx
 * function ChatPanel() {
 *   const { ok, models, error, loading } = useOllamaHealth();
 *   
 *   if (loading) return <div>Checking Ollama...</div>;
 *   if (!ok) return <div>Ollama not available: {error}</div>;
 *   
 *   return <div>Available models: {models.join(", ")}</div>;
 * }
 * ```
 */
export function useOllamaHealth() {
  const [state, setState] = useState<{
    ok: boolean;
    models: string[];
    error: string | null;
    loading: boolean;
  }>({
    ok: false,
    models: [],
    error: null,
    loading: true,
  });

  useEffect(() => {
    let mounted = true;

    async function check() {
      try {
        const res = await fetch(resolveApi("/api/health/ollama"));
        const data = (await res.json()) as OllamaHealthResponse;

        if (!mounted) return;

        if (data.ok) {
          const models = data.tags?.models?.map((m) => m.name) || [];
          setState({ ok: true, models, error: null, loading: false });
        } else {
          setState({ ok: false, models: [], error: data.error || "Unknown error", loading: false });
        }
      } catch (e) {
        if (!mounted) return;
        const errorMessage = e instanceof Error ? e.message : String(e);
        setState({ ok: false, models: [], error: errorMessage, loading: false });
      }
    }

    check();

    return () => {
      mounted = false;
    };
  }, []);

  return state;
}

/**
 * Banner component to show Ollama health status
 */
export function OllamaHealthBanner() {
  const { ok, error, loading } = useOllamaHealth();

  if (loading) {
    return (
      <div className="border-l-4 border-border-subtle bg-app-card-subtle p-4">
        <p className="text-sm text-fg-muted">Checking Ollama connection...</p>
      </div>
    );
  }

  if (!ok) {
    return (
      <div className="border-l-4 border-border-strong bg-app-card-subtle p-4">
        <div className="flex flex-col gap-2">
          <p className="text-sm text-state-warning">
            Ollama is not available: {error}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => window.open("https://ollama.com", "_blank")}
              className="text-sm font-medium text-state-warning underline hover:text-state-warning/80"
            >
              Install Ollama
            </button>
            <button
              onClick={() => window.location.reload()}
              className="text-sm font-medium text-state-warning underline hover:text-state-warning/80"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  return null;
}
