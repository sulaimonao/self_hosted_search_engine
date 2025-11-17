import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function BundleJobsSummary() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Bundle jobs</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p>Export #3312 · queued</p>
        <p>Import #3310 · completed</p>
      </CardContent>
    </Card>
  );
}
