import { Button } from "@/components/ui/button";

export type SearchResult = {
  id: string;
  title: string;
  snippet: string;
  source: string;
};

export function SearchResultItem({ result }: { result: SearchResult }) {
  return (
    <li className="rounded-xl border bg-background p-4">
      <p className="text-sm text-muted-foreground">{result.source}</p>
      <h3 className="text-lg font-semibold">{result.title}</h3>
      <p className="text-sm text-muted-foreground">{result.snippet}</p>
      <div className="mt-3 flex gap-2 text-sm">
        <Button variant="secondary" size="sm">Open in tab</Button>
        <Button variant="ghost" size="sm">Share to AI</Button>
      </div>
    </li>
  );
}
