<<<<<<< ours
<<<<<<< ours
export function SettingsModels() {
  return (
    <div>
      <h3 className="font-semibold">Model Selection</h3>
      <div className="mt-2">
        <label htmlFor="chat-model" className="block">Chat Model</label>
        <select id="chat-model" className="w-full p-2 border rounded-md">
          <option>gpt-oss</option>
          <option>Gemma3</option>
        </select>
      </div>
      <div className="mt-2">
        <label htmlFor="embedding-model" className="block">Embedding Model</label>
        <select id="embedding-model" className="w-full p-2 border rounded-md">
          <option>embeddinggemma</option>
        </select>
      </div>
    </div>
  );
}
=======
=======
>>>>>>> theirs
"use client";

import { useEffect } from "react";
import { RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { LlmStatusResponse } from "@/lib/api";

interface SettingsModelsProps {
  status?: LlmStatusResponse;
  loading?: boolean;
  error?: string;
  onRefresh: () => void;
  onUpdateSelection: (type: "chat" | "embedding", model: string) => void;
}

const chatOptions = ["gpt-oss", "Gemma3"];
const embeddingOptions = ["embeddinggemma"];

export function SettingsModels({ status, loading, error, onRefresh, onUpdateSelection }: SettingsModelsProps) {
  useEffect(() => {
    if (!status) return;
    if (status.chat && !status.available.includes(status.chat)) {
      console.warn(`Primary chat model ${status.chat} missing. Falling back if configured.`);
    }
  }, [status]);

  return (
    <Card className="border-muted-foreground/40">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <div>
          <CardTitle className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Model Settings
          </CardTitle>
          <CardDescription>Pick the Ollama models the co-pilot should use.</CardDescription>
        </div>
        <Button type="button" variant="ghost" size="icon" onClick={onRefresh} disabled={loading}>
          {loading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading && <Skeleton className="h-14 w-full" />}
        {error && <p className="text-sm text-destructive">{error}</p>}
        {status && (
          <div className="space-y-4 text-sm">
            <section>
              <header className="flex items-center gap-2">
                <h4 className="font-medium text-foreground">Chat model</h4>
                {status.chat ? (
                  <Badge variant={status.available.includes(status.chat) ? "success" : "warning"}>
                    {status.chat}
                  </Badge>
                ) : (
                  <Badge variant="destructive">Missing</Badge>
                )}
                {status.fallbackChat && <Badge variant="secondary">Fallback: {status.fallbackChat}</Badge>}
              </header>
              <p className="mt-1 text-xs text-muted-foreground">
                Available via Ollama: {status.available.length > 0 ? status.available.join(", ") : "(none)"}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {chatOptions.map((model) => (
                  <Button
                    key={model}
                    type="button"
                    variant={status.chat === model ? "default" : "secondary"}
                    onClick={() => onUpdateSelection("chat", model)}
                    disabled={!status.available.includes(model) && !status.fallbackChat}
                  >
                    {model}
                  </Button>
                ))}
              </div>
              {!status.chat && (
                <p className="mt-2 text-xs text-destructive">
                  No primary chat model detected. Install `gpt-oss` or `Gemma3` with `ollama pull` to enable chat.
                </p>
              )}
            </section>
            <section>
              <header className="flex items-center gap-2">
                <h4 className="font-medium text-foreground">Embedding model</h4>
                {status.embedding ? (
                  <Badge variant={status.available.includes(status.embedding) ? "success" : "warning"}>
                    {status.embedding}
                  </Badge>
                ) : (
                  <Badge variant="destructive">Missing</Badge>
                )}
                {status.fallbackEmbedding && <Badge variant="secondary">Fallback: {status.fallbackEmbedding}</Badge>}
              </header>
              <p className="mt-1 text-xs text-muted-foreground">
                Embedding models ensure new content can be indexed for retrieval.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {embeddingOptions.map((model) => (
                  <Button
                    key={model}
                    type="button"
                    variant={status.embedding === model ? "default" : "secondary"}
                    onClick={() => onUpdateSelection("embedding", model)}
                    disabled={!status.available.includes(model) && !status.fallbackEmbedding}
                  >
                    {model}
                  </Button>
                ))}
              </div>
              {!status.embedding && (
                <p className="mt-2 text-xs text-destructive">
                  Embedding model missing. Install `embeddinggemma` to enable semantic search.
                </p>
              )}
            </section>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
<<<<<<< ours
>>>>>>> theirs
=======
>>>>>>> theirs
