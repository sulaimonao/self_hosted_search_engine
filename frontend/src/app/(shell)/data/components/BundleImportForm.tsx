"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useBundleImport } from "@/lib/backend/hooks";

const COMPONENT_OPTIONS = [
  { id: "threads", label: "Threads" },
  { id: "browser_history", label: "Browser history" },
  { id: "tasks", label: "Tasks" },
];

interface BundleImportFormProps {
  autoFocus?: boolean;
}

export function BundleImportForm({ autoFocus }: BundleImportFormProps) {
  const [file, setFile] = useState("");
  const [components, setComponents] = useState<string[]>([]);
  const importMutation = useBundleImport();
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!autoFocus) return;
    inputRef.current?.focus();
    inputRef.current?.scrollIntoView({ block: "center" });
  }, [autoFocus]);

  function toggle(component: string, checked: boolean) {
    setComponents((prev) => (checked ? [...prev, component] : prev.filter((entry) => entry !== component)));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file.trim()) return;
    await importMutation.mutateAsync({ bundle_path: file.trim(), components });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Import bundle</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4 text-sm">
          <Input
            ref={inputRef}
            value={file}
            onChange={(event) => setFile(event.target.value)}
            placeholder="/path/to/bundle.json"
            data-testid="bundle-import-path"
          />
          <div className="grid gap-2">
            {COMPONENT_OPTIONS.map((option) => (
              <Label key={option.id} className="flex items-center gap-2 font-normal">
                <Checkbox
                  checked={components.includes(option.id)}
                  onCheckedChange={(checked) => toggle(option.id, Boolean(checked))}
                />
                {option.label}
              </Label>
            ))}
          </div>
          {importMutation.data && (
            <div className="rounded-lg border bg-muted/40 p-3 text-xs">
              <p className="font-medium text-foreground">Import queued</p>
              <p>Job {importMutation.data.job_id}</p>
            </div>
          )}
          {importMutation.error && <p className="text-sm text-destructive">{importMutation.error.message}</p>}
          <Button type="submit" variant="secondary" disabled={importMutation.isPending} data-testid="bundle-import-submit">
            {importMutation.isPending ? "Importing" : "Import"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
