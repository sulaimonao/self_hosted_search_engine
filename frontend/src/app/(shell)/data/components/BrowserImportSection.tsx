import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function BrowserImportSection() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Browser imports</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p>Pull history and bookmarks from Chrome or Firefox.</p>
        <Button variant="secondary">Import from Chrome</Button>
        <Button variant="secondary">Import from Firefox</Button>
      </CardContent>
    </Card>
  );
}
