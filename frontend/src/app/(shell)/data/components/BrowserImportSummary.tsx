import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface BrowserImportSummaryProps {
  entries?: number;
  lastVisit?: string | null;
}

export function BrowserImportSummary({ entries, lastVisit }: BrowserImportSummaryProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Import summary</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p>History entries captured: {entries ?? "--"}</p>
        <p>Last visit: {lastVisit ? new Date(lastVisit).toLocaleString() : "n/a"}</p>
      </CardContent>
    </Card>
  );
}
