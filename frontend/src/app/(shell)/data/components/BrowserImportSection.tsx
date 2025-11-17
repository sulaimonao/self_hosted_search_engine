"use client";

import { FormEvent, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";
import { apiClient } from "@/lib/backend/apiClient";

export function BrowserImportSection() {
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const { toast } = useToast();
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!url.trim()) return;
    try {
      setIsSubmitting(true);
      await apiClient.post("/api/browser/history", { url: url.trim(), title: title.trim() || undefined });
      toast({ title: "History row imported", description: url.trim() });
      setUrl("");
      setTitle("");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Import failed";
      toast({ title: "Import failed", description: message, variant: "destructive" });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Browser imports</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p>Paste a URL to add it to the captured history ledger.</p>
        <form onSubmit={handleSubmit} className="space-y-3">
          <Input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com" />
          <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Optional title" />
          <Button type="submit" variant="secondary" disabled={isSubmitting || !url.trim()}>
            {isSubmitting ? "Importing" : "Import"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
