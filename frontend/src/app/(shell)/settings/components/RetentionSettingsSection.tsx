import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";

export function RetentionSettingsSection() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Retention</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <Label htmlFor="retention">Keep data for (days)</Label>
        <Input id="retention" type="number" defaultValue={30} />
      </CardContent>
    </Card>
  );
}
