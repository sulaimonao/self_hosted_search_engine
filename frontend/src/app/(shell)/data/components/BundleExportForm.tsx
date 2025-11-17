"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { useBundleExport } from "@/lib/backend/hooks";

const COMPONENT_OPTIONS = [
  { id: "threads", label: "Threads" },
  { id: "messages", label: "Messages" },
  { id: "tasks", label: "Tasks" },
  { id: "browser_history", label: "Browser history" },
];

interface BundleExportFormProps {
  autoFocus?: boolean;
}

export function BundleExportForm({ autoFocus }: BundleExportFormProps) {
  const [selected, setSelected] = useState<string[]>(["threads", "messages"]);
  const exportMutation = useBundleExport();
  const firstOptionRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!autoFocus) return;
    const node = firstOptionRef.current;
    node?.focus();
    node?.scrollIntoView({ block: "center" });
  }, [autoFocus]);

  function handleToggle(component: string, checked: boolean) {
    setSelected((prev) => (checked ? [...prev, component] : prev.filter((entry) => entry !== component)));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await exportMutation.mutateAsync({ components: selected });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Export bundle</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4 text-sm">
          <div className="grid gap-2">
            {COMPONENT_OPTIONS.map((option, index) => (
              <Label key={option.id} className="flex items-center gap-2 font-normal">
                <Checkbox
                  ref={index === 0 ? firstOptionRef : undefined}
                  checked={selected.includes(option.id)}
                  onCheckedChange={(checked) => handleToggle(option.id, Boolean(checked))}
                />
                {option.label}
              </Label>
            ))}
          </div>
          {exportMutation.data && (
            <div className="rounded-lg border bg-muted/40 p-3 text-xs">
              <p className="font-medium text-foreground">Export complete</p>
              <p>Job {exportMutation.data.job_id}</p>
              <p>Bundle: {exportMutation.data.bundle_path}</p>
            </div>
          )}
          {exportMutation.error && (
            <p className="text-sm text-destructive">{exportMutation.error.message}</p>
          )}
          <Button type="submit" disabled={exportMutation.isPending}>
            {exportMutation.isPending ? "Exporting" : "Export"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
