import { Button } from "@/components/ui/button";

export type SearchResult = {
  id: string;
  title: string;
  snippet: string;
  source: string;
};

export function SearchResultItem({ result }: { result: SearchResult }) {
  return (
    <li className="rounded-xs border border-transparent bg-app-card px-4 py-3 text-fg transition-colors duration-fast hover:border-border-subtle hover:bg-app-card-hover">
      <p className="text-xs uppercase tracking-wide text-fg-muted">{result.source}</p>
      <h3 className="text-lg font-semibold text-fg">{result.title}</h3>
      <p className="text-sm text-fg-muted">{result.snippet}</p>
      <div className="mt-3 flex gap-2 text-sm">
        <Button variant="secondary" size="sm">Open in tab</Button>
        <Button variant="ghost" size="sm">Share to AI</Button>
      </div>
    </li>
  );
}
