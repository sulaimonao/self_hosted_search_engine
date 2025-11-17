import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";

export function SearchFilters() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Filters</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex items-center justify-between">
          <Label htmlFor="docs">Documents</Label>
          <Switch id="docs" defaultChecked />
        </div>
        <div className="flex items-center justify-between">
          <Label htmlFor="memories">Memories</Label>
          <Switch id="memories" defaultChecked />
        </div>
        <div className="flex items-center justify-between">
          <Label htmlFor="history">Browser history</Label>
          <Switch id="history" defaultChecked />
        </div>
      </CardContent>
    </Card>
  );
}
