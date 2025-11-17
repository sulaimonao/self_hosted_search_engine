import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function PrivacySettingsSection() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Privacy</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p>Clear browser history and delete chat threads.</p>
        <Button variant="destructive">Clear history</Button>
        <Button variant="secondary">Delete selected threads</Button>
      </CardContent>
    </Card>
  );
}
