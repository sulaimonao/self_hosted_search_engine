"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

export function CaptureSettingsForm() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Capture</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex items-center justify-between">
          <Label htmlFor="auto">Automatic capture</Label>
          <Switch id="auto" defaultChecked />
        </div>
        <div className="flex items-center justify-between">
          <Label htmlFor="screenshots">Screenshots</Label>
          <Switch id="screenshots" />
        </div>
      </CardContent>
    </Card>
  );
}
