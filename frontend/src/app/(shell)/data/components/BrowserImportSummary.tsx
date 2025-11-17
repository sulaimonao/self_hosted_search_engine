import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function BrowserImportSummary() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Import summary</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p>Bookmarks imported: 532</p>
        <p>History rows deduped: 2,931</p>
      </CardContent>
    </Card>
  );
}
