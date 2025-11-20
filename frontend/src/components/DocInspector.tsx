"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

// Candidate legacy component: document inspector panel is unused in current UI but kept for debugging.
interface DocInspectorProps {
  doc: Record<string, unknown> | null;
}

export function DocInspector({ doc }: DocInspectorProps) {
  if (!doc) {
    return null;
  }

  const categories = Array.isArray(doc.categories) ? (doc.categories as unknown[]).map(String) : [];
  const labels = Array.isArray(doc.labels) ? (doc.labels as unknown[]).map(String) : [];
  const url = typeof doc.url === "string" ? doc.url : "";
  const title = typeof doc.title === "string" && doc.title.trim() ? doc.title : url;
  const site = typeof doc.site === "string" ? doc.site : null;
  const tokens = typeof doc.tokens === "number" ? doc.tokens : null;
  const hash = typeof doc.content_hash === "string" ? doc.content_hash : null;

  return (
    <Card className="border-dashed">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Document inspector</CardTitle>
        {site ? <span className="text-xs text-muted-foreground">{site}</span> : null}
      </CardHeader>
      <CardContent className="space-y-2 pt-0 text-xs text-muted-foreground">
        <div className="space-y-1">
          <p className="font-medium text-foreground">{title}</p>
          <p className="break-all text-[11px]">{url}</p>
        </div>
        {hash ? (
          <div>
            <span className="font-medium text-foreground">Hash:</span> {hash.slice(0, 12)}…
          </div>
        ) : null}
        {typeof doc.language === "string" ? (
          <div>
            <span className="font-medium text-foreground">Language:</span> {doc.language}
          </div>
        ) : null}
        {tokens ? (
          <div>
            <span className="font-medium text-foreground">Tokens:</span> {tokens}
          </div>
        ) : null}
        {categories.length ? (
          <div className="flex flex-wrap gap-1">
            {categories.map((category) => (
              <Badge key={category} variant="outline">
                {category}
              </Badge>
            ))}
          </div>
        ) : null}
        {labels.length ? (
          <div className="flex flex-wrap gap-1">
            {labels.map((label) => (
              <Badge key={label} variant="secondary">
                {label}
              </Badge>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export default DocInspector;
